"""Agent Rédacteur : la note actuarielle IFRS 17 d'un dossier (D-036, D-055).

Partage du travail :
- **le code** calcule et écrit tout ce qui est chiffré ou structuré : données, hypothèses,
  évaluation initiale, roll-forward de la CSM, projection du compte de résultat, sensibilités,
  graphiques, contrôles, traçabilité (``engine/analysis.py``, ``agents/note_report.py``) ;
- **le LLM** n'écrit que deux textes : le résumé exécutif et le commentaire des sensibilités.
  Chaque nombre qu'il écrit doit exister dans les faits fournis, chaque paragraphe cité doit
  faire partie des passages fournis : le code le vérifie (même principe d'ancrage que D-020 et
  D-028). Sinon une relance, puis des textes écrits par le code (jamais de chiffre non vérifié).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime

from agents.rag_agent import normalize_ref
from agents.schemas import CsmResult, GroundedAnswer, PortfolioData, VerdictStatus
from core.llm import LLMClient, LLMError
from core.prompts import load_prompt
from engine.analysis import Projection, SensitivityReport, margin_ratio, projection, sensitivities
from engine.paa import paa_view
from engine.risk import ConfidenceReport, confidence_report
from multimodal.documents import numbers_in_text

UNIT = {1: "", 1_000: "milliers de ", 1_000_000: "millions de "}


def unit_label(p: PortfolioData) -> str:
    return f"{UNIT[p.unit_multiplier]}{p.currency}"


def fr(x: float, d: int = 2) -> str:
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def pct(x: float, d: int = 2) -> str:
    return f"{fr(x * 100, d)} %"


def signed(x: float, d: int = 2) -> str:
    return ("+" if x > 0 else "") + fr(x, d)


@dataclass
class NormPoint:
    """Une question posée à l'agent RAG pour fonder la note, avec sa réponse vérifiée."""
    question: str
    answer: GroundedAnswer
    verdict: str = "ok"            # ok | validation_humaine | non vérifié


@dataclass
class NoteContext:
    """Ce que la note doit dire de son origine (page de garde, données, traçabilité)."""
    case_id: str = ""
    entity: str = "Compagnie d'assurance fictive (projet pédagogique)"
    generated_at: datetime = field(default_factory=datetime.now)
    app_version: str = ""
    source_name: str = ""
    source_sha256: str = ""
    source_mime: str = ""
    extraction_mode: str = ""             # texte | vision | hybride ; vide : données fournies
    grounding: str = ""                   # document | transcription
    validated_by_human: bool = False
    field_confidence: dict[str, float] = field(default_factory=dict)
    provenance: dict[str, str] = field(default_factory=dict)   # donnée → page et tableau lus (D-067)
    human_changes: list[str] = field(default_factory=list)     # corrections du valideur (D-067)
    reader_notes: list[str] = field(default_factory=list)      # remarques de lecture (feuilles cachées, conversions…)
    ra_cv: float = 0.15                     # coefficient de variation des sorties (niveau de confiance du RA, D-056)
    ra_cv_source: str = ""                  # « calibrée sur … » ou « supposée … » (registre des hypothèses, D-074)
    ra_target_level: float | None = None    # niveau de confiance cible du registre (ex. 0,75)
    registry_version: str = ""              # version du registre des hypothèses appliqué (D-077)
    prompt_versions: dict[str, int] = field(default_factory=dict)
    models: dict[str, str] = field(default_factory=dict)


@dataclass
class Note:
    markdown: str
    html: str
    synthesis: str
    synthesis_source: str          # llm | code (repli)
    commentary: str = ""
    warnings: list[str] = field(default_factory=list)
    corrections: int = 0
    latency_ms: float = 0.0


# --------------------------------------------------------------------------- #
# Faits fournis au LLM (déjà formatés : il recopie, il ne calcule pas)
# --------------------------------------------------------------------------- #
def facts(p: PortfolioData, r: CsmResult, controls: list[str], sens: SensitivityReport | None = None,
          proj: Projection | None = None, conf: ConfidenceReport | None = None) -> dict:
    unit = unit_label(p)
    first = r.rollforward[0] if r.rollforward else None
    rates = p.discount_rates if isinstance(p.discount_rates, list) else [p.discount_rates]
    out = {
        "groupe": p.group_id, "unite_des_montants": unit, "nombre_de_periodes": p.n_periods,
        "taux_actualisation": " ; ".join(f"{fr(x * 100)} %" for x in rates),
        "ajustement_risque_pourcentage": f"{fr(p.risk_adjustment_pct * 100)} %",
        "valeur_actuelle_des_entrees": fr(r.pv_inflows), "valeur_actuelle_des_sorties": fr(r.pv_outflows),
        **({"valeur_actuelle_des_primes": fr(r.pv_inflows - r.pv_recoveries),
            "valeur_actuelle_des_recouvrements": fr(r.pv_recoveries)} if r.pv_recoveries > 0 else {}),
        **({"valeur_actuelle_des_frais_d_acquisition": fr(r.pv_acquisition)} if r.pv_acquisition > 0 else {}),
        "ajustement_au_titre_du_risque_non_financier": fr(r.risk_adjustment),
        "flux_de_tresorerie_d_execution": fr(r.fulfilment_cash_flows),
        "sens_des_flux_d_execution": ("positif : les sorties attendues dépassent les entrées, le groupe est déficitaire"
                                      if r.fulfilment_cash_flows > 0 else
                                      "négatif : les entrées attendues dépassent les sorties ; la CSM, de même montant "
                                      "en valeur absolue, met ce profit en réserve pour qu'aucun profit ne soit "
                                      "reconnu à l'origine"),
        "deficitaire": r.onerous,
        "csm_initiale": fr(r.initial_csm), "perte_initiale": fr(r.initial_loss_component),
        "liberation_totale_de_la_csm": fr(r.total_release),
        "liberation_premiere_periode": fr(first.release) if first else "0,00",
        "marge_attendue_csm_sur_primes": pct(margin_ratio(r)),
        "controles_a_faire_par_un_humain": controls,
    }
    if proj is not None:
        out["resultat_des_services_d_assurance_sur_la_duree"] = fr(proj.totals["insurance_service_result"])
        out["produits_des_activites_d_assurance_sur_la_duree"] = fr(proj.totals["insurance_revenue"])
        out["charges_financieres_d_assurance_sur_la_duree"] = fr(proj.totals["insurance_finance_expense"])
    if sens is not None:
        if sens.outflow_breakeven is not None:
            out["marge_de_securite_variation_des_sorties_qui_annule_la_marge"] = pct(sens.outflow_breakeven)
        if sens.rate_breakeven_shift is not None:
            out["translation_des_taux_qui_annule_la_marge_en_points"] = fr(sens.rate_breakeven_shift * 100)
        out["sensibilites"] = [{"choc": s.label, "csm_initiale": fr(s.csm), "perte_initiale": fr(s.loss),
                                "variation_du_resultat_a_l_origine": signed(s.delta_result_at_inception),
                                "deficitaire_apres_choc": s.onerous, "bascule": s.flips} for s in sens.items]
    if conf is not None:
        out["niveau_de_confiance_de_l_ajustement_pour_risque"] = pct(conf.level_of_retained_ra, 1)
        out["coefficient_de_variation_suppose_des_sorties"] = pct(conf.cv, 0)
    return out


def _allowed_numbers(f: dict) -> set[float]:
    vals: set[float] = set()

    def walk(v) -> None:
        if isinstance(v, bool):
            return
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, int | float):
            vals.add(round(float(v), 2))
        else:
            vals.update(round(n, 2) for n in numbers_in_text(str(v)))
    walk(f)
    return vals | {abs(v) for v in vals}      # « une baisse de 37,80 » recopie « -37,80 »


def synthesis_issues(text: str, f: dict, allowed_refs: set[str]) -> list[str]:
    issues = []
    allowed = _allowed_numbers(f)
    # années et numéros de période (« sur 5 ans », « période 1 ») ; IFRS 17 lui-même ; +100 pb, 10 %, 50 %
    small = {float(k) for k in range(0, f["nombre_de_periodes"] + 1)} | {17.0, 100.0, 10.0, 50.0, 0.1, 0.5}
    cleaned = re.sub(r"\[[^\]]*\]", " ", text)                    # les citations ne sont pas des montants
    cleaned = re.sub(r"IFRS\s*17", " ", cleaned, flags=re.I)
    for n in numbers_in_text(cleaned):
        if round(n, 2) not in allowed and abs(n) not in small and round(n * 100, 2) not in allowed:
            issues.append(f"nombre absent des faits : {fr(n) if n != int(n) else int(n)}")
    for m in re.finditer(r"\[([^\[\]]{1,60})\]", text):
        for ref in normalize_ref(m.group(1)):
            if ref not in allowed_refs:
                issues.append(f"paragraphe cité hors des passages fournis : {ref}")
    for m in DOUBLE_NEGATION.finditer(text):
        issues.append(f"double négation : « {m.group(0).strip()} » (écrire la valeur absolue après "
                      "« diminue », ou « varie de » avec le signe)")
    return sorted(set(issues))


# « diminue de -37,80 », « une baisse de −150,00 » : le sens est dit deux fois, et à l'envers (write_note v3)
DOUBLE_NEGATION = re.compile(r"\b(?:diminu\w*|baisse\w*|réduit|réduisent|réduction|recul\w*|dégrad\w*)"
                             r"\b[^.;:\d]{0,30}?[-\u2212]\s?\d", re.I)


# --------------------------------------------------------------------------- #
# Textes de repli, écrits par le code
# --------------------------------------------------------------------------- #
def fallback_synthesis(p: PortfolioData, r: CsmResult, refs: set[str], controls: list[str],
                       sens: SensitivityReport | None = None, proj: Projection | None = None) -> str:
    unit = unit_label(p)
    cite = lambda pid: f" [§{pid}]" if pid in refs else ""   # noqa: E731
    if r.onerous:
        s = (f"Le groupe {p.group_id} est déficitaire dès l'origine : les flux de trésorerie d'exécution "
             f"s'élèvent à {fr(r.fulfilment_cash_flows)} {unit}, ajustement pour risque de "
             f"{fr(r.risk_adjustment)} inclus, d'où une perte immédiate de {fr(r.initial_loss_component)} {unit} "
             f"et une marge sur services contractuels (CSM) nulle{cite('47')}.")
    else:
        s = (f"Le groupe {p.group_id} est bénéficiaire : les flux de trésorerie d'exécution s'élèvent à "
             f"{fr(r.fulfilment_cash_flows)} {unit}, ajustement pour risque de {fr(r.risk_adjustment)} inclus, "
             f"d'où une marge sur services contractuels (CSM) initiale de {fr(r.initial_csm)} {unit} : "
             f"aucun profit n'est reconnu à l'origine{cite('38')}. Elle sera reconnue en résultat au fil des "
             f"services rendus, selon les unités de couverture{cite('B119')}, dont "
             f"{fr(r.rollforward[0].release)} {unit} la première période.")
    if proj is not None:
        s += (f" Dans le scénario central, le résultat des services d'assurance cumulé sur la durée du groupe "
              f"est de {fr(proj.totals['insurance_service_result'])} {unit}.")
    if sens is not None and sens.outflow_breakeven is not None:
        if r.onerous:
            s += (f" Il faudrait une variation des sorties de {pct(sens.outflow_breakeven)} pour que le groupe "
                  f"cesse d'être déficitaire.")
        else:
            s += (f" La marge absorbe une hausse des sinistres et frais allant jusqu'à "
                  f"{pct(sens.outflow_breakeven)} avant que le groupe ne devienne déficitaire.")
    if controls:
        s += " Des points restent à valider par un humain avant diffusion."
    return s


def fallback_commentary(sens: SensitivityReport | None) -> str:
    if sens is None or not sens.items:
        return ""
    worst = min(sens.items, key=lambda s: s.delta_result_at_inception)
    rates = {s.key: s for s in sens.items}
    up, down = rates.get("taux_plus_100"), rates.get("taux_moins_100")
    text = (f"L'hypothèse la plus sensible est « {worst.label} », qui fait varier le résultat à l'origine "
            f"(CSM moins perte) de {signed(worst.delta_result_at_inception)}.")
    if up and down:
        sens_word = "améliore" if up.delta_result_at_inception > 0 else "dégrade"
        text += (f" Une hausse des taux de 100 pb {sens_word} la marge ({signed(up.delta_result_at_inception)}), "
                 f"une baisse de 100 pb la fait varier de {signed(down.delta_result_at_inception)}.")
    flips = [s.label for s in sens.items if s.flips]
    text += (" Aucun des chocs testés ne fait changer le groupe de statut." if not flips else
             " Les chocs suivants font changer le groupe de statut : " + " ; ".join(flips) + ".")
    return text


# --------------------------------------------------------------------------- #
# Appel du LLM (une relance au plus), contrôle des deux textes
# --------------------------------------------------------------------------- #
def write_texts(p: PortfolioData, r: CsmResult, norm: list[NormPoint], controls: list[str], client: LLMClient,
                case_id: str = "", sens: SensitivityReport | None = None, proj: Projection | None = None,
                conf: ConfidenceReport | None = None) -> tuple[str, str, str, list[str], int]:
    """Renvoie (synthèse, commentaire des sensibilités, source, avertissements, relances)."""
    f = facts(p, r, controls, sens, proj, conf)
    refs = {c.paragraph_id for n in norm if not n.answer.refused for c in n.answer.citations}
    norm_text = "\n".join(f"[§{c.paragraph_id}] {c.quote}" for n in norm if not n.answer.refused
                          for c in n.answer.citations) or "(aucun passage)"
    spec = load_prompt("write_note")
    messages = [{"role": "system", "content": spec.system},
                {"role": "user", "content": spec.render(facts=json.dumps(f, ensure_ascii=False, indent=1),
                                                        norm=norm_text)}]
    issues: list[str] = []
    for attempt in range(2):
        try:
            resp = client.chat(messages, model=spec.params.model, temperature=spec.params.temperature,
                               max_tokens=spec.params.max_tokens, json_mode=True,
                               trace={"agent": "redacteur", "prompt_id": spec.id,
                                      "prompt_version": spec.version, "case_id": case_id, "attempt": attempt})
            data = resp.json()
            data = data if isinstance(data, dict) else {}
            text = str(data.get("synthese") or "").strip()
            comment = str(data.get("commentaire_sensibilites") or "").strip()
        except LLMError as exc:
            issues = [f"rédacteur indisponible : {exc}"[:200]]
            break
        issues = synthesis_issues(text, f, refs) if text else ["synthèse vide"]
        if comment:
            issues += [f"commentaire : {i}" for i in synthesis_issues(comment, f, refs)]
        if not issues:
            return text, comment or fallback_commentary(sens), "llm", [], attempt
        messages += [{"role": "assistant", "content": json.dumps(data, ensure_ascii=False)},
                     {"role": "user", "content": "Le contrôle a trouvé : " + " ; ".join(issues)
                      + ". Recopie uniquement les nombres des faits et ne cite que les paragraphes fournis."}]
    return (fallback_synthesis(p, r, refs, controls, sens, proj), fallback_commentary(sens), "code",
            [f"textes du LLM rejetés ({'; '.join(issues)[:200]}) : textes écrits par le code"], 1)


def write_synthesis(p: PortfolioData, r: CsmResult, norm: list[NormPoint], controls: list[str],
                    client: LLMClient, case_id: str = "") -> tuple[str, str, list[str], int]:
    """Compatibilité (v1) : la synthèse seule."""
    text, _, source, warnings, corrections = write_texts(p, r, norm, controls, client, case_id)
    return text, source, warnings, corrections


def write_note(p: PortfolioData, r: CsmResult, norm: list[NormPoint], controls: list[str],
               checks: list[str], client: LLMClient, case_id: str = "",
               context: NoteContext | None = None) -> Note:
    from agents.note_report import render_note  # rendu séparé : gabarit long

    t0 = time.perf_counter()
    ctx = context or NoteContext(case_id=case_id)
    sens = sensitivities(p, r)
    proj = projection(p, r)
    conf = confidence_report(r.pv_inflows - r.pv_acquisition, r.pv_outflows, p.risk_adjustment_pct, ctx.ra_cv)
    paa = paa_view(p, r, [x.insurance_service_result for x in proj.rows] if proj else None)
    synthesis, commentary, source, warnings, corrections = write_texts(
        p, r, norm, controls, client, case_id, sens, proj, conf)
    md, page = render_note(p, r, synthesis, commentary, source, norm, controls, checks, sens, proj, ctx, conf, paa)
    return Note(markdown=md, html=page, synthesis=synthesis, synthesis_source=source, commentary=commentary,
                warnings=warnings, corrections=corrections,
                latency_ms=round((time.perf_counter() - t0) * 1000, 1))


def verdict_label(v) -> str:
    if v is None:
        return "non vérifié"
    return "ok" if v.status == VerdictStatus.OK else v.status.value
