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
class Intent(str, Enum):  # noqa: UP042 (str() et JSON inchangés)
    NORM_QUESTION = "question_norme"        # question sur le texte d'IFRS 17
    DOCUMENT = "traitement_document"        # un fichier à lire puis à calculer
    CALCULATION = "calcul"                  # données déjà structurées, calcul seul
    OUT_OF_SCOPE = "hors_perimetre"         # tout le reste : refus poli


class AgentName(str, Enum):  # noqa: UP042 (str() et JSON inchangés)
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
    - ``discount_rates`` : un taux plat, ou un taux spot annuel par fin de période ;
    - ``recoveries`` : recouvrements (récupération, subrogation), entrées de trésorerie en fin de période
      (IFRS 17, B65 k), facultatifs (D-071) ;
    - ``acquisition_costs`` : flux de trésorerie liés aux frais d'acquisition (B65 e, §28A-28F), payés en
      début de période, facultatifs (D-075) ;
    - ``coverage_months`` et ``line_of_business`` : durée de couverture des contrats (éligibilité à la PAA,
      §53, D-073) et branche (choix de la volatilité calibrée du RA, D-074), facultatives ;
    - ``declared_cv`` et ``declared_confidence`` : volatilité et niveau de confiance que le document annonce pour
      son ajustement pour risque, facultatifs (D-082).
    """

    group_id: str
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    unit_multiplier: Literal[1, 1_000, 1_000_000] = 1
    premiums: list[float]
    outflows: list[float]
    coverage_units: list[float]
    discount_rates: float | list[float] = 0.0
    risk_adjustment_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    recoveries: list[float] | None = Field(
        default=None,
        description="B65 k) : recouvrements attendus (récupération, subrogation) par période, encaissés en fin de "
        "période ; entrées de trésorerie qui viennent en déduction des sinistres",
    )
    acquisition_costs: list[float] | None = Field(
        default=None,
        description="B65 e) : frais d'acquisition (commissions, coûts de souscription) par période, payés en "
        "début de période ; sorties de trésorerie qui réduisent la CSM (§28A-28F)",
    )
    coverage_months: int | None = Field(
        default=None, ge=1, le=1200,
        description="Durée de couverture de chaque contrat, en mois (12 = contrats annuels) ; ≤ 12 : PAA possible (§53(b))",
    )
    line_of_business: str | None = Field(
        default=None, max_length=80,
        description="Branche d'assurance telle qu'écrite (ex. « Accidents du travail ») : choix de la volatilité du RA",
    )
    declared_cv: float | None = Field(
        default=None, gt=0.0, le=3.0,
        description="Coefficient de variation des sorties (volatilité) déclaré par le document pour son ajustement pour "
        "risque, en décimal (12 % → 0.12) ; comparé à la volatilité du registre des hypothèses (D-082)",
    )
    declared_confidence: float | None = Field(
        default=None, ge=0.5, lt=1.0,
        description="Niveau de confiance de l'ajustement pour risque déclaré par le document (§119), en décimal "
        "(75 % → 0.75) ; vérifié par le code avec la volatilité déclarée (D-082)",
    )
    future_service_adjustments: list[float] | None = Field(
        default=None,
        description="§44(c) : variation des flux liée au service futur, par période "
        "(positif = flux sortants plus élevés → le CSM baisse)",
    )
    field_confidence: dict[str, float] = Field(default_factory=dict)

    @field_validator("recoveries")
    @classmethod
    def _recoveries_non_negative(cls, v: list[float] | None) -> list[float] | None:
        if v is not None and any(x < 0 for x in v):
            raise ValueError("les recouvrements sont des entrées : montants positifs ou nuls")
        return v

    @field_validator("acquisition_costs")
    @classmethod
    def _acquisition_non_negative(cls, v: list[float] | None) -> list[float] | None:
        if v is not None and any(x < 0 for x in v):
            raise ValueError("les frais d'acquisition sont des sorties : montants positifs ou nuls")
        return v

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
        if self.recoveries is not None:
            lists["recoveries"] = self.recoveries
        if self.acquisition_costs is not None:
            lists["acquisition_costs"] = self.acquisition_costs
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


class TriangleData(StrictModel):
    """Dossier de sinistres survenus (LIC, D-083) : triangle de paiements par année de survenance.

    Conventions : la ligne 0 est la survenance la plus ancienne ; la ligne i a n − i valeurs (triangle en
    escalier) ; montants recopiés tels qu'affichés (``unit_multiplier`` pour l'unité) ; paiements futurs en fin
    d'année calendaire ; ``cumulative`` = False si le document donne des paiements de l'année (incréments), que
    le code cumule.
    """

    portfolio_id: str = Field(min_length=1, max_length=120, description="portefeuille ou groupe tel qu'écrit")
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    unit_multiplier: Literal[1, 1_000, 1_000_000] = 1
    line_of_business: str | None = Field(default=None, max_length=80)
    valuation_date: str | None = Field(default=None, max_length=40, description="date de clôture telle qu'écrite")
    origin_years: list[str] = Field(description="années (ou périodes) de survenance, de la plus ancienne à la plus récente")
    premiums: list[float] | None = Field(default=None, description="prime de chaque année de survenance (facultatif)")
    triangle: list[list[float]] = Field(description="une ligne par année de survenance, valeurs par retard")
    cumulative: bool = True
    discount_rates: float | list[float] = Field(default=0.0, description="taux spot par échéance (1 an, 2 ans…) ou un taux")
    confidence_level: float | None = Field(default=None, ge=0.5, lt=1.0, description="quantile du RA demandé")
    declared_cv: float | None = Field(default=None, gt=0.0, le=3.0, description="volatilité imposée par le document")
    tail_factor: float = Field(default=1.0, ge=1.0, le=3.0, description="facteur de queue (1 = aucun)")

    @model_validator(mode="after")
    def _staircase(self) -> TriangleData:
        n = len(self.triangle)
        if n < 3:
            raise ValueError("triangle trop petit : au moins 3 années de survenance")
        if len(self.origin_years) != n:
            raise ValueError(f"origin_years a {len(self.origin_years)} années, le triangle a {n} lignes")
        if self.premiums is not None and len(self.premiums) != n:
            raise ValueError(f"premiums a {len(self.premiums)} valeurs, le triangle a {n} lignes")
        for i, row in enumerate(self.triangle):
            if len(row) != n - i:
                raise ValueError(f"ligne {i + 1} ({self.origin_years[i]}) : {len(row)} valeurs au lieu de {n - i} "
                                 "(triangle en escalier attendu)")
        rates = self.discount_rates if isinstance(self.discount_rates, list) else [self.discount_rates]
        if any(r <= -1 for r in rates):
            raise ValueError("un taux d'actualisation doit être > -100 %")
        return self

    def cumulative_triangle(self) -> list[list[float]]:
        if self.cumulative:
            return [list(r) for r in self.triangle]
        out = []
        for row in self.triangle:
            acc, cum = 0.0, []
            for x in row:
                acc += x
                cum.append(acc)
            out.append(cum)
        return out

    @property
    def n_years(self) -> int:
        return len(self.triangle)


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
    pv_inflows: float                  # primes + recouvrements (B65 k)
    pv_outflows: float
    pv_recoveries: float = 0.0         # dont recouvrements (D-071)
    pv_acquisition: float = 0.0        # frais d'acquisition, payés en début de période (B65 e, D-075)
    risk_adjustment: float
    fulfilment_cash_flows: float       # PV sorties + PV frais d'acquisition + RA − PV entrées (positif = onéreux)
    initial_csm: float                 # §38
    initial_loss_component: float      # §47
    onerous: bool
    rollforward: list[CsmPeriod]
    total_release: float


# --------------------------------------------------------------------------- #
# Vérificateur
# --------------------------------------------------------------------------- #
class VerdictStatus(str, Enum):  # noqa: UP042 (str() et JSON inchangés)
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


OPTIONAL_FIELDS = ("recoveries", "acquisition_costs", "coverage_months", "line_of_business", "declared_cv",
                   "declared_confidence")


def truth_dict(p: PortfolioData) -> dict:
    """Vérité d'un cas de test : sans les champs de confiance ni les champs facultatifs absents
    (les jeux gelés avant D-071 restent identiques à l'octet près)."""
    d = p.model_dump(exclude={"field_confidence", "future_service_adjustments"})
    for k in OPTIONAL_FIELDS:
        if d.get(k) is None:
            d.pop(k, None)
    return d
