"""Contrats de sortie de chaque agent (Pydantic v2).

Chaque agent renvoie un de ces objets ; l'orchestrateur refuse toute sortie
qui ne passe pas la validation. C'est ce qui rend le système multi-agent
testable : les frontières entre agents sont typées.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    """Base commune : refuse les champs inconnus (une hallucination de clé = erreur)."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# Routeur
# --------------------------------------------------------------------------- #
class Intent(str, Enum):
    NORM_QUESTION = "question_norme"        # question sur le texte d'IFRS 17
    DOCUMENT = "traitement_document"        # un fichier à lire puis à calculer
    CALCULATION = "calcul"                  # données déjà structurées, calcul seul
    OUT_OF_SCOPE = "hors_perimetre"         # tout le reste : refus poli


class AgentName(str, Enum):
    EXTRACTOR = "extracteur"
    RAG = "chercheur_rag"
    CALCULATOR = "calculateur"
    VERIFIER = "verificateur"
    WRITER = "redacteur"


class Plan(StrictModel):
    intent: Intent
    steps: list[AgentName] = Field(description="Agents à appeler, dans l'ordre")
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(max_length=300, description="Une phrase : pourquoi ce plan")

    @model_validator(mode="after")
    def _steps_match_intent(self) -> Plan:
        if self.intent == Intent.OUT_OF_SCOPE and self.steps:
            raise ValueError("une demande hors périmètre ne doit appeler aucun agent")
        if self.intent != Intent.OUT_OF_SCOPE and AgentName.VERIFIER not in self.steps:
            raise ValueError("tout plan non vide doit passer par le vérificateur")
        return self


# --------------------------------------------------------------------------- #
# Extracteur multimodal
# --------------------------------------------------------------------------- #
class PortfolioData(StrictModel):
    """Données d'un groupe de contrats, modèle général (BBA), une ligne par période.

    Conventions (documentées dans docs/decisions.md, D-006) :
    - montants positifs ; ``premiums`` = entrées, ``outflows`` = sinistres + frais ;
    - primes encaissées en début de période, sorties payées en fin de période ;
    - ``discount_rates`` : un taux plat, ou un taux spot annuel par fin de période.
    """

    group_id: str
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    unit_multiplier: Literal[1, 1_000, 1_000_000] = 1
    premiums: list[float]
    outflows: list[float]
    coverage_units: list[float]
    discount_rates: float | list[float] = 0.0
    risk_adjustment_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    future_service_adjustments: list[float] | None = Field(
        default=None,
        description="§44(c) : variation des flux liée au service futur, par période "
        "(positif = flux sortants plus élevés → le CSM baisse)",
    )
    field_confidence: dict[str, float] = Field(default_factory=dict)

    @field_validator("premiums", "outflows", "coverage_units")
    @classmethod
    def _non_negative(cls, v: list[float]) -> list[float]:
        if not v:
            raise ValueError("la liste ne peut pas être vide")
        if any(x < 0 for x in v):
            raise ValueError("les montants doivent être positifs ou nuls")
        return v

    @model_validator(mode="after")
    def _consistent_lengths(self) -> PortfolioData:
        n = len(self.premiums)
        lists = {
            "outflows": self.outflows,
            "coverage_units": self.coverage_units,
        }
        if isinstance(self.discount_rates, list):
            lists["discount_rates"] = self.discount_rates
        if self.future_service_adjustments is not None:
            lists["future_service_adjustments"] = self.future_service_adjustments
        for name, values in lists.items():
            if len(values) != n:
                raise ValueError(f"{name} a {len(values)} périodes, premiums en a {n}")
        if sum(self.coverage_units) <= 0:
            raise ValueError("la somme des unités de couverture doit être > 0")
        rates = self.discount_rates if isinstance(self.discount_rates, list) else [self.discount_rates]
        if any(r <= -1 for r in rates):
            raise ValueError("un taux d'actualisation doit être > -100 %")
        return self

    @property
    def n_periods(self) -> int:
        return len(self.premiums)


# --------------------------------------------------------------------------- #
# Chercheur RAG
# --------------------------------------------------------------------------- #
class Citation(StrictModel):
    paragraph_id: str = Field(description="ex. '44', 'B119', 'BC283'")
    doc: str
    quote: str = Field(max_length=400, description="Extrait court, jamais le texte entier")
    chunk_id: str


class GroundedAnswer(StrictModel):
    answer: str | None = Field(description="None si aucun passage ne répond")
    citations: list[Citation] = Field(default_factory=list)
    refused: bool = False
    refusal_reason: str | None = None

    @model_validator(mode="after")
    def _answer_needs_citation(self) -> GroundedAnswer:
        if self.answer and not self.refused and not self.citations:
            raise ValueError("une réponse sans citation est interdite")
        if self.refused and not self.refusal_reason:
            raise ValueError("un refus doit être motivé")
        return self


# --------------------------------------------------------------------------- #
# Calculateur
# --------------------------------------------------------------------------- #
class CsmPeriod(StrictModel):
    period: int
    opening: float
    interest_accretion: float          # §44(b)
    future_service_adjustment: float   # §44(c)
    release: float                     # §44(e), B119
    closing: float
    loss_component_change: float = 0.0  # §48 : excédent non absorbé par le CSM


class CsmResult(StrictModel):
    group_id: str
    pv_inflows: float
    pv_outflows: float
    risk_adjustment: float
    fulfilment_cash_flows: float       # PV sorties - PV entrées + RA (positif = onéreux)
    initial_csm: float                 # §38
    initial_loss_component: float      # §47
    onerous: bool
    rollforward: list[CsmPeriod]
    total_release: float


# --------------------------------------------------------------------------- #
# Vérificateur
# --------------------------------------------------------------------------- #
class VerdictStatus(str, Enum):
    OK = "ok"
    FIX = "a_corriger"
    HUMAN = "validation_humaine"


class Issue(StrictModel):
    agent: AgentName
    kind: Literal[
        "citation_invalide", "chiffre_incoherent", "champ_manquant",
        "injection", "hors_perimetre", "non_soutenu", "hors_portee", "incomplet", "hors_sujet",
        "autre",
    ]
    detail: str


class Verdict(StrictModel):
    status: VerdictStatus
    issues: list[Issue] = Field(default_factory=list)

    @model_validator(mode="after")
    def _issues_when_not_ok(self) -> Verdict:
        if self.status != VerdictStatus.OK and not self.issues:
            raise ValueError("un verdict négatif doit lister au moins un problème")
        return self


# --------------------------------------------------------------------------- #
# État partagé tenu par l'orchestrateur
# --------------------------------------------------------------------------- #
class CaseState(StrictModel):
    case_id: str
    request: str
    attachments: list[str] = Field(default_factory=list)
    plan: Plan | None = None
    portfolio: PortfolioData | None = None
    answer: GroundedAnswer | None = None
    csm: CsmResult | None = None
    verdict: Verdict | None = None
    correction_rounds: int = Field(default=0, ge=0, le=2)
    final_note: str | None = None
