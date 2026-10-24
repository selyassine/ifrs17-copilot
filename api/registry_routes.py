"""Routes du registre (D-058) : connexion, dossiers, piste d'audit, tableau de bord, comptes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from api.security import ADMIN, ANALYSTE, VALIDEUR, Actor, current_actor, registry
from core.config import Settings, get_settings
from core.pdf import PdfUnavailable, find_browser, html_to_pdf
from core.registry import ROLES, SESSION_HOURS, STATUSES, AuthError, Registry

router = APIRouter()


# --------------------------------------------------------------------------- #
# Connexion
# --------------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=200)


@router.post("/v1/auth/login", tags=["comptes"])
def login(body: LoginRequest, reg: Registry = Depends(registry)) -> dict:
    try:
        token, user = reg.login(body.username, body.password)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"token": token, "expires_in": SESSION_HOURS * 3600, "user": user.public()}


@router.post("/v1/auth/logout", tags=["comptes"])
def logout(authorization: str | None = Header(default=None), reg: Registry = Depends(registry)) -> dict:
    if authorization and authorization.lower().startswith("bearer "):
        reg.logout(authorization[7:].strip())
    return {"ok": True}


@router.get("/v1/auth/me", tags=["comptes"])
def me(actor: Actor = Depends(current_actor), reg: Registry = Depends(registry)) -> dict:
    user = reg.get_user(actor.name) if actor.kind == "utilisateur" else None
    return user.public() if user else {"username": actor.name, "display_name": actor.name, "role": actor.role,
                                       "active": True, "last_login": ""}


@router.get("/v1/auth/status", tags=["comptes"])
def auth_status(reg: Registry = Depends(registry)) -> dict:
    """Sans authentification : le site sait s'il doit proposer la connexion (des comptes existent)."""
    return {"comptes": reg.has_users()}


# --------------------------------------------------------------------------- #
# Dossiers
# --------------------------------------------------------------------------- #
@router.get("/v1/cases", tags=["registre"])
def list_cases(status: str = Query("", description="statut"), source: str = "", q: str = "",
               limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0),
               _: Actor = Depends(ANALYSTE), reg: Registry = Depends(registry)) -> dict:
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"statut inconnu ; valeurs : {', '.join(STATUSES)}")
    rows, total = reg.list_cases(status=status, source=source, q=q, limit=limit, offset=offset)
    return {"total": total, "limit": limit, "offset": offset, "dossiers": rows}


@router.get("/v1/cases/{case_id}", tags=["registre"])
def case_detail(case_id: str, _: Actor = Depends(ANALYSTE), reg: Registry = Depends(registry)) -> dict:
    case = reg.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="dossier inconnu")
    return {**case, "evenements": reg.events(case_id)}


@router.get("/v1/cases/{case_id}/note", tags=["registre"], response_class=HTMLResponse)
def case_note(case_id: str, actor: Actor = Depends(ANALYSTE), reg: Registry = Depends(registry)) -> str:
    html = reg.note_html(case_id)
    if not html:
        raise HTTPException(status_code=404, detail="pas de note pour ce dossier")
    reg.add_event(case_id, actor.name, "note_consultee", {})
    return html


@router.get("/v1/cases/{case_id}/note.pdf", tags=["registre"], response_class=Response,
            responses={200: {"content": {"application/pdf": {}}}, 503: {"description": "aucun navigateur pour imprimer"}})
def case_note_pdf(case_id: str, actor: Actor = Depends(ANALYSTE), reg: Registry = Depends(registry),
                  settings: Settings = Depends(get_settings)) -> Response:
    """La note du dossier en PDF (D-065), imprimée par Edge, Chrome ou Chromium en mode headless."""
    html = reg.note_html(case_id)
    if not html:
        raise HTTPException(status_code=404, detail="pas de note pour ce dossier")
    try:
        pdf = html_to_pdf(html, find_browser(settings.note_pdf_browser))
    except PdfUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    case = reg.get_case(case_id) or {}
    groupe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(case.get("group_id") or "groupe"))
    reg.add_event(case_id, actor.name, "note_pdf_generee", {"octets": len(pdf)})
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="note_IFRS17_{groupe}_{case_id}.pdf"'})


class RejectRequest(BaseModel):
    comment: str = Field(min_length=3, max_length=1000)
    rejected_by: str | None = Field(default=None, description="valideur (n8n : adresse e-mail)")


@router.post("/v1/cases/{case_id}/reject", tags=["registre"])
def reject(case_id: str, body: RejectRequest, actor: Actor = Depends(VALIDEUR),
           reg: Registry = Depends(registry)) -> dict:
    case = reg.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="dossier inconnu")
    if case["status"] not in ("validation_humaine", "note_prete"):
        raise HTTPException(status_code=409, detail=f"dossier au statut « {case['status']} » : rejet impossible")
    reg.record_outcome(case_id, actor.name, "rejetee", action="validation_rejetee",
                       validated_by=body.rejected_by or actor.name, comment=body.comment)
    return reg.get_case(case_id)


class EventRequest(BaseModel):
    action: str = Field(pattern=r"^[a-z][a-z_]{2,39}$", description="ex. email_note_envoyee, archive")
    detail: dict = Field(default_factory=dict)


@router.post("/v1/cases/{case_id}/events", tags=["registre"])
def add_event(case_id: str, body: EventRequest, actor: Actor = Depends(ANALYSTE),
              reg: Registry = Depends(registry)) -> dict:
    """Trace d'une action faite hors de l'API (n8n : e-mail envoyé, dossier archivé…)."""
    if reg.get_case(case_id) is None:
        raise HTTPException(status_code=404, detail="dossier inconnu")
    return reg.add_event(case_id, actor.name, body.action, body.detail)


# --------------------------------------------------------------------------- #
# Tableau de bord, audit, comptes
# --------------------------------------------------------------------------- #
@router.get("/v1/dashboard", tags=["registre"])
def dashboard(days: int = Query(30, ge=7, le=365), _: Actor = Depends(ANALYSTE),
              reg: Registry = Depends(registry)) -> dict:
    return reg.dashboard(days)


@router.get("/v1/audit", tags=["audit"])
def audit(limit: int = Query(200, ge=1, le=2000), _: Actor = Depends(ADMIN),
          reg: Registry = Depends(registry)) -> dict:
    return {"evenements": reg.events(limit=limit)}


@router.get("/v1/audit/verify", tags=["audit"])
def audit_verify(_: Actor = Depends(ADMIN), reg: Registry = Depends(registry)) -> dict:
    return reg.verify_chain()


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=8, max_length=200)
    role: str = Field(pattern="^(" + "|".join(ROLES) + ")$")
    display_name: str = Field(default="", max_length=80)


class UserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern="^(" + "|".join(ROLES) + ")$")
    active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)


@router.get("/v1/users", tags=["comptes"])
def users(_: Actor = Depends(ADMIN), reg: Registry = Depends(registry)) -> list[dict]:
    return [u.public() for u in reg.list_users()]


@router.post("/v1/users", tags=["comptes"], status_code=201)
def create_user(body: UserCreate, actor: Actor = Depends(ADMIN), reg: Registry = Depends(registry)) -> dict:
    try:
        return reg.add_user(body.username, body.password, body.role, body.display_name, actor=actor.name).public()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/v1/users/{username}", tags=["comptes"])
def update_user(username: str, body: UserUpdate, actor: Actor = Depends(ADMIN),
                reg: Registry = Depends(registry)) -> dict:
    if username == actor.name and (body.active is False or (body.role and body.role != "admin")):
        raise HTTPException(status_code=400, detail="un administrateur ne peut pas se retirer ses propres droits")
    try:
        return reg.update_user(username, actor.name, role=body.role, active=body.active,
                               password=body.password).public()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
