"""Niveau 3 de la campagne de tests (D-070) : des états de portefeuille construits sur des DONNÉES RÉELLES.

Idée de l'équipe (script R d'un camarade), reprise en Python et corrigée :
- primes et sinistres réels : CAS Loss Reserving Database (NAIC Schedule P, compagnies américaines,
  survenances 1988 à 1997, 10 années de développement), base publique de la Casualty Actuarial Society ;
- courbe de taux réelle : rendements des bons du Trésor américain (FRED, 1 à 10 ans), interpolés ;
- plusieurs mises en page, dont une « libre » sans grille de tableau (texte positionné, comme le script R).

Données publiques : elles peuvent être envoyées aux LLM gratuits, contrairement à de vrais dossiers clients.

Corrections par rapport au script d'origine :
1. la vérité est calculée sur les valeurs AFFICHÉES dans le PDF (taux arrondis à 0,01 %), sinon la CSM
   attendue ne correspond pas au document et un extracteur parfait serait compté faux ;
2. les cohortes avec un paiement incrémental négatif (recours, annulations) sont écartées et comptées :
   le moteur, comme la norme, attend des sorties positives ;
3. la CSM attendue est calculée par le moteur du projet (mêmes conventions que tout le reste).

Limites assumées (à dire à l'oral) : une police d'accidents du travail couvre un an ; ici, les paiements des
10 années de développement sont traités comme les sorties d'un groupe sur 10 périodes, et les unités de
couverture sont les sinistres restant à payer en début d'année (convention de test, pas un traitement
IFRS 17 réel, qui relèverait du passif pour sinistres survenus et souvent de la PAA). La courbe est
d'aujourd'hui, appliquée à des survenances anciennes. Ce jeu teste la LECTURE de montants réels et le
calcul, pas la modélisation actuarielle.

    python -m multimodal.real_cas                         # télécharge, 60 documents (6 branches)
    python -m multimodal.real_cas --n 120 --taux-plat 0.04
    python -m multimodal.real_cas --fichier wkcomp_pos.csv # fichier déjà téléchargé
    python -m eval.eval_production --jeu reel
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import urllib.request
from collections import defaultdict
from pathlib import Path

from agents.schemas import PortfolioData, truth_dict
from core.config import ROOT
from engine.csm import compute_csm
from multimodal.synth import SynthDoc, fr, pct, render_pdf, render_png

OUT_DIR = ROOT / "data" / "real_cas"
CAS_URL = "https://www.casact.org/sites/default/files/2021-04/{ligne}_pos.csv"
LIGNES = {"wkcomp": "WC", "comauto": "CA", "ppauto": "PA", "othliab": "OL", "medmal": "MM", "prodliab": "PL"}
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={serie}"
FRED_SERIES = {1: "DGS1", 2: "DGS2", 3: "DGS3", 5: "DGS5", 7: "DGS7", 10: "DGS10"}
FOOTER = ("Montants réels : CAS Loss Reserving Database (NAIC Schedule P), en milliers de dollars. "
          "Document construit pour l'évaluation du projet IFRS 17 Copilot.")


# --------------------------------------------------------------------------- données
def _download(url: str, timeout: float = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "ifrs17-copilot/eval"})
    with urllib.request.urlopen(req, timeout=timeout) as r:     # noqa: S310 (URL fixes, publiques)
        return r.read().decode("utf-8", errors="replace")


def read_cas(text: str) -> list[dict]:
    """Lignes du CSV CAS, colonnes sans leur suffixe de branche : « EarnedPremNet_D », « _C », « _B »,
    « _h1 », « _F2 », « _R1 » selon la branche → « EarnedPremNet » (comme sub("_[^_]+$", "", …) en R)."""
    head = text.lstrip("\ufeff").lstrip()[:200].lower()
    if head.startswith("<") or "<html" in head:
        raise OSError("le site a renvoyé une page web au lieu du fichier CSV (adresse déplacée ?)")
    out = []
    for r in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))):
        clean = {}
        for k, v in r.items():
            if k is None:
                continue
            key = k.strip()
            if "_" in key and key.split("_", 1)[0] not in ("",):
                key = key.rsplit("_", 1)[0]
            clean[key] = (v or "").strip()
        out.append(clean)
    if out:
        missing = [c for c in ("GRCODE", "GRNAME", "AccidentYear", "DevelopmentLag", "CumPaidLoss", "EarnedPremNet")
                   if c not in out[0]]
        if missing:
            raise OSError(f"colonnes introuvables dans le fichier CAS : {missing} ; colonnes lues : {list(out[0])}")
    return out


def cohorts(rows: list[dict], ligne: str, lags: int = 10, recouvrements: bool = False) -> tuple[list[dict], int]:
    """Cohortes (compagnie, année de survenance) complètes et exploitables ; renvoie aussi le nombre écarté.
    Un paiement incrémental négatif est un recouvrement (recours, subrogation, sauvetage : B65 k). Sans
    ``recouvrements`` ces cohortes sont écartées (comportement mesuré en D-070) ; avec, elles sont gardées
    et l'année négative devient un recouvrement (D-071)."""
    by = defaultdict(list)
    for r in rows:
        if r.get("Single", "1") not in ("1", "1.0"):
            continue
        by[(r["GRCODE"], r["AccidentYear"])].append(r)
    keep, dropped = [], 0
    for (code, year), rs in by.items():
        rs.sort(key=lambda r: int(float(r["DevelopmentLag"])))
        if len(rs) != lags:
            continue
        prem = float(rs[0]["EarnedPremNet"] or 0)
        cum = [float(r["CumPaidLoss"] or 0) for r in rs]
        inc = [cum[0]] + [cum[k] - cum[k - 1] for k in range(1, lags)]
        if prem <= 0 or sum(inc) <= 0:
            continue
        if any(x < 0 for x in inc) and not recouvrements:
            dropped += 1                       # recours, annulations : sorties négatives
            continue
        keep.append({"ligne": ligne, "grcode": code, "nom": rs[0]["GRNAME"], "annee": int(float(year)),
                     "prime": prem, "sinistres": inc})
    return keep, dropped


def fred_curve(n: int = 10) -> tuple[list[float], str]:
    points = {}
    date = ""
    for m, serie in FRED_SERIES.items():
        rows = [r for r in csv.reader(io.StringIO(_download(FRED_URL.format(serie=serie)))) if len(r) == 2][1:]
        vals = [(d, float(v)) for d, v in rows if v not in (".", "")]
        date, points[m] = vals[-1][0], vals[-1][1] / 100
    xs = sorted(points)
    curve = []
    for t in range(1, n + 1):
        lo = max(x for x in xs if x <= t) if any(x <= t for x in xs) else xs[0]
        hi = min(x for x in xs if x >= t) if any(x >= t for x in xs) else xs[-1]
        r = points[lo] if hi == lo else points[lo] + (points[hi] - points[lo]) * (t - lo) / (hi - lo)
        curve.append(r)
    return curve, f"bons du Trésor américain (FRED) au {date}"


# --------------------------------------------------------------------------- documents
def portfolio(c: dict, rates: list[float], ra: float) -> PortfolioData:
    n = len(c["sinistres"])
    # la source ne donne que le paiement net de l'année : négatif → recouvrement, sans inventer de brut
    gross = [max(x, 0.0) for x in c["sinistres"]]
    rec = [round(max(-x, 0.0), 2) for x in c["sinistres"]]
    remaining = [sum(gross[k:]) for k in range(n)]
    return PortfolioData(
        group_id=f"{LIGNES[c['ligne']]}-{c['annee']}-{c['grcode']}", currency="USD", unit_multiplier=1000,
        premiums=[round(c["prime"], 2)] + [0.0] * (n - 1),
        outflows=[round(x, 2) for x in gross],
        recoveries=rec if any(rec) else None,
        coverage_units=[float(round(x)) for x in remaining],
        # vérité = valeurs affichées : « 4,12 % » ↔ 0,0412 (correction 1)
        discount_rates=[round(r, 4) for r in rates[:n]],
        risk_adjustment_pct=ra)


def render_libre(d: SynthDoc, path: Path, note: str, extra: str = "") -> None:
    """Mise en page sans grille (texte positionné en colonnes), comme le script R d'origine."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    t = d.truth
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    y = h - 60
    c.setFont("Helvetica-Bold", 14)
    c.drawString(45, y, f"{d.insurer} — État de portefeuille")
    c.setFont("Helvetica", 8.5)
    y -= 22
    c.drawString(45, y, f"Groupe de contrats : {t.group_id} · Devise : USD · Montants en milliers de dollars américains")
    y -= 14
    c.drawString(45, y, "Les taux d'actualisation (taux spot) figurent dans le tableau. L'ajustement au titre du risque non")
    y -= 12
    c.drawString(45, y, f"financier est fixé à {pct(t.risk_adjustment_pct)} de la valeur actualisée des sorties de trésorerie.")
    with_rec = d.recovery_column and bool(t.recoveries) and any(t.recoveries)
    cols = [45, 105, 190, 265, 320, 410, 490]
    heads = ["Période", "Primes", "Sinistres", "Frais", "Produits financiers", "Contrats en vigueur", "Taux spot"]
    if with_rec:
        cols = [45, 95, 160, 225, 270, 340, 410, 490]
        heads.insert(4, "Recouvrements")
    y -= 30
    c.setFont("Helvetica-Bold", 8)
    for x, s in zip(cols, heads, strict=True):
        c.drawString(x, y, s)
    c.line(45, y - 4, 550, y - 4)
    c.setFont("Helvetica", 8)
    for k in range(t.n_periods):
        y -= 16
        vals = [f"Année {k + 1}", fr(t.premiums[k]), fr(d.claims[k]), fr(0), fr(0), fr(t.coverage_units[k], 0),
                pct(t.discount_rates[k])]
        if with_rec:
            vals.insert(4, fr(t.recoveries[k]))
        for x, s in zip(cols, vals, strict=True):
            c.drawString(x, y, s)
    c.line(45, y - 6, 550, y - 6)
    c.setFont("Helvetica", 7)
    lines = [FOOTER, note, "« Contrats en vigueur » : sinistres restant à payer en début d'année "
             "(unités de couverture, convention de test)."] + ([extra] if extra else [])
    for k, line in enumerate(lines):
        c.drawString(45, y - 24 - 11 * k, line[:150])
    c.save()


def generate(n: int = 60, lignes: list[str] | None = None, rates: list[float] | None = None, source_taux: str = "",
             seed: int = 1988, out_dir: Path = OUT_DIR, fichiers: dict[str, Path] | None = None,
             images: bool = True, recouvrements: str = "non") -> tuple[Path, dict]:
    """``recouvrements`` : « non » (D-070, cohortes avec paiements négatifs écartées), « inclure »
    (tirage dans toutes les cohortes), « seulement » (uniquement des cohortes avec recouvrements)."""
    lignes = lignes or list(LIGNES)
    out_dir.mkdir(parents=True, exist_ok=True)
    pool, stats = [], {}
    for ligne in lignes:
        local = (fichiers or {}).get(ligne) or out_dir / f"{ligne}_pos.csv"
        try:
            if not local.exists():
                local.write_text(_download(CAS_URL.format(ligne=ligne)), encoding="utf-8")
            found, dropped = cohorts(read_cas(local.read_text(encoding="utf-8", errors="replace")), ligne,
                                     recouvrements=recouvrements != "non")
            if recouvrements == "seulement":
                found = [c for c in found if any(x < 0 for x in c["sinistres"])]
        except OSError as exc:                 # une branche inaccessible n'arrête pas les autres
            print(f"  branche {ligne} ignorée : {exc}")
            stats[ligne] = {"erreur": str(exc)[:200]}
            if local.exists() and ligne not in (fichiers or {}):
                local.unlink()                 # fichier téléchargé illisible : retéléchargé la prochaine fois
            continue
        pool += found
        stats[ligne] = {"cohortes": len(found), "ecartees_sorties_negatives": dropped,
                        "avec_recouvrements": sum(any(x < 0 for x in c["sinistres"]) for c in found)}
    if not pool:
        raise OSError("aucune branche CAS exploitable (voir les messages ci-dessus)")
    if rates is None:
        try:
            rates, source_taux = fred_curve()
        except (OSError, ValueError, IndexError) as exc:
            raise OSError(f"courbe FRED inaccessible ({exc}) : relancer avec --taux-plat 0.04") from exc
    rng = random.Random(seed)
    chosen = rng.sample(pool, min(n, len(pool)))
    layouts = ["lignes", "recit", "libre"]
    cases = []
    for i, c in enumerate(chosen):
        p = portfolio(c, rates, rng.choice([0.02, 0.03, 0.04, 0.05, 0.06]))
        # recouvrements : une fois sur deux dans une colonne à part, sinon en sinistres négatifs (comme la source)
        col = (i // 3) % 2 == 0
        claims = list(p.outflows) if col or not p.recoveries else [o - r for o, r in zip(p.outflows, p.recoveries, strict=True)]
        d = SynthDoc(doc_id=f"r{i + 1:03d}", layout=layouts[i % 3], scan=i % 3 == 1, truth=p, claims=claims,
                     expenses=[0.0] * p.n_periods, investment_income=[0.0] * p.n_periods, insurer=c["nom"].title(),
                     recovery_column=col)
        pdf = out_dir / f"{d.doc_id}.pdf"
        note = f"Taux : {source_taux}. Frais absents de la source. Survenance {c['annee']}, branche {c['ligne']}."
        extra = ("Un montant de sinistres négatif correspond à des recouvrements nets de l'année (recours, subrogation)."
                 if p.recoveries and not col else "")
        if d.layout == "libre":
            render_libre(d, pdf, note, extra)
        else:
            render_pdf(d, pdf, footer=f"{FOOTER} {note} {extra}".strip())
        img = None
        if images:
            name = f"{d.doc_id}.jpg" if d.scan else f"{d.doc_id}.png"
            render_png(pdf, out_dir / name, d.scan, seed + i)
            img = f"data/{out_dir.name}/{name}"
        csm = compute_csm(p)
        cases.append({"id": d.doc_id, "layout": d.layout, "scan": d.scan, "attendu": "exact", "piege": "",
                      "pdf": f"data/{out_dir.name}/{d.doc_id}.pdf", "image": img, "source": {k: c[k] for k in ("ligne", "grcode", "nom", "annee")},
                      "truth": truth_dict(p),
                      "csm_attendu": round(csm.initial_csm, 4), "perte_attendue": round(csm.initial_loss_component, 4)})
    path = out_dir / "cases.jsonl"
    path.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n", encoding="utf-8")
    stats |= {"documents": len(cases), "deficitaires": sum(c["perte_attendue"] > 0 for c in cases), "taux": source_taux,
              "documents_avec_recouvrements": sum(bool(c["truth"].get("recoveries")) for c in cases)}
    (out_dir / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    return path, stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--lignes", default=",".join(LIGNES), help="branches CAS, ex. wkcomp,ppauto")
    ap.add_argument("--fichier", action="append", default=[], help="CSV déjà téléchargé (nom : <branche>_pos.csv)")
    ap.add_argument("--taux-plat", type=float, default=None, help="sans Internet pour FRED : taux plat, ex. 0.04")
    ap.add_argument("--sans-images", action="store_true")
    ap.add_argument("--graine", type=int, default=1988, help="autre graine = autre tirage de cohortes (nouveau lot de test)")
    ap.add_argument("--recouvrements", choices=["non", "inclure", "seulement"], default="non",
                    help="cohortes avec paiements négatifs (recouvrements, B65 k, D-071)")
    args = ap.parse_args()
    files = {Path(f).name.split("_")[0]: Path(f) for f in args.fichier}
    rates, src = (None, "")
    if args.taux_plat is not None:
        rates, src = [args.taux_plat] * 10, f"taux plat de {args.taux_plat:.2%}"
    try:
        path, stats = generate(args.n, args.lignes.split(","), rates, src, seed=args.graine, fichiers=files,
                               images=not args.sans_images, recouvrements=args.recouvrements)
    except OSError as exc:
        raise SystemExit(f"Téléchargement impossible ({exc}). Télécharger à la main depuis "
                         f"{CAS_URL.format(ligne='wkcomp')} puis : --fichier wkcomp_pos.csv ; "
                         "et, sans accès à FRED : --taux-plat 0.04") from exc
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    print(f"→ {path}")


if __name__ == "__main__":
    main()
