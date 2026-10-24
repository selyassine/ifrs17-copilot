"""Niveau 1 de la campagne de tests (D-070) : un grand lot de documents JAMAIS VUS.

Même générateur que les jeux de référence, mais une autre graine et d'autres identifiants : aucun de ces
documents n'a servi à régler un prompt. Documents propres (trois mises en page, scans) et plusieurs séries
des 10 pièges (deux groupes, RA absent, instruction cachée, millions, photo dégradée…).

    python -m multimodal.volume                       # 100 propres + 5 séries de pièges = 150 documents
    python -m multimodal.volume --propres 200 --series 10
    python -m eval.eval_production --jeu volume       # la mesure
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from agents.schemas import truth_dict
from core.config import ROOT
from engine.csm import compute_csm
from multimodal.synth import draw, image_name, render_pdf, render_png
from multimodal.synth_hard import TRAPS, trap_case

OUT_DIR = ROOT / "data" / "volume"
SEED = 2026            # différente des graines des jeux de référence (17 et 31)


def generate(n_propres: int = 100, series: int = 5, seed: int = SEED, out_dir: Path = OUT_DIR,
             images: bool = True) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    cases = []
    for i in range(n_propres):
        d = draw(i, rng)
        d.doc_id = f"v{i + 1:03d}"
        pdf = out_dir / f"{d.doc_id}.pdf"
        render_pdf(d, pdf)
        img = None
        if images:
            render_png(pdf, out_dir / image_name(d), d.scan, seed + i)
            img = f"data/{out_dir.name}/{image_name(d)}"
        csm = compute_csm(d.truth)
        cases.append({"id": d.doc_id, "layout": d.layout, "scan": d.scan, "attendu": "exact", "piege": "",
                      "pdf": f"data/{out_dir.name}/{d.doc_id}.pdf", "image": img,
                      "truth": truth_dict(d.truth),
                      "csm_attendu": round(csm.initial_csm, 4), "perte_attendue": round(csm.initial_loss_component, 4)})
    for s in range(series):
        trng = random.Random(seed * 100 + s)
        for i, (doc_id, trap, expect, description) in enumerate(TRAPS):
            cases.append(trap_case(i, f"s{s + 1}_{doc_id}", trap, expect, description, trng, out_dir,
                                   seed * 100 + s, images))
    path = out_dir / "cases.jsonl"
    path.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n", encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--propres", type=int, default=100)
    ap.add_argument("--series", type=int, default=5, help="séries des 10 pièges")
    ap.add_argument("--sans-images", action="store_true")
    args = ap.parse_args()
    path = generate(args.propres, args.series, images=not args.sans_images)
    n = sum(1 for _ in path.open(encoding="utf-8"))
    print(f"{n} documents dans {path.parent} ; vérité : {path}")


if __name__ == "__main__":
    main()
