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


# --------------------------------------------------------------------------- #
# PAA dans le flux des dossiers (D-073) : à partir des données d'un groupe (PortfolioData)
# --------------------------------------------------------------------------- #
from dataclasses import dataclass as _dataclass  # noqa: E402

from agents.schemas import CsmResult, PortfolioData  # noqa: E402

PAA_MAX_MONTHS = 12


def coverage_months(p: PortfolioData) -> tuple[int, str]:
    """Durée de couverture des contrats : lue dans le document, sinon déduite des unités de couverture
    (périodes annuelles qui portent encore de la couverture)."""
    if p.coverage_months is not None:
        return p.coverage_months, "indiquée dans le document"
    covered = [t for t, cu in enumerate(p.coverage_units) if cu > 0]
    months = 12 * (covered[-1] + 1) if covered else 12 * p.n_periods
    return months, "déduite des unités de couverture (dernière période couverte)"


@_dataclass
class PaaYear:
    period: int
    revenue: float               # produits des activités d'assurance (B126)
    acquisition_expense: float   # frais d'acquisition passés en charges (amortis ou option §59(a))
    claims_incurred: float       # sinistres survenus : LIC initial (valeur actuelle + RA), année de couverture
    ra_release: float            # libération de l'ajustement pour risque du LIC
    service_result: float
    finance_expense: float       # désactualisation du LIC
    lrc_closing: float
    lic_closing: float


@_dataclass
class PaaView:
    eligible: bool
    months: int
    months_source: str
    lrc_initial: float           # §55(a) : primes reçues − frais d'acquisition payés (sauf option §59(a))
    onerous_loss: float          # §57-58 : flux d'exécution de la couverture restante − LRC (≥ 0)
    lic_initial: float           # sinistres de l'année de couverture : valeur actuelle + RA (§59(b) non retenu)
    discounted: bool             # règlements au-delà de 12 mois → LIC actualisé
    years: list[PaaYear]
    bba_service_results: list[float]
    total_paa: float
    total_bba: float
    first_year_gap: float        # écart PAA − modèle général sur le résultat de l'année de couverture


def paa_view(p: PortfolioData, r: CsmResult, bba_service_results: list[float] | None,
             expense_acquisition: bool = False) -> PaaView | None:
    """Mesure PAA d'un groupe dont la couverture tient dans la première période (≤ 12 mois, §53(b)).

    Conventions (les mêmes que le modèle général, pour que la comparaison mesure la méthode et non les
    hypothèses) : primes et frais d'acquisition au début de la couverture, sinistres survenus pendant
    l'année de couverture et réglés selon la cadence du document, LIC actualisé avec la même courbe et
    chargé du même pourcentage de RA. Scénario central : réalisé = attendu.
    """
    from engine.csm import acquisition_costs, discount_factors, recoveries

    months, source = coverage_months(p)
    eligible = months <= PAA_MAX_MONTHS
    if not eligible:
        return PaaView(eligible=False, months=months, months_source=source, lrc_initial=0.0, onerous_loss=0.0,
                       lic_initial=0.0, discounted=False, years=[], bba_service_results=[], total_paa=0.0,
                       total_bba=0.0, first_year_gap=0.0)
    n = p.n_periods
    df = discount_factors(p.discount_rates, n)
    rec, acq = recoveries(p), acquisition_costs(p)
    premiums, acq_total = sum(p.premiums), sum(acq)
    lrc0 = premiums - (0.0 if expense_acquisition else acq_total)
    k = p.risk_adjustment_pct

    def pv_net_at(t: int) -> float:              # sinistres restants nets des recouvrements, valeur en t
        return sum((p.outflows[s] - rec[s]) * df[s + 1] for s in range(t, n)) / df[t]

    def pv_out_at(t: int) -> float:
        return sum(p.outflows[s] * df[s + 1] for s in range(t, n)) / df[t]

    lic0 = pv_net_at(0) + k * pv_out_at(0)
    loss = max(r.fulfilment_cash_flows, 0.0)     # §58 : même quantité que la perte du modèle général
    years: list[PaaYear] = []
    lic = lic0
    ra = k * pv_out_at(0)
    for t in range(1, n + 1):
        f = df[t - 1] / df[t] - 1.0
        lic_c = pv_net_at(t) + k * pv_out_at(t)
        ra_c = k * pv_out_at(t)
        ra_rel = ra * (1 + f) - ra_c
        finance = lic * f
        if t == 1:
            revenue, acq_exp, incurred = premiums, acq_total, lic0
        else:
            revenue, acq_exp, incurred = 0.0, 0.0, 0.0
        # le RA du LIC est libéré au fil des règlements (gain des services passés) ; la perte d'un groupe
        # déficitaire (§58) est reprise dans l'année, la couverture s'achevant avec elle
        result = revenue - acq_exp - incurred + ra_rel
        years.append(PaaYear(period=t, revenue=revenue, acquisition_expense=acq_exp, claims_incurred=incurred,
                             ra_release=ra_rel, service_result=result, finance_expense=finance,
                             lrc_closing=0.0, lic_closing=lic_c))
        lic, ra = lic_c, ra_c
    bba = list(bba_service_results or [])
    total_paa = sum(y.service_result for y in years)
    return PaaView(eligible=True, months=months, months_source=source, lrc_initial=lrc0, onerous_loss=loss,
                   lic_initial=lic0, discounted=any(p.outflows[s] > 0 for s in range(1, n)), years=years,
                   bba_service_results=bba, total_paa=total_paa, total_bba=sum(bba),
                   first_year_gap=(years[0].service_result - bba[0]) if bba else 0.0)
