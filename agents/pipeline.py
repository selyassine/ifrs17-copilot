"""Chaîne « question sur la norme » : routeur → refus immédiat ou agent Chercheur RAG
→ vérificateur (LLM-juge) → au plus une correction → sinon validation humaine (D-033).

Utilisée par l'API (/v1/ask) et par l'évaluation (eval/eval_rag.py), pour que ce qui est
mesuré soit exactement ce qui tourne en démo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.rag_agent import RagResult, answer_question
from agents.router import route_heuristic, route_llm
from agents.schemas import GroundedAnswer, Intent, Plan, Verdict, VerdictStatus
from agents.verifier import feedback_text, verify_answer
from core.config import Settings
from core.llm import LLMClient
from rag.retrieve import Retriever

OUT_OF_SCOPE_MESSAGE = ("Cette demande ne porte pas sur IFRS 17 : je ne peux répondre qu'à des "
                        "questions sur la norme.")


@dataclass
class AskResult:
    plan: Plan
    rag: RagResult | None
    answer: GroundedAnswer
    warnings: list[str] = field(default_factory=list)
    verdict: Verdict | None = None          # None : vérificateur désactivé
    rounds: int = 0                         # corrections demandées par le vérificateur
    first_verdict: Verdict | None = None    # verdict sur la première réponse (évaluation)


def ask(question: str, settings: Settings, client: LLMClient, retriever_loader, k: int = 5,
        case_id: str = "") -> AskResult:
    """``retriever_loader`` : fonction sans argument qui renvoie le Retriever (chargé seulement si utile)."""
    if settings.router_mode == "llm":
        plan = route_llm(question, False, client=client, case_id=case_id)
    else:
        plan = route_heuristic(question, False)

    if plan.intent == Intent.OUT_OF_SCOPE:
        refusal = GroundedAnswer(answer=None, refused=True, refusal_reason=OUT_OF_SCOPE_MESSAGE)
        return AskResult(plan=plan, rag=None, answer=refusal)

    retriever: Retriever = retriever_loader()
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
