"""Registre des hypothèses actuarielles, versionné dans Git (D-077).

Une seule source pour toutes les hypothèses que le code applique sans les lire dans le document : volatilité
du RA par branche et niveau de confiance cible, méthode de projection et hypothèse de queue, règles PAA,
conventions de date des flux. Chaque modification incrémente la version et s'ajoute à l'historique ; la note
cite la version utilisée, ce qui rend chaque note reproductible (« quelles hypothèses, à quelle date ? »).
"""

from __future__ import annotations

import copy
import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from core.config import ROOT

REGISTRE = ROOT / "hypotheses" / "registre.json"

DEFAULT: dict = {
    "version": "0",
    "historique": [],
    "ajustement_risque": {
        "methode": "quantile (value at risk) d'une loi lognormale de la valeur actuelle des sorties, "
                   "CV mesuré par back-testing (actuariat/calibration.py)",
        "niveau_cible": 0.75,
        "cv_defaut": 0.15,
        "cv_defaut_justification": "hypothèse non calibrée : branche non indiquée dans le document",
        "branche_non_calibree": "plus forte volatilité calibrée (prudence : historique insuffisant)",
        "branches": {},
    },
    "projection": {
        "methode": "Chain Ladder (facteurs pondérés par les volumes) sur les paiements cumulés, sinistralité "
                   "attendue = S/P ultime moyen des survenances passées, information arrêtée au 31/12 précédent",
        "queue": "facteur 9→10 égal au facteur 8→9 (non observable sur 10 ans)",
        "selection": "compagnies « Single », prime ≥ 1 000 k$, triangle complet, S/P attendu entre 0,2 et 2",
    },
    "paa": {
        "duree_max_mois": 12,
        "regle": "§53(b) : couverture d'un an au plus → PAA permise sans test ; au-delà, modèle général",
        "actualisation_lic": "actualisée si des règlements sont attendus au-delà de 12 mois (§59(b) non applicable)",
        "frais_acquisition_en_charge": False,
    },
    "conventions": {
        "primes": "encaissées en début de période",
        "sinistres_et_frais": "payés en fin de période",
        "recouvrements": "encaissés en fin de période (B65 k)",
        "frais_acquisition": "payés en début de période, sans RA (B65 e, §28A)",
        "taux": "courbe spot fournie par le document ; à défaut, taux plat du document",
    },
}


def load_registry(path: Path = REGISTRE) -> dict:
    if not path.exists():
        return copy.deepcopy(DEFAULT)
    reg = json.loads(path.read_text(encoding="utf-8"))
    for key, value in DEFAULT.items():            # nouvelles rubriques : valeurs par défaut
        reg.setdefault(key, copy.deepcopy(value))
    return reg


def save_registry(reg: dict, path: Path = REGISTRE, change: str = "") -> dict:
    reg["version"] = str(int(str(reg.get("version", "0")).split(".")[0]) + 1)
    reg.setdefault("historique", []).append({"version": reg["version"], "date": date.today().isoformat(),
                                             "modification": change})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    current.cache_clear()
    return reg


@lru_cache
def current() -> dict:
    return load_registry(REGISTRE)


def ra_volatility(line_of_business: str | None, default_cv: float | None = None) -> tuple[float, str, str | None]:
    """(CV, explication, code de branche) pour la note : CV calibré si la branche est au registre."""
    from actuariat.donnees import LOB_LABELS, lob_code

    reg = current()
    ra = reg["ajustement_risque"]
    code = lob_code(line_of_business)
    cal = ra["branches"].get(code) if code else None
    if cal:
        return (float(cal["cv"]),
                f"volatilité calibrée sur {cal['kept']} cohortes réelles de la branche « {LOB_LABELS[code]} » "
                f"(CAS Schedule P, back-testing ; registre des hypothèses v{reg['version']})", code)
    if code and ra["branches"]:
        worst = max(ra["branches"].values(), key=lambda c: float(c["cv"]))
        return (float(worst["cv"]),
                f"volatilité prudente : branche « {LOB_LABELS[code]} » sans historique suffisant, plus forte volatilité "
                f"calibrée retenue (« {worst['label']} » ; registre des hypothèses v{reg['version']})", code)
    cv = default_cv if default_cv is not None else float(ra["cv_defaut"])
    why = (f"branche « {line_of_business} » non reconnue" if line_of_business
           else "branche non indiquée dans le document")
    return cv, f"volatilité supposée ({why}) : hypothèse à calibrer", code
