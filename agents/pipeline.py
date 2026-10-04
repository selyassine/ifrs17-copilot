"""Chaîne « question sur la norme » : routeur → refus immédiat ou agent Chercheur RAG
→ vérificateur (LLM-juge) → au plus une correction → sinon validation humaine (D-033).

Utilisée par l'API (/v1/ask) et par l'évaluation (eval/eval_rag.py), pour que ce qui est
mesuré soit exactement ce qui tourne en démo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agents.rag_agent import RagResult, answer_question
from agents.router import route_heuristic, route_llm
from agents.schemas import AgentName, GroundedAnswer, Intent, Plan, Verdict, VerdictStatus
from agents.verifier import feedback_text, verify_answer
from core.config import Settings
from core.llm import LLMClient
from rag.retrieve import Retriever, fold

OUT_OF_SCOPE_MESSAGE = ("Cette demande ne porte pas sur IFRS 17 : je ne peux répondre qu'à des "
                        "questions sur la norme.")
SMALL_TALK_MESSAGE = ("Bonjour ! Je suis le copilote IFRS 17. Je réponds aux questions sur la norme, en "
                      "citant les paragraphes du règlement (UE) 2021/2036, et j'analyse vos documents de "
                      "portefeuille. Par exemple : « Comment la CSM est-elle libérée en résultat ? »")
THANKS_MESSAGE = "Avec plaisir ! Posez-moi une autre question sur IFRS 17 quand vous voulez."

# Échanges de politesse : réponse aimable, sans appel au LLM ni au RAG (D-039).
_TRIGGER_WORDS = """salut bonjour bonsoir hello hey coucou cc slt bjr cv merci thanks
qui presente presentes presenter va sais savez"""
_POLITE_TRIGGERS = set(_TRIGGER_WORDS.split())
_OTHER_WORDS = """a allez aller au beaucoup bien bonne ca comment d de e es est et
etes fais faire je journee le les m moi ok peux pour qu que quoi sais savez super t te tes toi tres tu
un une va vas vous votre ton toi"""
_POLITE_WORDS = _POLITE_TRIGGERS | set(_OTHER_WORDS.split())


def small_talk(question: str) -> str | None:
    """Message de politesse adapté, ou None si la question doit suivre la chaîne normale."""
    words = re.findall(r"[a-z]+", fold(question))
    if not words or len(words) > 8 or not set(words) & _POLITE_TRIGGERS:
        return None
    if not all(w in _POLITE_WORDS for w in words):
        return None
    if "merci" in words or "thanks" in words:
        return THANKS_MESSAGE
    return SMALL_TALK_MESSAGE


@dataclass
class AskResult:
    plan: Plan
    rag: RagResult | None
    answer: GroundedAnswer
    warnings: list[str] = field(default_factory=list)
    verdict: Verdict | None = None          # None : vérificateur désactivé
    small_talk: bool = False                # politesse : message d'accueil, pas un refus
    rounds: int = 0                         # corrections demandées par le vérificateur
    first_verdict: Verdict | None = None    # verdict sur la première réponse (évaluation)


def ask(question: str, settings: Settings, client: LLMClient, retriever_loader, k: int = 5,
        case_id: str = "") -> AskResult:
    """``retriever_loader`` : fonction sans argument qui renvoie le Retriever (chargé seulement si utile)."""
    polite = small_talk(question)
    if polite is not None:
        plan = Plan(intent=Intent.OUT_OF_SCOPE, steps=[], confidence=1.0,
                    rationale="échange de politesse : message d'accueil, aucun agent appelé")
        return AskResult(plan=plan, rag=None, small_talk=True,
                         answer=GroundedAnswer(answer=None, refused=True, refusal_reason=polite))
    if settings.router_mode == "llm":
        plan = route_llm(question, False, client=client, case_id=case_id)
    else:
        plan = route_heuristic(question, False)

    if plan.intent == Intent.OUT_OF_SCOPE:
        refusal = GroundedAnswer(answer=None, refused=True, refusal_reason=OUT_OF_SCOPE_MESSAGE)
        return AskResult(plan=plan, rag=None, answer=refusal)

    retriever: Retriever = retriever_loader()
    res = verified_answer(question, settings, client, retriever, k=k, case_id=case_id)
    res.plan = plan
    return res


def verified_answer(question: str, settings: Settings, client: LLMClient, retriever: Retriever,
                    k: int = 5, case_id: str = "", plan: Plan | None = None) -> AskResult:
    """Agent RAG puis vérificateur, avec au plus ``verifier_max_rounds`` corrections.
    Utilisé par /v1/ask (après le routeur) et par l'orchestrateur d'un dossier (questions fixes)."""
    plan = plan or Plan(intent=Intent.NORM_QUESTION, steps=[AgentName.RAG, AgentName.VERIFIER],
                        confidence=1.0, rationale="question posée par l'orchestrateur")

    def run(feedback: str = "") -> RagResult:
        return answer_question(question, retriever, client=client, k=k, mode=settings.rag_mode,
                               expand=settings.rag_glossary, version=settings.rag_prompt_version,
                               case_id=case_id, feedback=feedback)

    rag = run()
    if not settings.verifier_enabled:
        return AskResult(plan=plan, rag=rag, answer=rag.answer, warnings=rag.warnings)

    check = verify_answer(question, rag.answer, rag.extracts, client, case_id=case_id)
    first, rounds = check.verdict, 0
    while check.verdict.status == VerdictStatus.FIX and rounds < settings.verifier_max_rounds:
        rounds += 1
        rag = run(feedback_text(check.verdict))
        check = verify_answer(question, rag.answer, rag.extracts, client, case_id=case_id)
    verdict = check.verdict
    if verdict.status == VerdictStatus.FIX:
        # le problème persiste après correction : un humain tranche (la réponse n'est pas envoyée seule)
        verdict = Verdict(status=VerdictStatus.HUMAN, issues=verdict.issues)
    warnings = list(rag.warnings)
    if verdict.status != VerdictStatus.OK:
        warnings.append("réponse à faire valider par un humain : " + feedback_text(verdict)[:500])
    return AskResult(plan=plan, rag=rag, answer=rag.answer, warnings=warnings, verdict=verdict,
                     rounds=rounds, first_verdict=first)
