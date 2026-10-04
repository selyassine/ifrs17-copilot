"""Documents de test synthétiques pour l'extracteur multimodal (D-027).

On ne dispose d'aucun vrai bordereau d'assureur (confidentiel). On génère donc des « états de
portefeuille » fictifs dont **on connaît la vérité exacte** : chaque document a sa fiche
``PortfolioData`` attendue et son CSM attendu (calculé par ``engine/csm.py``).

Les documents varient comme de vrais documents :

- mise en page : tableau en lignes (une ligne par année), tableau transposé (une colonne par
  année), récapitulatif rédigé + tableau ;
- format des nombres : « 1 234,50 » (français), montants en milliers ou en unités ;
- sorties en deux colonnes (sinistres + frais) qu'il faut additionner ;
- colonne piège à ignorer : « Produits financiers » (exclus des flux d'exécution, B66(a)) ;
- taux plat annoncé dans le texte, ou courbe de taux spot dans le tableau ;
- version image (PNG) de chaque page, et version « scan » (rotation, bruit, flou).

    python -m multimodal.synth              # 15 documents dans data/synth/ + eval/extraction_cases.jsonl
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from agents.schemas import PortfolioData
from core.config import ROOT
from engine.csm import compute_csm

OUT_DIR = ROOT / "data" / "synth"
CASES = ROOT / "eval" / "extraction_cases.jsonl"
LAYOUTS = ("lignes", "colonnes", "recit")
CURRENCIES = {"EUR": "euros", "TND": "dinars tunisiens", "USD": "dollars américains"}
_THOUSANDS = {"EUR": "milliers d'euros", "TND": "milliers de dinars tunisiens",
              "USD": "milliers de dollars américains"}


@dataclass
class SynthDoc:
    doc_id: str
    layout: str
    scan: bool
    truth: PortfolioData
    claims: list[float]            # sinistres (colonne séparée dans le document)
    expenses: list[float]          # frais (colonne séparée dans le document)
    investment_income: list[float]  # colonne piège
    insurer: str


# --------------------------------------------------------------------------- #
# Tirage des données
# --------------------------------------------------------------------------- #
def fr(x: float, decimals: int = 2) -> str:
    """1234.5 → « 1 234,50 » (espace fine insécable comme dans les états financiers)."""
    s = f"{x:,.{decimals}f}".replace(",", " ").replace(".", ",")
    return s


def pct(x: float) -> str:
    return f"{fr(x * 100, 2)} %"


def draw(i: int, rng: random.Random) -> SynthDoc:
    layout = LAYOUTS[i % len(LAYOUTS)]
    n = rng.randint(3, 6)
    multiplier = rng.choice([1, 1_000])
    scale = 1 if multiplier == 1 else 0.001          # montants affichés en milliers
    base = rng.choice([800_000, 1_500_000, 4_000_000]) * scale
    single = rng.random() < 0.4
    if single:
        premiums = [round(base, 2)] + [0.0] * (n - 1)
    else:
        premiums = [round(base / n * rng.uniform(0.9, 1.1), 2) for _ in range(n)]
    total_prem = sum(premiums)
    onerous = rng.random() < 0.2
    loss_ratio = rng.uniform(1.05, 1.2) if onerous else rng.uniform(0.6, 0.85)
    weights = [rng.uniform(0.7, 1.3) for _ in range(n)]
    total_out = total_prem * loss_ratio
    outflows_total = [total_out * w / sum(weights) for w in weights]
    claims = [round(o * rng.uniform(0.75, 0.9), 2) for o in outflows_total]
    expenses = [round(o - c, 2) for o, c in zip(outflows_total, claims, strict=True)]
    outflows = [round(c + e, 2) for c, e in zip(claims, expenses, strict=True)]
    in_force = rng.randint(800, 5000)
    lapse = rng.uniform(0.03, 0.12)
    units = []
    for _ in range(n):
        units.append(float(in_force))
        in_force = int(in_force * (1 - lapse))
    if rng.random() < 0.5:
        rates: float | list[float] = round(rng.uniform(0.015, 0.045), 4)
    else:
        start = rng.uniform(0.015, 0.03)
        rates = [round(start + 0.002 * k, 4) for k in range(n)]
    truth = PortfolioData(
        group_id=f"{rng.choice(['VIE', 'PREV', 'EMP', 'AUTO'])}-{rng.randint(2021, 2025)}-{chr(65 + i % 26)}",
        currency=rng.choice(list(CURRENCIES)),
        unit_multiplier=multiplier,
        premiums=premiums,
        outflows=outflows,
        coverage_units=units,
        discount_rates=rates,
        risk_adjustment_pct=round(rng.choice([0.03, 0.04, 0.05, 0.06, 0.075]), 4),
    )
    income = [round(p * rng.uniform(0.01, 0.04), 2) for p in premiums]
    return SynthDoc(
        doc_id=f"ext{i + 1:02d}", layout=layout, scan=i % 2 == 1, truth=truth,
        claims=claims, expenses=expenses, investment_income=income,
        insurer=rng.choice(["Assurances Atlas", "Mutuelle Carthage", "Horizon Vie", "Sahel Prévoyance"]),
    )


# --------------------------------------------------------------------------- #
# Rendu PDF (reportlab) puis image (pypdfium2 + Pillow)
# --------------------------------------------------------------------------- #
def render_pdf(doc: SynthDoc, path: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    t = doc.truth
    styles = getSampleStyleSheet()
    unit_label = (f"en {_THOUSANDS[t.currency]}" if t.unit_multiplier == 1_000
                  else f"en {CURRENCIES[t.currency]}")
    flat = not isinstance(t.discount_rates, list)
    n = t.n_periods
    years = [f"Année {k + 1}" for k in range(n)]

    story = [
        Paragraph(f"{doc.insurer} — État de portefeuille", styles["Title"]),
        Paragraph(f"Groupe de contrats : <b>{t.group_id}</b> · Devise : {t.currency} · "
                  f"Montants {unit_label}", styles["Normal"]),
        Spacer(1, 10),
    ]
    rate_txt = (f"Le taux d'actualisation retenu est de {pct(t.discount_rates)} pour toutes les échéances."
                if flat else "Les taux d'actualisation (taux spot) figurent dans le tableau.")
    ra_txt = (f"L'ajustement au titre du risque non financier est fixé à {pct(t.risk_adjustment_pct)} "
              f"de la valeur actualisée des sorties de trésorerie.")
    if doc.layout == "recit":
        prem = ("une prime unique de " + fr(t.premiums[0]) + " encaissée en début de première année"
                if all(p == 0 for p in t.premiums[1:]) else "des primes annuelles détaillées ci-dessous")
        story += [Paragraph(
            f"Le groupe {t.group_id} prévoit {prem}. Les sorties de trésorerie se composent des "
            f"sinistres et des frais de gestion. {rate_txt} {ra_txt} Les unités de couverture "
            "correspondent au nombre de contrats en vigueur. Les produits financiers des placements "
            "sont indiqués pour information.", styles["Normal"]), Spacer(1, 10)]
    else:
        story += [Paragraph(f"{rate_txt} {ra_txt}", styles["Normal"]), Spacer(1, 10)]

    headers = ["Primes", "Sinistres", "Frais", "Produits financiers", "Contrats en vigueur"]
    cols = [t.premiums, doc.claims, doc.expenses, doc.investment_income, t.coverage_units]
    fmts = [fr, fr, fr, fr, lambda v: fr(v, 0)]
    if not flat:
        headers.append("Taux spot")
        cols.append(t.discount_rates)
        fmts.append(pct)
    if doc.layout == "colonnes":
        data = [["Poste"] + years] + [[h] + [f(v) for v in col] for h, col, f in zip(headers, cols, fmts, strict=True)]
    else:
        data = [["Période"] + headers] + [
            [years[k]] + [f(col[k]) for col, f in zip(cols, fmts, strict=True)] for k in range(n)
        ]
    table = Table(data, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dde3ea")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
    ]))
    story += [table, Spacer(1, 12),
              Paragraph("Document fictif généré pour l'évaluation du projet IFRS 17 Copilot.", styles["Italic"])]
    SimpleDocTemplate(str(path), pagesize=A4, title=f"Etat {t.group_id}").build(story)


def render_png(pdf_path: Path, png_path: Path, scan: bool, seed: int) -> None:
    import pypdfium2 as pdfium
    from PIL import Image, ImageFilter

    page = pdfium.PdfDocument(str(pdf_path))[0]
    img = page.render(scale=150 / 72).to_pil().convert("L")
    if scan:   # imite un document scanné : légère rotation, bruit, flou
        rng = random.Random(seed)
        img = img.rotate(rng.uniform(-1.5, 1.5), expand=True, fillcolor=255)
        noise = Image.effect_noise(img.size, 18).point(lambda v: v - 128)
        img = Image.blend(img, Image.merge("L", [noise]).convert("L"), 0.08)
        img = img.filter(ImageFilter.GaussianBlur(0.6))
    if scan:
        img.save(png_path, quality=80)      # un scan est en général un JPEG
    else:
        img.save(png_path, optimize=True)


def image_name(d: SynthDoc) -> str:
    return f"{d.doc_id}.jpg" if d.scan else f"{d.doc_id}.png"


def generate(n_docs: int = 15, seed: int = 17, out_dir: Path = OUT_DIR,
             cases_path: Path = CASES, images: bool = True) -> list[SynthDoc]:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = [draw(i, rng) for i in range(n_docs)]
    lines = []
    for d in docs:
        pdf = out_dir / f"{d.doc_id}.pdf"
        render_pdf(d, pdf)
        if images:
            render_png(pdf, out_dir / image_name(d), d.scan, seed + int(d.doc_id[3:]))
        csm = compute_csm(d.truth)
        lines.append(json.dumps({
            "id": d.doc_id, "layout": d.layout, "scan": d.scan,
            "pdf": f"data/synth/{d.doc_id}.pdf", "image": f"data/synth/{image_name(d)}",
            "truth": d.truth.model_dump(exclude={"field_confidence", "future_service_adjustments"}),
            "csm_attendu": round(csm.initial_csm, 4), "perte_attendue": round(csm.initial_loss_component, 4),
        }, ensure_ascii=False))
    cases_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return docs


if __name__ == "__main__":
    docs = generate()
    onerous = sum(compute_csm(d.truth).onerous for d in docs)
    print(f"{len(docs)} documents dans {OUT_DIR} ({onerous} déficitaires) ; vérité : {CASES}")
