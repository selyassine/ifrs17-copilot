"""Flux de sinistres ATTENDUS d'une cohorte, comme un actuaire à la date d'évaluation (D-072).

Méthode (script R d'un membre de l'équipe, reprise à l'identique pour permettre un double calcul) :
1. date d'évaluation = 1er janvier de l'année de survenance ``cohort`` ; on ne garde du triangle que ce
   qui était connu au 31/12/``cohort - 1`` (années de survenance antérieures, diagonales passées) ;
2. facteurs de développement Chain Ladder (moyenne pondérée par les volumes) sur les paiements cumulés ;
   le facteur 9→10 n'est pas observable : il est pris égal au facteur 8→9 (hypothèse de queue, écrite
   dans le registre des hypothèses) ;
3. cadence de paiement = parts incrémentales de l'ultime ;
4. sinistralité attendue (S/P ultime) = moyenne des ultimes projetés des années passées / primes ;
5. flux attendus = prime × S/P × cadence. Les paiements réellement observés ensuite sont gardés à part
   pour le back-testing : ils ne servent jamais à construire les flux attendus.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

LAGS = 10


@dataclass
class Triangle:
    """Une compagnie : paiements cumulés par (survenance, retard) et prime acquise nette par survenance."""
    grcode: str
    name: str
    cum: dict[tuple[int, int], float] = field(default_factory=dict)
    premium: dict[int, float] = field(default_factory=dict)
    single: bool = True

    @property
    def years(self) -> list[int]:
        return sorted({a for a, _ in self.cum})

    def complete(self) -> bool:
        ys = self.years
        return len(ys) == LAGS and all((a, k) in self.cum for a in ys for k in range(1, LAGS + 1))

    def actual_incremental(self, year: int) -> list[float]:
        cum = [self.cum[(year, k)] for k in range(1, LAGS + 1)]
        return [cum[0]] + [cum[k] - cum[k - 1] for k in range(1, LAGS)]


def triangles(rows: list[dict]) -> dict[str, Triangle]:
    """Lignes CAS (colonnes sans suffixe de branche, voir ``multimodal.real_cas.read_cas``)."""
    out: dict[str, Triangle] = {}
    bad: set[str] = set()
    for r in rows:
        g = r["GRCODE"]
        t = out.setdefault(g, Triangle(grcode=g, name=r["GRNAME"]))
        try:
            a, k = int(float(r["AccidentYear"])), int(float(r["DevelopmentLag"]))
            t.cum[(a, k)] = float(r["CumPaidLoss"])
            if k == 1:
                t.premium[a] = float(r["EarnedPremNet"])
        except (ValueError, KeyError):
            bad.add(g)                      # valeur manquante (NA) : triangle incomplet
        if r.get("Single", "1") not in ("1", "1.0"):
            t.single = False
    for g in bad:
        out[g].cum.clear()
    return out


@dataclass
class Projection:
    cohort: int
    premium: float
    factors: list[float]          # f_1..f_9 (retard k → k+1)
    pattern: list[float]          # cadence de paiement, somme 1
    elr: float                    # S/P ultime attendu
    expected: list[float]         # prime × S/P × cadence
    actual: list[float]           # paiements réels observés ensuite (back-testing seulement)


def project(t: Triangle, cohort: int) -> Projection | None:
    """Flux attendus de la cohorte ``cohort`` avec l'information connue au 31/12/``cohort - 1``."""
    cutoff = cohort - 1
    known = {(a, k): v for (a, k), v in t.cum.items() if a < cohort and a + k - 1 <= cutoff}
    years = sorted({a for a, _ in known})
    f = [1.0] * (LAGS - 1)
    for k in range(1, LAGS - 1):                    # facteurs 1→2 … 8→9
        num = den = 0.0
        for a in years:
            if (a, k) in known and (a, k + 1) in known:
                num += known[(a, k + 1)]
                den += known[(a, k)]
        f[k - 1] = num / den if den > 0 else 1.0
    f[LAGS - 2] = f[LAGS - 3]                        # queue : facteur 9→10 = facteur 8→9
    chain = f + [1.0]
    cdf = [1.0] * LAGS                               # du retard k jusqu'à l'ultime
    for k in range(LAGS - 1, -1, -1):
        cdf[k] = chain[k] * (cdf[k + 1] if k + 1 < LAGS else 1.0)
    share = [1.0 / c if c else float("inf") for c in cdf]
    p = [share[0]] + [share[k] - share[k - 1] for k in range(1, LAGS)]
    if any(x != x or x in (float("inf"), float("-inf")) for x in p) or any(x < -1e-6 for x in p):
        return None
    p = [max(x, 0.0) for x in p]
    s = sum(p)
    if s <= 0:
        return None
    p = [x / s for x in p]

    ult = prem = 0.0
    for a in years:
        last = max(k for (b, k) in known if b == a)
        if a in t.premium:
            ult += known[(a, last)] * cdf[last - 1]
            prem += t.premium[a]
    if prem <= 0:
        return None
    elr = ult / prem
    premium = t.premium.get(cohort, 0.0)
    if premium <= 0:
        return None
    try:
        actual = t.actual_incremental(cohort)
    except KeyError:
        actual = []                                  # réalisé pas encore publié (triangle supérieur seul)
    return Projection(cohort=cohort, premium=premium, factors=f, pattern=p, elr=elr,
                      expected=[premium * elr * x for x in p], actual=actual)


def select(tris: dict[str, Triangle], per_lot: int = 5, min_premium: float = 1000.0,
           elr_range: tuple[float, float] = (0.2, 2.0), require_actual: bool = True) -> list[tuple[Triangle, Projection]]:
    """Choix du script R : dernière survenance du fichier, compagnies « Single » triées par prime décroissante,
    triangle complet (10 × 10), S/P attendu dans [0,2 ; 2] ; ``per_lot`` premières retenues.
    ``require_actual=False`` : fichier réduit au triangle supérieur (clrd.csv), 55 cases connues suffisent."""
    cohort = max((a for t in tris.values() for a, _ in t.cum), default=0)
    cands = [t for t in tris.values() if t.single and t.premium.get(cohort, 0) >= min_premium]
    cands.sort(key=lambda t: -t.premium[cohort])     # tri stable, comme arrange(desc()) en R
    out = []
    upper = LAGS * (LAGS + 1) // 2
    for t in cands:
        if not (t.complete() or (not require_actual and len(t.cum) == upper)):
            continue
        pr = project(t, cohort)
        if pr is None or not (elr_range[0] <= pr.elr <= elr_range[1]):
            continue
        if require_actual and len(pr.actual) != LAGS:
            continue
        out.append((t, pr))
        if len(out) >= per_lot:
            break
    return out


def all_projections(tris: dict[str, Triangle], min_history: int = LAGS - 1,
                    single_only: bool = False) -> list[tuple[Triangle, Projection]]:
    """Cohortes projetables avec leur réalisé complet : la base de la calibration du RA et du back-testing.
    ``min_history`` : survenances passées exigées. Avec 9 (défaut), seule la dernière survenance du fichier
    est projetée, comme dans le script R : tous les facteurs 1→2 … 8→9 sont alors observés. Avec moins
    d'historique, les facteurs non observés valent 1 et les sinistres attendus sont sous-estimés (biais
    mesuré : × 8 en responsabilité médicale), ce qui fausserait la volatilité."""
    out = []
    for t in tris.values():
        if (single_only and not t.single) or not t.complete():
            continue
        for cohort in t.years[min_history:]:
            pr = project(t, cohort)
            if pr is not None and pr.elr > 0:
                out.append((t, pr))
    return out


def by_company(rows: list[dict]) -> dict[str, list[dict]]:
    by = defaultdict(list)
    for r in rows:
        by[r["GRCODE"]].append(r)
    return by


@dataclass
class Reprojection:
    """Révision à la fin de la première année (31/12 de la survenance) : méthode Bornhuetter-Ferguson."""
    paid_year1: float             # paiement réel de l'année de survenance
    factors: list[float]          # facteurs recalculés avec la nouvelle diagonale
    ultimate: float               # ultime révisé = payé + prime × S/P × part restant à payer
    revised_future: list[float]   # paiements attendus des années 2 à 10, révisés


def reproject_after_year1(t: Triangle, proj: Projection) -> Reprojection | None:
    """Ce qu'un actuaire saurait à la première clôture : le paiement réel de l'année 1 et une diagonale de plus.
    Bornhuetter-Ferguson plutôt que Chain Ladder : sur une seule année de développement, Chain Ladder multiplie
    le bruit du premier paiement par le facteur cumulé ; BF garde la sinistralité attendue pour la part non payée."""
    cohort = proj.cohort
    if (cohort, 1) not in t.cum:
        return None
    known = {(a, k): v for (a, k), v in t.cum.items() if a + k - 1 <= cohort}
    years = sorted({a for a, _ in known if a <= cohort})
    f = [1.0] * (LAGS - 1)
    for k in range(1, LAGS - 1):
        num = den = 0.0
        for a in years:
            if a < cohort and (a, k) in known and (a, k + 1) in known:
                num += known[(a, k + 1)]
                den += known[(a, k)]
        f[k - 1] = num / den if den > 0 else 1.0
    f[LAGS - 2] = f[LAGS - 3]
    chain = f + [1.0]
    cdf = [1.0] * LAGS
    for k in range(LAGS - 1, -1, -1):
        cdf[k] = chain[k] * (cdf[k + 1] if k + 1 < LAGS else 1.0)
    share = [1.0 / c for c in cdf]
    pattern = [share[0]] + [share[k] - share[k - 1] for k in range(1, LAGS)]
    pattern = [max(x, 0.0) for x in pattern]
    paid = t.cum[(cohort, 1)]
    unpaid_share = max(1.0 - share[0], 0.0)
    expected_unpaid = proj.premium * proj.elr * unpaid_share
    rest = pattern[1:]
    s = sum(rest)
    future = [expected_unpaid * x / s for x in rest] if s > 0 else [0.0] * (LAGS - 1)
    return Reprojection(paid_year1=paid, factors=f, ultimate=paid + expected_unpaid, revised_future=future)
