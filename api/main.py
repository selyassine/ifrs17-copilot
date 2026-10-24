"""API FastAPI appelée par n8n.

    uvicorn api.main:app --reload --port 8000
    → documentation interactive : http://localhost:8000/docs

Endpoints : santé, routage, calcul du CSM (S1), recherche dans la norme (S2),
question sur la norme avec réponse citée (S3, /v1/ask), lecture d'un document client
(S3, /v1/extract) et chaîne document → données vérifiées → CSM (S3, /v1/case/document).
Vérification et rédaction s'ajoutent en S4.
"""

from __future__ import annotations

import json
import logging
import queue
import re
import threading
import time
import uuid
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agents.orchestrator import UnreadableDocument, extract_document, run_case
from agents.pipeline import ask as run_ask
from agents.router import route_heuristic, route_llm
from agents.schemas import CsmResult, GroundedAnswer, Plan, PortfolioData, TriangleData, Verdict
from api.security import ANALYSTE, VALIDEUR, Actor, current_actor, registry
from core.config import ROOT, Settings, get_settings
from core.llm import LLMClient, LLMError
from core.registry import Registry, llm_usage
from core.tracing import traced
from core.version import VERSION
from engine.bba import BbaResult, BbaScenario, roll_forward_bba
from engine.cloture import ClosingInput, ClosingResult, close_first_period
from engine.csm import compute_csm
from engine.paa import PaaContract, PaaPosition, position
from multimodal.extract import ExtractionResult
from multimodal.speech import audio_type, transcribe
from multimodal.vision import detect_mime, vision_client
from rag.service import IndexMissing, get_retriever, rag_status, retrieval_options

logger = logging.getLogger("ifrs17.api")
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


from api.registry_routes import router as registry_router  # noqa: E402

app.include_router(registry_router)


def check_token(actor: Actor = Depends(current_actor)) -> Actor:
    """Jeton machine (n8n) ou session utilisateur (site) : voir api/security.py (D-058)."""
    return actor


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
        "rag": rag_status(settings),
        "registre": {"comptes": registry(settings).has_users()},
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


@app.post("/v1/csm/rollforward", response_model=BbaResult, dependencies=[Depends(check_token)])
def csm_rollforward(scenario: BbaScenario, settings: Settings = Depends(get_settings)) -> BbaResult:
    """Modèle général sur plusieurs années (D-042) : BEL au taux courant, OCI, RA, écarts
    d'expérience, révisions, composante de perte et compte de résultat IFRS 17."""
    with traced(settings.trace_path, kind="tool", agent="calculateur",
                tool="roll_forward_bba", group_id=scenario.group_id):
        return roll_forward_bba(scenario)


class PaaRequest(BaseModel):
    contract: PaaContract
    at: list[date] = Field(min_length=1, max_length=24, description="Dates de clôture à évaluer")


@app.post("/v1/paa/position", response_model=list[PaaPosition], dependencies=[Depends(check_token)])
def paa_position(body: PaaRequest, settings: Settings = Depends(get_settings)) -> list[PaaPosition]:
    """Méthode d'affectation des primes (D-043) : LRC, LIC et résultat cumulé à chaque date."""
    with traced(settings.trace_path, kind="tool", agent="calculateur",
                tool="paa_position", group_id=body.contract.group_id):
        return [position(body.contract, d) for d in body.at]


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
        retriever = get_retriever(settings.rag_strategy, model, **retrieval_options(settings))
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
    small_talk: bool = Field(default=False, description="salutation : message d'accueil, pas un refus")
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
                      lambda: get_retriever(settings.rag_strategy, model, **retrieval_options(settings)), k=body.k, case_id=case_id)
    except IndexMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"LLM indisponible : {exc}"[:500]) from exc
    rag = res.rag
    return AskResponse(case_id=case_id, plan=res.plan, answer=res.answer, verdict=res.verdict,
                       rounds=res.rounds, small_talk=res.small_talk,
                       sources=rag.sources if rag else [], warnings=res.warnings,
                       corrections=rag.corrections if rag else 0,
                       latency_ms=rag.latency_ms if rag else 0.0)


# --------------------------------------------------------------------------- #
# Extracteur multimodal (S3) : document client → PortfolioData vérifié
# --------------------------------------------------------------------------- #
class ExtractResponse(BaseModel):
    case_id: str
    mode: str = Field(description="texte | vision | hybride | tableur")
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
    mime = detect_mime(data, file.filename or "")
    if mime is None:
        from multimodal.spreadsheet import is_xls
        if is_xls(data):
            raise HTTPException(status_code=415, detail="classeur Excel 97-2003 (.xls) : l'enregistrer au format .xlsx")
        raise HTTPException(status_code=415, detail="format non pris en charge : PDF, PNG, JPEG, Excel (.xlsx) ou CSV")
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


class GroupSummary(BaseModel):
    group_id: str
    status: str                       # note_prete | validation_humaine
    portfolio: PortfolioData
    csm: CsmResult
    controls: list[str] = []


class LicSummary(BaseModel):
    """Passif pour sinistres survenus (D-083) : chiffres du moteur, pour n8n et le site."""
    reserve: float
    mack_se: float
    cv: float
    cv_source: str
    bel: float
    risk_adjustment: float
    lic: float
    level: float
    discount_effect: float
    cash_flows: list[float]
    factors: list[float]


def lic_summary(r) -> LicSummary:
    return LicSummary(reserve=r.reserve, mack_se=r.mack_se, cv=r.cv, cv_source=r.cv_source, bel=r.bel,
                      risk_adjustment=r.risk_adjustment, lic=r.lic, level=r.level, discount_effect=r.discount_effect,
                      cash_flows=r.cash_flows, factors=r.factors)


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
    groups: list[GroupSummary] = Field(default=[], description="document à plusieurs groupes : un par groupe (D-078)")
    kind: str = Field(default="lrc", description="lrc : état de portefeuille (CSM) ; lic : triangle de sinistres (D-083)")
    triangle: TriangleData | None = None
    lic: LicSummary | None = None


def _case_response(out) -> CaseResponse:
    ext = out.extraction
    return CaseResponse(
        case_id=out.case_id, status=out.status,
        steps=[CaseStep(**s.__dict__) for s in out.steps],
        extraction_status=ext.status if ext else None,
        portfolio=out.portfolio, csm=out.csm,
        norm=[NormItem(question=n.question, answer=n.answer, verdict=n.verdict) for n in out.norm],
        controls=out.controls, warnings=out.warnings,
        note_markdown=out.note.markdown if out.note else None,
        note_html=out.note.html if out.note else None,
        groups=[GroupSummary(group_id=g.portfolio.group_id, status="validation_humaine" if g.controls else "note_prete",
                             portfolio=g.portfolio, csm=g.csm, controls=g.controls)
                for g in out.groups] if len(out.groups) > 1 else [],
        kind=out.kind, triangle=out.triangle, lic=lic_summary(out.lic) if out.lic is not None else None)


def _stored_data(out) -> dict | None:
    """Données inscrites au registre : le portefeuille, ou pour un dossier LIC le triangle et ses chiffres."""
    if out.portfolio is not None:
        return out.portfolio.model_dump(mode="json")
    if out.triangle is not None:
        t = out.triangle
        return {"kind": "lic", "group_id": t.portfolio_id, "currency": t.currency, "unit_multiplier": t.unit_multiplier,
                "triangle_data": t.model_dump(mode="json"),
                "lic": lic_summary(out.lic).model_dump(mode="json") if out.lic is not None else None}
    return None


def _retriever_loader(settings: Settings):
    model = settings.rag_embed_model if settings.rag_mode in ("dense", "hybrid") else ""
    try:
        get_retriever(settings.rag_strategy, model, **retrieval_options(settings))       # vérifie que l'index existe
    except IndexMissing:
        return None
    return lambda: get_retriever(settings.rag_strategy, model, **retrieval_options(settings))


# --------------------------------------------------------------------------- #
# Registre (D-058) : chaque dossier est enregistré, chaque étape laisse une trace d'audit
# --------------------------------------------------------------------------- #
def _trace_offset(settings: Settings) -> int:
    return settings.trace_path.stat().st_size if settings.trace_path.exists() else 0


def _record_start(reg: Registry, actor: Actor, cid: str, source: str | None, submitter: str | None,
                  filename: str, data: bytes) -> None:
    import hashlib

    src = source or ("site" if actor.kind == "utilisateur" else "api")
    reg.open_case(cid, src, actor.name, submitter=submitter or "", filename=filename,
                  sha256=hashlib.sha256(data).hexdigest() if data else "")


def _record_end(reg: Registry, actor: Actor, settings: Settings, cid: str, out, t0: float, offset: int,
                action: str = "analyse", validated_by: str = "", comment: str = "") -> None:
    status = out.status
    if validated_by and status == "note_prete":
        status = "validee"
    reg.record_outcome(
        cid, actor.name, status, action=action,
        portfolio=_stored_data(out),
        csm=out.csm.model_dump(mode="json") if out.csm else None, controls=out.controls,
        note_html=out.note.html if out.note else None, note_markdown=out.note.markdown if out.note else None,
        duration_ms=round((time.perf_counter() - t0) * 1000, 1), usage=llm_usage(settings.trace_path, cid, offset),
        validated_by=validated_by, comment=comment)


def _record_failure(reg: Registry, actor: Actor, cid: str, status: str, detail: str) -> None:
    reg.record_outcome(cid, actor.name, status, action="echec", controls=[detail[:300]])


@app.post("/v1/case", response_model=CaseResponse)
def case(file: UploadFile = File(...), case_id: str | None = Form(default=None),
         source: str | None = Form(default=None, description="site | n8n-email | n8n-formulaire | api"),
         submitter: str | None = Form(default=None, description="déposant (adresse e-mail, nom)"),
         settings: Settings = Depends(get_settings), actor: Actor = Depends(ANALYSTE),
         reg: Registry = Depends(registry)) -> CaseResponse:
    """Dossier complet à partir d'un document (PDF, PNG, JPEG). Toujours une réponse exploitable
    par n8n : ``status`` dit si la note peut partir ou doit être validée par un humain."""
    data, mime = _read_upload(file)
    cid = case_id or uuid.uuid4().hex[:12]
    _record_start(reg, actor, cid, source, submitter, file.filename or "", data)
    t0, offset = time.perf_counter(), _trace_offset(settings)
    try:
        out = run_case(data, mime, settings, lambda: make_client(settings),
                       lambda: make_vision_client(settings), _retriever_loader(settings), cid,
                       source_name=file.filename or "")
    except UnreadableDocument as exc:
        _record_failure(reg, actor, cid, "document_illisible", str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMError as exc:
        _record_failure(reg, actor, cid, "erreur", f"LLM indisponible : {exc}")
        raise HTTPException(status_code=502, detail=f"LLM indisponible : {exc}"[:500]) from exc
    except Exception as exc:   # noqa: BLE001 — n8n et le registre doivent toujours connaître la cause
        logger.exception("dossier %s : erreur interne", cid)
        _record_failure(reg, actor, cid, "erreur", f"erreur interne : {type(exc).__name__} : {exc}"[:300])
        raise HTTPException(status_code=500, detail=f"erreur interne : {type(exc).__name__} : {exc}"[:500]) from exc
    _record_end(reg, actor, settings, cid, out, t0, offset)
    return _case_response(out)


class CaseFromDataRequest(BaseModel):
    portfolio: PortfolioData | None = None
    triangle: TriangleData | None = Field(default=None, description="dossier de sinistres survenus validé (D-083)")
    other_groups: list[PortfolioData] = Field(default=[], description="autres groupes du même document, repris tels quels")
    case_id: str | None = None
    validated_by: str | None = Field(default=None, description="valideur (n8n : adresse e-mail du valideur)")
    comment: str | None = Field(default=None, max_length=1000)


CHANGE_LABELS = {"group_id": "groupe", "currency": "devise", "unit_multiplier": "unité", "premiums": "primes",
                 "outflows": "sinistres et frais", "recoveries": "recouvrements", "coverage_units": "unités de couverture",
                 "discount_rates": "taux d'actualisation", "risk_adjustment_pct": "ajustement pour risque"}


def validator_changes(before: dict | None, after: PortfolioData) -> list[str]:
    """Ce que le valideur a changé par rapport aux données extraites (D-067) : écrit dans la note et la
    piste d'audit, pour qu'un changement d'unité ou de groupe ne passe jamais inaperçu."""
    if not before:
        return []
    from multimodal.extract import compare_portfolios
    try:
        old = PortfolioData(**before)
    except ValueError:
        return []
    out: dict[str, list[str]] = {}
    for diff in compare_portfolios(old, after):
        field, _, detail = diff.partition(" : ")
        out.setdefault(field.split("[")[0], []).append(detail)
    lines = []
    for field, details in out.items():
        label = CHANGE_LABELS.get(field, field)
        if len(details) == 1 and " / " in details[0]:
            a, b = details[0].split(" / ", 1)
            lines.append(f"{label} : {a} → {b}")
        else:
            lines.append(f"{label} : {len(details)} valeur(s) corrigée(s)")
    return lines


def triangle_changes(before: dict | None, after: TriangleData) -> list[str]:
    """Corrections du valideur sur un triangle (D-083) : cellules, unité, taux, niveau de confiance."""
    if not before or not isinstance(before.get("triangle_data"), dict):
        return []
    try:
        old = TriangleData(**before["triangle_data"])
    except ValueError:
        return []
    out = []
    if old.unit_multiplier != after.unit_multiplier:
        out.append(f"unité : {old.unit_multiplier} → {after.unit_multiplier}")
    cells = [f"{after.origin_years[i] if i < len(after.origin_years) else i + 1}, retard {k + 1} : {a:g} → {b:g}"
             for i, (ra, rb) in enumerate(zip(old.triangle, after.triangle, strict=False))
             for k, (a, b) in enumerate(zip(ra, rb, strict=False)) if abs(a - b) > 0.005]
    if len(old.triangle) != len(after.triangle):
        out.append(f"années de survenance : {old.n_years} → {after.n_years}")
    if cells:
        out.append(cells[0] if len(cells) == 1 else f"triangle : {len(cells)} cellule(s) corrigée(s)")
    if old.discount_rates != after.discount_rates:
        out.append("taux d'actualisation corrigés")
    if old.confidence_level != after.confidence_level:
        out.append(f"niveau de confiance : {old.confidence_level} → {after.confidence_level}")
    return out


@app.post("/v1/case/validated", response_model=CaseResponse)
def case_validated(body: CaseFromDataRequest, settings: Settings = Depends(get_settings),
                   actor: Actor = Depends(VALIDEUR), reg: Registry = Depends(registry)) -> CaseResponse:
    """Suite de la validation humaine : données corrigées → calcul → norme → note. Réservé au rôle
    valideur (ou à n8n, qui transmet l'adresse du valideur qui a approuvé depuis sa boîte mail)."""
    cid = body.case_id or uuid.uuid4().hex[:12]
    validator = body.validated_by or actor.name
    if reg.get_case(cid) is None:
        reg.open_case(cid, "validation", actor.name, submitter=validator)
    if (body.portfolio is None) == (body.triangle is None):
        raise HTTPException(status_code=422, detail="fournir soit portfolio, soit triangle")
    before = (reg.get_case(cid) or {}).get("portfolio")
    changes = (validator_changes(before, body.portfolio) if body.portfolio is not None
               else triangle_changes(before, body.triangle))
    reg.add_event(cid, actor.name, "validation_approuvee", {"valideur": validator,
                                                            "commentaire": (body.comment or "")[:300],
                                                            "modifications": changes})
    t0, offset = time.perf_counter(), _trace_offset(settings)
    try:
        out = run_case(b"", "", settings, lambda: make_client(settings), lambda: make_vision_client(settings),
                       _retriever_loader(settings), cid, portfolio=body.portfolio, human_changes=changes,
                       other_portfolios=body.other_groups, triangle=body.triangle, validated_by=validator)
    except LLMError as exc:
        _record_failure(reg, actor, cid, "erreur", f"LLM indisponible : {exc}")
        raise HTTPException(status_code=502, detail=f"LLM indisponible : {exc}"[:500]) from exc
    _record_end(reg, actor, settings, cid, out, t0, offset, action="analyse_apres_validation",
                validated_by=validator, comment=body.comment or "")
    return _case_response(out)


class ClosingRequest(BaseModel):
    cloture: ClosingInput
    case_id: str | None = Field(default=None, description="dossier déjà calculé : ses données d'origine sont reprises")
    portfolio: PortfolioData | None = Field(default=None, description="données d'origine, si le dossier n'est pas au registre")


class ClosingResponse(BaseModel):
    case_id: str
    result: ClosingResult
    note_markdown: str
    note_html: str


@app.post("/v1/case/cloture", response_model=ClosingResponse)
def case_closing(body: ClosingRequest, settings: Settings = Depends(get_settings),
                 actor: Actor = Depends(ANALYSTE), reg: Registry = Depends(registry)) -> ClosingResponse:
    """Première clôture d'un dossier (D-076) : réalisé de la période, révision des estimations, CSM, résultat et
    rapprochement du passif. Calcul et note par le code seul (aucun appel au LLM)."""
    from actuariat.registre import current as registry_now
    from agents.closing_report import render_closing_note

    cid = body.case_id or uuid.uuid4().hex[:12]
    portfolio = body.portfolio
    if portfolio is None:
        stored = (reg.get_case(cid) or {}).get("portfolio") if body.case_id else None
        if not stored:
            raise HTTPException(status_code=404, detail="dossier inconnu ou sans données : fournir « portfolio »")
        if stored.get("kind") == "lic":
            raise HTTPException(status_code=422, detail="dossier de sinistres survenus (LIC) : la clôture d'un groupe "
                                                        "s'applique à un état de portefeuille")
        portfolio = PortfolioData(**stored)
    try:
        r = compute_csm(portfolio)
        res = close_first_period(portfolio, body.cloture, r)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:500]) from exc
    if abs(res.reconciliation_gap) > 1e-6:
        raise HTTPException(status_code=500, detail=f"rapprochement du passif en échec ({res.reconciliation_gap})")
    md, page = render_closing_note(portfolio, r, res, cid, settings.note_entity, str(registry_now().get("version", "")))
    if reg.get_case(cid) is None:
        reg.open_case(cid, "cloture", actor.name)
    reg.add_event(cid, actor.name, "cloture_calculee", {"au": res.as_of, "resultat": round(res.profit, 2),
                                                        "ecarts_experience": round(res.experience_adjustment, 2),
                                                        "passif_cloture": round(res.closing_liability, 2)})
    return ClosingResponse(case_id=cid, result=res, note_markdown=md, note_html=page)


class CopilotRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    portfolio: PortfolioData
    case_id: str | None = None


class CopilotResponse(BaseModel):
    case_id: str
    answer: str
    source: str                       # llm (réponse contrôlée) | code (repli)
    tools: list[dict]                 # outils appelés : nom, arguments, résultat
    steps: list[dict]
    llm_calls: int
    latency_ms: float
    engine: str
    memory_used: int = 0              # échanges passés placés dans le contexte (mémoire épisodique)
    trajectory: list[dict] = []       # points de reprise de cette question (checkpointer LangGraph)


def _copilot(settings: Settings, portfolio: PortfolioData, cid: str, reg: Registry, client=None):
    """Copilot d'un dossier, avec sa mémoire (registre) et son état sauvegardé (checkpointer) — D-061."""
    from agents.copilot import Copilot, DossierTools, copilot_checkpointer, norm_search_with
    from agents.memory import RECENT, case_facts, context_block, recall_with

    client = client or make_client(settings)
    past = reg.memories(cid)
    recent, older = past[-RECENT:], past[:-RECENT]
    from actuariat.registre import ra_volatility

    tools = DossierTools(portfolio, ra_cv=ra_volatility(portfolio.line_of_business, settings.ra_cv)[0],
                         norm_search=norm_search_with(settings, client, _retriever_loader(settings), cid),
                         recall=recall_with(older) if older else None)
    memory = context_block(recent, case_facts(reg.get_case(cid)))
    refs = {r for m in past for r in m["refs"]}
    return Copilot(tools, client, case_id=cid, memory=memory, memory_refs=refs, memory_used=len(recent),
                   checkpointer=copilot_checkpointer(settings.copilot_checkpoints))


def _copilot_response(cid: str, res) -> CopilotResponse:
    return CopilotResponse(case_id=cid, answer=res.answer, source=res.source, tools=res.observations,
                           steps=res.steps, llm_calls=res.llm_calls, latency_ms=res.latency_ms, engine=res.engine,
                           memory_used=res.memory_used, trajectory=res.trajectory)


def _remember(reg: Registry, cid: str, actor: Actor, question: str, res) -> None:
    import re as _re

    from agents.rag_agent import normalize_ref
    refs = sorted({r for m in _re.finditer(r"\[([^\[\]]{1,60})\]", res.answer) for r in normalize_ref(m.group(1))})
    from agents.memory import tool_digest
    reg.add_memory(cid, actor.name, question, res.answer, res.source, tool_digest(res.observations), refs)


@app.post("/v1/copilot", response_model=CopilotResponse)
def copilot(body: CopilotRequest, settings: Settings = Depends(get_settings),
            actor: Actor = Depends(ANALYSTE), reg: Registry = Depends(registry)) -> CopilotResponse:
    """Agent Copilot (D-057) : le LLM choisit les outils (scénario, sensibilités, niveau de confiance,
    projection, norme, mémoire) pour répondre sur un dossier ; outils en lecture seule, réponse
    contrôlée. Mémoire du dossier et état sauvegardé par question (D-061)."""
    cid = body.case_id or uuid.uuid4().hex[:12]
    try:
        res = _copilot(settings, body.portfolio, cid, reg).ask(body.question, thread_id=cid)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"LLM indisponible : {exc}"[:500]) from exc
    _remember(reg, cid, actor, body.question, res)
    if reg.get_case(cid) is not None:
        reg.add_event(cid, actor.name, "question_copilot", {"question": body.question[:200],
                                                            "outils": [o["outil"] for o in res.observations],
                                                            "memoire": res.memory_used})
    return _copilot_response(cid, res)


@app.get("/v1/copilot/{case_id}", tags=["copilot"])
def copilot_history(case_id: str, settings: Settings = Depends(get_settings), _: Actor = Depends(ANALYSTE),
                    reg: Registry = Depends(registry)) -> dict:
    """Mémoire du dossier (échanges contrôlés) et points de reprise sauvegardés par le checkpointer."""
    from agents.copilot import Copilot, DossierTools, copilot_checkpointer

    checkpoints = []
    saver = copilot_checkpointer(settings.copilot_checkpoints)
    case = reg.get_case(case_id)
    if saver is not None and case and case.get("portfolio") and case["portfolio"].get("kind") != "lic":
        try:
            cp = Copilot(DossierTools(PortfolioData(**case["portfolio"])), make_client(settings), case_id=case_id,
                         checkpointer=saver)
            checkpoints = cp.history(case_id)[:200]
        except ImportError:
            checkpoints = []
    return {"case_id": case_id, "echanges": reg.memories(case_id), "points_de_reprise": checkpoints,
            "checkpointer": type(saver).__name__ if saver is not None else None}


class ReplayRequest(BaseModel):
    checkpoint_id: str = Field(min_length=8, max_length=80)
    portfolio: PortfolioData


@app.post("/v1/copilot/{case_id}/rejouer", response_model=CopilotResponse, tags=["copilot"])
def copilot_replay(case_id: str, body: ReplayRequest, settings: Settings = Depends(get_settings),
                   actor: Actor = Depends(VALIDEUR), reg: Registry = Depends(registry)) -> CopilotResponse:
    """Rejoue une question depuis un point de reprise (débogage, audit) : l'état sauvegardé est repris,
    les nœuds suivants sont réexécutés ; l'historique d'origine reste intact."""
    cp = _copilot(settings, body.portfolio, case_id, reg)
    if cp.checkpointer is None:
        raise HTTPException(status_code=409, detail="rejeu impossible : LangGraph n'est pas installé")
    if body.checkpoint_id not in {c["checkpoint_id"] for c in cp.history(case_id)}:
        raise HTTPException(status_code=404, detail="point de reprise inconnu pour ce dossier")
    try:
        res = cp.replay(case_id, body.checkpoint_id)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"LLM indisponible : {exc}"[:500]) from exc
    if reg.get_case(case_id) is not None:
        reg.add_event(case_id, actor.name, "copilot_rejoue", {"point_de_reprise": body.checkpoint_id})
    return _copilot_response(case_id, res)


@app.delete("/v1/copilot/{case_id}/memoire", tags=["copilot"])
def copilot_forget(case_id: str, actor: Actor = Depends(VALIDEUR), reg: Registry = Depends(registry)) -> dict:
    """Efface la mémoire du Copilot pour ce dossier (par exemple après une correction des données)."""
    n = reg.forget(case_id)
    if reg.get_case(case_id) is not None:
        reg.add_event(case_id, actor.name, "copilot_memoire_effacee", {"echanges": n})
    return {"effaces": n}


# --------------------------------------------------------------------------- #
# Interface web (S4) : site servi par l'API, suivi des agents en direct, documents d'exemple
# --------------------------------------------------------------------------- #
WEB_DIR = Path(__file__).parent / "web"
SAMPLE_ID = re.compile(r"^(ext|dur)\d{2}$")


@app.get("/", include_in_schema=False)
def home():
    """Page de présentation publique du produit ; l'espace de travail est sous /app/."""
    site = WEB_DIR / "site.html"
    return FileResponse(site, media_type="text/html") if site.exists() else RedirectResponse("/app/")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(WEB_DIR / "assets" / "img" / "favicon.svg", media_type="image/svg+xml")


if WEB_DIR.exists():
    app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="web")


@app.post("/v1/case/stream")
def case_stream(file: UploadFile = File(...), case_id: str | None = Form(default=None),
                source: str | None = Form(default=None), submitter: str | None = Form(default=None),
                settings: Settings = Depends(get_settings), actor: Actor = Depends(ANALYSTE),
                reg: Registry = Depends(registry)) -> StreamingResponse:
    """Comme /v1/case, mais en flux (text/event-stream) : un événement par début et fin d'étape,
    puis le résultat complet. Permet à l'interface d'afficher les agents au travail."""
    data, mime = _read_upload(file)
    cid = case_id or uuid.uuid4().hex[:12]
    events: queue.Queue = queue.Queue()
    filename = file.filename or ""
    _record_start(reg, actor, cid, source, submitter, filename, data)

    def worker() -> None:
        t0, offset = time.perf_counter(), _trace_offset(settings)
        try:
            out = run_case(data, mime, settings, lambda: make_client(settings),
                           lambda: make_vision_client(settings), _retriever_loader(settings), cid,
                           on_step=lambda i, st: events.put({"type": "step", "index": i, **st.__dict__}),
                           source_name=filename)
            _record_end(reg, actor, settings, cid, out, t0, offset)
            result = _case_response(out).model_dump(mode="json")
            if result["status"] == "validation_humaine":
                events.put({"type": "notification", "status": "en cours"})
                result["notification"] = notify_validation(result, settings)
                reg.add_event(cid, "systeme", "email_validation", result["notification"])
            events.put({"type": "result", "data": result})
        except UnreadableDocument as exc:
            _record_failure(reg, actor, cid, "document_illisible", str(exc))
            events.put({"type": "error", "detail": str(exc)})
        except LLMError as exc:
            _record_failure(reg, actor, cid, "erreur", f"LLM indisponible : {exc}")
            events.put({"type": "error", "detail": f"LLM indisponible : {exc}"[:500]})
        except Exception as exc:  # noqa: BLE001 — l'interface doit toujours recevoir une fin
            _record_failure(reg, actor, cid, "erreur", f"erreur interne : {type(exc).__name__}")
            events.put({"type": "error", "detail": f"erreur interne : {type(exc).__name__}"})
        finally:
            events.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        yield f"data: {json.dumps({'type': 'start', 'case_id': cid})}\n\n"
        while (item := events.get()) is not None:
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def notify_validation(payload: dict, settings: Settings) -> dict:
    """Validation humaine demandée sur le site : transmet le dossier au workflow n8n 06, qui envoie
    la note provisoire et l'e-mail avec le formulaire pré-rempli (D-041). Point d'injection (tests)."""
    import httpx

    url = settings.n8n_validation_url
    if not url:
        return {"envoyee": False, "detail": "e-mail non configuré : N8N_VALIDATION_URL est vide dans .env"}
    try:
        r = httpx.post(url, json=payload, timeout=15, trust_env=False)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        return {"envoyee": False,
                "detail": f"n8n injoignable ou workflow inactif ({type(exc).__name__})"}
    return {"envoyee": True, "detail": "e-mail de validation envoyé par n8n"}


def _sample_cases() -> list[dict]:
    out = []
    for name, kind in (("extraction_cases.jsonl", "simple"), ("extraction_hard_cases.jsonl", "piege")):
        path = ROOT / "eval" / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                c = json.loads(line)
                images = c.get("images") or ([c["image"]] if c.get("image") else [])
                out.append({"id": c["id"], "kind": kind, "layout": c["layout"], "scan": c.get("scan", False),
                            "piege": c.get("piege", ""), "attendu": c.get("attendu", "exact"),
                            "pdf": c["pdf"], "image": images[0] if images else None,
                            "available": (ROOT / c["pdf"]).exists()})
    return out


@app.get("/v1/samples")
def samples() -> list[dict]:
    """Documents de démonstration (fictifs) : générés par `python -m multimodal.synth` et `synth_hard`."""
    return [{k: v for k, v in c.items() if k not in ("pdf", "image")} | {"has_image": bool(c["image"])}
            for c in _sample_cases()]


@app.get("/v1/samples/{sample_id}")
def sample_file(sample_id: str, format: str = "pdf") -> FileResponse:
    if not SAMPLE_ID.match(sample_id):
        raise HTTPException(status_code=404, detail="document inconnu")
    case = next((c for c in _sample_cases() if c["id"] == sample_id), None)
    rel = None if case is None else (case["image"] if format == "image" else case["pdf"])
    if rel is None or not (ROOT / rel).exists():
        raise HTTPException(status_code=404, detail="document absent : lancer python -m multimodal.synth")
    media = "application/pdf" if rel.endswith(".pdf") else "image/jpeg" if rel.endswith(".jpg") else "image/png"
    return FileResponse(ROOT / rel, media_type=media, filename=Path(rel).name)
