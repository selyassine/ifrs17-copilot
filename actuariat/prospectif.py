"""Dossiers prospectifs à montants réels, comme un actuaire à la date d'évaluation (D-072).

Méthode du script R d'un membre de l'équipe, reprise en Python et vérifiée par double calcul (les 50 dossiers
du script R sont retrouvés à l'identique : même sélection, mêmes S/P, mêmes sinistres attendus au centime) :
- une cohorte par compagnie (dernière survenance du fichier, 1997 ou 2007), évaluée au 1er janvier de son année ;
- flux ATTENDUS par Chain Ladder et S/P des années passées, sans information a posteriori
  (``actuariat.chain_ladder``) ; les paiements réellement observés ensuite sont gardés pour le back-testing ;
- contrats annuels : couverture de 12 mois (PAA admissible, §53(b)), unités de couverture = prime acquise la
  première année, puis 0 (le règlement des sinistres n'est pas un service de couverture).

Corrections par rapport au script R :
1. la vérité (et donc la CSM attendue) est calculée sur les valeurs AFFICHÉES (montants au centime, taux à
   0,01 %) : l'écart R ↔ Python sur la CSM vient de là (0,80 sur le dossier 2, 3,56 sur le dossier 26) ;
2. les flux attendus sont écrits dans le fichier de vérité, ce qui permet un contrôle champ par champ ;
3. courbe des taux à la date d'évaluation (FRED, historique depuis 1962) au lieu de la courbe d'aujourd'hui
   appliquée à 1997 (``--fred-historique``) ; à défaut, ``--courbe`` (une courbe saisie) ;
4. branche et durée de couverture écrites dans le document, pour la PAA et la calibration du RA.

    python -m actuariat.prospectif data/cas/clrd.csv data/cas/clrd2025.csv --courbe 4.54,4.75,4.80,4.81,4.82,4.83,4.85,4.88,4.90,4.93
    python -m actuariat.prospectif data/cas/clrd.csv data/cas/clrd2025.csv --fred-historique
    python -m actuariat.prospectif data/cas/clrd.csv data/cas/clrd2025.csv --camarade chemin/dossiers_reels
    python -m eval.eval_production --jeu prospectif        # ou --jeu independants pour les PDF du camarade
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from actuariat import donnees
from actuariat.chain_ladder import (
    LAGS,
    Projection,
    Triangle,
    reproject_after_year1,
    select,
    triangles,
)
from agents.schemas import PortfolioData, truth_dict
from core.config import ROOT
from engine.csm import compute_csm

OUT_DIR = ROOT / "data" / "prospectif"
INDEP_DIR = ROOT / "data" / "independants"
ORDER = ["WC", "PA", "CA", "OL", "MM"]                  # ordre du script R (sans la RC produits)
R_CODES = {"WC": "WC", "PA": "PPA", "CA": "CA", "OL": "OL", "MM": "MM"}   # codes de groupe du script R
# courbe affichée dans les 50 PDF du script R (EIOPA USD au 30/09/2026), en %
EIOPA_2026_09 = [4.54, 4.75, 4.80, 4.81, 4.82, 4.83, 4.85, 4.88, 4.90, 4.93]
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={serie}"
FRED_SERIES = {1: "DGS1", 2: "DGS2", 3: "DGS3", 5: "DGS5", 7: "DGS7", 10: "DGS10"}


@dataclass
class Dossier:
    lob: str
    triangle: Triangle
    proj: Projection
    portfolio: PortfolioData          # valeurs AFFICHÉES (vérité)
    rates_source: str

    @property
    def group(self) -> str:
        return f"{R_CODES[self.lob]}-{self.proj.cohort}-{self.triangle.grcode}"


# --------------------------------------------------------------------------- taux
def _fred_series(serie: str, cache: Path) -> list[tuple[str, float]]:
    f = cache / f"fred_{serie}.csv"
    if not f.exists():
        req = urllib.request.Request(FRED_URL.format(serie=serie), headers={"User-Agent": "ifrs17-copilot/eval"})
        with urllib.request.urlopen(req, timeout=60) as r:          # noqa: S310 (adresse fixe)
            f.write_text(r.read().decode("utf-8"), encoding="utf-8")
    rows = list(csv.reader(io.StringIO(f.read_text(encoding="utf-8"))))[1:]
    return [(d, float(v) / 100) for d, v in rows if v not in (".", "")]


def fred_curve_at(day: date, cache: Path) -> list[float]:
    """Courbe du Trésor américain au dernier jour coté avant ``day``, interpolée de 1 à 10 ans (en fraction)."""
    points = {}
    for m, serie in FRED_SERIES.items():
        vals = [v for d, v in _fred_series(serie, cache) if d < day.isoformat()]
        if not vals:
            raise OSError(f"{serie} : aucune cotation avant le {day}")
        points[m] = vals[-1]
    xs = sorted(points)
    curve = []
    for t in range(1, LAGS + 1):
        lo = max(x for x in xs if x <= t)
        hi = min(x for x in xs if x >= t)
        curve.append(points[lo] if hi == lo else points[lo] + (points[hi] - points[lo]) * (t - lo) / (hi - lo))
    return curve


# --------------------------------------------------------------------------- dossiers
def displayed(proj: Projection, rates: list[float], ra: float, lob: str, group: str) -> PortfolioData:
    """Ce que le document affiche, donc ce qu'un lecteur parfait doit retrouver."""
    n = LAGS
    return PortfolioData(
        group_id=group, currency="USD", unit_multiplier=1000,
        premiums=[round(proj.premium, 2)] + [0.0] * (n - 1),
        outflows=[float(f"{x:.2f}") for x in proj.expected],
        coverage_units=[float(round(proj.premium))] + [0.0] * (n - 1),
        discount_rates=[round(r, 4) for r in rates[:n]], risk_adjustment_pct=ra,
        coverage_months=12, line_of_business=donnees.LOB_LABELS[lob])


def build(paths: list[Path], rates_for, ra: float = 0.03, per_lot: int = 5) -> list[Dossier]:
    """``rates_for(cohorte) -> (courbe, source)``. Ordre du script R : 1988-1997 puis 1998-2007, branche par branche."""
    data = donnees.load(paths)
    out: list[Dossier] = []
    n_files = max((len(v) for v in data.values()), default=0)
    for k in range(n_files):
        for lob in ORDER:
            files = data.get(lob, [])
            if k >= len(files):
                continue
            for tri, proj in select(triangles(files[k]), per_lot=per_lot, require_actual=False):
                curve, src = rates_for(proj.cohort)
                group = f"{R_CODES[lob]}-{proj.cohort}-{tri.grcode}"
                out.append(Dossier(lob=lob, triangle=tri, proj=proj, rates_source=src,
                                   portfolio=displayed(proj, curve, ra, lob, group)))
    return out


def render(d: Dossier, path: Path) -> None:
    from multimodal.synth import SynthDoc, render_pdf

    p = d.portfolio
    doc = SynthDoc(doc_id=path.stem, layout="lignes", scan=False, truth=p, claims=list(p.outflows),
                   expenses=[0.0] * p.n_periods, investment_income=[0.0] * p.n_periods, insurer=d.triangle.name)
    intro = [f"Branche : {p.line_of_business} · Date d'évaluation : 01/01/{d.proj.cohort} · Flux attendus (projection)",
             "Durée de couverture : 1 an (contrats annuels). Les années 2 à 10 correspondent au seul règlement des sinistres."]
    footer = (f"Source : CAS Loss Reserving Database (NAIC Schedule P), code NAIC {d.triangle.grcode}. Sinistres attendus : "
              f"prime × S/P ultime {d.proj.elr * 100:.2f} % × cadence Chain Ladder, estimés sur les données connues au "
              f"31/12/{d.proj.cohort - 1}. Taux : {d.rates_source}. Frais absents de la source. « Contrats en vigueur » : "
              "exposition couverte (prime acquise), nulle après l'année de couverture.").replace(".", ",", 0)
    render_pdf(doc, path, footer=footer, intro=intro)


def case_row(d: Dossier, doc_id: str, pdf: str) -> dict:
    r = compute_csm(d.portfolio)
    return {"id": doc_id, "layout": "prospectif", "scan": False, "attendu": "exact", "piege": "", "pdf": pdf,
            "image": None, "source": {"branche": d.lob, "grcode": d.triangle.grcode, "nom": d.triangle.name,
                                      "cohorte": d.proj.cohort, "taux": d.rates_source},
            "truth": truth_dict(d.portfolio), "csm_attendu": round(r.initial_csm, 4),
            "perte_attendue": round(r.initial_loss_component, 4),
            "backtest": {"sp_attendu": round(d.proj.elr, 6), "attendu": [round(x, 2) for x in d.proj.expected],
                         "reel": d.proj.actual or None},
            "cloture": closing_inputs(d)}


def closing_inputs(d: Dossier) -> dict | None:
    """Données de la première clôture (31/12 de la survenance) : paiement réel de l'année et sinistres futurs
    révisés par Bornhuetter-Ferguson (``reproject_after_year1``) ; None si le réalisé n'est pas publié."""
    rp = reproject_after_year1(d.triangle, d.proj) if d.proj.actual else None
    if rp is None:
        return None
    return {"as_of": f"31/12/{d.proj.cohort}", "actual_outflow": round(rp.paid_year1, 2),
            "revised_outflows": [round(x, 2) for x in rp.revised_future]}


def generate(dossiers: list[Dossier], out_dir: Path = OUT_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, d in enumerate(dossiers, start=1):
        doc_id = f"p{i:03d}"
        render(d, out_dir / f"{doc_id}.pdf")
        rows.append(case_row(d, doc_id, f"data/{out_dir.name}/{doc_id}.pdf"))
    path = out_dir / "cases.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- dossiers du camarade (script R)
def _bar(xs: list[float], d: int = 2) -> str:
    return " | ".join(f"{x:.{d}f}".replace(".", ",") for x in xs)


def import_camarade(dossiers: list[Dossier], ref_csv: Path, pdf_dir: Path | None, out_dir: Path = INDEP_DIR) -> dict:
    """Double calcul R ↔ Python, puis ``attendus.csv`` des 50 PDF du script R pour ``--jeu independants``."""
    ref = list(csv.DictReader(ref_csv.open(encoding="utf-8-sig")))
    by_group = {d.group: d for d in dossiers}
    out_dir.mkdir(parents=True, exist_ok=True)
    lines, report = [], []
    for row in ref:
        d = by_group.get(row["groupe"])
        if d is None:
            report.append({"dossier": row["dossier"], "groupe": row["groupe"], "trouve": False})
            continue
        r_ours = compute_csm(d.portfolio)
        report.append({
            "dossier": row["dossier"], "groupe": row["groupe"], "trouve": True,
            "sp_R": float(row["sp_attendu"]), "sp_py": round(d.proj.elr, 4),
            "sinistres_R": float(row["sinistres_attendus_total"]), "sinistres_py": round(sum(d.proj.expected), 2),
            "reels_R": float(row["sinistres_reels_total"]), "reels_py": sum(d.proj.actual) if d.proj.actual else None,
            "csm_R": float(row["CSM"]) - float(row["Perte_onereux"]),
            "csm_py_valeurs_affichees": round(r_ours.initial_csm - r_ours.initial_loss_component, 2)})
        if pdf_dir is not None and (pdf_dir / row["dossier"]).exists():
            shutil.copy2(pdf_dir / row["dossier"], out_dir / row["dossier"])
        p = d.portfolio
        lines.append(";".join([row["dossier"], p.group_id, "USD", "1000", _bar(p.premiums), _bar(p.outflows),
                               _bar(p.coverage_units, 0), " | ".join(f"{x * 100:.2f} %".replace(".", ",")
                                                                     for x in p.discount_rates),
                               f"{p.risk_adjustment_pct * 100:.2f} %".replace(".", ","), "exact",
                               f"script R de l'équipe, {row['branche']}, survenance {d.proj.cohort}"]))
    head = "fichier;groupe;devise;unite;primes;sorties;unites_couverture;taux;ajustement_risque;attendu;commentaire"
    (out_dir / "attendus.csv").write_text(head + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    found = [x for x in report if x["trouve"]]
    same = [x for x in found if abs(x["sp_R"] - x["sp_py"]) < 5e-5 and abs(x["sinistres_R"] - x["sinistres_py"]) < 0.006]
    summary = {"dossiers": len(ref), "retrouves": len(found), "identiques_au_centime": len(same),
               "ecart_csm_max": max((abs(x["csm_R"] - x["csm_py_valeurs_affichees"]) for x in found), default=0.0),
               "lignes": report}
    return summary


def write_double_calc_report(summary: dict, path: Path = ROOT / "eval" / "double_calcul_report.md") -> None:
    rows = summary["lignes"]
    out = ["# Double calcul : script R de l'équipe contre `actuariat/` (Python)", "",
           f"Généré le {date.today():%d/%m/%Y} par `python -m actuariat.prospectif … --camarade`. Deux programmes écrits "
           "indépendamment, dans deux langages, à partir des mêmes données CAS : ils doivent sélectionner les mêmes "
           "compagnies et projeter les mêmes sinistres attendus.", "",
           "| Mesure | Valeur |", "| --- | --- |",
           f"| Dossiers du script R | {summary['dossiers']} |",
           f"| Retrouvés par le programme Python (même sélection) | {summary['retrouves']} |",
           f"| S/P attendu et sinistres attendus identiques au centime | {summary['identiques_au_centime']} |",
           f"| Plus grand écart de CSM (R sur valeurs non arrondies, Python sur valeurs affichées) | "
           f"{summary['ecart_csm_max']:.2f} k$ |", "",
           "L'écart de CSM ne vient pas de la méthode : le script R calcule sa CSM de référence avant d'arrondir les "
           "montants et les taux affichés dans le PDF. Un lecteur parfait du PDF ne peut retrouver que la CSM des "
           "valeurs affichées ; c'est elle qui sert de vérité.", "",
           "| Dossier | Groupe | S/P R | S/P Python | Sinistres attendus R | Python | CSM R | CSM Python (affiché) |",
           "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for x in rows:
        if not x["trouve"]:
            out.append(f"| {x['dossier']} | {x['groupe']} | introuvable | | | | | |")
            continue
        out.append(f"| {x['dossier']} | {x['groupe']} | {x['sp_R']:.4f} | {x['sp_py']:.4f} | {x['sinistres_R']:,.2f} | "
                   f"{x['sinistres_py']:,.2f} | {x['csm_R']:,.2f} | {x['csm_py_valeurs_affichees']:,.2f} |")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Dossiers prospectifs à montants réels (Chain Ladder, D-072)")
    ap.add_argument("fichiers", nargs="+", type=Path, help="clrd.csv, clrd2025.csv ou fichiers de casact.org")
    ap.add_argument("--courbe", default=None, help="taux spot 1 à 10 ans en %%, séparés par des virgules")
    ap.add_argument("--fred-historique", action="store_true", help="courbe du Trésor à la date d'évaluation (FRED)")
    ap.add_argument("--ra", type=float, default=0.03, help="ajustement pour risque affiché (fraction des sorties)")
    ap.add_argument("--par-lot", type=int, default=5)
    ap.add_argument("--camarade", type=Path, default=None,
                    help="dossier des 50 PDF du script R (avec reference_50_dossiers.csv) : double calcul et attendus.csv")
    args = ap.parse_args()

    if args.fred_historique:
        cache = ROOT / "data" / "cas"
        cache.mkdir(parents=True, exist_ok=True)

        def rates_for(cohort: int):
            day = date(cohort, 1, 1)
            return fred_curve_at(day, cache), f"courbe du Trésor américain (FRED) au {day:%d/%m/%Y}"
    else:
        curve = [float(x) / 100 for x in (args.courbe.split(",") if args.courbe else EIOPA_2026_09)]

        def rates_for(cohort: int):
            return curve, ("courbe saisie" if args.courbe else "courbe sans risque EIOPA (USD) au 30/09/2026")
    dossiers = build(args.fichiers, rates_for, ra=args.ra, per_lot=args.par_lot)
    if args.camarade is not None:
        if not args.fred_historique and args.courbe is None:
            print("courbe du script R (EIOPA USD au 30/09/2026), pour retrouver les valeurs de ses PDF")
        ref = args.camarade / "reference_50_dossiers.csv"
        summary = import_camarade(dossiers, ref, args.camarade)
        write_double_calc_report(summary)
        print(f"double calcul : {summary['retrouves']}/{summary['dossiers']} dossiers retrouvés, "
              f"{summary['identiques_au_centime']} identiques au centime ; écart de CSM max "
              f"{summary['ecart_csm_max']:.2f} (arrondis du PDF) → eval/double_calcul_report.md")
        print(f"→ {INDEP_DIR / 'attendus.csv'} : python -m eval.eval_production --jeu independants")
        return
    path = generate(dossiers)
    print(f"{len(dossiers)} dossiers → {path} : python -m eval.eval_production --jeu prospectif")


if __name__ == "__main__":
    main()
