"""Jeu de test des dossiers de sinistres survenus (D-083) : triangles réels CAS (``data/cas/clrd.csv``, ce qui
était connu fin 1997), mis en forme comme un dossier de clôture, avec la vérité calculée par le moteur.

Mises en page et pièges (``python -m multimodal.lic_cases`` → ``data/lic/`` et ``eval/lic_cases.jsonl``) :
- lc01-lc03 : tableau en colonnes sans grille (comme le dossier C du camarade), primes et courbe de taux ;
- lc04 : paiements de l'année (incréments) au lieu des cumuls ;
- lc05 : sans colonne de primes, taux unique, quantile 90 % ;
- lc06 : classeur Excel ;
- lc07 (piège) : une cellule cumulée inférieure à la précédente (coquille du document) : alerte attendue ;
- lc08 (piège) : unité absente du document alors que les montants sont en milliers dans la source : la lecture
  doit rester en unités (aucune mention), le calcul est juste en unités ; le piège vérifie qu'aucune unité n'est
  inventée.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from agents.schemas import TriangleData
from core.config import ROOT
from engine.lic import compute_lic

OUT_DIR = ROOT / "data" / "lic"
CASES = ROOT / "eval" / "lic_cases.jsonl"
LOB_FR = {"wkcomp": "accidents du travail", "othliab": "responsabilité civile générale",
          "comauto": "auto commerciale", "ppauto": "auto particuliers"}
CURVE = [0.0559, 0.0574, 0.0576, 0.0578, 0.0580, 0.0583, 0.0587, 0.0586, 0.0585]


def fr(x: float, d: int = 0) -> str:
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def pct(x: float) -> str:
    return fr(x * 100, 2) + " %"


def load_triangles(path: Path = ROOT / "data" / "cas" / "clrd.csv") -> list[dict]:
    """Triangles complets (10 survenances, aucun cumul nul ou en recul de plus de 2 %), triés par code."""
    by: dict[tuple[str, str], dict] = {}
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = (r["LOB"], r["GRCODE"])
            d = by.setdefault(key, {"lob": r["LOB"], "code": r["GRCODE"], "name": r["GRNAME"], "cells": {}, "prem": {}})
            ay, lag = int(r["AccidentYear"]), int(r["DevelopmentLag"])
            if ay + lag - 1 <= 1997:
                d["cells"][(ay, lag)] = float(r["CumPaidLoss"])
                d["prem"][ay] = float(r["EarnedPremNet"])
    out = []
    for d in by.values():
        tri = [[d["cells"].get((ay, k)) for k in range(1, 1997 - ay + 2)] for ay in range(1988, 1998)]
        if any(v is None or v <= 0 for row in tri for v in row):
            continue
        if any(row[k] < 0.98 * row[k - 1] for row in tri for k in range(1, len(row))):
            continue
        prem = [d["prem"].get(ay, 0.0) for ay in range(1988, 1998)]
        if min(prem) < 2000 or tri[0][-1] < 5000:
            continue
        out.append({**d, "triangle": tri, "premiums": prem})
    return sorted(out, key=lambda d: (d["lob"], int(d["code"])))


def _pdf(path: Path, title: str, header: list[str], rows: list[list[str]], intro: list[str], foot: list[str]) -> None:
    """Mise en page sans grille : texte positionné en colonnes (relu par le code via les blancs, F-019)."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=landscape(A4))
    w, h = landscape(A4)
    y = h - 45
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, y, title)
    c.setFont("Helvetica", 8.5)
    for line in intro:
        y -= 13
        c.drawString(40, y, line)
    y -= 24
    xs = [40 + 62 * k for k in range(len(header))]
    c.setFont("Helvetica-Bold", 8)
    for x, s in zip(xs, header, strict=True):
        c.drawString(x, y, s)
    c.setFont("Helvetica", 8)
    for row in rows:
        y -= 14
        for x, s in zip(xs, row, strict=False):
            c.drawString(x, y, s)
    for line in foot:
        y -= 13
        c.drawString(40, y - 8, line)
    c.save()


def _xlsx(path: Path, title: str, header: list[str], rows: list[list], intro: list[list]) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Triangle"
    ws.append([title])
    for r in intro:
        ws.append(r)
    ws.append([])
    ws.append(header)
    for r in rows:
        ws.append(r)
    wb.save(path)


SPECS = [  # (id, mise en page, cumulés ?, primes ?, taux, niveau, piège)
    ("lc01", "pdf", True, True, CURVE, 0.75, ""),
    ("lc02", "pdf", True, True, CURVE, 0.75, ""),
    ("lc03", "pdf", True, True, CURVE, 0.80, ""),
    ("lc04", "pdf", False, True, CURVE, 0.75, ""),
    ("lc05", "pdf", True, False, 0.045, 0.90, ""),
    ("lc06", "xlsx", True, True, CURVE, 0.75, ""),
    ("lc07", "pdf", True, True, CURVE, 0.75, "cumul_en_recul"),
    ("lc08", "pdf", True, True, CURVE, 0.75, "unite_absente"),
]


def generate(out_dir: Path = OUT_DIR, cases_path: Path = CASES) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    tris = load_triangles()
    # une compagnie par branche, à tour de rôle, sur une grille fixe (reproductible)
    pool = []
    for lob in ("wkcomp", "othliab", "comauto", "ppauto"):
        pool += [t for t in tris if t["lob"] == lob][::3][:2]
    cases = []
    for (cid, layout, cumul, with_prem, rates, level, trap), src in zip(SPECS, pool, strict=False):
        tri = [list(r) for r in src["triangle"]]
        if trap == "cumul_en_recul":
            tri[3][2] = round(tri[3][1] * 0.5)                 # coquille : la moitié de la valeur précédente
        shown = tri if cumul else [[row[0]] + [row[k] - row[k - 1] for k in range(1, len(row))] for row in tri]
        years = [str(y) for y in range(1988, 1998)]
        unit = 1 if trap == "unite_absente" else 1000
        truth = TriangleData(portfolio_id=f"{src['name']} — {LOB_FR[src['lob']]}", currency="USD", unit_multiplier=unit,
                             line_of_business=LOB_FR[src["lob"]], valuation_date="31/12/1997", origin_years=years,
                             premiums=src["premiums"] if with_prem else None, triangle=shown, cumulative=cumul,
                             discount_rates=rates, confidence_level=level)
        res = compute_lic(truth.cumulative_triangle(), rates, level)
        kind = "paiements cumulés" if cumul else "paiements de l'année (non cumulés)"
        unit_txt = "" if trap == "unite_absente" else " · Montants en milliers de dollars américains"
        title = f"{src['name']} — Dossier de clôture au 31/12/1997"
        intro = [f"Portefeuille : {LOB_FR[src['lob']]} (États-Unis) · Code NAIC : {src['code']} · Devise : USD{unit_txt}",
                 "Objet : évaluation du passif pour sinistres survenus (LIC) au 31/12/1997, années de survenance 1988 à 1997.",
                 f"Données : triangle des {kind}, nets de réassurance."]
        rate_txt = ("Taux d'actualisation unique : " + pct(rates) if not isinstance(rates, list) else
                    "Taux spot par échéance (1 à 9 ans) : " + " ; ".join(pct(r) for r in rates))
        foot = ["Hypothèses : Chain Ladder (facteurs pondérés par les volumes), sans facteur de queue ; paiements en fin "
                "d'année calendaire.", rate_txt,
                f"Ajustement au titre du risque : quantile {fr(level * 100)} % d'une loi lognormale, coefficient de "
                "variation = erreur de prédiction de Mack (1993) rapportée à la provision non actualisée.",
                "Source : CAS Loss Reserving Database (NAIC Schedule P, partie 3). Document généré pour l'évaluation du projet."]
        header = ["Survenance"] + (["Prime nette"] if with_prem else []) + [f"Ret. {k + 1}" for k in range(10)]
        rows = [[years[i]] + ([fr(src["premiums"][i])] if with_prem else []) + [fr(v) for v in shown[i]]
                for i in range(10)]
        if layout == "xlsx":
            path = out_dir / f"{cid}.xlsx"
            _xlsx(path, title, header,
                  [[int(years[i])] + ([src["premiums"][i]] if with_prem else []) + shown[i] for i in range(10)],
                  [[x] for x in intro] + [[x] for x in foot])
        else:
            path = out_dir / f"{cid}.pdf"
            _pdf(path, title, header, rows, intro, foot)
        cases.append({"id": cid, "fichier": str(path.relative_to(ROOT)), "piege": trap,
                      "attendu": "alerte" if trap == "cumul_en_recul" else "exact",
                      "truth": truth.model_dump(mode="json"),
                      "lic_attendu": round(res.lic, 2), "bel_attendu": round(res.bel, 2),
                      "provision_attendue": round(res.reserve, 2)})
    cases_path.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n", encoding="utf-8")
    return cases_path


if __name__ == "__main__":
    print(generate())
