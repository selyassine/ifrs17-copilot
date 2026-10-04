"""Agent Vérificateur : contrôle une réponse avant qu'elle parte (D-033).

Deux étages, du moins cher au plus cher :

1. **Contrôles du code** (gratuits, sûrs) : déjà faits en amont par les autres agents
   (citations dans les extraits, chiffres ancrés dans le document). Le vérificateur ne les refait
   pas, il en lit le résultat.
2. **LLM-juge** (prompt ``verify_answer``) : ce que le code ne sait pas voir. Une phrase est-elle
   vraiment soutenue par le paragraphe cité ? Un paragraphe « réassurance » ou « transition »
   est-il présenté comme la règle générale (erreur de portée, F-011) ? La réponse répond-elle à la
   question ?

Verdict : ``ok`` → la réponse part ; ``a_corriger`` → l'orchestrateur relance l'agent avec la
liste des problèmes (boucle bornée) ; si le problème persiste → ``validation_humaine``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from agents.schemas import AgentName, GroundedAnswer, Issue, Verdict, VerdictStatus
from core.llm import LLMClient, LLMError
from core.prompts import load_prompt

KINDS = {"non_soutenu", "hors_portee", "incomplet", "hors_sujet"}


@dataclass
class VerifierResult:
    verdict: Verdict
    analysis: list[dict] = field(default_factory=list)
    latency_ms: float = 0.0
    error: str = ""


def answer_text(answer: GroundedAnswer) -> str:
    return answer.answer or ""


def to_verdict(data: dict) -> Verdict:
    problems = data.get("problemes") or []
    issues = []
    for p in problems if isinstance(problems, list) else []:
        if not isinstance(p, dict):
            continue
        kind = p.get("type") if p.get("type") in KINDS else "autre"
        where = f"[{p.get('paragraphe')}] " if p.get("paragraphe") else ""
        issues.append(Issue(agent=AgentName.RAG, kind=kind, detail=(where + str(p.get("detail", "")))[:400]))
    says_ok = str(data.get("verdict", "")).strip().lower() == "ok"
    off_topic = data.get("repond_a_la_question") is False
    if says_ok and not issues and not off_topic:
        return Verdict(status=VerdictStatus.OK)
    if not issues:
        issues = [Issue(agent=AgentName.RAG, kind="hors_sujet" if off_topic else "autre",
                        detail="le juge rejette la réponse sans détailler")]
    return Verdict(status=VerdictStatus.FIX, issues=issues)


def verify_answer(question: str, answer: GroundedAnswer, extracts: str, client: LLMClient,
                  version: int | None = None, case_id: str = "") -> VerifierResult:
    """Un refus n'a rien à vérifier : il part tel quel (le routeur et l'agent l'ont décidé)."""
    if answer.refused or not answer.answer:
        return VerifierResult(verdict=Verdict(status=VerdictStatus.OK))
    return judge(question, answer_text(answer), extracts, client, version, case_id)


def judge(question: str, answer: str, extracts: str, client: LLMClient,
          version: int | None = None, case_id: str = "", spec_override=None) -> VerifierResult:
    """``spec_override`` : fiche de prompt modifiée (ex. autre modèle) pour les comparaisons."""
    t0 = time.perf_counter()
    spec = spec_override or load_prompt("verify_answer", version)
    messages = [{"role": "system", "content": spec.system},
                {"role": "user", "content": spec.render(question=question, extracts=extracts,
                                                        answer=answer)}]
    try:
        resp = client.chat(messages, model=spec.params.model, temperature=spec.params.temperature,
                           max_tokens=spec.params.max_tokens, json_mode=True,
                           trace={"agent": "verificateur", "prompt_id": spec.id,
                                  "prompt_version": spec.version, "case_id": case_id})
        data = resp.json()
        if not isinstance(data, dict):
            raise LLMError("la réponse JSON n'est pas un objet")
    except LLMError as exc:
        # juge indisponible : on ne laisse pas passer sans contrôle
        verdict = Verdict(status=VerdictStatus.HUMAN, issues=[Issue(
            agent=AgentName.VERIFIER, kind="autre", detail=f"vérificateur indisponible : {exc}"[:300])])
        return VerifierResult(verdict=verdict, error=str(exc)[:300],
                              latency_ms=round((time.perf_counter() - t0) * 1000, 1))
    analysis = data.get("analyse") if isinstance(data.get("analyse"), list) else []
    return VerifierResult(verdict=to_verdict(data), analysis=analysis,
                          latency_ms=round((time.perf_counter() - t0) * 1000, 1))


def feedback_text(verdict: Verdict) -> str:
    return "\n".join(f"- {i.kind} : {i.detail}" for i in verdict.issues)
