"""API FastAPI appelée par n8n.

    uvicorn api.main:app --reload --port 8000
    → documentation interactive : http://localhost:8000/docs

Endpoints S1 : santé, routage, calcul du CSM. Les agents RAG, extraction,
vérification et rédaction s'ajoutent en S2-S3 derrière /v1/case.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from agents.router import route_heuristic, route_llm
from agents.schemas import CsmResult, Plan, PortfolioData
from core.config import Settings, get_settings
from core.tracing import traced
from engine.csm import compute_csm

VERSION = "0.1.0"

app = FastAPI(
    title="IFRS 17 Copilot",
    version=VERSION,
    description="Services IA appelés par les workflows n8n.",
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
