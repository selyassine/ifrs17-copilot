"""Chargement paresseux du moteur de recherche pour l'API (une fois par processus)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from rag.chunking import load_chunks
from rag.retrieve import Retriever, load_dense

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
INDEX_DIR = ROOT / "data" / "index"


class IndexMissing(RuntimeError):
    pass


@lru_cache(maxsize=4)
def get_retriever(strategy: str = "B", embed_model: str = "") -> Retriever:
    path = PROCESSED / f"chunks_{strategy}.jsonl"
    if not path.exists():
        raise IndexMissing(f"{path.name} introuvable : lancer `python -m rag.build_index`")
    chunks = load_chunks(path)
    if not embed_model:
        return Retriever(chunks)
    vectors = load_dense(INDEX_DIR, strategy, embed_model, chunks)
    if vectors is None:
        raise IndexMissing(f"index dense absent pour {embed_model} : "
                           f"lancer `python -m rag.build_index --dense --model {embed_model}`")
    from rag.retrieve import SentenceTransformerEncoder

    return Retriever(chunks, encoder=SentenceTransformerEncoder(embed_model), vectors=vectors)
