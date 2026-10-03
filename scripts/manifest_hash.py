"""Vérifie le manifeste du corpus et remplit les empreintes SHA-256.

    python -m scripts.manifest_hash            # contrôle seulement
    python -m scripts.manifest_hash --write    # remplit sha256 et date_acces

Contrôles : identifiants uniques, licence renseignée, fichier présent pour
chaque ligne au statut « ok », empreinte inchangée (détecte une nouvelle version
d'un document, qui invaliderait l'index et les résultats d'évaluation).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "corpus_manifest.csv"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    with MANIFEST.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        rows = list(reader)

    problems: list[str] = []
    seen: set[str] = set()
    for r in rows:
        rid = r["id"]
        if rid in seen:
            problems.append(f"{rid} : identifiant en double")
        seen.add(rid)
        if not r["licence"].strip():
            problems.append(f"{rid} : licence inconnue")
        local = r["fichier_local"].strip()
        path = ROOT / local if local else None
        if path and path.exists():
            digest = sha256(path)
            if r["sha256"] and r["sha256"] != digest:
                problems.append(f"{rid} : le fichier a changé depuis l'indexation (sha256)")
            if args.write and not r["sha256"]:
                r["sha256"] = digest
                r["date_acces"] = r["date_acces"] or date.today().isoformat()
        elif r["statut"] == "ok":
            problems.append(f"{rid} : statut ok mais fichier absent ({local})")

    if args.write:
        with MANIFEST.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    statuts: dict[str, int] = {}
    for r in rows:
        statuts[r["statut"]] = statuts.get(r["statut"], 0) + 1
    print(f"{len(rows)} documents — " + ", ".join(f"{k} : {v}" for k, v in sorted(statuts.items())))
    for p in problems:
        print("  PROBLÈME", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
