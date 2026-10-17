"""Query indexing : index des questions hypothétiques de chaque morceau (D-048).

Le cours RAG (stratégies d'indexation) : « index the hypothetical questions a chunk could answer,
then match the user's query to those questions ». Les 1 571 questions générées pour le fine-tuning
(data/finetune/pairs.jsonl, rag/finetune.py) servent ici d'index : une question d'utilisateur écrite
avec des mots de praticien ressemble plus à une question générée qu'au texte de la norme.

Garde-fou : les questions trop proches d'une question d'un des trois jeux de test sont retirées
(même filtre que pour le fine-tuning), sinon l'index « connaîtrait » les réponses du test.

    python -m rag.qindex                         # index BM25 des questions (aucun modèle)
    python -m rag.qindex --model BAAI/bge-m3     # + vecteurs des questions
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from rag.chunking import Chunk, load_chunks
from rag.finetune import OUT_DIR, leaks, load_test_questions, read_jsonl, word_set
from rag.retrieve import QuestionIndex, model_slug

ROOT = Path(__file__).resolve().parent.parent
INDEX_DIR = ROOT / "data" / "index"
PAIRS = OUT_DIR / "pairs.jsonl"


def paths(strategy: str, model: str | None) -> tuple[Path, Path | None]:
    meta = INDEX_DIR / f"questions_{strategy}.json"
    vec = INDEX_DIR / f"questions_{strategy}__{model_slug(model)}.npy" if model else None
    return meta, vec


def collect(records: list[dict], chunks: list[Chunk], tests: list[dict]) -> tuple[list[str], list[str], int]:
    known = {c.chunk_id for c in chunks}
    test_sets = [word_set(q["question"]) for q in tests]
    questions, chunk_ids, removed, seen = [], [], 0, set()
    for rec in records:
        if rec["chunk_id"] not in known:
            continue
        for q in rec["questions"]:
            text = q["question"].strip()
            if text.lower() in seen:
                continue
            if leaks(text, test_sets):
                removed += 1
                continue
            seen.add(text.lower())
            questions.append(text)
            chunk_ids.append(rec["chunk_id"])
    return questions, chunk_ids, removed


def build(strategy: str = "B", model: str | None = None) -> dict:
    chunks = load_chunks(ROOT / "data" / "processed" / f"chunks_{strategy}.jsonl")
    questions, chunk_ids, removed = collect(read_jsonl(PAIRS), chunks, load_test_questions())
    if not questions:
        raise SystemExit(f"{PAIRS} absent ou vide : lancer d'abord `python -m rag.finetune pairs`")
    meta, vec = paths(strategy, model)
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps({"questions": questions, "chunk_ids": chunk_ids, "retirees_fuite": removed},
                               ensure_ascii=False), encoding="utf-8")
    if model:
        from rag.retrieve import SentenceTransformerEncoder
        np.save(vec, SentenceTransformerEncoder(model).encode(questions, is_query=True))
    return {"questions": len(questions), "morceaux_couverts": len(set(chunk_ids)), "retirees_fuite": removed}


def load(chunks: list[Chunk], strategy: str = "B", model: str | None = None) -> QuestionIndex | None:
    meta, vec = paths(strategy, model)
    if not meta.exists():
        return None
    data = json.loads(meta.read_text(encoding="utf-8"))
    pos = {c.chunk_id: i for i, c in enumerate(chunks)}
    keep = [k for k, cid in enumerate(data["chunk_ids"]) if cid in pos]
    vectors = np.load(vec)[keep] if vec is not None and vec.exists() else None
    return QuestionIndex([data["questions"][k] for k in keep], [pos[data["chunk_ids"][k]] for k in keep], vectors)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    ap.add_argument("--strategy", default="B")
    a = ap.parse_args()
    print(json.dumps(build(a.strategy, a.model), ensure_ascii=False))
