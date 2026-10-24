"""Calibration de l'ajustement au titre du risque non financier par branche (D-074).

IFRS 17 laisse la méthode libre (B86 à B92) mais impose de publier le niveau de confiance (§119). Le moteur
traduit un RA en niveau de confiance par une loi lognormale de la valeur actuelle des sorties (``engine/risk.py``) ;
il lui faut le coefficient de variation (CV) de cette valeur. Jusqu'ici il était SUPPOSÉ (15 %). Ici, il est
MESURÉ sur des données réelles, par back-testing :

1. pour chaque compagnie et chaque survenance dont le réalisé est complet (10 années), on projette les sinistres
   comme un actuaire l'aurait fait au 1er janvier de la survenance (``actuariat.chain_ladder.project``) ;
2. on compare au réalisé : X = paiements réels / paiements attendus ;
3. dispersion de ln X sur les compagnies dont la prime atteint 1 000 k$ (les très petites sont dominées par le
   bruit), mesurée par un écart-type ROBUSTE (1,4826 × écart absolu médian) : les valeurs aberrantes (fusion,
   changement de périmètre) ne la gonflent pas, et, contrairement à un écart-type après suppression des queues,
   l'estimateur n'est pas biaisé (vérifié par un test sur une volatilité connue). Pas de pondération par les
   primes : quelques très grands groupes écraseraient la mesure. Le biais moyen et les quantiles 10 % et 90 %
   sont calculés après avoir écarté 2,5 % des valeurs à chaque extrémité ;
4. CV = racine(exp(σ²) − 1) ; RA en % des sorties au niveau α = quantile_α / moyenne − 1.

Le biais moyen (X moyen ≠ 1) est publié à part : il mesure la qualité de la méthode de projection, pas
l'incertitude, et n'entre pas dans le RA (un biais connu se corrige dans la meilleure estimation).

Limites (écrites dans le registre) : volatilité d'une compagnie entière, pas d'un groupe de contrats ; données
américaines 1998-2016 ; même méthode de projection pour tous ; sinistres payés seulement (pas de frais).

    python -m actuariat.calibration clrd2025.csv                 # écrit hypotheses/registre.json
    python -m actuariat.calibration wkcomp_pos.csv medmal_pos.csv --niveau 0.75
"""

from __future__ import annotations

import argparse
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from actuariat import donnees
from actuariat.chain_ladder import all_projections, triangles
from actuariat.registre import REGISTRE, load_registry, save_registry
from engine.risk import ra_at_level

LEVELS = (0.65, 0.75, 0.85, 0.90, 0.995)


@dataclass
class BranchCalibration:
    code: str
    label: str
    cohorts: int                # cohortes (compagnie × survenance) avec réalisé complet
    kept: int                   # après exclusion des extrêmes
    sigma_log: float
    cv: float
    bias: float                 # moyenne pondérée de X (1 = sans biais)
    ratio_p10: float
    ratio_p90: float
    ra_pct: dict[str, float]    # niveau → RA en % de la valeur actuelle des sorties
    source: str


def calibrate_branch(code: str, files_rows: list[list[dict]], trim: float = 0.025, min_premium: float = 1000.0,
                     source: str = "") -> BranchCalibration | None:
    obs: list[float] = []
    for rows in files_rows:
        for _, pr in all_projections(triangles(rows)):
            exp_total, act_total = sum(pr.expected), sum(pr.actual)
            if len(pr.actual) == 10 and pr.premium >= min_premium and exp_total > 0 and act_total > 0:
                obs.append(act_total / exp_total)
    if len(obs) < 30:
        return None
    obs.sort()
    logs = [math.log(x) for x in obs]
    med = statistics.median(logs)
    # écart-type robuste : 1,4826 × écart absolu médian (estimateur sans biais pour une loi normale, insensible
    # aux valeurs aberrantes) ; écarter des queues puis prendre l'écart-type sous-estimerait σ d'environ 12 %
    sigma = 1.4826 * statistics.median(abs(v - med) for v in logs)
    var = sigma * sigma
    cv = math.sqrt(math.exp(var) - 1.0)
    cut = int(len(obs) * trim)
    kept = obs[cut:len(obs) - cut] if cut else obs
    return BranchCalibration(
        code=code, label=donnees.LOB_LABELS[code], cohorts=len(obs), kept=len(obs), sigma_log=round(sigma, 6),
        cv=round(cv, 6), bias=round(sum(kept) / len(kept), 6), ratio_p10=round(kept[int(0.1 * (len(kept) - 1))], 4),
        ratio_p90=round(kept[int(0.9 * (len(kept) - 1))], 4),
        ra_pct={f"{lv:.3f}".rstrip("0").rstrip("."): round(ra_at_level(1.0, cv, lv), 6) for lv in LEVELS},
        source=source)


def calibrate(paths: list[Path]) -> dict[str, BranchCalibration]:
    data = donnees.load(paths)
    src = ", ".join(p.name for p in paths)
    out = {}
    for code, files_rows in sorted(data.items()):
        cal = calibrate_branch(code, files_rows, source=src)
        if cal is not None:
            out[code] = cal
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("fichiers", nargs="+", type=Path, help="fichiers CAS avec le réalisé complet")
    ap.add_argument("--niveau", type=float, default=None, help="niveau de confiance cible du RA (ex. 0.75)")
    ap.add_argument("--registre", type=Path, default=REGISTRE)
    args = ap.parse_args()
    cals = calibrate(args.fichiers)
    if not cals:
        raise SystemExit("aucune branche calibrable : il faut le réalisé complet (clrd2025.csv ou fichiers casact.org)")
    reg = load_registry(args.registre)
    ra = reg["ajustement_risque"]
    if args.niveau is not None:
        ra["niveau_cible"] = args.niveau
    ra["branches"] = {c: asdict(v) for c, v in cals.items()}
    ra["calibre_le"] = date.today().isoformat()
    save_registry(reg, args.registre, change=f"calibration du RA sur {', '.join(p.name for p in args.fichiers)}")
    print(f"{'branche':<34}{'cohortes':>9}{'CV':>8}{'biais':>8}{'RA 75 %':>9}")
    for c in cals.values():
        print(f"{c.label:<34}{c.kept:>9}{c.cv:>8.1%}{c.bias:>8.2f}{c.ra_pct['0.75']:>9.2%}")
    print(f"→ {args.registre} (version {reg['version']})")


if __name__ == "__main__":
    main()
