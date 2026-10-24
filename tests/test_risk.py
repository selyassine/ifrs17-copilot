"""Niveau de confiance de l'ajustement pour risque (D-056)."""

import math

import pytest

from engine.risk import confidence_level, confidence_report, ra_at_level


def test_quantile_et_niveau_sont_reciproques():
    for lv in (0.6, 0.75, 0.9, 0.995):
        ra = ra_at_level(1000.0, 0.15, lv)
        assert confidence_level(1000.0, 0.15, ra) == pytest.approx(lv, abs=1e-9)


def test_loi_lognormale_bien_parametree():
    # médiane d'une lognormale = moyenne / sqrt(1 + cv²) : le RA à 50 % est donc négatif
    assert ra_at_level(1000.0, 0.15, 0.5) == pytest.approx(1000 / math.sqrt(1.0225) - 1000)
    # plus de volatilité ou plus de prudence → RA plus élevé
    assert ra_at_level(1000.0, 0.20, 0.75) > ra_at_level(1000.0, 0.15, 0.75) > ra_at_level(1000.0, 0.15, 0.65)


def test_rapport_et_bascule():
    # VA primes 1 100, VA sorties 1 000 : à 99,5 % le RA dépasse la marge de 100 → déficitaire
    rep = confidence_report(1100.0, 1000.0, 0.03, 0.15)
    assert 0.5 < rep.level_of_retained_ra < 0.7
    rows = {r.level: r for r in rep.rows}
    assert not rows[0.65].onerous and rows[0.995].onerous
    assert rows[0.75].csm == pytest.approx(1100 - 1000 - rows[0.75].ra)
