"""API FastAPI appelée par n8n.

    uvicorn api.main:app --reload --port 8000
    → documentation interactive : http://localhost:8000/docs

Endpoints : santé, routage, calcul du CSM (S1), recherche dans la norme (S2),
question sur la norme avec réponse citée (S3, /v1/ask), lecture d'un document client
(S3, /v1/extract) et chaîne document → données vérifiées → CSM (S3, /v1/case/document).
Vérification et rédaction s'ajoutent en S4.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agents.orchestrator import UnreadableDocument, extract_document, run_case
from agents.pipeline import ask as run_ask
from agents.router import route_heuristic, route_llm
from agents.schemas import CsmResult, GroundedAnswer, Plan, PortfolioData, Verdict
from core.config import Settings, get_settings
from core.llm import LLMClient, LLMError
from core.tracing import traced
from engine.csm import compute_csm
from multimodal.extract import ExtractionResult
from multimodal.speech import audio_type, transcribe
from multimodal.vision import detect_mime, vision_client
from rag.service import IndexMissing, get_retriever

VERSION = "0.4.0"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

class UTF8JSONResponse(JSONResponse):
    """Annonce explicitement l'UTF-8 : sans « charset », Windows PowerShell 5.1 décode les
    réponses en Latin-1 et affiche « libÃ©rÃ©e » au lieu de « libérée » (F-007)."""

    media_type = "application/json; charset=utf-8"


app = FastAPI(
    title="IFRS 17 Copilot",
    version=VERSION,
    description="Services IA appelés par les workflows n8n.",
    default_response_class=UTF8JSONResponse,
)


def check_token(
    x_api_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Jeton simple, obligatoire dès que l'API est exposée par un tunnel."""
    if settings.api_token and x_api_token != settings.api_token:
        raise HTTPException(status_code=401, detail="jeton API invalide")


class RouteRequest(BaseModel):
    request: str = Field(min_length=1, max_length=4000)
    has_attachment: bool = False
    case_id: str | None = None


class RouteResponse(BaseModel):
    case_id: str
    router: str
    plan: Plan


@app.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "status": "ok",
        "version": VERSION,
        "llm_provider": settings.llm_provider,
        "router_mode": settings.router_mode,
    }


@app.post("/v1/route", response_model=RouteResponse, dependencies=[Depends(check_token)])
def route(body: RouteRequest, settings: Settings = Depends(get_settings)) -> RouteResponse:
    case_id = body.case_id or uuid.uuid4().hex[:12]
    if settings.router_mode == "llm":
        plan = route_llm(body.request, body.has_attachment, case_id=case_id)
    else:
        with traced(settings.trace_path, kind="tool", agent="routeur",
                    tool="route_heuristic", case_id=case_id):
            plan = route_heuristic(body.request, body.has_attachment)
    return RouteResponse(case_id=case_id, router=settings.router_mode, plan=plan)


@app.post("/v1/csm/compute", response_model=CsmResult, dependencies=[Depends(check_token)])
def csm_compute(portfolio: PortfolioData,
                settings: Settings = Depends(get_settings)) -> CsmResult:
    with traced(settings.trace_path, kind="tool", agent="calculateur",
                tool="compute_csm", group_id=portfolio.group_id):
        return compute_csm(portfolio)


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    k: int = Field(default=5, ge=1, le=20)
    mode: str | None = Field(default=None, pattern="^(bm25|dense|hybrid)$",
                             description="par défaut : RAG_MODE du .env")
    zones: list[str] | None = Field(default=None, description="ex. ['norme', 'annexe_B']")
    glossary: bool | None = None


class SearchHit(BaseModel):
    rank: int
    score: float
    chunk_id: str
    paragraph_ids: list[str]
    zone: str
    heading: str
    page_start: int
    text: str


class SearchResponse(BaseModel):
    query: str
    mode: str
    strategy: str
    hits: list[SearchHit]


@app.post("/v1/search", response_model=SearchResponse, dependencies=[Depends(check_token)])
def search(body: SearchRequest, settings: Settings = Depends(get_settings)) -> SearchResponse:
    mode = body.mode or settings.rag_mode
    model = settings.rag_embed_model if mode in ("dense", "hybrid") else ""
    if mode in ("dense", "hybrid") and not model:
        raise HTTPException(status_code=400, detail=f"mode '{mode}' : définir RAG_EMBED_MODEL dans .env")
    try:
        retriever = get_retriever(settings.rag_strategy, model)
    except IndexMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    expand = settings.rag_glossary if body.glossary is None else body.glossary
    with traced(settings.trace_path, kind="tool", agent="chercheur_rag", tool="search",
                mode=mode, strategy=settings.rag_strategy):
        hits = retriever.search(body.query, k=body.k, mode=mode, zones=body.zones, expand=expand)
    return SearchResponse(
        query=body.query, mode=mode, strategy=settings.rag_strategy,
        hits=[SearchHit(rank=h.rank, score=round(h.score, 4), chunk_id=h.chunk.chunk_id,
                        paragraph_ids=h.chunk.paragraph_ids, zone=h.chunk.zone,
                        heading=h.chunk.heading, page_start=h.chunk.page_start, text=h.chunk.text)
              for h in hits],
    )


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    k: int = Field(default=5, ge=1, le=10)
    case_id: str | None = None


class AskResponse(BaseModel):
    case_id: str
    plan: Plan
    answer: GroundedAnswer
    verdict: Verdict | None = Field(default=None, description="ok | a_corriger | validation_humaine")
    rounds: int = 0
    sources: list[dict]
    warnings: list[str]
    corrections: int
    latency_ms: float


def make_client(settings: Settings) -> LLMClient:
    """Point d'injection (remplacé par un LLM factice dans les tests)."""
    return LLMClient(settings)


@app.post("/v1/ask", response_model=AskResponse, dependencies=[Depends(check_token)])
def ask(body: AskRequest, settings: Settings = Depends(get_settings)) -> AskResponse:
    """Routeur → (hors périmètre : refus immédiat, sans appel au RAG) → agent Chercheur RAG."""
    case_id = body.case_id or uuid.uuid4().hex[:12]
    mode = settings.rag_mode
    model = settings.rag_embed_model if mode in ("dense", "hybrid") else ""
    try:
        res = run_ask(body.question, settings, make_client(settings),
                      lambda: get_retriever(settings.rag_strategy, model), k=body.k, case_id=case_id)
    except IndexMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"LLM indisponible : {exc}"[:500]) from exc
    rag = res.rag
    return AskResponse(case_id=case_id, plan=res.plan, answer=res.answer, verdict=res.verdict,
                       rounds=res.rounds,
                       sources=rag.sources if rag else [], warnings=res.warnings,
                       corrections=rag.corrections if rag else 0,
                       latency_ms=rag.latency_ms if rag else 0.0)


# --------------------------------------------------------------------------- #
# Extracteur multimodal (S3) : document client → PortfolioData vérifié
# --------------------------------------------------------------------------- #
class ExtractResponse(BaseModel):
    case_id: str
    mode: str = Field(description="texte | vision | hybride")
    status: str = Field(description="ok | a_verifier | echec")
    portfolio: PortfolioData | None
    issues: list[str]
    missing: list[str]
    warnings: list[str]
    corrections: int
    latency_ms: float


class CaseDocumentResponse(ExtractResponse):
    next_step: str = Field(description="calcul_fait | validation_humaine | document_illisible")
    csm: CsmResult | None = None


def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="fichier trop volumineux (10 Mo maximum)")
    mime = detect_mime(data)
    if mime is None:
        raise HTTPException(status_code=415, detail="format non pris en charge : PDF, PNG ou JPEG")
    return data, mime


def make_vision_client(settings: Settings) -> LLMClient:
    """Point d'injection du client vision (remplacé dans les tests)."""
    return vision_client(settings)


def _run_extraction(data: bytes, mime: str, case_id: str, settings: Settings) -> ExtractionResult:
    """PDF à couche texte → mode texte (ou hybride selon EXTRACT_PDF_MODE) ; scan ou image → vision."""
    try:
        return extract_document(data, mime, settings, lambda: make_client(settings),
                                lambda: make_vision_client(settings), case_id)
    except UnreadableDocument as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _extract(file: UploadFile, case_id: str, settings: Settings) -> ExtractResponse:
    data, mime = _read_upload(file)
    try:
        res = _run_extraction(data, mime, case_id, settings)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"LLM indisponible : {exc}"[:500]) from exc
    return ExtractResponse(case_id=case_id, mode=res.mode, status=res.status, portfolio=res.portfolio,
                           issues=res.issues, missing=res.missing, warnings=res.warnings,
                           corrections=res.corrections, latency_ms=res.latency_ms)


@app.post("/v1/extract", response_model=ExtractResponse, dependencies=[Depends(check_token)])
def extract(file: UploadFile = File(...), case_id: str | None = Form(default=None),
            settings: Settings = Depends(get_settings)) -> ExtractResponse:
    """État de portefeuille (PDF, PNG ou JPEG) → données du groupe, avec contrôle d'ancrage."""
    return _extract(file, case_id or uuid.uuid4().hex[:12], settings)


@app.post("/v1/case/document", response_model=CaseDocumentResponse, dependencies=[Depends(check_token)])
def case_document(file: UploadFile = File(...), case_id: str | None = Form(default=None),
                  settings: Settings = Depends(get_settings)) -> CaseDocumentResponse:
    """Document → extraction vérifiée → CSM. Le calcul ne part que si l'extraction est « ok » ;
    sinon n8n demande une validation humaine, puis appelle /v1/csm/compute avec les données corrigées."""
    ext = _extract(file, case_id or uuid.uuid4().hex[:12], settings)
    if ext.status == "ok" and ext.portfolio is not None:
        with traced(settings.trace_path, kind="tool", agent="calculateur", tool="compute_csm",
                    group_id=ext.portfolio.group_id, case_id=ext.case_id):
            csm = compute_csm(ext.portfolio)
        return CaseDocumentResponse(**ext.model_dump(), next_step="calcul_fait", csm=csm)
    step = "validation_humaine" if ext.status == "a_verifier" else "document_illisible"
    return CaseDocumentResponse(**ext.model_dump(), next_step=step)


# --------------------------------------------------------------------------- #
# Question vocale (S3) : audio → Whisper → même chaîne que /v1/ask
# --------------------------------------------------------------------------- #
class AskAudioResponse(AskResponse):
    transcription: str
    audio_duration_s: float = 0.0


def speech_fake() -> None:
    """Point d'injection des tests (transcription scriptée) ; None en usage réel."""
    return None


@app.post("/v1/ask/audio", response_model=AskAudioResponse, dependencies=[Depends(check_token)])
def ask_audio(file: UploadFile = File(...), case_id: str | None = Form(default=None),
              settings: Settings = Depends(get_settings)) -> AskAudioResponse:
    name = file.filename or "question.m4a"
    if audio_type(name) is None:
        raise HTTPException(status_code=415, detail="audio non pris en charge : mp3, wav, m4a, ogg, webm, flac")
    data = file.file.read()
    try:
        tr = transcribe(data, name, settings, fake=speech_fake())
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"transcription impossible : {exc}"[:500]) from exc
    if len(tr.text) < 2:
        raise HTTPException(status_code=422, detail="aucune parole reconnue dans l'audio")
    res = ask(AskRequest(question=tr.text[:2000], case_id=case_id), settings)
    return AskAudioResponse(**res.model_dump(), transcription=tr.text, audio_duration_s=tr.duration_s)


# --------------------------------------------------------------------------- #
# Dossier complet (S4) : document → extracteur → calculateur → RAG + vérificateur → rédacteur
# --------------------------------------------------------------------------- #
class CaseStep(BaseModel):
    agent: str
    status: str
    detail: str
    ms: float


class NormItem(BaseModel):
    question: str
    answer: GroundedAnswer
    verdict: str


class CaseResponse(BaseModel):
    case_id: str
    status: str = Field(description="note_prete | validation_humaine | document_illisible")
    steps: list[CaseStep]
    extraction_status: str | None = None
    portfolio: PortfolioData | None = None
    csm: CsmResult | None = None
    norm: list[NormItem] = []
    controls: list[str] = []
    warnings: list[str] = []
    note_markdown: str | None = None
    note_html: str | None = None


def _case_response(out) -> CaseResponse:
    ext = out.extraction
    return CaseResponse(
        case_id=out.case_id, status=out.status,
        steps=[CaseStep(**s.__dict__) for s in out.steps],
        extraction_status=ext.status if ext else None,
        portfolio=ext.portfolio if ext else None, csm=out.csm,
        norm=[NormItem(question=n.question, answer=n.answer, verdict=n.verdict) for n in out.norm],
        controls=out.controls, warnings=out.warnings,
        note_markdown=out.note.markdown if out.note else None,
        note_html=out.note.html if out.note else None)


def _retriever_loader(settings: Settings):
    model = settings.rag_embed_model if settings.rag_mode in ("dense", "hybrid") else ""
    try:
        get_retriever(settings.rag_strategy, model)       # vérifie que l'index existe
    except IndexMissing:
        return None
    return lambda: get_retriever(settings.rag_strategy, model)


@app.post("/v1/case", response_model=CaseResponse, dependencies=[Depends(check_token)])
def case(file: UploadFile = File(...), case_id: str | None = Form(default=None),
         settings: Settings = Depends(get_settings)) -> CaseResponse:
    """Dossier complet à partir d'un document (PDF, PNG, JPEG). Toujours une réponse exploitable
    par n8n : ``status`` dit si la note peut partir ou doit être validée par un humain."""
    data, mime = _read_upload(file)
    cid = case_id or uuid.uuid4().hex[:12]
    try:
        out = run_case(data, mime, settings, lambda: make_client(settings),
                       lambda: make_vision_client(settings), _retriever_loader(settings), cid)
    except UnreadableDocument as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"LLM indisponible : {exc}"[:500]) from exc
    return _case_response(out)


class CaseFromDataRequest(BaseModel):
    portfolio: PortfolioData
    case_id: str | None = None


@app.post("/v1/case/validated", response_model=CaseResponse, dependencies=[Depends(check_token)])
def case_validated(body: CaseFromDataRequest, settings: Settings = Depends(get_settings)) -> CaseResponse:
    """Suite de la validation humaine dans n8n : données corrigées → calcul → norme → note."""
    cid = body.case_id or uuid.uuid4().hex[:12]
    try:
        out = run_case(b"", "", settings, lambda: make_client(settings), lambda: make_vision_client(settings),
                       _retriever_loader(settings), cid, portfolio=body.portfolio)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"LLM indisponible : {exc}"[:500]) from exc
    return _case_response(out)
