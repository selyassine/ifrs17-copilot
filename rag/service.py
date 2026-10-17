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


def retrieval_options(settings) -> dict:
    """Options avancées lues dans .env (D-048, D-049)."""
    return {"rerank_model": settings.rag_rerank_model, "questions": settings.rag_questions,
            "graph": settings.rag_graph}


@lru_cache(maxsize=4)
def get_retriever(strategy: str = "B", embed_model: str = "", rerank_model: str = "",
                  questions: bool = False, graph: bool = False) -> Retriever:
    path = PROCESSED / f"chunks_{strategy}.jsonl"
    if not path.exists():
        raise IndexMissing(f"{path.name} introuvable : lancer `python -m rag.build_index`")
    chunks = load_chunks(path)
    encoder = vectors = None
    if embed_model:
        vectors = load_dense(INDEX_DIR, strategy, embed_model, chunks)
        if vectors is None:
            raise IndexMissing(f"index dense absent pour {embed_model} : "
                               f"lancer `python -m rag.build_index --dense --model {embed_model}`")
        from rag.retrieve import SentenceTransformerEncoder
        encoder = SentenceTransformerEncoder(embed_model)
    reranker = qindex = cgraph = None
    if rerank_model:
        from rag.retrieve import CrossEncoderReranker
        reranker = CrossEncoderReranker(rerank_model)
    if questions:
        from rag.qindex import load as load_qindex
        qindex = load_qindex(chunks, strategy, embed_model or None)
        if qindex is None:
            raise IndexMissing("index des questions absent : lancer `python -m rag.qindex`")
    if graph:
        from rag.graph import load_chunk_graph
        cgraph = load_chunk_graph(PROCESSED / "C002_units.jsonl", chunks)
    return Retriever(chunks, encoder=encoder, vectors=vectors, reranker=reranker, qindex=qindex, graph=cgraph,
                     options={"rerank": bool(reranker), "questions": bool(qindex), "graphe": bool(cgraph)})
