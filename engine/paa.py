"""Méthode d'affectation des primes (PAA, §53 à §59) pour un groupe de contrats courts (D-043).

Passif au titre de la couverture restante (LRC, §55) :
    primes reçues − frais d'acquisition payés + frais d'acquisition amortis − produits reconnus
(si l'option §59(a) est retenue, les frais d'acquisition sont passés en charge à leur paiement et
n'entrent pas dans la LRC).

Produits des activités d'assurance (B126) : la prime est répartie selon l'écoulement du temps
(ici au prorata des mois de couverture écoulés).

Passif au titre des sinistres survenus (LIC, §59(b)) : estimation du sinistre + ajustement pour
risque, sans actualisation quand le règlement intervient dans l'année. Au règlement, l'écart entre
le montant payé et le montant provisionné va en résultat (charges des activités d'assurance).

Contrôle des contrats déficitaires (§57-58) non modélisé : il suppose une projection des flux
d'exécution, fournie par le modèle général (engine/bba.py). Le LLM n'exécute jamais ces calculs.
"""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import Field, model_validator

from agents.schemas import StrictModel


class PaaClaim(StrictModel):
    occurred: date
    estimate: float = Field(ge=0, description="Provision du sinistre (meilleure estimation)")
    risk_adjustment: float = Field(default=0.0, ge=0)
    paid_on: date | None = None
    paid_amount: float | None = Field(default=None, ge=0)


class PaaContract(StrictModel):
    group_id: str = "PAA-1"
    premium: float = Field(ge=0)
    coverage_start: date
    coverage_months: int = Field(ge=1, le=12, description="La PAA vise d'abord les couvertures d'un an au plus (§53(b))")
    acquisition_costs: float = Field(default=0.0, ge=0)
    expense_acquisition_costs: bool = Field(default=True, description="Option §59(a) : frais d'acquisition en charge")
    claims: list[PaaClaim] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> PaaContract:
        for c in self.claims:
            if (c.paid_on is None) != (c.paid_amount is None):
                raise ValueError("un règlement a une date et un montant")
        return self


class PaaPosition(StrictModel):
    at: date
    months_elapsed: int
    lrc: float                      # passif au titre de la couverture restante
    lic: float                      # passif au titre des sinistres survenus
    revenue_to_date: float          # produits des activités d'assurance cumulés (B126)
    acquisition_expense_to_date: float
    claims_expense_to_date: float   # sinistres + RA comptabilisés, écarts de règlement compris
    result_to_date: float


def _add_months(d: date, k: int) -> date:
    y, m = divmod(d.month - 1 + k, 12)
    year, month = d.year + y, m + 1
    last = (date(year + month // 12, month % 12 + 1, 1) - date(year, month, 1)).days
    return date(year, month, min(d.day, last))


def months_elapsed(start: date, at: date, cap: int) -> int:
    """Mois de couverture entièrement écoulés à la date ``at`` incluse, plafonnés à la durée."""
    k = 0
    while k < cap and _add_months(start, k + 1) <= at + timedelta(days=1):
        k += 1
    return k


def position(c: PaaContract, at: date) -> PaaPosition:
    """Bilan et résultat cumulé du groupe à la date ``at``."""
    received = c.premium if at >= c.coverage_start else 0.0
    m = months_elapsed(c.coverage_start, at, c.coverage_months)
    share = m / c.coverage_months
    revenue = c.premium * share
    iacf = c.acquisition_costs if at >= c.coverage_start else 0.0
    if c.expense_acquisition_costs:
        acq_expense, lrc = iacf, received - revenue
    else:
        amortised = iacf * share
        acq_expense, lrc = amortised, received - iacf + amortised - revenue

    lic, claims_expense = 0.0, 0.0
    for cl in c.claims:
        if cl.occurred > at:
            continue
        if cl.paid_on is not None and cl.paid_on <= at:
            claims_expense += cl.paid_amount       # provision + RA reprises, écart de règlement en charge
        else:
            lic += cl.estimate + cl.risk_adjustment
            claims_expense += cl.estimate + cl.risk_adjustment
    return PaaPosition(at=at, months_elapsed=m, lrc=lrc, lic=lic, revenue_to_date=revenue,
                       acquisition_expense_to_date=acq_expense, claims_expense_to_date=claims_expense,
                       result_to_date=revenue - acq_expense - claims_expense)
