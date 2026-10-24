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
            "graph": settings.rag_graph, "store": settings.rag_store, "qdrant_url": settings.qdrant_url}


def rag_status(settings) -> dict:
    """Configuration de recherche réellement active, avec les incohérences détectées (exposée par /health)."""
    warnings = []
    dense = settings.rag_mode in ("dense", "hybrid")
    if dense and not settings.rag_embed_model:
        warnings.append("RAG_MODE dense/hybrid sans RAG_EMBED_MODEL : index dense introuvable")
    if not dense and settings.rag_store == "qdrant":
        warnings.append("RAG_STORE=qdrant inutilisé : RAG_MODE=bm25 n'utilise pas de vecteurs")
    if not dense and settings.rag_agentic:
        warnings.append("agent LangGraph mesuré en hybride (D-050) : RAG_MODE=bm25 donne de moins bons passages")
    if settings.rag_agentic and (settings.rag_questions or settings.rag_graph):
        warnings.append("agent + index des questions / graphe : non additif (D-051), plus lent")
    return {"chunking": settings.rag_strategy, "mode": settings.rag_mode,
            "embedding": settings.rag_embed_model or None,
            "store": settings.rag_store if dense else "aucun (bm25)",
            "agent_langgraph": settings.rag_agentic, "glossaire": settings.rag_glossary,
            "index_questions": settings.rag_questions, "graphe_renvois": settings.rag_graph,
            "reranker": settings.rag_rerank_model or None, "verificateur": settings.verifier_enabled,
            "avertissements": warnings}


@lru_cache(maxsize=4)
def get_retriever(strategy: str = "B", embed_model: str = "", rerank_model: str = "",
                  questions: bool = False, graph: bool = False, store: str = "numpy",
                  qdrant_url: str = "") -> Retriever:
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
        if qindex is None:                      # option non bloquante : la recherche marche sans
            import logging
            logging.getLogger(__name__).warning("RAG_QUESTIONS=1 mais index des questions absent : "
                                                "lancer `python -m rag.qindex --model %s`", embed_model)
    if graph:
        from rag.graph import load_chunk_graph
        cgraph = load_chunk_graph(PROCESSED / "C002_units.jsonl", chunks)
    from rag.retrieve import model_slug
    return Retriever(chunks, encoder=encoder, vectors=vectors, reranker=reranker, qindex=qindex, graph=cgraph,
                     store=store if embed_model else "numpy", qdrant_path=ROOT / "data" / "qdrant",
                     qdrant_url=qdrant_url, collection=f"{strategy}__{model_slug(embed_model or 'bm25')}",
                     options={"rerank": bool(reranker), "questions": bool(qindex), "graphe": bool(cgraph)})
