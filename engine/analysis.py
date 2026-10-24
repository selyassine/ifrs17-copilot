"""Analyses actuarielles de la note (D-055) : projection, compte de résultat, sensibilités.

Tout est calculé par le code à partir de ``engine/csm.py`` ; le LLM ne fait que commenter des
chiffres déjà calculés (D-005). Trois analyses :

1. **Projection du scénario central** (réalisé = attendu, taux courants = taux à terme implicites
   de la courbe initiale, donc taux courant = taux bloqué) : à chaque clôture, meilleure estimation
   (BEL), ajustement pour risque (RA), CSM et composante de perte ; compte de résultat IFRS 17 :
   - produits des activités d'assurance = sorties attendues de la période + RA libéré + CSM
     libérée (B124) ; pour un groupe déficitaire, la part affectée à la composante de perte est
     exclue des produits (§49-50, B123) ;
   - charges des services d'assurance = sorties de la période − reprise de la composante de perte
     (+ perte initiale, §47) ;
   - charges financières d'assurance = désactualisation du BEL, du RA (variation du RA ventilée
     entre service et finance, option du §81) et de la CSM au taux bloqué (§44(b), B72(b)).
   Composante de perte : répartition systématique (§50(a)) au ratio constant
   LC₀ / (valeur actuelle des sorties + RA) à l'origine, de sorte qu'elle s'éteint en fin de couverture.
2. **Analyse des mouvements de la CSM** sur la durée du groupe (cascade).
3. **Sensibilités** : le moteur est relancé avec des hypothèses choquées (taux, sorties, primes,
   RA) ; seuils de bascule (hausse des sorties ou baisse des taux qui rend le groupe déficitaire).

Hors périmètre (dit dans la note) : revenus des placements (côté actif), frais d'acquisition,
composantes d'investissement, réassurance, VFA. Les ajustements de service futur (§44(c)) sont
repris dans la CSM, mais la projection du compte de résultat n'est alors pas produite.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.schemas import CsmResult, PortfolioData
from engine.csm import acquisition_costs, compute_csm, discount_factors, recoveries


# --------------------------------------------------------------------------- #
# 1. Projection du scénario central
# --------------------------------------------------------------------------- #
@dataclass
class ProjectionRow:
    period: int
    premium: float                  # encaissée en début de période
    outflow: float                  # payée en fin de période (sinistres et frais)
    forward_rate: float             # taux à terme de la période (= taux bloqué)
    bel_closing: float              # meilleure estimation en fin de période (sorties − entrées)
    ra_closing: float
    csm_closing: float
    loss_component_closing: float
    lrc_closing: float              # passif pour couverture restante = BEL + RA + CSM
    ra_release: float
    csm_release: float
    loss_component_reversal: float
    insurance_revenue: float
    insurance_service_expense: float
    insurance_service_result: float
    insurance_finance_expense: float
    recovery: float = 0.0           # recouvrement encaissé en fin de période (B65 k, D-071)
    acquisition: float = 0.0        # frais d'acquisition payés en début de période (B65 e, D-075)
    acquisition_amortisation: float = 0.0   # part des frais d'acquisition en produits et en charges (B125, §103(b))


@dataclass
class Projection:
    rows: list[ProjectionRow]
    opening_lrc: float              # passif à la comptabilisation initiale (avant la 1re prime)
    systematic_loss_ratio: float    # 0 pour un groupe bénéficiaire
    totals: dict[str, float]


def projection(p: PortfolioData, r: CsmResult) -> Projection | None:
    """Scénario central. None si des ajustements de service futur sont fournis (hors scénario central)."""
    if p.future_service_adjustments and any(abs(x) > 1e-12 for x in p.future_service_adjustments):
        return None
    n = p.n_periods
    df = discount_factors(p.discount_rates, n)

    def pv_out_at(t: int) -> float:          # valeur en t des sorties restantes (payées en s + 1)
        return sum(p.outflows[s] * df[s + 1] for s in range(t, n)) / df[t]

    rec = recoveries(p)

    def pv_rec_at(t: int) -> float:          # valeur en t des recouvrements restants (reçus en s + 1)
        return sum(rec[s] * df[s + 1] for s in range(t, n)) / df[t]

    def pv_in_at(t: int) -> float:           # primes restantes (payées en s) et recouvrements restants
        return sum(p.premiums[s] * df[s] for s in range(t, n)) / df[t] + pv_rec_at(t)

    acq = acquisition_costs(p)

    def pv_acq_at(t: int) -> float:          # frais d'acquisition restants (payés en début de période s)
        return sum(acq[s] * df[s] for s in range(t, n)) / df[t]

    # B125 : la part des primes qui couvre les frais d'acquisition est affectée aux périodes selon les unités
    # de couverture ; le même montant est passé en charges (amortissement, §103(b)(iii)) : sans effet sur le résultat
    total_cu = sum(p.coverage_units)
    amort = [sum(acq) * cu / total_cu for cu in p.coverage_units]

    k = p.risk_adjustment_pct
    loss0 = r.initial_loss_component
    # sinistres nets des recouvrements (B65 k) + ajustement pour risque
    pool0 = pv_out_at(0) - pv_rec_at(0) + k * pv_out_at(0)
    slr = loss0 / pool0 if pool0 > 0 else 0.0

    bel, ra, lc = pv_out_at(0) - pv_in_at(0) + pv_acq_at(0), k * pv_out_at(0), loss0
    opening_lrc = bel + ra + r.initial_csm
    rows: list[ProjectionRow] = []
    for t in range(1, n + 1):
        f = df[t - 1] / df[t] - 1.0
        prem, out_gross, recovery = p.premiums[t - 1], p.outflows[t - 1], rec[t - 1]
        out = out_gross - recovery           # sinistres et frais nets des recouvrements
        cp = r.rollforward[t - 1]
        bel_c = pv_out_at(t) - pv_in_at(t) + (pv_acq_at(t) if t < n else 0.0)
        ra_c = k * pv_out_at(t)
        ra_rel = ra * (1 + f) - ra_c
        lc_fin = lc * f
        lc_rev = slr * (out + ra_rel)
        lc_c = lc + lc_fin - lc_rev
        acq_t, am = acq[t - 1], amort[t - 1]
        finance = (bel + prem - acq_t) * f + ra * f + cp.interest_accretion
        revenue = (out + ra_rel) * (1 - slr) + cp.release + am
        expense = out - lc_rev + (loss0 if t == 1 else 0.0) + am
        rows.append(ProjectionRow(
            period=t, premium=prem, outflow=out_gross, recovery=recovery, acquisition=acq_t,
            acquisition_amortisation=am, forward_rate=f, bel_closing=bel_c, ra_closing=ra_c,
            csm_closing=cp.closing, loss_component_closing=lc_c, lrc_closing=bel_c + ra_c + cp.closing,
            ra_release=ra_rel, csm_release=cp.release, loss_component_reversal=lc_rev,
            insurance_revenue=revenue, insurance_service_expense=expense,
            insurance_service_result=revenue - expense, insurance_finance_expense=finance))
        bel, ra, lc = bel_c, ra_c, lc_c
    keys = ("premium", "outflow", "recovery", "acquisition", "acquisition_amortisation", "insurance_revenue",
            "insurance_service_expense", "insurance_service_result", "insurance_finance_expense", "ra_release", "csm_release", "loss_component_reversal")
    totals = {key: sum(getattr(x, key) for x in rows) for key in keys}
    return Projection(rows=rows, opening_lrc=opening_lrc, systematic_loss_ratio=slr, totals=totals)


# --------------------------------------------------------------------------- #
# 2. Mouvements de la CSM sur la durée du groupe
# --------------------------------------------------------------------------- #
@dataclass
class CsmMovements:
    initial: float
    interest: float
    future_service: float           # signe de la CSM : négatif = baisse
    release: float                  # positif = montant reconnu en résultat
    closing: float
    loss_component_change: float


def csm_movements(r: CsmResult) -> CsmMovements:
    rf = r.rollforward
    return CsmMovements(
        initial=r.initial_csm,
        interest=sum(x.interest_accretion for x in rf),
        future_service=sum(x.future_service_adjustment for x in rf),
        release=sum(x.release for x in rf),
        closing=rf[-1].closing if rf else r.initial_csm,
        loss_component_change=sum(x.loss_component_change for x in rf),
    )


# --------------------------------------------------------------------------- #
# 3. Sensibilités
# --------------------------------------------------------------------------- #
@dataclass
class Sensitivity:
    key: str
    label: str
    fulfilment_cash_flows: float
    csm: float
    loss: float
    delta_result_at_inception: float    # variation de (CSM − perte) par rapport au central
    onerous: bool
    flips: bool                         # le groupe change de statut (bénéficiaire ↔ déficitaire)


@dataclass
class SensitivityReport:
    central: CsmResult
    items: list[Sensitivity] = field(default_factory=list)
    outflow_breakeven: float | None = None      # variation relative des sorties qui annule les FCF
    rate_breakeven_shift: float | None = None   # translation des taux qui annule les FCF (None : hors ±5 points)


def _shift_rates(rates: float | list[float], d: float) -> float | list[float]:
    if isinstance(rates, list):
        return [max(x + d, -0.99) for x in rates]
    return max(rates + d, -0.99)


SHOCKS: list[tuple[str, str, dict]] = [
    ("taux_plus_100", "Taux d'actualisation +100 pb", {"rates": +0.01}),
    ("taux_moins_100", "Taux d'actualisation −100 pb", {"rates": -0.01}),
    ("sorties_plus_10", "Sinistres et frais +10 %", {"outflows": 1.10}),
    ("sorties_moins_10", "Sinistres et frais −10 %", {"outflows": 0.90}),
    ("primes_moins_10", "Primes −10 %", {"premiums": 0.90}),
    ("ra_plus_50", "Ajustement pour risque +50 % (relatif)", {"ra": 1.50}),
]


def shocked(p: PortfolioData, rates: float = 0.0, outflows: float = 1.0, premiums: float = 1.0,
            ra: float = 1.0) -> PortfolioData:
    return p.model_copy(update={
        "discount_rates": _shift_rates(p.discount_rates, rates),
        "outflows": [x * outflows for x in p.outflows],
        # les recouvrements suivent les sinistres auxquels ils se rattachent
        "recoveries": None if p.recoveries is None else [x * outflows for x in p.recoveries],
        "premiums": [x * premiums for x in p.premiums],
        "risk_adjustment_pct": min(p.risk_adjustment_pct * ra, 1.0),
    })


def _fcf_with_shift(p: PortfolioData, d: float) -> float:
    return compute_csm(shocked(p, rates=d)).fulfilment_cash_flows


def sensitivities(p: PortfolioData, r: CsmResult | None = None) -> SensitivityReport:
    r = r or compute_csm(p)
    base = r.initial_csm - r.initial_loss_component
    rep = SensitivityReport(central=r)
    for key, label, shock in SHOCKS:
        s = compute_csm(shocked(p, **shock))
        rep.items.append(Sensitivity(
            key=key, label=label, fulfilment_cash_flows=s.fulfilment_cash_flows, csm=s.initial_csm,
            loss=s.initial_loss_component, delta_result_at_inception=(s.initial_csm - s.initial_loss_component) - base,
            onerous=s.onerous, flips=s.onerous != r.onerous))
    # Seuil de bascule sur les sorties : FCF(k) = k·[VA(sorties)·(1 + RA%) − VA(recouvrements)]
    #                                             + VA(frais d'acquisition, non choqués) − VA(primes) = 0
    load = r.pv_outflows * (1 + p.risk_adjustment_pct) - r.pv_recoveries
    if load > 0:
        rep.outflow_breakeven = (r.pv_inflows - r.pv_recoveries - r.pv_acquisition) / load - 1.0
    # Seuil de bascule sur les taux : bissection sur une translation parallèle dans [−5 ; +5] points
    lo, hi = -0.05, 0.05
    f_lo, f_hi = _fcf_with_shift(p, lo), _fcf_with_shift(p, hi)
    if f_lo * f_hi < 0:
        for _ in range(60):
            mid = (lo + hi) / 2
            f_mid = _fcf_with_shift(p, mid)
            if f_lo * f_mid <= 0:
                hi = mid
            else:
                lo, f_lo = mid, f_mid
        rep.rate_breakeven_shift = (lo + hi) / 2
    return rep


# --------------------------------------------------------------------------- #
# Indicateurs du résumé
# --------------------------------------------------------------------------- #
def margin_ratio(r: CsmResult) -> float:
    """CSM (ou −perte) rapportée à la valeur actuelle des primes : marge attendue du groupe."""
    if r.pv_inflows <= 0:
        return 0.0
    return (r.initial_csm - r.initial_loss_component) / r.pv_inflows


def macaulay_duration(p: PortfolioData) -> float:
    """Duration des sorties (en périodes), pondérée par leur valeur actuelle."""
    df = discount_factors(p.discount_rates, p.n_periods)
    pv = [p.outflows[s] * df[s + 1] for s in range(p.n_periods)]
    total = sum(pv)
    return sum((s + 1) * v for s, v in enumerate(pv)) / total if total > 0 else 0.0
