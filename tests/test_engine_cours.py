"""Le moteur contre les exercices chiffrés d'un cours IFRS 17 (Mazars, EAM 2024, D-042 à D-043).

Seuls les chiffres des exercices sont repris, avec la page du cours ; le support lui-même n'est
pas versionné (droits de son auteur). Tolérance : 1 € quand le cours arrondit à l'euro.
"""

import math
from datetime import date

import pytest

from agents.schemas import PortfolioData
from engine.bba import BbaScenario, ClaimRevision, roll_forward_bba
from engine.csm import compute_csm
from engine.paa import PaaClaim, PaaContract, position


def near(a: float, b: float, tol: float = 1.0) -> bool:
    return math.isclose(a, b, abs_tol=tol)


def one_period(premium: float, pv_claims: float, ra: float):
    """Exemples à une période du cours : flux déjà actualisés, RA donné en montant."""
    return compute_csm(PortfolioData(group_id="COURS", premiums=[premium], outflows=[pv_claims],
                                     coverage_units=[1], discount_rates=0.0, risk_adjustment_pct=ra / pv_claims))


@pytest.mark.parametrize("page, premium, pv_claims, ra, csm, loss", [
    ("p. 21 : contrat profitable", 1000, 900, 10, 90, 0),
    ("p. 24 : contrat onéreux", 1000, 1080, 10, 0, 90),
    ("p. 25 : scénario 1", 900, 545, 120, 235, 0),
    ("p. 26 : scénario 2", 900, 1089, 120, 0, 309),
])
def test_exemples_a_une_periode(page, premium, pv_claims, ra, csm, loss):
    r = one_period(premium, pv_claims, ra)
    assert near(r.initial_csm, csm, 0.01) and near(r.initial_loss_component, loss, 0.01), page
    assert r.onerous == (loss > 0)


# ---------------------------------------------------------------- p. 32 à 36 : modèle général sur 4 ans
COURSE_BBA = BbaScenario(
    group_id="COURS-BBA", single_premium=1_000_000, expected_claims=[200_000] * 4,
    actual_claims=[200_000, 220_000, 220_000, 220_000], rates=[0.042, 0.043, 0.044, 0.035, 0.030],
    ra_initial=50_000, ra_changes=[0, 5_000, 0, 0], coverage_units=[100] * 4,
    claim_revisions=[ClaimRevision(at_end_of_year=3, expected_claims=[200_000, 200_000, 200_000, 220_000])],
)


def test_moteur_v0_retrouve_l_origine_et_20x1():
    """p. 33 et 36 avec le moteur v0 (CSM seule) : BEL 722 570, CSM 227 430, puis 9 552 et 59 245."""
    pv_claims = sum(200_000 / 1.042 ** t for t in range(1, 5))
    r = compute_csm(PortfolioData(group_id="COURS", premiums=[1_000_000, 0, 0, 0], outflows=[200_000] * 4,
                                  coverage_units=[100] * 4, discount_rates=0.042,
                                  risk_adjustment_pct=50_000 / pv_claims))
    y1 = r.rollforward[0]
    assert near(r.pv_outflows, 722_570) and near(r.initial_csm, 227_430)
    assert near(y1.interest_accretion, 9_552) and near(y1.release, 59_245) and near(y1.closing, 177_736)


def test_bba_origine():
    r = roll_forward_bba(COURSE_BBA)
    assert near(r.bel_initial, 722_570) and near(r.csm_initial, 227_430) and r.loss_initial == 0


def test_bba_20x1_comme_le_cours():
    """p. 34 à 36 : BEL, RA et CSM de 20X1, à l'euro près."""
    y = roll_forward_bba(COURSE_BBA).years[0]
    assert near(y.bel_interest, 30_348)            # 722 570 × 4,2 %
    assert near(y.bel_rate_effect, -1_045)         # passage de 4,2 % à 4,3 %
    assert near(y.bel_close, 551_873)
    assert near(y.ra_release, 12_500) and near(y.ra_close, 37_500)
    assert near(y.csm_accretion, 9_552) and near(y.csm_release, 59_245) and near(y.csm_close, 177_736)
    assert near(y.oci, 1_045)                      # option OCI : l'effet de taux ne passe pas en résultat


def test_bba_annees_suivantes_respectent_la_norme():
    """20X2 à 20X4 : le cours donne les événements, pas les résultats. On vérifie les règles."""
    y2, y3, y4 = roll_forward_bba(COURSE_BBA).years[1:]
    # 20X2 : sinistres réels 220 000 au lieu de 200 000 → écart en résultat, pas en CSM (B97(c))
    assert near(y2.experience_adjustment, 20_000) and near(y2.insurance_service_expenses, 220_000)
    # 20X2 : RA + 5 000 au titre des services futurs → la CSM baisse de 5 000 (B96(d))
    assert near(y2.csm_adjustment, -5_000) and near(y2.ra_release, (37_500 + 5_000) / 3)
    # 20X3 : sinistres 20X4 revus à 220 000 → CSM ajustée au taux bloqué de 4,2 % (B96(b), B72(c))
    assert near(y3.csm_adjustment, -20_000 / 1.042)
    assert near(y3.bel_close, 220_000 / 1.035)
    # 20X4 : tout est écoulé
    assert near(y4.bel_close, 0) and near(y4.ra_close, 0) and near(y4.csm_close, 0)


def test_bba_bilan_des_flux():
    """Sur la vie du groupe : résultat + OCI = primes − sinistres payés, avec l'option OCI comme P&L."""
    for option in ("OCI", "PL"):
        r = roll_forward_bba(COURSE_BBA.model_copy(update={"finance_option": option}))
        assert near(r.total_profit + r.total_oci, 1_000_000 - 860_000, 0.01)
        if option == "OCI":
            assert near(r.total_oci, 0, 0.01)      # l'OCI se recycle entièrement sur la durée


def test_bba_groupe_qui_devient_deficitaire_puis_redevient_profitable():
    """§48 : perte au-delà de la CSM ; §50(b) : une révision favorable reprend d'abord la perte."""
    s = BbaScenario(single_premium=1_000, expected_claims=[300, 300, 300], rates=[0, 0, 0, 0], ra_initial=0,
                    claim_revisions=[ClaimRevision(at_end_of_year=1, expected_claims=[300, 300, 500]),
                                     ClaimRevision(at_end_of_year=2, expected_claims=[300, 300, 350])])
    y1, y2, _ = roll_forward_bba(s).years
    assert near(y1.csm_close, 0, 0.01) and near(y1.loss_component_change, 100, 0.01)    # 100 − 200
    assert near(y2.loss_component_change, -100, 0.01)                                    # reprise d'abord
    assert near(y2.csm_close, 25, 0.01)                                                  # 50 restants, moitié libérée


# ---------------------------------------------------------------- p. 39 : modèle simplifié PAA, cas n°1
CLAIM = PaaClaim(occurred=date(2026, 5, 15), estimate=750, risk_adjustment=50,
                 paid_on=date(2026, 10, 15), paid_amount=900)


def paa(expense: bool) -> PaaContract:
    return PaaContract(group_id="AUTO", premium=1_000, coverage_start=date(2025, 7, 1), coverage_months=12,
                       acquisition_costs=30, expense_acquisition_costs=expense, claims=[CLAIM])


def test_paa_q1_au_31_12_n_frais_en_charge():
    p = position(paa(True), date(2025, 12, 31))
    assert p.lrc == 500 and p.lic == 0 and p.revenue_to_date == 500 and p.acquisition_expense_to_date == 30


def test_paa_q2_frais_d_acquisition_dans_la_lrc():
    p = position(paa(False), date(2025, 12, 31))
    assert p.lrc == 485 and p.acquisition_expense_to_date == 15     # 1 000 − 30 + 15 − 500


def test_paa_q3_au_30_06_n1():
    p = position(paa(True), date(2026, 6, 30))
    assert p.lrc == 0 and p.lic == 800                              # 750 + 50 de RA


def test_paa_q4_ecart_de_reglement_en_resultat():
    n = position(paa(True), date(2026, 6, 30))
    n1 = position(paa(True), date(2026, 12, 31))
    assert n1.lic == 0
    assert n1.claims_expense_to_date - n.claims_expense_to_date == 100   # 900 payés − 800 provisionnés
