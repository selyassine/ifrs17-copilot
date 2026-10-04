"""Réponses de référence aux questions fixes de la note (D-037).

Les questions posées à la norme pour fonder une note sont toujours les mêmes (2 ou 3). Les
reposer à chaque dossier coûtait 4 à 6 appels LLM et envoyait 4 dossiers justes sur 7 en
validation humaine, uniquement parce que le vérificateur hésitait sur l'une de ces réponses
(eval/case_report_difficile.md). Elles sont donc calculées une fois, vérifiées une fois,
relues par un humain, puis réutilisées.

    python -m agents.reference            # calcule les réponses manquantes (data/norm_reference.json)
    python -m agents.reference --force    # recalcule tout (après un changement d'index ou de prompt)

Le fichier est dans data/ (hors Git : il contient des extraits de la norme). Une réponse sert de
référence si le vérificateur l'a acceptée, ou si un humain a mis ``"valide": true``.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from agents.schemas import GroundedAnswer
from core.config import ROOT, Settings

REF_PATH = ROOT / "data" / "norm_reference.json"

BASE_QUESTIONS = [
    "Comment la marge sur services contractuels est-elle déterminée lors de la comptabilisation initiale d'un groupe de contrats ?",
    "Comment la marge sur services contractuels est-elle comptabilisée en résultat au fil des périodes, selon les unités de couverture ?",
]
ONEROUS_QUESTION = ("Comment comptabiliser un groupe de contrats d'assurance déficitaire lors de la "
                    "comptabilisation initiale ?")
ALL_QUESTIONS = BASE_QUESTIONS + [ONEROUS_QUESTION]


def load(path: Path = REF_PATH) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {e["question"]: e for e in json.loads(path.read_text(encoding="utf-8"))}


def usable(entry: dict | None) -> GroundedAnswer | None:
    """Réponse réutilisable : acceptée par le vérificateur ou validée par un humain."""
    if not entry or not (entry.get("verdict") == "ok" or entry.get("valide") is True):
        return None
    answer = GroundedAnswer(**entry["answer"])
    return None if answer.refused else answer


def build(settings: Settings, force: bool = False, path: Path = REF_PATH) -> list[dict]:
    from agents.pipeline import verified_answer
    from agents.writer import verdict_label
    from core.llm import LLMClient
    from rag.service import get_retriever

    model = settings.rag_embed_model if settings.rag_mode in ("dense", "hybrid") else ""
    retriever = get_retriever(settings.rag_strategy, model)
    client = LLMClient(settings)
    current = load(path)
    out = []
    for q in ALL_QUESTIONS:
        entry = current.get(q)
        if entry and not force and usable(entry):
            out.append(entry)
            continue
        res = verified_answer(q, settings, client, retriever, case_id="reference")
        out.append({"question": q, "answer": res.answer.model_dump(), "verdict": verdict_label(res.verdict),
                    "problemes": [i.detail for i in (res.verdict.issues if res.verdict else [])],
                    "valide": False, "date": date.today().isoformat(),
                    "prompt_rag": settings.rag_prompt_version})
        print(f"{verdict_label(res.verdict):20} {q[:80]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    from core.config import get_settings

    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    entries = build(get_settings(), force=args.force)
    ok = sum(usable(e) is not None for e in entries)
    print(f"\n{ok}/{len(entries)} réponses utilisables comme référence → {REF_PATH}")
    if ok < len(entries):
        print("Relire les autres dans le fichier ; si elles sont justes, mettre \"valide\": true.")
