"""Back-testing des hypothèses et de la première clôture (D-077) : nos estimations étaient-elles bonnes ?

Trois mesures, sur données réelles (CAS Schedule P) :
1. **Projection** : pour chaque dossier prospectif, sinistres attendus au 1er janvier contre sinistres
   réellement payés ensuite (jusqu'à 10 ans) ; par branche, rapport moyen et part des dossiers à ±20 % ;
2. **Première clôture** : pour les dossiers dont le réalisé est publié, la note de clôture est calculée avec
   le paiement réel de l'année et les sinistres futurs révisés (Bornhuetter-Ferguson) : écarts d'expérience,
   révision des estimations, résultat de la période contre attendu, et contrôle du rapprochement du passif ;
3. **Calibration du RA** : rappel du registre des hypothèses (cohortes, biais, dispersion par branche).

    python -m actuariat.backtest data/cas/clrd.csv data/cas/clrd2025.csv --reference reference_50_dossiers.csv
"""

from __future__ import annotations

import argparse
import csv
import statistics
from datetime import date
from pathlib import Path

from actuariat import donnees
from actuariat.prospectif import EIOPA_2026_09, R_CODES, build, closing_inputs
from actuariat.registre import current
from core.config import ROOT
from engine.cloture import ClosingInput, close_first_period
from engine.csm import compute_csm

REPORT = ROOT / "eval" / "backtest_report.md"


def run(paths: list[Path], reference: Path | None = None) -> dict:
    curve = [x / 100 for x in EIOPA_2026_09]
    dossiers = build(paths, lambda c: (curve, "courbe EIOPA"))
    ref = {}
    if reference is not None and reference.exists():
        ref = {r["groupe"]: r for r in csv.DictReader(reference.open(encoding="utf-8-sig"))}
    proj_rows, close_rows = [], []
    for d in dossiers:
        expected = sum(d.proj.expected)
        actual = sum(d.proj.actual) if d.proj.actual else (float(ref[d.group]["sinistres_reels_total"])
                                                            if d.group in ref else None)
        if actual is not None:
            proj_rows.append({"groupe": d.group, "branche": d.lob, "cohorte": d.proj.cohort, "attendu": expected,
                              "reel": actual, "ratio": actual / expected if expected else None,
                              "sp_attendu": d.proj.elr, "sp_reel": actual / d.proj.premium})
        ci = closing_inputs(d)
        if ci is not None:
            r = compute_csm(d.portfolio)
            c = close_first_period(d.portfolio, ClosingInput(**ci), r)
            close_rows.append({"groupe": d.group, "branche": d.lob, "attendu_annee1": d.portfolio.outflows[0],
                               "paye_annee1": ci["actual_outflow"], "experience": c.experience_adjustment,
                               "revision": c.future_flows_change + c.ra_future_change,
                               "resultat": c.insurance_service_result, "resultat_attendu": c.expected_service_result,
                               "ecart_rapprochement": c.reconciliation_gap})
    return {"projection": proj_rows, "cloture": close_rows}


def _branch_table(rows: list[dict]) -> list[list[str]]:
    out = []
    for code in sorted({r["branche"] for r in rows}, key=lambda c: list(R_CODES).index(c)):
        xs = [r["ratio"] for r in rows if r["branche"] == code and r["ratio"]]
        within = sum(0.8 <= x <= 1.2 for x in xs)
        out.append([donnees.LOB_LABELS[code], str(len(xs)), f"{statistics.mean(xs):.2f}", f"{statistics.median(xs):.2f}",
                    f"{min(xs):.2f} à {max(xs):.2f}", f"{within}/{len(xs)}"])
    xs = [r["ratio"] for r in rows if r["ratio"]]
    out.append(["Ensemble", str(len(xs)), f"{statistics.mean(xs):.2f}", f"{statistics.median(xs):.2f}",
                f"{min(xs):.2f} à {max(xs):.2f}", f"{sum(0.8 <= x <= 1.2 for x in xs)}/{len(xs)}"])
    return out


def write_report(res: dict, path: Path = REPORT) -> None:
    reg = current()
    proj, close = res["projection"], res["cloture"]
    md = ["# Back-testing des hypothèses actuarielles", "",
          f"Généré le {date.today():%d/%m/%Y} par `python -m actuariat.backtest`. Données réelles CAS Schedule P ; "
          f"registre des hypothèses v{reg.get('version', '?')}.", ""]
    if proj:
        md += ["## 1. Projection : sinistres attendus au 1er janvier contre sinistres réellement payés", "",
               "Rapport = sinistres réels / sinistres attendus (1 = projection exacte).", "",
               "| Branche | Dossiers | Rapport moyen | Médian | Étendue | Dans ±20 % |", "| --- | --- | --- | --- | --- | --- |"]
        md += ["| " + " | ".join(row) + " |" for row in _branch_table(proj)]
        worst = sorted(proj, key=lambda r: -abs((r["ratio"] or 1) - 1))[:5]
        md += ["", "Écarts les plus forts :", "", "| Groupe | S/P attendu | S/P réel | Rapport |", "| --- | --- | --- | --- |"]
        md += [f"| {r['groupe']} | {r['sp_attendu']:.1%} | {r['sp_reel']:.1%} | {r['ratio']:.2f} |" for r in worst]
        md += ["", "Lecture : une projection mécanique (Chain Ladder et S/P moyen du passé, sans jugement) se trompe "
               "fortement pour certaines compagnies (changement de souscription, sinistres graves, données de peu "
               "d'années). C'est l'incertitude que l'ajustement pour risque doit couvrir, et la raison pour laquelle "
               "une note n'est jamais diffusée sans revue actuarielle.", ""]
    if close:
        gaps = max(abs(r["ecart_rapprochement"]) for r in close)
        md += ["## 2. Première clôture sur le réalisé", "",
               f"{len(close)} dossiers dont le réalisé est publié (survenance 2007, clôture au 31/12/2007). Paiement "
               "réel de l'année et sinistres futurs révisés par Bornhuetter-Ferguson ; la couverture d'un an étant "
               "achevée, la révision va en charges (services passés, B97(b)).", "",
               "| Groupe | Payé attendu | Payé réel | Écart d'expérience | Révision des flux futurs | Résultat des services | Attendu |",
               "| --- | --- | --- | --- | --- | --- | --- |"]
        md += [f"| {r['groupe']} | {r['attendu_annee1']:,.0f} | {r['paye_annee1']:,.0f} | {r['experience']:+,.0f} | "
               f"{r['revision']:+,.0f} | {r['resultat']:,.0f} | {r['resultat_attendu']:,.0f} |" for r in close]
        md += ["", f"Rapprochement du passif (ouverture + flux + charges financières − résultat des services = clôture) : "
               f"écart maximal {gaps:.2e} sur {len(close)} dossiers.", ""]
    cal = reg["ajustement_risque"].get("branches", {})
    if cal:
        md += ["## 3. Calibration de l'ajustement pour risque (registre)", "",
               f"Niveau de confiance cible : {reg['ajustement_risque']['niveau_cible']:.0%}. Méthode : "
               f"{reg['ajustement_risque']['methode']}.", "",
               "| Branche | Cohortes | Biais moyen | P10 | P90 | CV | RA au niveau cible |", "| --- | --- | --- | --- | --- | --- | --- |"]
        level = f"{reg['ajustement_risque']['niveau_cible']:.3f}".rstrip("0").rstrip(".")
        for c in cal.values():
            md.append(f"| {c['label']} | {c['kept']} | {c['bias']:.2f} | {c['ratio_p10']:.2f} | {c['ratio_p90']:.2f} | "
                      f"{c['cv']:.1%} | {c['ra_pct'].get(level, float('nan')):.1%} |")
        missing = [donnees.LOB_LABELS[k] for k in donnees.LOB_LABELS if k not in cal]
        if missing:
            md += ["", f"Non calibrées (moins de 30 cohortes exploitables) : {', '.join(missing)} ; par prudence, la note "
                   "leur applique la plus forte volatilité calibrée et le signale (le back-testing de la responsabilité "
                   "médicale montre des écarts jusqu'à × 3,7 : une volatilité faible par défaut serait dangereuse)."]
        md += ["", "Les dossiers du script R portent un RA de 3 % des sorties : selon la branche, cela correspond à un "
               "niveau de confiance d'environ 60 % (la loi lognormale est asymétrique : un RA nul vaut déjà plus de 50 %), loin du niveau cible ; la note le signale à l'actuaire.", ""]
    path.write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Back-testing des projections et de la première clôture")
    ap.add_argument("fichiers", nargs="+", type=Path)
    ap.add_argument("--reference", type=Path, default=None, help="reference_50_dossiers.csv du script R (réel 1997)")
    args = ap.parse_args()
    res = run(args.fichiers, args.reference)
    write_report(res)
    print(f"projection : {len(res['projection'])} dossiers ; clôture : {len(res['cloture'])} dossiers → {REPORT}")


if __name__ == "__main__":
    main()
