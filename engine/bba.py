"""Modèle général (BBA) sur plusieurs années, comme dans un cours IFRS 17 (D-042).

Le moteur v0 (engine/csm.py) calcule la CSM à l'origine et son écoulement prévu. Ce module suit
le groupe année après année avec les événements réels :

- BEL réévalué chaque année au taux courant ; l'effet du changement de taux va en OCI (option
  OCI, §88(b), B131) ou en résultat (option P&L) ;
- ajustement pour risque (RA) : variation au titre des services futurs (ajuste la CSM, B96(d))
  puis libération selon les unités de couverture (simplification du cours) ;
- révision des sinistres futurs : ajuste la CSM au taux bloqué de l'origine (B96(b), B72(c)) ;
  l'écart entre taux courant et taux bloqué est financier ;
- écarts d'expérience (sinistres réels ≠ attendus) : en résultat, jamais en CSM (B97(c)) ;
- groupe devenu déficitaire : composante de perte (§48), reprise prioritaire (§50(b)) ;
- compte de résultat IFRS 17 : produits des activités d'assurance (sinistres attendus + RA libéré
  + CSM libérée, B124), charges (sinistres réels, pertes), résultat financier d'assurance, OCI.

Conventions (celles de l'exemple du cours) : une prime unique encaissée à l'origine, sinistres
payés en fin d'année, courbe de taux plate à chaque date (un taux par date), pas de frais
d'acquisition. Le LLM n'exécute jamais ces calculs (D-005).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from agents.schemas import StrictModel


class ClaimRevision(StrictModel):
    at_end_of_year: int = Field(ge=1, description="Révision connue à la clôture de l'année t (1 = première année)")
    expected_claims: list[float] = Field(description="Sinistres attendus de toutes les années, après révision")


class BbaScenario(StrictModel):
    group_id: str = "G1"
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    single_premium: float = Field(ge=0, description="Prime unique encaissée à l'origine")
    expected_claims: list[float] = Field(min_length=1, description="Sinistres attendus à l'origine, payés en fin d'année")
    actual_claims: list[float] | None = Field(default=None, description="Sinistres réels de chaque année (défaut : attendus)")
    rates: list[float] = Field(description="Taux d'actualisation à l'origine puis à chaque clôture (n + 1 valeurs)")
    ra_initial: float = Field(ge=0, description="Ajustement pour risque à l'origine")
    ra_changes: list[float] | None = Field(default=None, description="Variation du RA au titre des services futurs, par année")
    claim_revisions: list[ClaimRevision] = Field(default_factory=list)
    coverage_units: list[float] | None = Field(default=None, description="Unités de couverture par année (défaut : 1 par an)")
    finance_option: Literal["OCI", "PL"] = "OCI"

    @model_validator(mode="after")
    def _lengths(self) -> BbaScenario:
        n = len(self.expected_claims)
        if len(self.rates) != n + 1:
            raise ValueError(f"rates : {n + 1} valeurs attendues (origine + {n} clôtures)")
        for name in ("actual_claims", "ra_changes", "coverage_units"):
            v = getattr(self, name)
            if v is not None and len(v) != n:
                raise ValueError(f"{name} : {n} valeurs attendues")
        for r in self.claim_revisions:
            if len(r.expected_claims) != n or r.at_end_of_year > n:
                raise ValueError("claim_revisions : une valeur par année, révision au plus tard à la dernière clôture")
        return self


class BbaYear(StrictModel):
    year: int
    rate_open: float
    rate_close: float
    # BEL (meilleure estimation des sinistres futurs)
    bel_open: float
    bel_interest: float              # BEL d'ouverture × taux d'ouverture
    bel_claims_expected: float       # sinistres attendus de l'année (sortie du BEL)
    bel_estimate_change: float       # révision des sinistres futurs, au taux d'ouverture
    bel_rate_effect: float           # changement de taux sur les flux futurs
    bel_close: float
    bel_locked_close: float          # même flux au taux bloqué de l'origine
    # ajustement pour risque
    ra_open: float
    ra_future_change: float
    ra_release: float
    ra_close: float
    # CSM
    csm_open: float
    csm_accretion: float             # au taux bloqué (§44(b))
    csm_adjustment: float            # services futurs au taux bloqué (§44(c), B96)
    coverage_ratio: float            # CU de l'année / CU restantes
    csm_release: float               # §44(e), B119
    csm_close: float
    loss_component_change: float     # perte (+) ou reprise (−) de l'année (§48, §50)
    loss_component_close: float
    # compte de résultat et OCI
    insurance_revenue: float         # sinistres attendus + RA libéré + CSM libérée
    insurance_service_expenses: float  # sinistres réels + pertes (− reprises)
    experience_adjustment: float     # sinistres réels − attendus (en résultat, B97(c))
    insurance_service_result: float
    insurance_finance_expense: float   # en résultat (négatif = charge)
    oci: float                       # autres éléments du résultat global de l'année
    profit: float                    # résultat des activités d'assurance + résultat financier d'assurance


class BbaResult(StrictModel):
    group_id: str
    finance_option: str
    pv_premiums: float
    bel_initial: float
    ra_initial: float
    fulfilment_cash_flows: float
    csm_initial: float
    loss_initial: float
    years: list[BbaYear]
    total_insurance_revenue: float
    total_profit: float
    total_oci: float


def _pv(flows: list[float], start: int, rate: float) -> float:
    """Valeur à la fin de l'année ``start`` des flux des années start+1… (payés en fin d'année)."""
    return sum(f / (1 + rate) ** (k - start) for k, f in enumerate(flows, start=1) if k > start)


def roll_forward_bba(s: BbaScenario) -> BbaResult:
    n = len(s.expected_claims)
    r0 = s.rates[0]
    actual = s.actual_claims or list(s.expected_claims)
    ra_changes = s.ra_changes or [0.0] * n
    cu = s.coverage_units or [1.0] * n
    revisions = {r.at_end_of_year: list(r.expected_claims) for r in s.claim_revisions}

    est = list(s.expected_claims)                  # estimation en vigueur
    bel = _pv(est, 0, r0)
    fcf = bel + s.ra_initial - s.single_premium    # > 0 : déficitaire (§47)
    csm, lc = max(-fcf, 0.0), max(fcf, 0.0)
    ra = s.ra_initial
    oci_reserve = 0.0                              # BEL au taux bloqué − BEL au taux courant (cumul)
    years: list[BbaYear] = []

    for t in range(1, n + 1):
        r_open, r_close = s.rates[t - 1], s.rates[t]
        bel_open, bel_locked_open = bel, _pv(est, t - 1, r0)
        interest = bel_open * r_open
        expected_t = est[t - 1]

        new_est = revisions.get(t, est)
        estimate_change = _pv(new_est, t, r_open) - _pv(est, t, r_open)
        change_locked = _pv(new_est, t, r0) - _pv(est, t, r0)
        bel_close = _pv(new_est, t, r_close)
        rate_effect = bel_close - (bel_open + interest - expected_t + estimate_change)
        bel_locked_close = _pv(new_est, t, r0)

        # RA : variation au titre des services futurs, puis libération selon les unités de couverture
        ra_open = ra
        ra_after = ra_open + ra_changes[t - 1]
        ratio = cu[t - 1] / sum(cu[t - 1:]) if sum(cu[t - 1:]) > 0 else 1.0
        ra_release = ra_after * ratio
        ra = ra_after - ra_release

        # CSM : capitalisation au taux bloqué, ajustement (services futurs), libération
        csm_open = csm
        accretion = csm_open * r0
        adjustment = -(change_locked + ra_changes[t - 1])  # hausse des flux futurs = baisse de la CSM
        lc_change = 0.0
        after = csm_open + accretion
        if adjustment >= 0:                        # favorable : reprise de la perte d'abord (§50(b))
            reversal = min(lc, adjustment)
            lc -= reversal
            lc_change = -reversal
            after += adjustment - reversal
        else:                                      # défavorable : au-delà de la CSM, perte (§48)
            after += adjustment
            if after < 0:
                lc_change = -after
                lc += lc_change
                after = 0.0
        csm_release = after * ratio
        csm = after - csm_release

        # compte de résultat
        revenue = expected_t + ra_release + csm_release
        experience = actual[t - 1] - expected_t
        expenses = actual[t - 1] + lc_change
        service_result = revenue - expenses
        locked_interest = bel_locked_open * r0
        total_finance = interest + rate_effect + (estimate_change - change_locked) + accretion
        if s.finance_option == "OCI":
            finance_pl = -(locked_interest + accretion)
            new_reserve = bel_locked_close - bel_close
            oci = new_reserve - oci_reserve
            oci_reserve = new_reserve
        else:
            finance_pl, oci = -total_finance, 0.0

        years.append(BbaYear(
            year=t, rate_open=r_open, rate_close=r_close,
            bel_open=bel_open, bel_interest=interest, bel_claims_expected=-expected_t,
            bel_estimate_change=estimate_change, bel_rate_effect=rate_effect, bel_close=bel_close,
            bel_locked_close=bel_locked_close,
            ra_open=ra_open, ra_future_change=ra_changes[t - 1], ra_release=ra_release, ra_close=ra,
            csm_open=csm_open, csm_accretion=accretion, csm_adjustment=adjustment, coverage_ratio=ratio,
            csm_release=csm_release, csm_close=csm, loss_component_change=lc_change, loss_component_close=lc,
            insurance_revenue=revenue, insurance_service_expenses=expenses, experience_adjustment=experience,
            insurance_service_result=service_result, insurance_finance_expense=finance_pl, oci=oci,
            profit=service_result + finance_pl,
        ))
        est, bel = new_est, bel_close

    return BbaResult(
        group_id=s.group_id, finance_option=s.finance_option, pv_premiums=s.single_premium,
        bel_initial=_pv(s.expected_claims, 0, r0), ra_initial=s.ra_initial, fulfilment_cash_flows=fcf,
        csm_initial=max(-fcf, 0.0), loss_initial=max(fcf, 0.0), years=years,
        total_insurance_revenue=sum(y.insurance_revenue for y in years),
        total_profit=sum(y.profit for y in years) - max(fcf, 0.0),
        total_oci=sum(y.oci for y in years),
    )
