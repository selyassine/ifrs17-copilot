"""Orchestrateur d'un dossier complet (D-036) : document → données → CSM → norme → note.

    extracteur ─► calculateur ─► chercheur RAG + vérificateur (questions fixes) ─► rédacteur
        │               │                       │                                   │
   ancrage des     moteur Python          citations vérifiées,                synthèse ancrée
    chiffres      (jamais le LLM)        juge, 1 correction max          (chiffres et paragraphes)

Chaque étape est journalisée (agent, statut, durée) : n8n affiche ce journal et décide de la
suite. Le dossier part en **validation humaine** dès qu'un contrôle n'est pas passé ; la note est
alors produite quand même, marquée « à valider », pour que l'humain ait tout sous les yeux.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from agents.pipeline import verified_answer
from agents.schemas import CsmResult, PortfolioData, VerdictStatus
from agents.writer import NormPoint, Note, verdict_label, write_note
from core.config import Settings
from core.llm import LLMClient
from engine.csm import compute_csm
from multimodal.documents import pdf_text
from multimodal.extract import ExtractionResult, extract_from_images, extract_from_text
from multimodal.vision import normalize_image, pdf_page_images

BASE_QUESTIONS = [
    "Comment la marge sur services contractuels est-elle déterminée lors de la comptabilisation initiale d'un groupe de contrats ?",
    "Comment la marge sur services contractuels est-elle comptabilisée en résultat au fil des périodes, selon les unités de couverture ?",
]
ONEROUS_QUESTION = ("Comment comptabiliser un groupe de contrats d'assurance déficitaire lors de la "
                    "comptabilisation initiale ?")


class UnreadableDocument(ValueError):
    """PDF ou image illisible (corrompu, chiffré, format inconnu)."""


@dataclass
class Step:
    agent: str
    status: str
    detail: str = ""
    ms: float = 0.0


@dataclass
class CaseOutcome:
    case_id: str
    status: str                     # note_prete | validation_humaine | document_illisible
    steps: list[Step] = field(default_factory=list)
    extraction: ExtractionResult | None = None
    csm: CsmResult | None = None
    norm: list[NormPoint] = field(default_factory=list)
    note: Note | None = None
    controls: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def extract_document(data: bytes, mime: str, settings: Settings, text_client: Callable[[], LLMClient],
                     vision_client: Callable[[], LLMClient], case_id: str = "") -> ExtractionResult:
    """PDF à couche texte → mode texte (ou hybride selon EXTRACT_PDF_MODE) ; scan ou image → vision."""
    if mime == "application/pdf":
        try:
            doc = pdf_text(data)
        except Exception as exc:          # PDF corrompu ou chiffré
            raise UnreadableDocument(f"PDF illisible : {exc}"[:300]) from exc
        has_text = len(doc.table_numbers) + len(doc.text_numbers) >= 3
        if has_text and settings.extract_pdf_mode != "hybride":
            return extract_from_text(doc, text_client(), case_id=case_id)
        return extract_from_images(pdf_page_images(data, max_pages=2), vision_client(),
                                   doc=doc if has_text else None, case_id=case_id,
                                   double_read=settings.vision_double_read)
    try:
        image = normalize_image(data)
    except Exception as exc:
        raise UnreadableDocument(f"image illisible : {exc}"[:300]) from exc
    return extract_from_images([image], vision_client(), case_id=case_id,
                               double_read=settings.vision_double_read)


def _timed(steps: list[Step], agent: str):
    class _T:
        def __enter__(self):
            self.t0 = time.perf_counter()
            self.step = Step(agent=agent, status="en cours")
            steps.append(self.step)
            return self.step

        def __exit__(self, *exc):
            self.step.ms = round((time.perf_counter() - self.t0) * 1000, 1)
            return False
    return _T()


def run_case(data: bytes, mime: str, settings: Settings, text_client: Callable[[], LLMClient],
             vision_client: Callable[[], LLMClient], retriever_loader: Callable | None,
             case_id: str, portfolio: PortfolioData | None = None) -> CaseOutcome:
    """``portfolio`` fourni (données validées par un humain) : l'extraction est sautée."""
    out = CaseOutcome(case_id=case_id, status="note_prete")
    client = text_client()

    # 1. Extracteur
    if portfolio is None:
        with _timed(out.steps, "extracteur") as st:
            ext = extract_document(data, mime, settings, text_client, vision_client, case_id)
            out.extraction = ext
            st.status = ext.status
            st.detail = f"mode {ext.mode}, ancrage {ext.grounding}" + (f", {len(ext.issues)} problème(s)" if ext.issues else "")
        if ext.portfolio is None:
            out.status = "document_illisible"
            out.controls = ext.issues or ["aucune donnée exploitable"]
            return out
        portfolio = ext.portfolio
        out.controls += [f"extraction : {i}" for i in ext.issues]
        out.controls += [f"extraction : champ absent du document ({m})" for m in ext.missing]
    else:
        out.steps.append(Step(agent="extracteur", status="saute", detail="données fournies (validées)"))

    # 2. Calculateur (Python, jamais le LLM)
    with _timed(out.steps, "calculateur") as st:
        out.csm = compute_csm(portfolio)
        st.status = "ok"
        st.detail = "groupe déficitaire" if out.csm.onerous else "groupe bénéficiaire"

    # 3. Chercheur RAG + vérificateur, sur des questions fixes adaptées au cas
    questions = BASE_QUESTIONS + ([ONEROUS_QUESTION] if out.csm.onerous else [])
    if retriever_loader is None:
        out.warnings.append("norme non indexée : note sans fondements cités")
    else:
        retriever = retriever_loader()
        for q in questions:
            with _timed(out.steps, "chercheur_rag+verificateur") as st:
                res = verified_answer(q, settings, client, retriever, case_id=case_id)
                label = verdict_label(res.verdict)
                out.norm.append(NormPoint(question=q, answer=res.answer, verdict=label))
                st.status = "refus" if res.answer.refused else label
                st.detail = q[:80]
                if res.verdict is not None and res.verdict.status != VerdictStatus.OK:
                    out.controls.append(f"norme : réponse non validée par le vérificateur ({q[:60]}…)")

    # 4. Rédacteur
    checks = ["Calcul effectué par le moteur Python (le LLM ne calcule jamais)"]
    if out.extraction is not None:
        checks.append(f"Chiffres extraits contrôlés contre le document ({out.extraction.grounding})")
    if out.norm:
        checks.append("Citations de la norme vérifiées par le code, réponses relues par le vérificateur")
    with _timed(out.steps, "redacteur") as st:
        out.note = write_note(portfolio, out.csm, out.norm, out.controls, checks + [
            "Synthèse : chaque nombre et chaque paragraphe cité vérifiés par le code"], client, case_id)
        st.status = "ok" if out.note.synthesis_source == "llm" else "repli"
        st.detail = "synthèse du LLM vérifiée" if st.status == "ok" else "synthèse écrite par le code"
        out.warnings += out.note.warnings

    if out.controls:
        out.status = "validation_humaine"
    return out
