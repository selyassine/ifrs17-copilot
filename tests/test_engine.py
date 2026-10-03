"""Tests du moteur CSM contre des calculs faits à la main (écart toléré < 0,01).

Chaque cas est recalculé dans docs/engine_hand_calcs.md, ligne par ligne.
"""

import math

import pytest

from agents.schemas import PortfolioData
from engine.csm import compute_csm, discount_factors

TOL = 0.01


def close(a: float, b: float) -> bool:
    return math.isclose(a, b, abs_tol=TOL)


def portfolio(**kw) -> PortfolioData:
    base = dict(
        group_id="G-TEST",
        premiums=[100.0, 0.0, 0.0],
        outflows=[20.0, 20.0, 20.0],
        coverage_units=[1.0, 1.0, 1.0],
    )
    base.update(kw)
    return PortfolioData(**base)


def test_cas_1_taux_nul_liberation_lineaire():
    """Taux 0, RA 0 : CSM = 100 - 60 = 40, libéré par tiers."""
    r = compute_csm(portfolio())
    assert close(r.initial_csm, 40.0)
    assert not r.onerous
    assert [round(p.release, 4) for p in r.rollforward] == [13.3333, 13.3333, 13.3333]
    assert close(r.rollforward[-1].closing, 0.0)


def test_cas_2_taux_5_pourcent_avec_ajustement_pour_risque():
    """Taux plat 5 %, RA 5 % des sorties, sinistres de 30 par an (calcul manuel)."""
    r = compute_csm(
        portfolio(outflows=[30.0, 30.0, 30.0], discount_rates=0.05, risk_adjustment_pct=0.05)
    )
    assert close(r.pv_outflows, 81.6974)
    assert close(r.risk_adjustment, 4.0849)
    assert close(r.fulfilment_cash_flows, -14.2177)
    assert close(r.initial_csm, 14.2177)

    expected = [
        # opening, accretion, release, closing
        (14.2177, 0.7109, 4.9762, 9.9524),
        (9.9524, 0.4976, 5.2250, 5.2250),
        (5.2250, 0.2613, 5.4863, 0.0000),
    ]
    for p, (op, acc, rel, cl) in zip(r.rollforward, expected, strict=True):
        assert close(p.opening, op)
        assert close(p.interest_accretion, acc)
        assert close(p.release, rel)
        assert close(p.closing, cl)


def test_cas_3_groupe_onereux():
    """Primes 50 < sorties 60 : composante perte de 10, CSM nul (§47)."""
    r = compute_csm(portfolio(premiums=[50.0, 0.0, 0.0]))
    assert r.onerous
    assert close(r.initial_csm, 0.0)
    assert close(r.initial_loss_component, 10.0)
    assert all(close(p.release, 0.0) for p in r.rollforward)


def test_cas_4_ajustement_defavorable_cree_une_perte():
    """§44(c) puis §48 : une hausse de 30 des flux futurs en période 2 épuise le CSM."""
    r = compute_csm(portfolio(future_service_adjustments=[0.0, 30.0, 0.0]))
    p2 = r.rollforward[1]
    assert close(p2.opening, 26.6667)
    assert close(p2.future_service_adjustment, -26.6667)
    assert close(p2.loss_component_change, 3.3333)
    assert close(p2.closing, 0.0)


def test_cas_5_ajustement_favorable_augmente_le_csm():
    r = compute_csm(portfolio(future_service_adjustments=[0.0, -6.0, 0.0]))
    assert [round(p.release, 4) for p in r.rollforward] == [13.3333, 16.3333, 16.3333]
    assert close(r.total_release, 46.0)


def test_unites_de_couverture_non_uniformes():
    """B119 : la libération suit les unités de couverture (1, 2, 1)."""
    r = compute_csm(portfolio(coverage_units=[1.0, 2.0, 1.0]))
    assert [round(p.release, 4) for p in r.rollforward] == [10.0, 20.0, 10.0]


@pytest.mark.parametrize("rates", [0.0, 0.03, [0.02, 0.03, 0.04]])
def test_invariant_liberation_totale(rates):
    """Sans ajustement : total libéré = CSM initial + intérêts capitalisés, CSM final = 0."""
    r = compute_csm(portfolio(discount_rates=rates, risk_adjustment_pct=0.1))
    accretion = sum(p.interest_accretion for p in r.rollforward)
    assert close(r.total_release, r.initial_csm + accretion)
    assert close(r.rollforward[-1].closing, 0.0)


def test_facteurs_actualisation_courbe():
    dfs = discount_factors([0.02, 0.03], 2)
    assert close(dfs[1], 1 / 1.02)
    assert close(dfs[2], 1 / 1.03**2)
