"""Construit les unités, les chunks A et B et (option) les index denses.

    python -m rag.build_index                                  # unités + chunks + BM25 (rapide, sans GPU)
    python -m rag.build_index --dense                          # + embeddings BGE-M3
    python -m rag.build_index --dense --model BAAI/bge-m3 --model Qwen/Qwen3-Embedding-0.6B
    python -m rag.build_index --dense --store qdrant           # + collections Qdrant (D-052)

Lit data/corpus_manifest.csv : chaque document dont le fichier existe est ingéré,
avec son parseur dédié s'il en a un (rag/ingest.py, STRUCTURED_PARSERS), sinon page par page.
Sur un PC sans GPU, BGE-M3 encode ~500 chunks en quelques minutes ; sinon, lancer sur Colab.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

from rag.chunking import STRATEGIES, save_chunks, stats
from rag.ingest import STRUCTURED_PARSERS, Unit, ingest_generic, load_units, save_units, summary

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "corpus_manifest.csv"
PROCESSED = ROOT / "data" / "processed"
INDEX_DIR = ROOT / "data" / "index"


def corpus_files() -> list[tuple[str, Path]]:
    with MANIFEST.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        path = ROOT / r["fichier_local"] if r["fichier_local"].strip() else None
        if path and path.exists():
            out.append((r["id"], path))
    return out


def build_units(force: bool = False) -> list[Unit]:
    units: list[Unit] = []
    for doc_id, path in corpus_files():
        cache = PROCESSED / f"{doc_id}_units.jsonl"
        if cache.exists() and not force and cache.stat().st_mtime > path.stat().st_mtime:
            doc_units = load_units(cache)
        else:
            parser = STRUCTURED_PARSERS.get(doc_id)
            doc_units = parser(path, doc_id) if parser else ingest_generic(path, doc_id)
            save_units(doc_units, cache)
        print(f"  {doc_id} : {len(doc_units)} unités ({'dédié' if doc_id in STRUCTURED_PARSERS else 'par page'})")
        units.extend(doc_units)
    return units


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dense", action="store_true", help="calculer les embeddings")
    ap.add_argument("--model", action="append", default=None, help="modèle(s) d'embedding")
    ap.add_argument("--store", choices=["numpy", "qdrant"], default="numpy")
    ap.add_argument("--force", action="store_true", help="réingérer les PDF même si le cache existe")
    args = ap.parse_args()

    print("1. Ingestion")
    units = build_units(args.force)
    if not units:
        raise SystemExit("Aucun document trouvé : placer les PDF dans data/corpus/ (voir le manifeste).")
    print("   ", json.dumps(summary(units), ensure_ascii=False))

    print("2. Découpage")
    all_chunks = {}
    for name, fn in STRATEGIES.items():
        chunks = fn(units)
        save_chunks(chunks, PROCESSED / f"chunks_{name}.jsonl")
        all_chunks[name] = chunks
        print(f"   {name} : {json.dumps(stats(chunks), ensure_ascii=False)}")

    if args.dense:
        from rag.retrieve import (
            QdrantStore,
            SentenceTransformerEncoder,
            model_slug,
            save_dense,
            texts_fingerprint,
        )

        for model in args.model or ["BAAI/bge-m3"]:
            print(f"3. Embeddings : {model}")
            enc = SentenceTransformerEncoder(model)
            for name, chunks in all_chunks.items():
                t0 = time.perf_counter()
                vecs = enc.encode([c.embed_text for c in chunks])
                save_dense(INDEX_DIR, name, model, vecs, chunks)
                if args.store == "qdrant":
                    import os
                    coll = f"{name}__{model_slug(model)}__{texts_fingerprint(chunks)[:10]}"
                    QdrantStore(coll, path=ROOT / "data" / "qdrant", url=os.getenv("QDRANT_URL", "")).build(vecs, chunks)
                print(f"   {name} : {len(chunks)} vecteurs de dim {vecs.shape[1]} "
                      f"en {time.perf_counter() - t0:.0f} s")
    print("Terminé.")


if __name__ == "__main__":
    main()
