"""Recherche : lexicale (BM25), dense (embeddings) et hybride (fusion RRF).

Configurations comparées dans l'évaluation (section 6.4 du planning) :
    bm25    : BM25 Okapi, analyseur français maison (minuscules, accents, mots vides, racinisation légère)
    dense   : embeddings (BGE-M3 ou Qwen3-Embedding) + similarité cosinus
    hybrid  : fusion des deux listes par Reciprocal Rank Fusion (k = 60)
    options (D-048, D-049), activables séparément pour être mesurées une à une :
      questions : index des questions hypothétiques de chaque morceau (query indexing), 3ᵉ classement RRF
      graphe    : voisins par les renvois de la norme (« voir paragraphe B96 »), classement RRF de poids 0,5
      rerank    : cross-encoder (bge-reranker-v2-m3) qui réordonne les 20 premiers candidats

Stockage des vecteurs :
    NumpyStore  : matrice en mémoire, sauvegardée en .npy ; suffit pour quelques milliers de chunks
    QdrantStore : Qdrant en mode embarqué (fichier local, sans serveur), avec filtres de métadonnées
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
import zlib
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from rag.chunking import Chunk

# --------------------------------------------------------------------------- #
# Analyseur français pour BM25
# --------------------------------------------------------------------------- #
STOPWORDS = set("""
a au aux avec ce ces cet cette dans de des du elle elles en et eux il ils je la le les leur leurs
lui ma mais me meme mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur
ta te tes toi ton tu un une vos votre vous c d j l m n s t y ete etre est sont sera peut doit doivent
ainsi afin dont lorsque lors selon si sous entre tout tous toute toutes autre autres meme cas
quel quelle quels quelles comment quoi quand
""".split())

_SUFFIXES = sorted([
    "issements", "issement", "ements", "ement", "ations", "ation", "ateurs", "ateur", "atrices",
    "atrice", "ances", "ance", "ences", "ence", "ables", "able", "ibles", "ible", "istes", "iste",
    "ismes", "isme", "ites", "ite", "ifs", "ives", "ive", "if", "euses", "euse", "eux", "eurs",
    "eur", "elles", "elle", "els", "el", "aux", "ales", "ale", "al", "ees", "ee", "ers", "er",
    "es", "s", "x", "e",
], key=len, reverse=True)


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def stem(token: str) -> str:
    if token.isdigit() or re.match(r"^[bc]\d", token) or len(token) <= 4:
        return token
    for suf in _SUFFIXES:
        if token.endswith(suf) and len(token) - len(suf) >= 4:
            return token[: -len(suf)]
    return token


def analyze(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", fold(text).replace("'", " "))
    return [stem(t) for t in tokens if t not in STOPWORDS and len(t) > 1]


class BM25:
    def __init__(self, docs: Sequence[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tfs = [Counter(analyze(d)) for d in docs]
        self.lens = [sum(tf.values()) for tf in self.tfs]
        self.avgdl = sum(self.lens) / max(len(self.lens), 1)
        df: Counter = Counter()
        for tf in self.tfs:
            df.update(tf.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.postings: dict[str, list[int]] = defaultdict(list)
        for i, tf in enumerate(self.tfs):
            for t in tf:
                self.postings[t].append(i)

    def search(self, query: str, k: int = 10) -> list[tuple[int, float]]:
        scores: dict[int, float] = defaultdict(float)
        for t in set(analyze(query)):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i in self.postings[t]:
                f = self.tfs[i][t]
                norm = f + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avgdl)
                scores[i] += idf * f * (self.k1 + 1) / norm
        return sorted(scores.items(), key=lambda x: -x[1])[:k]


# --------------------------------------------------------------------------- #
# Embeddings
# --------------------------------------------------------------------------- #
class Encoder(Protocol):
    name: str

    def encode(self, texts: list[str], is_query: bool = False) -> np.ndarray: ...


def _l2(x: np.ndarray) -> np.ndarray:
    return x / np.clip(np.linalg.norm(x, axis=1, keepdims=True), 1e-12, None)


class SentenceTransformerEncoder:
    """BGE-M3 : pas de préfixe. Qwen3-Embedding : instruction obligatoire côté requête."""

    QUERY_PROMPTS = {
        "Qwen/Qwen3-Embedding-0.6B": "Instruct: Étant donné une question sur la norme IFRS 17, "
                                     "retrouver les paragraphes de la norme qui y répondent\nQuery: ",
    }

    def __init__(self, model_name: str = "BAAI/bge-m3", device: str | None = None,
                 batch_size: int = 16):
        # Windows : plantages intermittents 0xC0000005 dans PyTorch quand OpenMP/MKL lancent
        # trop de fils en parallèle (F-010). Valeurs prudentes, modifiables dans l'environnement.
        import os
        os.environ.setdefault("OMP_NUM_THREADS", "4")
        os.environ.setdefault("MKL_NUM_THREADS", "4")
        os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
        from sentence_transformers import (
            SentenceTransformer,  # dépendance lourde, chargée à la demande
        )

        self.name = model_name
        self.batch_size = batch_size
        self.model = SentenceTransformer(model_name, device=device)
        if self.model.device.type == "cpu":
            self.model.float()      # modèle adapté enregistré en FP16 (D-046) : FP32 sur CPU
        self.query_prefix = self.QUERY_PROMPTS.get(model_name, "")

    def encode(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        if is_query and self.query_prefix:
            texts = [self.query_prefix + t for t in texts]
        vecs = self.model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True,
                                 show_progress_bar=len(texts) > 50, convert_to_numpy=True)
        return vecs.astype(np.float32)


class HashingEncoder:
    """Encodeur factice déterministe (sacs de mots hachés) : tests et CI, sans modèle."""

    def __init__(self, dim: int = 512):
        self.name, self.dim = f"hashing-{dim}", dim

    def encode(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for tok in analyze(t):
                out[i, zlib.crc32(tok.encode()) % self.dim] += 1.0
        return _l2(out)


# --------------------------------------------------------------------------- #
# Stockage des vecteurs
# --------------------------------------------------------------------------- #
class NumpyStore:
    def __init__(self, vectors: np.ndarray):
        self.vectors = _l2(vectors.astype(np.float32))

    def search(self, qvec: np.ndarray, k: int, allowed: np.ndarray | None = None) -> list[tuple[int, float]]:
        sims = self.vectors @ qvec
        if allowed is not None:
            sims = np.where(allowed, sims, -np.inf)
        top = np.argsort(-sims)[:k]
        return [(int(i), float(sims[i])) for i in top if np.isfinite(sims[i])]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, self.vectors)

    @classmethod
    def load(cls, path: Path) -> NumpyStore:
        return cls(np.load(path))


class QdrantStore:
    """Qdrant embarqué : ``QdrantClient(path=...)``, aucun serveur ni Docker."""

    def __init__(self, path: Path, collection: str):
        from qdrant_client import QdrantClient

        self.client = QdrantClient(path=str(path))
        self.collection = collection

    def build(self, vectors: np.ndarray, chunks: list[Chunk]) -> None:
        from qdrant_client.models import Distance, PointStruct, VectorParams

        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
        self.client.create_collection(
            self.collection, vectors_config=VectorParams(size=vectors.shape[1], distance=Distance.COSINE))
        points = [PointStruct(id=i, vector=v.tolist(),
                              payload={"chunk_id": c.chunk_id, "zone": c.zone, "doc_id": c.doc_id})
                  for i, (v, c) in enumerate(zip(vectors, chunks, strict=True))]
        for s in range(0, len(points), 256):
            self.client.upsert(self.collection, points=points[s:s + 256])

    def search(self, qvec: np.ndarray, k: int, zones: list[str] | None = None) -> list[tuple[int, float]]:
        from qdrant_client.models import FieldCondition, Filter, MatchAny

        flt = Filter(must=[FieldCondition(key="zone", match=MatchAny(any=zones))]) if zones else None
        res = self.client.query_points(self.collection, query=qvec.tolist(), limit=k, query_filter=flt)
        return [(int(p.id), float(p.score)) for p in res.points]


# --------------------------------------------------------------------------- #
# Fusion et recherche complète
# --------------------------------------------------------------------------- #
def rrf(rankings: list[list[tuple[int, float]]], k: int = 60,
        weights: list[float] | None = None) -> list[tuple[int, float]]:
    scores: dict[int, float] = defaultdict(float)
    for w, ranking in zip(weights or [1.0] * len(rankings), rankings, strict=True):
        for rank, (idx, _) in enumerate(ranking, start=1):
            scores[idx] += w / (k + rank)
    return sorted(scores.items(), key=lambda x: -x[1])


# --------------------------------------------------------------------------- #
# Options avancées : reranker, index de questions, graphe des renvois
# --------------------------------------------------------------------------- #
class Reranker(Protocol):
    def score(self, query: str, texts: list[str]) -> list[float]: ...


class CrossEncoderReranker:
    """Cross-encoder : lit la question et le passage ensemble (plus précis qu'une similarité de
    vecteurs, mais trop lent pour tout le corpus : on ne l'applique qu'aux premiers candidats)."""

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3", device: str | None = None,
                 batch_size: int = 16, max_length: int = 512):
        import os
        os.environ.setdefault("OMP_NUM_THREADS", "4")
        os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
        from sentence_transformers import CrossEncoder

        self.name = model_name
        self.batch_size = batch_size
        self.model = CrossEncoder(model_name, device=device, max_length=max_length)

    def score(self, query: str, texts: list[str]) -> list[float]:
        scores = self.model.predict([(query, t) for t in texts], batch_size=self.batch_size,
                                    show_progress_bar=False)
        return [float(x) for x in scores]


class QuestionIndex:
    """Query indexing : on indexe les questions qu'un morceau peut résoudre (générées par le LLM,
    rag/finetune.py) ; une question d'utilisateur proche d'une de ces questions remonte le morceau.
    Dense si des vecteurs sont fournis, BM25 sur les questions sinon."""

    def __init__(self, questions: list[str], chunk_pos: list[int], vectors: np.ndarray | None = None):
        if len(questions) != len(chunk_pos):
            raise ValueError("une position de morceau par question")
        self.questions, self.chunk_pos = questions, chunk_pos
        self.bm25 = BM25(questions)
        self.vectors = _l2(vectors.astype(np.float32)) if vectors is not None else None

    def search(self, query: str, qvec: np.ndarray | None, depth: int,
               allowed: np.ndarray | None = None) -> list[tuple[int, float]]:
        if self.vectors is not None and qvec is not None:
            sims = self.vectors @ qvec
            order = np.argsort(-sims)[: depth * 5]
            pairs = [(int(i), float(sims[i])) for i in order]
        else:
            pairs = self.bm25.search(query, depth * 5)
        best: dict[int, float] = {}
        for qi, sc in pairs:                       # meilleure question de chaque morceau
            ci = self.chunk_pos[qi]
            if (allowed is None or allowed[ci]) and ci not in best:
                best[ci] = sc
        return list(best.items())[:depth]


@dataclass
class Hit:
    rank: int
    score: float
    chunk: Chunk


class Retriever:
    """Recherche sur un jeu de chunks (une stratégie de découpage)."""

    RERANK_DEPTH = 20     # candidats relus par le cross-encoder
    GRAPH_SEEDS = 3       # premiers résultats dont on suit les renvois
    GRAPH_ALPHA = 0.25    # poids d'un renvoi (choisi sur le jeu de mise au point, D-049)

    def __init__(self, chunks: list[Chunk], encoder: Encoder | None = None,
                 vectors: np.ndarray | None = None, store: str = "numpy",
                 qdrant_path: Path | None = None, collection: str = "chunks",
                 reranker: Reranker | None = None, qindex: QuestionIndex | None = None,
                 graph: dict[int, list[int]] | None = None, options: dict | None = None):
        self.chunks = chunks
        self.bm25 = BM25([c.embed_text for c in chunks])
        self.encoder = encoder
        self.reranker, self.qindex, self.graph = reranker, qindex, graph
        # options appliquées par défaut (réglées par .env dans l'API, une par une dans l'évaluation)
        self.options = {"rerank": False, "questions": False, "graphe": False, **(options or {})}
        self.store: NumpyStore | QdrantStore | None = None
        if encoder is not None:
            if vectors is None:
                vectors = encoder.encode([c.embed_text for c in chunks])
            if store == "qdrant":
                self.store = QdrantStore(qdrant_path or Path("data/qdrant"), collection)
                self.store.build(vectors, chunks)
            else:
                self.store = NumpyStore(vectors)

    def _allowed(self, zones: list[str] | None) -> np.ndarray | None:
        if not zones:
            return None
        return np.array([c.zone in zones for c in self.chunks])

    def search(self, query: str, k: int = 5, mode: str = "hybrid", depth: int = 30,
               zones: list[str] | None = None, expand: bool = False, rerank: bool | None = None,
               questions: bool | None = None, graphe: bool | None = None) -> list[Hit]:
        rerank = self.options["rerank"] if rerank is None else rerank
        questions = self.options["questions"] if questions is None else questions
        graphe = self.options["graphe"] if graphe is None else graphe
        original = query
        if expand:
            from rag.query import expand_glossary
            query = expand_glossary(query)
        allowed = self._allowed(zones)
        lex = [(i, s) for i, s in self.bm25.search(query, depth * 3)
               if allowed is None or allowed[i]][:depth]
        qvec = None
        if mode == "bm25" or self.store is None:
            if mode in ("dense", "hybrid") and self.store is None:
                raise RuntimeError(f"mode '{mode}' demandé mais aucun index dense n'est chargé")
            rankings = [lex]
        else:
            qvec = self.encoder.encode([query], is_query=True)[0]
            if isinstance(self.store, QdrantStore):
                dense = self.store.search(qvec, depth, zones)   # filtre fait par Qdrant
            else:
                dense = self.store.search(qvec, depth, allowed)
            rankings = [dense] if mode == "dense" else [lex, dense]
        if questions and self.qindex is not None:
            rankings.append(self.qindex.search(query, qvec, depth, allowed))
        ranked = rankings[0] if len(rankings) == 1 else rrf(rankings)
        if graphe and self.graph:
            ranked = self._with_neighbours(ranked, k, allowed)
        if rerank and self.reranker is not None:
            cand = ranked[: max(self.RERANK_DEPTH, k)]
            scores = self.reranker.score(original, [self.chunks[i].embed_text for i, _ in cand])
            ranked = sorted(((i, sc) for (i, _), sc in zip(cand, scores, strict=True)), key=lambda x: -x[1])
        return [Hit(rank=r + 1, score=s, chunk=self.chunks[i]) for r, (i, s) in enumerate(ranked[:k])]

    def _with_neighbours(self, ranked: list[tuple[int, float]], k: int,
                         allowed: np.ndarray | None) -> list[tuple[int, float]]:
        """Graph RAG léger : chaque résultat reçoit le score 1 / rang ; un paragraphe auquel renvoie
        l'un des GRAPH_SEEDS premiers résultats reçoit au moins GRAPH_ALPHA / rang de ce résultat.
        Il complète la liste sans pouvoir passer devant le résultat qui le cite."""
        score = {i: 1.0 / r for r, (i, _) in enumerate(ranked, start=1)}
        for r, (i, _) in enumerate(ranked[: self.GRAPH_SEEDS], start=1):
            for j in self.graph.get(i, []):
                if allowed is None or allowed[j]:
                    score[j] = max(score.get(j, 0.0), self.GRAPH_ALPHA / r)
        return sorted(score.items(), key=lambda x: -x[1])


def model_slug(model_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", model_name.lower()).strip("-")


def index_paths(index_dir: Path, strategy: str, model_name: str) -> tuple[Path, Path]:
    base = index_dir / f"{strategy}__{model_slug(model_name)}"
    return base.with_suffix(".npy"), base.with_suffix(".json")


def save_dense(index_dir: Path, strategy: str, model_name: str, vectors: np.ndarray,
               chunks: list[Chunk]) -> None:
    vec_path, meta_path = index_paths(index_dir, strategy, model_name)
    NumpyStore(vectors).save(vec_path)
    meta_path.write_text(json.dumps({"model": model_name, "strategy": strategy,
                                     "chunk_ids": [c.chunk_id for c in chunks],
                                     "texts_sha1": texts_fingerprint(chunks)}), encoding="utf-8")


def texts_fingerprint(chunks: list[Chunk]) -> str:
    """Empreinte des textes encodés : un changement d'en-tête (D-025) rend l'index périmé même si
    les identifiants de chunks sont identiques."""
    h = hashlib.sha1()
    for c in chunks:
        h.update(c.embed_text.encode("utf-8") + b"\x00")
    return h.hexdigest()


def load_dense(index_dir: Path, strategy: str, model_name: str, chunks: list[Chunk],
               strict: bool = True) -> np.ndarray | None:
    """Vecteurs en cache, ou None s'ils sont absents. Index périmé (autres chunks ou autres textes) :
    erreur si ``strict``, sinon None pour que l'appelant réencode."""
    vec_path, meta_path = index_paths(index_dir, strategy, model_name)
    if not vec_path.exists():
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if (meta["chunk_ids"] != [c.chunk_id for c in chunks]
            or meta.get("texts_sha1") != texts_fingerprint(chunks)):
        if strict:
            raise RuntimeError(f"index {vec_path.name} périmé (textes modifiés) : "
                               f"relancer .\\make.ps1 index-dense")
        return None
    return np.load(vec_path)
