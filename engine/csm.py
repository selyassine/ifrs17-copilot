"""Moteur IFRS 17 v0 — modèle général (BBA), un groupe de contrats.

Périmètre volontairement réduit (voir docs/decisions.md, D-006) :
- valeur actuelle des flux (§33-36), ajustement pour risque en % des sorties (§37) ;
- CSM initial (§38) ou composante perte si le groupe est onéreux (§47) ;
- roll-forward par période : intérêts au taux bloqué (§44(b), B72(b)),
  ajustement pour service futur (§44(c)), libération par unités de couverture
  (§44(e), B119).

Hors périmètre v0 : VFA, PAA, libération de l'ajustement pour risque,
revenus d'assurance détaillés, réassurance.

Le LLM n'exécute jamais ces calculs : l'agent Calculateur appelle ces fonctions.
"""

from __future__ import annotations

from agents.schemas import CsmPeriod, CsmResult, PortfolioData


def discount_factors(rates: float | list[float], n: int) -> list[float]:
    """Facteurs d'actualisation DF_0..DF_n (DF_0 = 1).

    - taux plat r : DF_t = (1 + r)^-t
    - courbe spot s_t (une valeur par fin de période) : DF_t = (1 + s_t)^-t
    """
    dfs = [1.0]
    for t in range(1, n + 1):
        r = rates if isinstance(rates, (int, float)) else rates[t - 1]
        dfs.append((1.0 + r) ** -t)
    return dfs


def present_values(p: PortfolioData) -> tuple[float, float, list[float]]:
    """PV des entrées (début de période) et des sorties (fin de période)."""
    n = p.n_periods
    dfs = discount_factors(p.discount_rates, n)
    pv_in = sum(p.premiums[t] * dfs[t] for t in range(n))           # payé en t (début de t+1)
    pv_out = sum(p.outflows[t] * dfs[t + 1] for t in range(n))      # payé en t+1 (fin de t+1)
    return pv_in, pv_out, dfs


def compute_csm(p: PortfolioData) -> CsmResult:
    n = p.n_periods
    pv_in, pv_out, dfs = present_values(p)
    ra = p.risk_adjustment_pct * pv_out
    fcf = pv_out + ra - pv_in                     # > 0 : net sortant → onéreux

    initial_csm = max(-fcf, 0.0)                  # §38
    initial_loss = max(fcf, 0.0)                  # §47

    adjustments = p.future_service_adjustments or [0.0] * n
    cu = p.coverage_units

    periods: list[CsmPeriod] = []
    csm = initial_csm
    for t in range(n):
        opening = csm
        # §44(b) : taux bloqué à la comptabilisation initiale = taux forward de la période
        locked_forward = dfs[t] / dfs[t + 1] - 1.0
        accretion = opening * locked_forward
        after_accretion = opening + accretion

        # §44(c) : une hausse des flux futurs réduit le CSM ; l'excédent devient une perte (§48)
        adj = -adjustments[t]
        after_adj = after_accretion + adj
        loss_change = 0.0
        if after_adj < 0:
            loss_change = -after_adj
            adj = -after_accretion
            after_adj = 0.0

        # §44(e), B119 : libération = CSM × CU de la période / (CU de la période + CU futures)
        remaining_cu = sum(cu[t:])
        release = after_adj * cu[t] / remaining_cu if remaining_cu > 0 else after_adj
        closing = after_adj - release

        periods.append(
            CsmPeriod(
                period=t + 1,
                opening=opening,
                interest_accretion=accretion,
                future_service_adjustment=adj,
                release=release,
                closing=closing,
                loss_component_change=loss_change,
            )
        )
        csm = closing

    return CsmResult(
        group_id=p.group_id,
        pv_inflows=pv_in,
        pv_outflows=pv_out,
        risk_adjustment=ra,
        fulfilment_cash_flows=fcf,
        initial_csm=initial_csm,
        initial_loss_component=initial_loss,
        onerous=fcf > 0,
        rollforward=periods,
        total_release=sum(x.release for x in periods),
    )
