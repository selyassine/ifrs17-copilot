"""Agent Copilot : un agent qui choisit lui-même ses outils pour répondre sur un dossier (D-057).

Différence avec l'orchestrateur (pipeline fixe, D-036) : ici, c'est le LLM qui décide quels
outils appeler, dans quel ordre et combien de fois, selon la question. Exemple : « si les sinistres
augmentent de 15 %, le groupe reste-t-il bénéficiaire, et que dit la norme ? » → l'agent évalue le
scénario, puis cherche dans la norme, puis répond en citant ses sources.

Autonomie, mais bornée là où il le faut :
- **outils en lecture seule et déterministes** : le moteur calcule, le LLM ne calcule jamais
  (D-005) ; aucun outil ne modifie le dossier, n'envoie d'e-mail ni n'écrit en base ;
- **arguments validés** par Pydantic (bornes réalistes : un choc de 1 000 % est refusé) ;
- **budget** : au plus MAX_TOOL_CALLS appels d'outils, puis réponse obligatoire ;
- **réponse contrôlée par le code** : chaque nombre doit venir d'un résultat d'outil (ou de la
  question), chaque paragraphe cité doit venir de l'outil de recherche ; sinon une correction,
  puis une réponse écrite par le code à partir des résultats d'outils.

Le graphe (LangGraph, StateGraph) :

    START → décider ─┬─(outil)→ agir ──→ décider
                     └─(réponse)→ vérifier ─┬─(ok, ou corrections épuisées)→ END
                                            └─(nombre ou citation non fondés)→ décider

Mémoire et état (D-061) : les échanges déjà contrôlés sur le dossier et les faits établis par
l'équipe sont placés dans le contexte (mémoire épisodique et sémantique, agents/memory.py), les plus
anciens se retrouvent avec l'outil ``memoire_du_dossier`` ; avec un checkpointer LangGraph, l'état du
graphe est sauvegardé après chaque nœud (un fil par dossier) : on peut relire la trajectoire d'une
question et la rejouer à partir de n'importe quel point de reprise.

Le protocole d'appel d'outils est un objet JSON validé (et non l'appel de fonctions natif d'un
fournisseur) : il fonctionne avec tout modèle compatible OpenAI et avec le LLM factice des tests.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypedDict

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agents.rag_agent import normalize_ref
from agents.schemas import PortfolioData
from agents.writer import fr, pct, signed, unit_label
from core.llm import LLMClient, LLMError
from core.prompts import load_prompt
from engine.analysis import projection, sensitivities, shocked
from engine.csm import compute_csm
from engine.risk import confidence_level, ra_at_level
from multimodal.documents import numbers_in_text, parse_number

MAX_TOOL_CALLS = 5
CALC_TOOLS = {"donnees_du_dossier", "evaluer_scenario", "sensibilites", "niveau_de_confiance", "projection_resultat"}
CORRECTION_HINT = ("Recopie uniquement des nombres des résultats d'outils (ou de la mémoire) et ne cite que les "
                   "paragraphes renvoyés par rechercher_norme. Si un chiffre te manque, appelle l'outil qui le donne : "
                   "chiffres centraux et CSM libérée la première période → donnees_du_dossier ; scénario « et si » → "
                   "evaluer_scenario ; seuil de bascule (de combien monter ou baisser) → sensibilites ; niveau de "
                   "confiance → niveau_de_confiance ; résultat par période → projection_resultat.")
MAX_CORRECTIONS = 1


# --------------------------------------------------------------------------- #
# Outils (lecture seule, calcul par le moteur)
# --------------------------------------------------------------------------- #
class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoArgs(_Args):
    pass


class ScenarioArgs(_Args):
    sorties_pct: float = Field(0.0, ge=-90, le=300, description="variation des sinistres et frais, en %, ex. 15")
    primes_pct: float = Field(0.0, ge=-90, le=300, description="variation des primes, en %")
    taux_pb: float = Field(0.0, ge=-500, le=500, description="translation des taux, en points de base, ex. 100")
    ajustement_risque_pct: float = Field(0.0, ge=-100, le=500, description="variation relative du RA, en %")


class LevelArgs(_Args):
    niveau: float = Field(..., gt=50, lt=100, description="niveau de confiance en %, ex. 75")


class SujetArgs(_Args):
    sujet: str = Field(..., min_length=3, max_length=200, description="sujet à retrouver dans les échanges passés")


class NormArgs(_Args):
    question: str = Field(..., min_length=5, max_length=300, description="question sur la norme, en français")


@dataclass
class Tool:
    name: str
    description: str
    args: type[_Args]
    run: Callable[..., dict]


def _status(onerous: bool) -> str:
    return "déficitaire" if onerous else "bénéficiaire"


class DossierTools:
    """Les outils du Copilot pour un dossier (un groupe de contrats)."""

    def __init__(self, portfolio: PortfolioData, ra_cv: float = 0.15,
                 norm_search: Callable[[str], dict] | None = None, recall: Callable[[str], dict] | None = None):
        self.p = portfolio
        self.recall = recall
        self.r = compute_csm(portfolio)
        self.cv = ra_cv
        self.norm_search = norm_search
        self.unit = unit_label(portfolio)

    def tools(self) -> dict[str, Tool]:
        out = [
            Tool("donnees_du_dossier", "Résumé du dossier : groupe, durée, unité, ajustement pour risque, résultats "
                 "centraux (CSM ou perte), CSM libérée la première période.", NoArgs, self.dossier),
            Tool("evaluer_scenario", "Recalcule le groupe avec des hypothèses modifiées (sinistres, primes, taux, "
                 "ajustement pour risque) et compare au scénario central.", ScenarioArgs, self.scenario),
            Tool("sensibilites", "Tableau des 6 chocs standard et seuils de bascule : de combien les sinistres "
                 "doivent monter (groupe bénéficiaire) ou baisser (groupe déficitaire) pour que le résultat à l'origine "
                 "s'annule, et translation des taux équivalente.", NoArgs, self.sensitivities),
            Tool("niveau_de_confiance", "Ajustement pour risque exigé à un niveau de confiance donné et son effet "
                 "sur la CSM ; niveau de confiance de l'ajustement retenu.", LevelArgs, self.confidence),
            Tool("projection_resultat", "Compte de résultat IFRS 17 attendu par période (produits, résultat des "
                 "services, charges financières) dans le scénario central.", NoArgs, self.projection),
        ]
        if self.norm_search is not None:
            out.append(Tool("rechercher_norme", "Cherche dans le texte officiel d'IFRS 17 et renvoie une réponse "
                            "vérifiée avec les paragraphes cités.", NormArgs, self.norm))
        if self.recall is not None:
            out.append(Tool("memoire_du_dossier", "Retrouve les questions déjà posées sur ce dossier et leurs réponses "
                            "vérifiées (échanges plus anciens que ceux du contexte).", SujetArgs, self.memory))
        return {t.name: t for t in out}

    # -------------------------------------------------------------- outils
    def dossier(self) -> dict:
        r, p = self.r, self.p
        return {"groupe": p.group_id, "unite": self.unit, "periodes": p.n_periods,
                "ajustement_risque_pourcentage": pct(p.risk_adjustment_pct),
                "valeur_actuelle_primes": fr(r.pv_inflows - r.pv_recoveries),
                **({"valeur_actuelle_recouvrements": fr(r.pv_recoveries)} if r.pv_recoveries > 0 else {}),
                "valeur_actuelle_sorties": fr(r.pv_outflows),
                "ajustement_risque": fr(r.risk_adjustment), "flux_execution": fr(r.fulfilment_cash_flows),
                "csm_initiale": fr(r.initial_csm), "perte_initiale": fr(r.initial_loss_component),
                "liberation_csm_premiere_periode": fr(r.rollforward[0].release) if r.rollforward else "0,00",
                "volatilite_registre": pct(self.cv, 1),
                **({"volatilite_declaree_par_le_document": pct(p.declared_cv, 1)} if p.declared_cv else {}),
                **({"niveau_de_confiance_declare_par_le_document": pct(p.declared_confidence, 1)}
                   if p.declared_confidence else {}),
                "statut": _status(r.onerous)}

    def scenario(self, sorties_pct: float = 0.0, primes_pct: float = 0.0, taux_pb: float = 0.0,
                 ajustement_risque_pct: float = 0.0) -> dict:
        s = compute_csm(shocked(self.p, rates=taux_pb / 10_000, outflows=1 + sorties_pct / 100,
                                premiums=1 + primes_pct / 100, ra=1 + ajustement_risque_pct / 100))
        base = self.r.initial_csm - self.r.initial_loss_component
        return {"hypotheses": {"sorties": f"{signed(sorties_pct, 1)} %", "primes": f"{signed(primes_pct, 1)} %",
                               "taux": f"{signed(taux_pb, 0)} pb", "ajustement_risque": f"{signed(ajustement_risque_pct, 1)} %"},
                "flux_execution": fr(s.fulfilment_cash_flows), "csm_initiale": fr(s.initial_csm),
                "perte_initiale": fr(s.initial_loss_component), "statut": _status(s.onerous),
                "statut_central": _status(self.r.onerous),
                "variation_du_resultat_a_l_origine": signed((s.initial_csm - s.initial_loss_component) - base),
                "csm_centrale": fr(self.r.initial_csm), "perte_centrale": fr(self.r.initial_loss_component)}

    def sensitivities(self) -> dict:
        rep = sensitivities(self.p, self.r)
        out = {"chocs": [{"choc": s.label, "csm": fr(s.csm), "perte": fr(s.loss),
                          "variation_du_resultat_a_l_origine": signed(s.delta_result_at_inception),
                          "statut": _status(s.onerous), "bascule": s.flips} for s in rep.items]}
        if rep.outflow_breakeven is not None:
            out["variation_des_sorties_qui_annule_la_marge"] = pct(rep.outflow_breakeven)
        out["translation_des_taux_qui_annule_la_marge"] = (
            f"{fr(rep.rate_breakeven_shift * 100)} points" if rep.rate_breakeven_shift is not None
            else "aucune entre -5 et +5 points")
        return out

    def confidence(self, niveau: float) -> dict:
        r = self.r
        ra = ra_at_level(r.pv_outflows, self.cv, niveau / 100)
        fcf = r.pv_outflows + ra + r.pv_acquisition - r.pv_inflows
        return {"niveau_demande": f"{fr(niveau, 1)} %", "ajustement_risque_exige": fr(ra),
                "ajustement_risque_exige_en_pourcentage_des_sorties": pct(ra / r.pv_outflows) if r.pv_outflows else "0,00 %",
                "csm_initiale": fr(max(-fcf, 0.0)), "perte_initiale": fr(max(fcf, 0.0)), "statut": _status(fcf > 0),
                "ajustement_risque_retenu": fr(r.risk_adjustment),
                "niveau_de_confiance_retenu": pct(confidence_level(r.pv_outflows, self.cv, r.risk_adjustment), 1),
                "hypothese": f"loi lognormale, coefficient de variation {pct(self.cv, 0)}"}

    def projection(self) -> dict:
        pr = projection(self.p, self.r)
        if pr is None:
            return {"erreur": "projection non disponible : ajustements de service futur fournis"}
        return {"par_periode": [{"periode": x.period, "produits": fr(x.insurance_revenue),
                                 "resultat_des_services": fr(x.insurance_service_result),
                                 "charges_financieres": fr(x.insurance_finance_expense)} for x in pr.rows],
                "total_produits": fr(pr.totals["insurance_revenue"]),
                "total_resultat_des_services": fr(pr.totals["insurance_service_result"]),
                "total_charges_financieres": fr(pr.totals["insurance_finance_expense"])}

    def memory(self, sujet: str) -> dict:
        return self.recall(sujet) if self.recall else {"echanges": []}

    def norm(self, question: str) -> dict:
        return self.norm_search(question) if self.norm_search else {"erreur": "norme non indexée"}


def norm_search_with(settings, client: LLMClient, retriever_loader: Callable | None,
                     case_id: str = "") -> Callable[[str], dict] | None:
    """Outil de recherche branché sur la chaîne habituelle : agent RAG (et LangGraph) + vérificateur."""
    if retriever_loader is None:
        return None
    from agents.pipeline import verified_answer

    def search(question: str) -> dict:
        res = verified_answer(question, settings, client, retriever_loader(), case_id=case_id)
        a = res.answer
        if a.refused:
            return {"reponse": None, "refus": a.refusal_reason}
        return {"reponse": a.answer, "verdict": res.verdict.status.value if res.verdict else "non vérifié",
                "citations": [{"paragraphe": c.paragraph_id, "extrait": c.quote} for c in a.citations]}
    return search


# --------------------------------------------------------------------------- #
# Contrôle de la réponse finale
# --------------------------------------------------------------------------- #
def _numbers(obj: Any) -> set[float]:
    vals: set[float] = set()
    if isinstance(obj, dict):
        for v in obj.values():
            vals |= _numbers(v)
    elif isinstance(obj, list):
        for v in obj:
            vals |= _numbers(v)
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, int | float):
        vals.add(round(float(obj), 2))
    elif isinstance(obj, str):
        vals |= {round(n, 2) for n in numbers_in_text(obj)}
    return vals | {abs(v) for v in vals}


def _refs(observations: list[dict]) -> set[str]:
    refs = set()
    for o in observations:
        for c in (o.get("resultat") or {}).get("citations", []) if isinstance(o.get("resultat"), dict) else []:
            refs |= set(normalize_ref(str(c.get("paragraphe", ""))))
    return refs


_UNIT_RE = re.compile(r"(-?\d{1,3}(?:[\u00a0\u202f ]\d{3})+(?:,\d+)?|-?\d+(?:[.,]\d+)?)\s*"
                      r"(points?\s+de\s+base|pdb|pb|bp|points?|pts?|%|pour\s*cent)(?![\w])", re.I)


def _unit_key(u: str) -> str:
    u = u.lower()
    if "base" in u or u in ("pdb", "pb", "bp"):
        return "points de base"
    if u.startswith("p") and "cent" not in u:
        return "points"
    return "%"


def unit_pairs(obj: Any) -> dict[float, set[str]]:
    """Nombres suivis d'une unité (« 1,25 points », « 15,00 % », « 100 points de base ») dans un texte ou un
    résultat d'outil : valeur → unités écrites."""
    out: dict[float, set[str]] = {}
    if isinstance(obj, dict):
        for v in obj.values():
            for k, us in unit_pairs(v).items():
                out.setdefault(k, set()).update(us)
    elif isinstance(obj, list):
        for v in obj:
            for k, us in unit_pairs(v).items():
                out.setdefault(k, set()).update(us)
    elif isinstance(obj, str):
        for m in _UNIT_RE.finditer(obj):
            v = parse_number(m.group(1))
            if v is not None:
                out.setdefault(round(abs(v), 2), set()).add(_unit_key(m.group(2)))
    return out


def unit_mismatches(answer: str, question: str, observations: list[dict]) -> list[str]:
    """F-018 (t06) : le chiffre est juste mais l'unité réécrite (« points de base » au lieu de « points »). Un nombre
    de la réponse suivi d'une unité doit porter une unité que l'outil (ou la question) lui donne."""
    told = unit_pairs([o.get("resultat") for o in observations])
    asked = unit_pairs(question)
    issues = []
    for v, units in unit_pairs(answer).items():
        known = told.get(v, set()) | asked.get(v, set())
        if told.get(v) and not units & known:
            issues.append(f"unité de {fr(v)} : l'outil écrit « {' / '.join(sorted(told[v]))} », la réponse "
                          f"« {' / '.join(sorted(units))} » ; recopie l'unité de l'outil")
    return issues


# F-023 : réponse qui prétend avoir agi (« le dossier est donc validé », « l'ajustement est fixé à 0 % »)
ACTION_CLAIM = re.compile(
    r"\b(?:j['’]ai|nous avons)\s+(?:bien\s+)?(?:validé|approuvé|modifié|fixé|mis|changé|remplacé|enregistré)"
    r"|\b(?:dossier|groupe|note)\s+(?:est|a été)\s+(?:donc\s+|désormais\s+|bien\s+)?(?:validée?|approuvée?|marquée? comme)"
    r"|\b(?:est|sont)\s+(?:donc\s+|désormais\s+|maintenant\s+)?(?:fixée?s?|mise?s?|ramenée?s?|modifiée?s?)\s+à"
    r"|\bannoncée?s?\s+à\b|\bje\s+(?:valide|confirme la validation)", re.I)


def answer_issues(answer: str, question: str, observations: list[dict], n_periods: int,
                  memory: str = "", memory_refs: set[str] | None = None) -> list[str]:
    """Nombres et paragraphes non fondés. La mémoire (échanges déjà contrôlés) compte comme source."""
    # F-023 : un nombre de la question n'est repris que s'il a servi d'argument à un outil (« +15 % » → sorties_pct
    # = 15) ; sinon « annonce une CSM de 5 000 » laissait passer 5 000, écrit par l'utilisateur et non calculé
    args_numbers = _numbers([o.get("arguments") for o in observations])
    allowed = (_numbers([o.get("resultat") for o in observations]) | (_numbers(question) & args_numbers)
               | args_numbers | _numbers(memory))
    small = {float(k) for k in range(0, n_periods + 1)} | {17.0, 100.0}
    cleaned = re.sub(r"\[[^\]]*\]", " ", answer)
    cleaned = re.sub(r"IFRS\s*17", " ", cleaned, flags=re.I)
    issues = [f"nombre absent des résultats d'outils : {fr(n) if n != int(n) else int(n)}"
              for n in numbers_in_text(cleaned)
              if round(n, 2) not in allowed and abs(n) not in small and round(n * 100, 2) not in allowed]
    refs = _refs(observations) | set(memory_refs or ())
    for o in observations:   # paragraphes cités dans des réponses retrouvées en mémoire (déjà contrôlées)
        if o.get("outil") == "memoire_du_dossier" and isinstance(o.get("resultat"), dict):
            for e in o["resultat"].get("echanges", []):
                for m in re.finditer(r"\[([^\[\]]{1,60})\]", str(e.get("reponse", ""))):
                    refs |= set(normalize_ref(m.group(1)))
    for m in re.finditer(r"\[([^\[\]]{1,60})\]", answer):
        issues += [f"paragraphe cité sans être renvoyé par rechercher_norme : {ref}"
                   for ref in normalize_ref(m.group(1)) if ref not in refs]
    computed = [o for o in observations if o.get("outil") in CALC_TOOLS and isinstance(o.get("resultat"), dict)
                and "erreur" not in o["resultat"]]
    tool_numbers = _numbers([o["resultat"] for o in computed]) - _numbers(question)
    if computed and tool_numbers and not any(round(n, 2) in tool_numbers or round(abs(n), 2) in tool_numbers
                                             for n in numbers_in_text(cleaned)):
        issues.append("la réponse ne donne aucun chiffre des résultats d'outils : indique le montant ou le "
                      "pourcentage qui répond (CSM ou perte, variation, seuil), recopié du résultat")
    issues += unit_mismatches(answer, question, observations)
    if ACTION_CLAIM.search(answer):
        issues.append("la réponse annonce une modification ou une validation : le Copilot ne peut ni modifier les "
                      "données ni valider un dossier ; refuse la demande et donne les chiffres des outils")
    return sorted(set(issues))


def fallback_tool(question: str) -> tuple[str, dict]:
    """Outil de repli choisi par le code, sans LLM (mots-clés), quand le modèle n'en a appelé aucun."""
    q = question.lower()
    if re.search(r"niveau de confiance|quantile", q):
        m = re.search(r"(\d{2}(?:[.,]\d+)?)\s*%", q)
        level = float(m.group(1).replace(",", ".")) if m else 75.0
        return "niveau_de_confiance", {"niveau": level if 50 < level < 100 else 75.0}
    if re.search(r"seuil|bascul|annul|dispara|cesse|à partir de|de combien|translation|déplacement", q):
        return "sensibilites", {}
    if re.search(r"durée|sur toute|total|par période|par année|chaque année|projection|produits des activités", q):
        return "projection_resultat", {}
    return "donnees_du_dossier", {}


def fallback_answer(observations: list[dict]) -> str:
    """Réponse écrite par le code : les résultats d'outils, sans interprétation."""
    if not observations:
        return "Je n'ai pas pu obtenir de résultat fiable pour cette question."
    parts = ["Réponse construite à partir des résultats des outils (le texte du modèle n'a pas passé le contrôle) :"]
    for o in observations:
        parts.append(f"- {o['outil']} : {json.dumps(o.get('resultat'), ensure_ascii=False)[:600]}")
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# Le graphe
# --------------------------------------------------------------------------- #
class CopilotState(TypedDict, total=False):
    question: str
    messages: list[dict]          # conversation avec le LLM (système, utilisateur, observations)
    pending: dict | None          # décision du LLM en attente (outil ou réponse)
    observations: list[dict]      # {outil, arguments, resultat}
    answer: str
    sources: list[str]
    corrections: int
    llm_calls: int
    steps: list[dict]             # journal lisible (interface, rapport)
    source: str                   # llm | code
    memory: str                   # mémoire placée dans le contexte (faits + échanges contrôlés)


@dataclass
class CopilotResult:
    answer: str
    source: str
    observations: list[dict]
    steps: list[dict]
    llm_calls: int
    latency_ms: float
    engine: str
    warnings: list[str] = field(default_factory=list)
    trajectory: list[dict] = field(default_factory=list)   # points de reprise de cette question (checkpointer)
    memory_used: int = 0                                     # échanges passés placés dans le contexte


class Copilot:
    def __init__(self, tools: DossierTools, client: LLMClient, case_id: str = "", memory: str = "",
                 memory_refs: set[str] | None = None, memory_used: int = 0, checkpointer: Any = None):
        self.tools = tools.tools()
        self.n_periods = tools.p.n_periods
        self.client = client
        self.case_id = case_id
        self.memory = memory
        self.memory_refs = set(memory_refs or ())
        self.memory_used = memory_used
        self.checkpointer = checkpointer
        self.spec = load_prompt("copilot_agent")

    # -------------------------------------------------------------- nœuds
    def start_messages(self, question: str) -> list[dict]:
        catalogue = "\n".join(
            f"- {t.name}({' ; '.join(f'{k} = {v.description or v.annotation}' for k, v in t.args.model_fields.items())}) : "
            f"{t.description}" for t in self.tools.values())
        user = self.spec.render(question=question)
        if self.memory:
            user = f"<memoire>\n{self.memory}\n</memoire>\n{user}"
        return [{"role": "system", "content": self.spec.system.replace("$outils", catalogue)},
                {"role": "user", "content": user}]

    def decide(self, state: CopilotState) -> CopilotState:
        messages = state["messages"]
        calls = len(state.get("observations", []))
        if calls >= MAX_TOOL_CALLS:
            messages = messages + [{"role": "user", "content": "Budget d'outils épuisé : réponds maintenant "
                                    "avec les résultats obtenus (action « repondre »)."}]
        try:
            resp = self.client.chat(messages, model=self.spec.params.model, temperature=self.spec.params.temperature,
                                    max_tokens=self.spec.params.max_tokens, json_mode=True,
                                    trace={"agent": "copilote", "prompt_id": self.spec.id,
                                           "prompt_version": self.spec.version, "case_id": self.case_id,
                                           "step": len(state.get("steps", []))})
            data = resp.json()
            data = data if isinstance(data, dict) else {}
        except (LLMError, ValueError) as exc:
            data = {"action": "erreur", "detail": str(exc)[:200]}
        if data.get("action") == "outil" and calls >= MAX_TOOL_CALLS:
            data = {"action": "repondre", "reponse": ""}
        steps = state.get("steps", []) + [{"noeud": "decider", "pensee": str(data.get("pensee", ""))[:300],
                                            "action": data.get("action"), "outil": data.get("outil")}]
        return {"pending": data, "llm_calls": state.get("llm_calls", 0) + 1, "steps": steps,
                "messages": state["messages"] + [{"role": "assistant", "content": json.dumps(data, ensure_ascii=False)}]}

    def route_decision(self, state: CopilotState) -> str:
        return "agir" if (state.get("pending") or {}).get("action") == "outil" else "verifier"

    def act(self, state: CopilotState) -> CopilotState:
        d = state["pending"]
        name, raw = str(d.get("outil", "")), d.get("arguments") or {}
        tool = self.tools.get(name)
        if tool is None:
            result: dict = {"erreur": f"outil inconnu : {name} ; outils disponibles : {', '.join(self.tools)}"}
        else:
            try:
                args = tool.args.model_validate(raw).model_dump()
                result = tool.run(**args)
            except ValidationError as exc:
                result = {"erreur": "arguments invalides : " + "; ".join(e["msg"] for e in exc.errors())[:300]}
        obs = {"outil": name, "arguments": raw, "resultat": result}
        return {"observations": state.get("observations", []) + [obs],
                "steps": state.get("steps", []) + [{"noeud": "agir", "outil": name, "arguments": raw,
                                                     "erreur": result.get("erreur") if isinstance(result, dict) else None}],
                "messages": state["messages"] + [{"role": "user", "content":
                                                  f"<resultat outil=\"{name}\">\n{json.dumps(result, ensure_ascii=False)}\n</resultat>"}]}

    def verify(self, state: CopilotState) -> CopilotState:
        d = state.get("pending") or {}
        answer = str(d.get("reponse") or "").strip()
        obs = state.get("observations", [])
        issues = (answer_issues(answer, state["question"], obs, self.n_periods, state.get("memory", ""), self.memory_refs)
                  if answer else ["réponse vide"])
        steps = state.get("steps", []) + [{"noeud": "verifier", "problemes": issues}]
        if not issues:
            return {"answer": answer, "source": "llm", "sources": d.get("sources") or [], "steps": steps}
        if state.get("corrections", 0) < MAX_CORRECTIONS and d.get("action") != "erreur":
            return {"corrections": state.get("corrections", 0) + 1, "steps": steps, "answer": "",
                    "messages": state["messages"] + [{"role": "user", "content": "Le contrôle a trouvé : "
                                                      + " ; ".join(issues) + ". " + CORRECTION_HINT}]}
        return {"answer": fallback_answer(self._fallback_observations(obs, state["question"])), "source": "code",
                "steps": steps}

    def _fallback_observations(self, obs: list[dict], question: str = "") -> list[dict]:
        """F-018 (t07) et mesure test2 (u03, u05) : aucun outil appelé → le code choisit l'outil par mots-clés
        (seuil → sensibilites ; durée, total → projection_resultat ; niveau de confiance → niveau_de_confiance ;
        sinon donnees_du_dossier) et la réponse de repli donne ses chiffres au lieu d'un refus."""
        if obs:
            return obs
        name, args = fallback_tool(question)
        if name not in self.tools:
            return obs
        return [{"outil": name, "arguments": args, "resultat": self.tools[name].run(**args)}]

    def route_verification(self, state: CopilotState) -> str:
        return "fin" if state.get("answer") else "decider"

    # -------------------------------------------------------------- exécution
    def initial_state(self, question: str) -> CopilotState:
        return {"question": question, "messages": self.start_messages(question), "observations": [],
                "steps": [], "corrections": 0, "llm_calls": 0, "answer": "", "source": "", "sources": [],
                "pending": None, "memory": self.memory}

    def build_graph(self):
        from langgraph.graph import END, START, StateGraph

        g = StateGraph(CopilotState)
        g.add_node("decider", self.decide)
        g.add_node("agir", self.act)
        g.add_node("verifier", self.verify)
        g.add_edge(START, "decider")
        g.add_conditional_edges("decider", self.route_decision, {"agir": "agir", "verifier": "verifier"})
        g.add_edge("agir", "decider")
        g.add_conditional_edges("verifier", self.route_verification, {"fin": END, "decider": "decider"})
        return g.compile(checkpointer=self.checkpointer)

    def run_without_langgraph(self, state: CopilotState) -> CopilotState:
        """Même graphe, mêmes nœuds, parcouru à la main (LangGraph absent) : comportement identique."""
        node = "decider"
        for _ in range(4 * (MAX_TOOL_CALLS + MAX_CORRECTIONS + 2)):
            if node == "decider":
                state = {**state, **self.decide(state)}
                node = self.route_decision(state)
            elif node == "agir":
                state = {**state, **self.act(state)}
                node = "decider"
            else:
                state = {**state, **self.verify(state)}
                if self.route_verification(state) == "fin":
                    return state
                node = "decider"
        return {**state, "answer": fallback_answer(self._fallback_observations(state.get("observations", []),
                                                                                state.get("question", ""))),
                "source": "code"}

    LIMIT = 4 * (MAX_TOOL_CALLS + MAX_CORRECTIONS + 2)

    def _config(self, thread_id: str | None, checkpoint_id: str | None = None) -> dict:
        cfg: dict = {"recursion_limit": self.LIMIT}
        if self.checkpointer is not None and thread_id:
            cfg["configurable"] = {"thread_id": thread_id, **({"checkpoint_id": checkpoint_id} if checkpoint_id else {})}
        return cfg

    def _result(self, final: dict, engine: str, t0: float, trajectory: list[dict]) -> CopilotResult:
        return CopilotResult(answer=final.get("answer", ""), source=final.get("source", "code"),
                             observations=final.get("observations", []), steps=final.get("steps", []),
                             llm_calls=final.get("llm_calls", 0), engine=engine, trajectory=trajectory,
                             memory_used=self.memory_used, latency_ms=round((time.perf_counter() - t0) * 1000, 1))

    def ask(self, question: str, thread_id: str | None = None) -> CopilotResult:
        t0 = time.perf_counter()
        state = self.initial_state(question)
        try:
            graph = self.build_graph()
            engine = "langgraph" + (" + checkpointer" if self.checkpointer is not None and thread_id else "")
        except ImportError:
            graph, engine = None, "boucle python (LangGraph absent)"
        if graph is None:
            return self._result(self.run_without_langgraph(state), engine, t0, [])
        cfg = self._config(thread_id)
        before = {c["checkpoint_id"] for c in self.history(thread_id, graph)} if "configurable" in cfg else set()
        final = graph.invoke(state, cfg)
        run = [c for c in self.history(thread_id, graph) if c["checkpoint_id"] not in before] if "configurable" in cfg else []
        return self._result(final, engine, t0, run[::-1])

    def history(self, thread_id: str | None, graph: Any = None) -> list[dict]:
        """Points de reprise du fil (le plus récent d'abord) : prochaine étape, question, réponse."""
        if self.checkpointer is None or not thread_id:
            return []
        graph = graph or self.build_graph()
        out = []
        for snap in graph.get_state_history({"configurable": {"thread_id": thread_id}}):
            v = snap.values or {}
            out.append({"checkpoint_id": snap.config["configurable"]["checkpoint_id"],
                        "cree_le": snap.created_at, "etape": (snap.metadata or {}).get("step"),
                        "prochaine": list(snap.next), "question": v.get("question", ""),
                        "reponse": v.get("answer", ""), "outils": [o.get("outil") for o in v.get("observations", [])],
                        "appels_llm": v.get("llm_calls", 0)})
        return out

    def replay(self, thread_id: str, checkpoint_id: str) -> CopilotResult:
        """Rejoue depuis un point de reprise : l'état sauvegardé est repris tel quel, les nœuds suivants
        sont réexécutés (une nouvelle branche est créée ; l'historique d'origine est conservé)."""
        t0 = time.perf_counter()
        graph = self.build_graph()
        before = {c["checkpoint_id"] for c in self.history(thread_id, graph)}
        final = graph.invoke(None, self._config(thread_id, checkpoint_id))
        run = [c for c in self.history(thread_id, graph) if c["checkpoint_id"] not in before]
        return self._result(final, "langgraph + checkpointer (rejeu)", t0, run[::-1])


_CHECKPOINTERS: dict[str, Any] = {}


def copilot_checkpointer(path) -> Any:
    """Checkpointer SQLite (un fichier, partagé entre les requêtes) ; en mémoire si le paquet
    langgraph-checkpoint-sqlite manque ; None si LangGraph est absent."""
    key = str(path)
    if key in _CHECKPOINTERS:
        return _CHECKPOINTERS[key]
    try:
        import sqlite3
        from pathlib import Path

        from langgraph.checkpoint.sqlite import SqliteSaver
        Path(key).parent.mkdir(parents=True, exist_ok=True)
        saver: Any = SqliteSaver(sqlite3.connect(key, check_same_thread=False))
    except ImportError:
        try:
            from langgraph.checkpoint.memory import InMemorySaver
            saver = InMemorySaver()
        except ImportError:
            saver = None
    _CHECKPOINTERS[key] = saver
    return saver
