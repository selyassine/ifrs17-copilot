"""Lecture des données CAS Loss Reserving Database (NAIC Schedule P), deux formats acceptés (D-072) :

- un fichier par branche, comme sur casact.org (``wkcomp_pos.csv``, ``wkcomp_pos_98-07.csv``…) : la branche
  est lue dans le nom du fichier, les colonnes portent un suffixe de branche (``CumPaidLoss_D``) ;
- un fichier toutes branches avec une colonne ``LOB`` (``clrd.csv`` et ``clrd2025.csv`` du paquet Python
  ``chainladder`` de la CAS : github.com/casact/chainladder-python, dossier chainladder/utils/data).

Attention : ``clrd.csv`` (survenances 1988-1997) ne contient que le triangle supérieur (ce qui était connu fin
1997) : il suffit pour projeter, pas pour le back-testing. ``clrd2025.csv`` (1998-2007) et les fichiers de
casact.org contiennent le carré complet (10 années de développement), donc le réalisé.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

# codes de branche du projet ; « PPA » (script R) et « PA » désignent la même branche
LOB_CODES = {"wkcomp": "WC", "ppauto": "PA", "comauto": "CA", "othliab": "OL", "medmal": "MM", "prodliab": "PL"}
LOB_LABELS = {"WC": "Accidents du travail", "PA": "Auto particuliers (RC)", "CA": "Auto commerciale (RC)",
              "OL": "Responsabilité civile générale", "MM": "Responsabilité médicale",
              "PL": "Responsabilité civile produits"}
_KEYWORDS = [  # (motif, code) : du plus précis au plus général
    (r"accidents? du travail|workers?'? ?comp|wkcomp|\bWC\b", "WC"),
    (r"auto(mobile)? particuliers?|private passenger|ppauto|\bPPA\b|\bPA\b", "PA"),
    (r"auto(mobile)? commerciale|commercial auto|comauto|\bCA\b", "CA"),
    (r"r(esponsabilit[ée])?\.? ?c(ivile)?\.? ?produits?|product liability|prodliab|\bPL\b", "PL"),
    (r"m[ée]dical|malpractice|medmal|\bMM\b", "MM"),
    (r"responsabilit[ée] civile g[ée]n[ée]rale|other liability|othliab|\bOL\b|\bRCG\b", "OL"),
]


def lob_code(text: str | None) -> str | None:
    """Branche écrite librement (« Accidents du travail », « Workers' compensation », « WC ») → code."""
    if not text:
        return None
    for pattern, code in _KEYWORDS:
        if re.search(pattern, text, flags=re.I):
            return code
    return None


def _clean(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if k is None:
            continue
        key = k.strip()
        if key not in ("LOB",) and "_" in key:
            key = key.rsplit("_", 1)[0]            # « CumPaidLoss_D » → « CumPaidLoss »
        out[key] = (v or "").strip()
    # « IncurredLosses » (clrd2025) ≡ « IncurLoss » ; colonnes non utilisées ici
    return out


def read_file(path: Path) -> dict[str, list[dict]]:
    """Lignes d'un fichier CAS, regroupées par code de branche."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if text.lstrip()[:1] == "<":
        raise OSError(f"{path.name} : page web au lieu d'un fichier CSV")
    rows = [_clean(r) for r in csv.DictReader(text.splitlines())]
    if not rows:
        return {}
    for col in ("GRCODE", "GRNAME", "AccidentYear", "DevelopmentLag", "CumPaidLoss", "EarnedPremNet"):
        if col not in rows[0]:
            raise OSError(f"{path.name} : colonne {col} introuvable ({list(rows[0])[:8]}…)")
    by: dict[str, list[dict]] = {}
    if "LOB" in rows[0]:
        for r in rows:
            code = LOB_CODES.get(r["LOB"].lower())
            if code:
                by.setdefault(code, []).append(r)
        return by
    code = LOB_CODES.get(path.name.split("_")[0].lower())
    if code is None:
        raise OSError(f"{path.name} : branche inconnue (nom attendu : wkcomp_pos.csv, medmal_pos_98-07.csv…)")
    return {code: rows}


def load(paths: list[Path]) -> dict[str, list[list[dict]]]:
    """Plusieurs fichiers → {branche: [lignes du fichier 1, lignes du fichier 2…]} (une période par fichier,
    les compagnies ne sont pas mélangées d'une période à l'autre)."""
    out: dict[str, list[list[dict]]] = {}
    for path in paths:
        for code, rows in read_file(path).items():
            out.setdefault(code, []).append(rows)
    return out
