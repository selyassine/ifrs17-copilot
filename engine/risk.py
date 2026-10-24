"""Niveau de confiance de l'ajustement au titre du risque non financier (D-056).

IFRS 17 ne prescrit pas de méthode pour l'ajustement pour risque (RA, §37, B86 à B92), mais une
entité qui utilise une autre technique que celle des quantiles doit publier le **niveau de
confiance** auquel il correspond (§119). Le moteur exprime le RA en pourcentage de la valeur
actuelle des sorties ; ce module traduit ce pourcentage en niveau de confiance, et inversement.

Méthode des quantiles (value at risk) sur la valeur actuelle des sorties X :
- X suit une loi **lognormale** de moyenne la meilleure estimation et de coefficient de
  variation ``cv`` (écart-type / moyenne) : asymétrique à droite, comme une charge de sinistres ;
- RA(α) = quantile d'ordre α de X − moyenne de X ;
- niveau de confiance d'un RA donné : α = P(X ≤ moyenne + RA).

Le coefficient de variation est une hypothèse (``RA_CV``, 15 % par défaut) qu'un actuaire
calibrerait sur l'historique des sinistres ; la note le dit et montre la sensibilité. Les primes
ne sont pas aléatoires dans ce modèle : seule l'incertitude des sorties porte le risque.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

STANDARD_LEVELS = (0.65, 0.75, 0.85, 0.90, 0.995)
_N = NormalDist()


def _params(mean: float, cv: float) -> tuple[float, float]:
    sigma2 = math.log(1.0 + cv * cv)
    return math.log(mean) - sigma2 / 2.0, math.sqrt(sigma2)


def ra_at_level(mean: float, cv: float, level: float) -> float:
    """RA (en montant) correspondant au quantile ``level`` de la valeur actuelle des sorties."""
    if mean <= 0 or cv <= 0:
        return 0.0
    mu, sigma = _params(mean, cv)
    return math.exp(mu + sigma * _N.inv_cdf(level)) - mean


def confidence_level(mean: float, cv: float, ra: float) -> float:
    """Niveau de confiance α tel que P(X ≤ moyenne + RA) = α."""
    if mean <= 0 or cv <= 0:
        return 1.0 if ra > 0 else 0.5
    mu, sigma = _params(mean, cv)
    return _N.cdf((math.log(mean + max(ra, -mean * 0.999999)) - mu) / sigma)


@dataclass
class ConfidenceRow:
    level: float
    ra: float
    ra_pct: float                 # RA en % de la valeur actuelle des sorties
    csm: float                    # CSM initiale avec ce RA
    loss: float                   # perte initiale avec ce RA
    onerous: bool


@dataclass
class ConfidenceReport:
    cv: float
    level_of_retained_ra: float   # niveau de confiance du RA retenu par l'entité
    rows: list[ConfidenceRow]


def confidence_report(pv_inflows: float, pv_outflows: float, ra_pct: float, cv: float,
                      levels: tuple[float, ...] = STANDARD_LEVELS) -> ConfidenceReport:
    """Niveau de confiance du RA retenu, puis RA, CSM et statut pour des niveaux usuels."""
    rows = []
    for lv in levels:
        ra = ra_at_level(pv_outflows, cv, lv)
        fcf = pv_outflows + ra - pv_inflows
        rows.append(ConfidenceRow(level=lv, ra=ra, ra_pct=ra / pv_outflows if pv_outflows else 0.0,
                                  csm=max(-fcf, 0.0), loss=max(fcf, 0.0), onerous=fcf > 0))
    return ConfidenceReport(cv=cv, rows=rows,
                            level_of_retained_ra=confidence_level(pv_outflows, cv, ra_pct * pv_outflows))


CV_GAP = 0.25          # écart relatif de volatilité au-delà duquel l'hypothèse est à arbitrer (D-082)
LEVEL_GAP = 0.025      # écart de niveau de confiance toléré entre l'annonce du document et le calcul (2,5 points)


@dataclass
class DeclaredRiskCheck:
    """Hypothèses que le document annonce pour son RA, rapprochées du calcul et du registre (D-082)."""
    declared_cv: float | None
    declared_confidence: float | None
    registry_cv: float
    level_with_declared_cv: float | None      # niveau de confiance du RA retenu avec la volatilité du document
    level_with_registry_cv: float
    cv_gap: float | None                      # écart relatif (document / registre − 1)
    cv_disagrees: bool
    confidence_disagrees: bool                # l'annonce du document ne correspond pas à son propre RA


def declared_risk_check(pv_outflows: float, ra: float, registry_cv: float, declared_cv: float | None,
                        declared_confidence: float | None) -> DeclaredRiskCheck | None:
    """Rapproche le RA du document de ce qu'il annonce : avec sa propre volatilité, son RA atteint-il le niveau de
    confiance qu'il déclare ? et sa volatilité est-elle proche de celle du registre ? Le registre reste
    l'hypothèse de référence ; l'écart est montré pour que l'actuaire tranche (grille, point H3)."""
    if declared_cv is None and declared_confidence is None:
        return None
    lv_reg = confidence_level(pv_outflows, registry_cv, ra)
    lv_doc = confidence_level(pv_outflows, declared_cv, ra) if declared_cv else None
    gap = declared_cv / registry_cv - 1 if declared_cv and registry_cv > 0 else None
    ref = lv_doc if lv_doc is not None else lv_reg
    return DeclaredRiskCheck(
        declared_cv=declared_cv, declared_confidence=declared_confidence, registry_cv=registry_cv,
        level_with_declared_cv=lv_doc, level_with_registry_cv=lv_reg, cv_gap=gap,
        cv_disagrees=gap is not None and abs(gap) > CV_GAP,
        confidence_disagrees=declared_confidence is not None and abs(ref - declared_confidence) > LEVEL_GAP)
