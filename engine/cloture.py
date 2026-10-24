"""Première clôture d'un groupe (modèle général) : réalisé de l'année et révision des estimations (D-076).

À la comptabilisation initiale, la note projette le scénario central. Un an plus tard, l'entité connaît le
réalisé de la première période et révise ses estimations. Ce module produit l'analyse des écarts de la
première clôture, dans les conventions du moteur (``engine/csm.py``, ``engine/analysis.py``) :

- **écarts d'expérience** (réalisé − attendu de la période : primes, sinistres, recouvrements, frais
  d'acquisition) : en résultat des services d'assurance, jamais dans la CSM (B97(c)) ;
- **révision des flux futurs**, mesurée au taux bloqué (B72(c)) :
  * s'il reste de la couverture après la période, elle concerne les services futurs : elle ajuste la CSM
    (§44(c), B96(b)) ; au-delà de la CSM, elle devient une perte (§48) ; une révision favorable reprend
    d'abord la composante de perte (§50(b)) ;
  * sinon (couverture achevée, ex. contrats annuels), elle concerne des sinistres déjà survenus : services
    passés, en charges des services d'assurance (B97(b)) ;
  * l'ajustement pour risque suit la même règle (B96(d)) ;
- **effet du changement de taux** (taux courant − taux bloqué) : en charges financières d'assurance, sans
  option OCI (§87, §88).

Le passif de clôture se rapproche exactement : ouverture + primes − frais d'acquisition − sinistres
+ recouvrements + charges financières − résultat des services d'assurance (vérifié par les tests).

Simplification assumée (écrite dans la note) : toute révision des flux futurs est rattachée aux services
futurs dès qu'il reste de la couverture ; une entité distinguerait, flux par flux, sinistres survenus et à
survenir. Première clôture seulement ; les suivantes repartent de cet état.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from agents.schemas import CsmResult, PortfolioData, StrictModel
from engine.analysis import projection
from engine.csm import acquisition_costs, compute_csm, discount_factors, recoveries


class ClosingInput(StrictModel):
    """Réalisé de la première période et estimations révisées à la clôture."""
    actual_premium: float | None = Field(default=None, ge=0, description="Primes encaissées sur la période (défaut : attendu)")
    actual_outflow: float = Field(ge=0, description="Sinistres et frais payés sur la période")
    actual_recovery: float | None = Field(default=None, ge=0, description="Recouvrements encaissés (défaut : attendu)")
    actual_acquisition: float | None = Field(default=None, ge=0, description="Frais d'acquisition payés (défaut : attendu)")
    revised_outflows: list[float] | None = Field(default=None, description="Sinistres et frais attendus des périodes "
                                                 "2 à n, révisés à la clôture (défaut : estimations initiales)")
    revised_recoveries: list[float] | None = None
    closing_rates: list[float] | float | None = Field(default=None, description="Courbe spot à la clôture pour les "
                                                      "périodes 2 à n (défaut : taux à terme de la courbe initiale)")
    as_of: str = Field(default="", max_length=40, description="Date de clôture (texte libre, ex. 31/12/1997)")

    @model_validator(mode="after")
    def _check(self) -> ClosingInput:
        for name in ("revised_outflows", "revised_recoveries"):
            v = getattr(self, name)
            if v is not None and any(x < 0 for x in v):
                raise ValueError(f"{name} : montants positifs ou nuls")
        return self


class ClosingResult(StrictModel):
    group_id: str
    as_of: str
    future_coverage: bool              # reste-t-il de la couverture après la période ?
    locked_forward: float              # taux à terme bloqué de la période 1
    # attendu (scénario central) et réalisé de la période
    expected_premium: float
    actual_premium: float
    expected_outflow: float
    actual_outflow: float
    expected_recovery: float
    actual_recovery: float
    expected_acquisition: float
    actual_acquisition: float
    experience_adjustment: float       # effet sur le résultat (+ favorable) des écarts de la période, B97(c)
    # révision des flux futurs, au taux bloqué
    future_flows_change: float         # BEL : + = flux nets sortants plus élevés
    ra_future_change: float
    csm_adjustment: float              # appliqué à la CSM (− = baisse)
    new_loss: float                    # part non absorbée par la CSM (§48)
    loss_reversal: float               # reprise de composante de perte (§50(b))
    past_service_change: float         # en charges si la couverture est achevée (B97(b))
    rate_effect: float                 # BEL + RA : taux courant − taux bloqué (charges financières)
    # bilan d'ouverture et de clôture
    opening_liability: float
    bel_close: float
    ra_close: float
    csm_open: float
    csm_accretion: float
    csm_release: float
    csm_close: float
    loss_component_close: float
    closing_liability: float
    expected_closing_liability: float
    # compte de résultat de la période
    insurance_revenue: float
    insurance_service_expense: float
    insurance_service_result: float
    insurance_finance_expense: float
    expected_service_result: float
    profit: float
    reconciliation_gap: float          # doit être nul


def _pv(flows: list[float], df_from_1: list[float]) -> float:
    """Valeur en fin de période 1 de flux payés en fin des périodes 2…n (df_from_1[k] : facteur de la période k+2)."""
    return sum(x * d for x, d in zip(flows, df_from_1, strict=True))


def close_first_period(p: PortfolioData, c: ClosingInput, r: CsmResult | None = None) -> ClosingResult:
    r = r or compute_csm(p)
    n = p.n_periods
    if n < 2:
        raise ValueError("une clôture suppose au moins deux périodes de flux")
    if p.future_service_adjustments and any(abs(x) > 1e-12 for x in p.future_service_adjustments):
        raise ValueError("ajustements de service futur déjà fournis : clôture non prise en charge")
    proj = projection(p, r)
    row = proj.rows[0]
    df = discount_factors(p.discount_rates, n)
    f = df[0] / df[1] - 1.0
    k = p.risk_adjustment_pct
    rec, acq = recoveries(p), acquisition_costs(p)

    # facteurs en fin de période 1 : bloqués (courbe initiale) et courants (courbe de clôture)
    locked = [df[t] / df[1] for t in range(2, n + 1)]
    if c.closing_rates is None:
        current = locked
    else:
        rates = c.closing_rates if isinstance(c.closing_rates, list) else [c.closing_rates] * (n - 1)
        if len(rates) != n - 1:
            raise ValueError(f"closing_rates : {n - 1} taux attendus (périodes 2 à {n})")
        current = [(1 + rates[j]) ** -(j + 1) for j in range(n - 1)]
    # flux restants (périodes 2…n) ; primes et frais d'acquisition futurs payés en début de période
    prem_f = list(p.premiums[1:])
    acq_f = acq[1:]
    out_old, rec_old = list(p.outflows[1:]), rec[1:]
    out_new = list(c.revised_outflows) if c.revised_outflows is not None else out_old
    rec_new = list(c.revised_recoveries) if c.revised_recoveries is not None else rec_old
    if len(out_new) != n - 1 or len(rec_new) != n - 1:
        raise ValueError(f"flux révisés : {n - 1} valeurs attendues (périodes 2 à {n})")

    def start(d: list[float]) -> list[float]:      # facteurs de début de période 2…n (= fin de la précédente)
        return [1.0] + d[:-1]

    def bel(out: list[float], rc: list[float], d: list[float]) -> float:
        return _pv(out, d) - _pv(rc, d) - _pv(prem_f, start(d)) + _pv(acq_f, start(d))

    bel_old_locked = bel(out_old, rec_old, locked)               # = BEL attendu de clôture (projection)
    bel_new_locked = bel(out_new, rec_new, locked)
    bel_new_current = bel(out_new, rec_new, current)
    ra_old_locked = k * _pv(out_old, locked)
    ra_new_locked = k * _pv(out_new, locked)
    ra_new_current = k * _pv(out_new, current)

    prem_e, out_e, rec_e, acq_e = p.premiums[0], p.outflows[0], rec[0], acq[0]
    prem_a = prem_e if c.actual_premium is None else c.actual_premium
    out_a = c.actual_outflow
    rec_a = rec_e if c.actual_recovery is None else c.actual_recovery
    acq_a = acq_e if c.actual_acquisition is None else c.actual_acquisition
    experience = (prem_a - prem_e) - (acq_a - acq_e) - (out_a - out_e) + (rec_a - rec_e)

    d_est = bel_new_locked - bel_old_locked
    d_ra = ra_new_locked - ra_old_locked
    rate_effect = (bel_new_current - bel_new_locked) + (ra_new_current - ra_new_locked)
    future_cov = sum(p.coverage_units[1:]) > 0

    csm_open = r.initial_csm
    accretion = csm_open * f
    lc_expected_close = row.loss_component_closing
    change = d_est + d_ra                                  # + = défavorable
    adj = new_loss = reversal = past = 0.0
    after = csm_open + accretion
    if future_cov:
        if change > 0:
            adj = -min(after, change)
            new_loss = change + adj
        else:
            reversal = min(lc_expected_close, -change)
            adj = -change - reversal
        after += adj
    else:
        past = change
    cu = p.coverage_units
    ratio = cu[0] / sum(cu) if sum(cu) > 0 else 1.0
    release = after * ratio
    csm_close = after - release
    lc_close = lc_expected_close + new_loss - reversal

    slr = proj.systematic_loss_ratio
    ra_rel_e = row.ra_release
    revenue = ((out_e - rec_e) + ra_rel_e) * (1 - slr) + release + row.acquisition_amortisation + (prem_a - prem_e)
    # la perte initiale d'un groupe déficitaire (§47) est une charge de la première période
    expense = ((out_a - rec_a) - row.loss_component_reversal + r.initial_loss_component
               + row.acquisition_amortisation + (acq_a - acq_e) + past + new_loss - reversal)
    isr = revenue - expense
    bel0 = r.pv_outflows + r.pv_acquisition - r.pv_inflows
    finance = (bel0 + prem_e - acq_e) * f + r.risk_adjustment * f + accretion + rate_effect
    # passif juste avant la comptabilisation initiale : nul (la CSM absorbe les flux d'un groupe bénéficiaire,
    # la perte d'un groupe déficitaire passe en charges de la période)
    opening = bel0 + r.risk_adjustment + csm_open - r.initial_loss_component
    closing = bel_new_current + ra_new_current + csm_close
    cash = prem_a - acq_a - out_a + rec_a
    gap = closing - (opening + cash + finance - isr)
    return ClosingResult(
        group_id=p.group_id, as_of=c.as_of, future_coverage=future_cov, locked_forward=f,
        expected_premium=prem_e, actual_premium=prem_a, expected_outflow=out_e, actual_outflow=out_a,
        expected_recovery=rec_e, actual_recovery=rec_a, expected_acquisition=acq_e, actual_acquisition=acq_a,
        experience_adjustment=experience, future_flows_change=d_est, ra_future_change=d_ra, csm_adjustment=adj,
        new_loss=new_loss, loss_reversal=reversal, past_service_change=past, rate_effect=rate_effect,
        opening_liability=opening, bel_close=bel_new_current, ra_close=ra_new_current, csm_open=csm_open,
        csm_accretion=accretion, csm_release=release, csm_close=csm_close, loss_component_close=lc_close,
        closing_liability=closing, expected_closing_liability=row.lrc_closing,
        insurance_revenue=revenue, insurance_service_expense=expense, insurance_service_result=isr,
        insurance_finance_expense=finance, expected_service_result=row.insurance_service_result,
        profit=isr - finance, reconciliation_gap=gap)
