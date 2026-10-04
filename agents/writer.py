"""Agent Rédacteur : la note finale d'un dossier (D-036).

Partage du travail :
- **le code** écrit tout ce qui est chiffré ou structuré : données du groupe, résultats du moteur,
  tableau du roll-forward, graphique (SVG), contrôles effectués, passages de la norme cités ;
- **le LLM** n'écrit que la synthèse (4 à 6 phrases). Chaque nombre qu'il écrit doit exister dans
  les faits fournis, chaque paragraphe cité doit faire partie des passages fournis : le code le
  vérifie (même principe d'ancrage que D-020 et D-028). Sinon une relance, puis une synthèse
  écrite par le code (jamais de chiffre non vérifié dans la note).
"""

from __future__ import annotations

import html
import json
import re
import time
from dataclasses import dataclass, field

from agents.rag_agent import normalize_ref
from agents.schemas import CsmResult, GroundedAnswer, PortfolioData, VerdictStatus
from core.llm import LLMClient, LLMError
from core.prompts import load_prompt
from multimodal.documents import numbers_in_text

UNIT = {1: "", 1_000: "milliers de ", 1_000_000: "millions de "}


def unit_label(p: PortfolioData) -> str:
    return f"{UNIT[p.unit_multiplier]}{p.currency}"


def fr(x: float, d: int = 2) -> str:
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


@dataclass
class NormPoint:
    """Une question posée à l'agent RAG pour fonder la note, avec sa réponse vérifiée."""
    question: str
    answer: GroundedAnswer
    verdict: str = "ok"            # ok | validation_humaine | non vérifié


@dataclass
class Note:
    markdown: str
    html: str
    synthesis: str
    synthesis_source: str          # llm | code (repli)
    warnings: list[str] = field(default_factory=list)
    corrections: int = 0
    latency_ms: float = 0.0


# --------------------------------------------------------------------------- #
# Faits fournis au LLM (déjà formatés : il recopie, il ne calcule pas)
# --------------------------------------------------------------------------- #
def facts(p: PortfolioData, r: CsmResult, controls: list[str]) -> dict:
    unit = unit_label(p)
    first = r.rollforward[0] if r.rollforward else None
    rates = p.discount_rates if isinstance(p.discount_rates, list) else [p.discount_rates]
    out = {
        "groupe": p.group_id, "unite_des_montants": unit, "nombre_de_periodes": p.n_periods,
        "taux_actualisation": " ; ".join(f"{fr(x * 100)} %" for x in rates),
        "ajustement_risque_pourcentage": f"{fr(p.risk_adjustment_pct * 100)} %",
        "valeur_actuelle_des_entrees": fr(r.pv_inflows), "valeur_actuelle_des_sorties": fr(r.pv_outflows),
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
        "controles_a_faire_par_un_humain": controls,
    }
    return out


def _allowed_numbers(f: dict) -> set[float]:
    vals: set[float] = set()
    for v in f.values():
        for x in (v if isinstance(v, list) else [v]):
            if isinstance(x, bool):
                continue
            if isinstance(x, int | float):
                vals.add(round(float(x), 2))
            else:
                vals.update(round(n, 2) for n in numbers_in_text(str(x)))
    return vals


def synthesis_issues(text: str, f: dict, allowed_refs: set[str]) -> list[str]:
    issues = []
    allowed = _allowed_numbers(f)
    # années et numéros de période (« sur 5 ans », « période 1 ») ; IFRS 17 lui-même
    small = {float(k) for k in range(0, f["nombre_de_periodes"] + 1)} | {17.0}
    cleaned = re.sub(r"\[[^\]]*\]", " ", text)                    # les citations ne sont pas des montants
    cleaned = re.sub(r"IFRS\s*17", " ", cleaned, flags=re.I)
    for n in numbers_in_text(cleaned):
        if round(n, 2) not in allowed and n not in small and round(n * 100, 2) not in allowed:
            issues.append(f"nombre absent des faits : {fr(n) if n != int(n) else int(n)}")
    for m in re.finditer(r"\[([^\[\]]{1,60})\]", text):
        for ref in normalize_ref(m.group(1)):
            if ref not in allowed_refs:
                issues.append(f"paragraphe cité hors des passages fournis : {ref}")
    return sorted(set(issues))


def fallback_synthesis(p: PortfolioData, r: CsmResult, refs: set[str], controls: list[str]) -> str:
    unit = unit_label(p)
    cite = lambda pid: f" [§{pid}]" if pid in refs else ""   # noqa: E731
    if r.onerous:
        s = (f"Le groupe {p.group_id} est déficitaire dès l'origine : les flux de trésorerie d'exécution "
             f"s'élèvent à {fr(r.fulfilment_cash_flows)} {unit}, d'où une perte immédiate de "
             f"{fr(r.initial_loss_component)} {unit} et une marge sur services contractuels nulle{cite('47')}.")
    else:
        s = (f"Le groupe {p.group_id} est bénéficiaire : la marge sur services contractuels initiale est de "
             f"{fr(r.initial_csm)} {unit}, de sorte qu'aucun profit n'est reconnu à l'origine{cite('38')}. "
             f"Elle sera reconnue en résultat au fil des services rendus, selon les unités de couverture"
             f"{cite('B119')}, dont {fr(r.rollforward[0].release)} {unit} la première période.")
    if controls:
        s += " Des points restent à valider par un humain avant diffusion."
    return s


def write_synthesis(p: PortfolioData, r: CsmResult, norm: list[NormPoint], controls: list[str],
                    client: LLMClient, case_id: str = "") -> tuple[str, str, list[str], int]:
    f = facts(p, r, controls)
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
            text = str(data.get("synthese") or "").strip() if isinstance(data, dict) else ""
        except LLMError as exc:
            issues = [f"rédacteur indisponible : {exc}"[:200]]
            break
        issues = synthesis_issues(text, f, refs) if text else ["synthèse vide"]
        if not issues:
            return text, "llm", [], attempt
        messages += [{"role": "assistant", "content": json.dumps(data, ensure_ascii=False)},
                     {"role": "user", "content": "Le contrôle a trouvé : " + " ; ".join(issues)
                      + ". Recopie uniquement les nombres des faits et ne cite que les paragraphes fournis."}]
    return (fallback_synthesis(p, r, refs, controls), "code",
            [f"synthèse du LLM rejetée ({'; '.join(issues)[:200]}) : synthèse écrite par le code"], 1)


# --------------------------------------------------------------------------- #
# Rendu (Markdown pour Git/n8n, HTML avec graphique SVG pour l'e-mail)
# --------------------------------------------------------------------------- #
def svg_chart(r: CsmResult) -> str:
    """Barres : CSM en fin de période ; ligne : libération en résultat de la période."""
    rows = r.rollforward
    if not rows:
        return ""
    w, h, pad = 520, 220, 36
    top = max([x.opening for x in rows] + [x.closing for x in rows] + [x.release for x in rows] + [1e-9])
    bw = (w - 2 * pad) / len(rows)
    bars, pts, labels = [], [], []
    for k, x in enumerate(rows):
        bh = (h - 2 * pad) * x.closing / top
        bx = pad + k * bw + bw * 0.15
        bars.append(f'<rect x="{bx:.1f}" y="{h - pad - bh:.1f}" width="{bw * 0.7:.1f}" height="{bh:.1f}" '
                    f'fill="#5b7fa6"><title>CSM fin de période {x.period} : {fr(x.closing)}</title></rect>')
        py = h - pad - (h - 2 * pad) * x.release / top
        pts.append(f"{pad + (k + 0.5) * bw:.1f},{py:.1f}")
        labels.append(f'<text x="{pad + (k + 0.5) * bw:.1f}" y="{h - pad + 14}" font-size="10" '
                      f'text-anchor="middle">P{x.period}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'role="img" aria-label="Évolution de la CSM">'
            f'<line x1="{pad}" y1="{h - pad}" x2="{w - pad}" y2="{h - pad}" stroke="#888"/>'
            + "".join(bars) + f'<polyline points="{" ".join(pts)}" fill="none" stroke="#c0504d" stroke-width="2"/>'
            + "".join(labels)
            + f'<text x="{pad}" y="16" font-size="11">■ CSM en fin de période   ━ libération en résultat</text></svg>')


def render(p: PortfolioData, r: CsmResult, synthesis: str, norm: list[NormPoint], controls: list[str],
           checks: list[str]) -> tuple[str, str]:
    unit = unit_label(p)
    status = "À VALIDER PAR UN HUMAIN" if controls else "Contrôles automatiques passés"
    md = [f"# Note IFRS 17 — groupe {p.group_id}", "", f"**Statut : {status}** · montants en {unit}", "",
          "## Synthèse", "", synthesis, "", "## Résultats du modèle général", "",
          "| Élément | Montant |", "| --- | --- |",
          f"| Valeur actuelle des entrées (primes) | {fr(r.pv_inflows)} |",
          f"| Valeur actuelle des sorties (sinistres et frais) | {fr(r.pv_outflows)} |",
          f"| Ajustement au titre du risque non financier | {fr(r.risk_adjustment)} |",
          f"| Flux de trésorerie d'exécution (négatif : entrées nettes) | {fr(r.fulfilment_cash_flows)} |",
          f"| CSM initiale (§38) | {fr(r.initial_csm)} |",
          f"| Perte initiale, groupe déficitaire (§47) | {fr(r.initial_loss_component)} |", "",
          "## Évolution de la CSM", "", "| Période | Ouverture | Intérêt (§44 b) | Libération (B119) | Clôture |",
          "| --- | --- | --- | --- | --- |"]
    md += [f"| {x.period} | {fr(x.opening)} | {fr(x.interest_accretion)} | {fr(x.release)} | {fr(x.closing)} |"
           for x in r.rollforward]
    md += ["", "## Fondements dans la norme", ""]
    for n in norm:
        if n.answer.refused:
            md += [f"**{n.question}** — pas de réponse fiable dans la norme indexée.", ""]
            continue
        flag = "" if n.verdict == "ok" else f" *(vérificateur : {n.verdict})*"
        md += [f"**{n.question}**{flag}", "", n.answer.answer or "", ""]
        md += [f"> [§{c.paragraph_id}] « {c.quote} »" for c in n.answer.citations] + [""]
    md += ["## Contrôles", ""] + [f"- {c}" for c in checks] + [f"- ⚠ {c}" for c in controls] + [
        "", "*Note générée par IFRS 17 Copilot (projet pédagogique, sans valeur de conseil). "
        "Les montants viennent du moteur de calcul, jamais du LLM.*"]
    markdown = "\n".join(md) + "\n"

    def esc(s: str) -> str:
        return html.escape(s)

    rows_html = "".join(f"<tr><td>{x.period}</td><td>{fr(x.opening)}</td><td>{fr(x.interest_accretion)}</td>"
                        f"<td>{fr(x.release)}</td><td>{fr(x.closing)}</td></tr>" for x in r.rollforward)
    norm_html = ""
    for n in norm:
        if n.answer.refused:
            norm_html += f"<p><b>{esc(n.question)}</b> — pas de réponse fiable dans la norme indexée.</p>"
            continue
        quotes = "".join(f"<blockquote>[§{esc(c.paragraph_id)}] « {esc(c.quote)} »</blockquote>"
                         for c in n.answer.citations)
        flag = "" if n.verdict == "ok" else f" <i>(vérificateur : {esc(n.verdict)})</i>"
        norm_html += f"<p><b>{esc(n.question)}</b>{flag}<br>{esc(n.answer.answer or '')}</p>{quotes}"
    color = "#b45309" if controls else "#15803d"
    page = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Note IFRS 17 — {esc(p.group_id)}</title>
<style>body{{font-family:Arial,sans-serif;max-width:760px;margin:24px auto;color:#1f2933;line-height:1.45}}
table{{border-collapse:collapse;width:100%;margin:8px 0}}td,th{{border:1px solid #cbd2d9;padding:4px 8px;text-align:right}}
td:first-child,th:first-child{{text-align:left}}th{{background:#eef2f6}}blockquote{{margin:4px 0 4px 12px;color:#52606d;font-size:90%}}
.status{{color:{color};font-weight:bold}}</style></head><body>
<h1>Note IFRS 17 — groupe {esc(p.group_id)}</h1><p class="status">{esc(status)}</p><p>Montants en {esc(unit)}</p>
<h2>Synthèse</h2><p>{esc(synthesis)}</p>
<h2>Résultats du modèle général</h2><table>
<tr><td>Valeur actuelle des entrées (primes)</td><td>{fr(r.pv_inflows)}</td></tr>
<tr><td>Valeur actuelle des sorties (sinistres et frais)</td><td>{fr(r.pv_outflows)}</td></tr>
<tr><td>Ajustement au titre du risque non financier</td><td>{fr(r.risk_adjustment)}</td></tr>
<tr><td>Flux de trésorerie d'exécution (négatif : entrées nettes)</td><td>{fr(r.fulfilment_cash_flows)}</td></tr>
<tr><td>CSM initiale (§38)</td><td>{fr(r.initial_csm)}</td></tr>
<tr><td>Perte initiale, groupe déficitaire (§47)</td><td>{fr(r.initial_loss_component)}</td></tr></table>
<h2>Évolution de la CSM</h2>{svg_chart(r)}
<table><tr><th>Période</th><th>Ouverture</th><th>Intérêt (§44 b)</th><th>Libération (B119)</th><th>Clôture</th></tr>{rows_html}</table>
<h2>Fondements dans la norme</h2>{norm_html}
<h2>Contrôles</h2><ul>{"".join(f"<li>{esc(c)}</li>" for c in checks)}{"".join(f"<li>⚠ {esc(c)}</li>" for c in controls)}</ul>
<p><i>Note générée par IFRS 17 Copilot (projet pédagogique, sans valeur de conseil). Les montants viennent du moteur de calcul, jamais du LLM.</i></p>
</body></html>"""
    return markdown, page


def write_note(p: PortfolioData, r: CsmResult, norm: list[NormPoint], controls: list[str],
               checks: list[str], client: LLMClient, case_id: str = "") -> Note:
    t0 = time.perf_counter()
    synthesis, source, warnings, corrections = write_synthesis(p, r, norm, controls, client, case_id)
    md, page = render(p, r, synthesis, norm, controls, checks)
    return Note(markdown=md, html=page, synthesis=synthesis, synthesis_source=source, warnings=warnings,
                corrections=corrections, latency_ms=round((time.perf_counter() - t0) * 1000, 1))


def verdict_label(v) -> str:
    if v is None:
        return "non vérifié"
    return "ok" if v.status == VerdictStatus.OK else v.status.value
