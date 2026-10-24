"""Passif pour sinistres survenus (LIC) à partir d'un triangle de paiements cumulés (D-083).

IFRS 17 évalue les sinistres déjà survenus comme les autres flux : meilleure estimation actualisée des paiements
futurs, plus un ajustement au titre du risque non financier (§33, §37, §40(b)). Ce module fait le calcul
actuariel classique, entièrement en Python (le LLM ne calcule jamais) :

1. **Chain Ladder** (facteurs de développement pondérés par les volumes) : sinistres ultimes et provision par année
   de survenance, sans facteur de queue sauf s'il est donné ;
2. **erreur de prédiction de Mack (1993)** : écart-type de la provision par année de survenance et au total, avec la
   covariance entre années ; extrapolation du dernier σ² selon Mack ;
3. **cadence des paiements futurs par année calendaire** : diagonales futures du triangle complété, payées en fin
   d'année (convention du moteur, D-006) ;
4. **actualisation** : taux spot par échéance (un taux plat ou une courbe ; au-delà de la courbe, le dernier taux) ;
5. **ajustement pour risque** : quantile d'une loi lognormale (méthode du moteur, D-056) appliquée à la valeur
   actuelle des paiements, avec pour coefficient de variation l'erreur de Mack rapportée à la provision non
   actualisée (ou une volatilité imposée).

Validé sur l'exemple de Mack (1993), triangle de Taylor et Ashe (1983) : provision 18 680 856, erreur de
prédiction 2 447 095 (tests/test_lic.py).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from engine.risk import STANDARD_LEVELS, confidence_level, ra_at_level


class TriangleError(ValueError):
    """Triangle inexploitable (forme, valeurs, colonne sans données)."""


def check_triangle(cumulative: list[list[float]]) -> int:
    """Triangle « en escalier » : n années de survenance, la ligne i (0 = la plus ancienne) a n − i valeurs.
    Renvoie n."""
    n = len(cumulative)
    if n < 3:
        raise TriangleError("triangle trop petit : au moins 3 années de survenance")
    for i, row in enumerate(cumulative):
        if len(row) != n - i:
            raise TriangleError(f"ligne {i + 1} : {len(row)} valeurs au lieu de {n - i} (triangle en escalier attendu)")
        if any((not isinstance(x, int | float)) or x < 0 or math.isnan(x) for x in row):
            raise TriangleError(f"ligne {i + 1} : montants cumulés négatifs ou non numériques")
    for k in range(n - 1):
        if sum(cumulative[i][k] for i in range(n - k - 1)) <= 0:
            raise TriangleError(f"retard {k + 1} : aucun paiement cumulé, facteur de développement indéfini")
    return n


def development_factors(cumulative: list[list[float]]) -> list[float]:
    """f_k = Σ C(i, k+1) / Σ C(i, k), sur les années qui ont les deux retards (pondération par les volumes)."""
    n = check_triangle(cumulative)
    return [sum(cumulative[i][k + 1] for i in range(n - k - 1)) / sum(cumulative[i][k] for i in range(n - k - 1))
            for k in range(n - 1)]


def mack_sigma2(cumulative: list[list[float]], factors: list[float]) -> list[float]:
    """Variances de Mack σ²_k ; la dernière (une seule observation) est extrapolée : min(σ⁴_{n-2}/σ²_{n-3},
    σ²_{n-3}, σ²_{n-2}) (Mack 1993, formule 3.4 et remarque)."""
    n = len(cumulative)
    s2 = []
    for k in range(n - 1):
        m = n - k - 1                                    # nombre de rapports observés
        if m >= 2:
            s2.append(sum(cumulative[i][k] * (cumulative[i][k + 1] / cumulative[i][k] - factors[k]) ** 2
                          for i in range(m) if cumulative[i][k] > 0) / (m - 1))
        else:
            s2.append(math.nan)
    for k in range(n - 1):
        if math.isnan(s2[k]):
            a, b = (s2[k - 1], s2[k - 2]) if k >= 2 else (0.0, 0.0)
            s2[k] = min(a * a / b, b, a) if b > 0 else a
    return s2


@dataclass
class AccidentYearRow:
    label: str
    premium: float | None
    latest: float                 # dernier cumul connu (diagonale)
    development: float            # facteur de développement restant (produit des f)
    ultimate: float
    reserve: float                # provision non actualisée
    mack_se: float                # erreur de prédiction de Mack
    loss_ratio: float | None      # sinistres ultimes / prime


@dataclass
class LicResult:
    factors: list[float]
    sigma2: list[float]
    tail: float
    rows: list[AccidentYearRow]
    reserve: float                       # provision totale non actualisée
    mack_se: float                       # erreur de prédiction totale
    cv: float                            # coefficient de variation retenu pour le RA
    cv_source: str
    cash_flows: list[float]              # paiements futurs par année calendaire (fin d'année 1, 2, …)
    rates: list[float]                   # taux spot utilisés par échéance
    discount: list[float]                # facteurs d'actualisation
    bel: float                           # meilleure estimation actualisée
    level: float                         # niveau de confiance du RA
    risk_adjustment: float
    lic: float                           # BEL + RA
    discount_effect: float               # provision − BEL
    levels: list[tuple[float, float, float]] = field(default_factory=list)   # (niveau, RA, LIC)
    rate_shocks: list[tuple[float, float, float]] = field(default_factory=list)  # (choc en points, BEL, LIC)
    duration: float = 0.0                # duration de Macaulay des paiements (années)


def mack(cumulative: list[list[float]], tail: float = 1.0) -> tuple[list[float], list[float], list[float],
                                                                   list[float], list[float], float]:
    """Chain Ladder et erreur de Mack. Renvoie (facteurs, σ², ultimes, provisions, erreurs par année, erreur totale).
    Un facteur de queue > 1 multiplie les ultimes ; il n'entre pas dans l'erreur de Mack (hypothèse notée)."""
    n = check_triangle(cumulative)
    f = development_factors(cumulative)
    s2 = mack_sigma2(cumulative, f)
    full = [list(row) + [0.0] * (n - len(row)) for row in cumulative]
    for i in range(1, n):
        for k in range(n - i, n):
            full[i][k] = full[i][k - 1] * f[k - 1]
    ult = [full[i][n - 1] * tail for i in range(n)]
    latest = [cumulative[i][-1] for i in range(n)]
    res = [ult[i] - latest[i] for i in range(n)]
    col = [sum(cumulative[j][k] for j in range(n - k - 1)) for k in range(n - 1)]   # Σ C(j,k) sur les années observées
    mse = []
    for i in range(n):
        s = sum(s2[k] / f[k] ** 2 * (1 / full[i][k] + 1 / col[k]) for k in range(n - i - 1, n - 1) if full[i][k] > 0)
        mse.append(full[i][n - 1] ** 2 * s)
    total = sum(mse)
    for i in range(1, n):
        later = sum(full[j][n - 1] for j in range(i + 1, n))
        total += 2 * full[i][n - 1] * later * sum(s2[k] / f[k] ** 2 / col[k] for k in range(n - i - 1, n - 1))
    return f, s2, ult, res, [math.sqrt(m) for m in mse], math.sqrt(total)


def future_cash_flows(cumulative: list[list[float]], factors: list[float], tail: float = 1.0) -> list[float]:
    """Paiements futurs par année calendaire : année t = diagonale t du triangle complété (incréments). Le facteur
    de queue est payé l'année qui suit la dernière diagonale (convention simple, notée dans la note)."""
    n = len(cumulative)
    full = [list(row) + [0.0] * (n - len(row)) for row in cumulative]
    for i in range(1, n):
        for k in range(n - i, n):
            full[i][k] = full[i][k - 1] * factors[k - 1]
    cf = [0.0] * n
    for i in range(1, n):
        for k in range(n - i, n):
            t = k - (n - 1 - i)                          # 1 = l'année qui suit la date de clôture
            cf[t - 1] += full[i][k] - full[i][k - 1]
    if tail > 1.0:
        cf[n - 1] += sum(full[i][n - 1] for i in range(n)) * (tail - 1.0)
    while cf and abs(cf[-1]) < 1e-12:
        cf.pop()
    return cf


def _rates(discount_rates: float | list[float], horizon: int) -> list[float]:
    if isinstance(discount_rates, list):
        if not discount_rates:
            return [0.0] * horizon
        return [discount_rates[min(t, len(discount_rates) - 1)] for t in range(horizon)]
    return [float(discount_rates)] * horizon


def present_value(cf: list[float], rates: list[float]) -> tuple[float, list[float]]:
    v = [(1 + rates[t]) ** -(t + 1) for t in range(len(cf))]
    return sum(c * d for c, d in zip(cf, v, strict=True)), v


def compute_lic(cumulative: list[list[float]], discount_rates: float | list[float] = 0.0, level: float = 0.75,
                cv: float | None = None, cv_source: str = "", tail: float = 1.0, labels: list[str] | None = None,
                premiums: list[float] | None = None) -> LicResult:
    """LIC = valeur actuelle des paiements futurs (Chain Ladder) + RA au quantile ``level`` (lognormale).
    ``cv`` : volatilité imposée ; sinon l'erreur de Mack rapportée à la provision non actualisée."""
    n = check_triangle(cumulative)
    if not 0.5 <= level < 1:
        raise TriangleError("niveau de confiance hors de [50 % ; 100 %[")
    if tail < 1.0:
        raise TriangleError("facteur de queue inférieur à 1")
    f, s2, ult, res, se, se_total = mack(cumulative, tail)
    reserve = sum(res)
    if cv is None:
        cv = se_total / reserve if reserve > 0 else 0.0
        cv_source = cv_source or "erreur de prédiction de Mack (1993) rapportée à la provision non actualisée"
    cf = future_cash_flows(cumulative, f, tail)
    rates = _rates(discount_rates, len(cf))
    bel, v = present_value(cf, rates)
    ra = ra_at_level(bel, cv, level) if bel > 0 else 0.0
    labels = labels or [str(i + 1) for i in range(n)]
    rows = []
    for i in range(n):
        prem = premiums[i] if premiums and i < len(premiums) else None
        dev = ult[i] / cumulative[i][-1] if cumulative[i][-1] > 0 else math.nan
        rows.append(AccidentYearRow(label=labels[i], premium=prem, latest=cumulative[i][-1], development=dev,
                                    ultimate=ult[i], reserve=res[i], mack_se=se[i],
                                    loss_ratio=ult[i] / prem if prem else None))
    out = LicResult(factors=f, sigma2=s2, tail=tail, rows=rows, reserve=reserve, mack_se=se_total, cv=cv,
                    cv_source=cv_source, cash_flows=cf, rates=rates, discount=v, bel=bel, level=level,
                    risk_adjustment=ra, lic=bel + ra, discount_effect=reserve - bel)
    out.levels = [(lv, ra_at_level(bel, cv, lv), bel + ra_at_level(bel, cv, lv)) for lv in STANDARD_LEVELS]
    for shock in (-0.01, 0.01):
        b, _ = present_value(cf, [r + shock for r in rates])
        out.rate_shocks.append((shock * 100, b, b + ra_at_level(b, cv, level)))
    out.duration = (sum((t + 1) * c * d for t, (c, d) in enumerate(zip(cf, v, strict=True))) / bel) if bel > 0 else 0.0
    return out


def level_of(result: LicResult, ra: float) -> float:
    """Niveau de confiance d'un RA donné (pour comparer à un RA annoncé par le document)."""
    return confidence_level(result.bel, result.cv, ra)
