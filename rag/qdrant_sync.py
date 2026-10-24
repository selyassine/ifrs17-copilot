"""Charge l'index dense existant (.npy) dans Qdrant et vérifie qu'il donne les mêmes résultats (D-052).

    python -m rag.qdrant_sync                          # Qdrant embarqué (data/qdrant)
    $env:QDRANT_URL="http://localhost:6333"; python -m rag.qdrant_sync   # serveur Docker

Pas de nouvel encodage : les vecteurs de data/index/ sont recopiés tels quels. La vérification compare,
pour 50 vecteurs de requête, les 5 premiers résultats de Qdrant (index HNSW) à ceux de la recherche
exacte NumPy : même ensemble attendu, sinon l'écart est affiché.
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np

from core.config import get_settings
from rag.chunking import load_chunks
from rag.retrieve import NumpyStore, QdrantStore, load_dense, model_slug, texts_fingerprint
from rag.service import INDEX_DIR, PROCESSED, ROOT


def main() -> None:
    s = get_settings()
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default=s.rag_strategy)
    ap.add_argument("--model", default=s.rag_embed_model or "BAAI/bge-m3")
    ap.add_argument("--rebuild", action="store_true", help="recrée la collection même si elle existe")
    a = ap.parse_args()

    chunks = load_chunks(PROCESSED / f"chunks_{a.strategy}.jsonl")
    vecs = load_dense(INDEX_DIR, a.strategy, a.model, chunks)
    if vecs is None:
        raise SystemExit(f"index dense absent : lancer `python -m rag.build_index --dense --model {a.model}`")
    coll = f"{a.strategy}__{model_slug(a.model)}__{texts_fingerprint(chunks)[:10]}"
    store = QdrantStore(coll, path=ROOT / "data" / "qdrant", url=s.qdrant_url, api_key=s.qdrant_api_key)
    t0 = time.perf_counter()
    built = store.build(vecs, chunks) if a.rebuild else store.ensure(vecs, chunks)
    t_build = time.perf_counter() - t0

    ref = NumpyStore(vecs)
    rng = np.random.default_rng(0)
    probes = vecs[rng.choice(len(vecs), size=min(50, len(vecs)), replace=False)]
    probes = probes + rng.normal(0, 0.05, probes.shape).astype(np.float32)   # requêtes proches, pas identiques
    probes /= np.linalg.norm(probes, axis=1, keepdims=True)
    same, lat = 0, []
    for q in probes:
        t = time.perf_counter()
        got = [i for i, _ in store.search(q, 5)]
        lat.append((time.perf_counter() - t) * 1000)
        same += set(got) == {i for i, _ in ref.search(q, 5)}
    zone = store.search(probes[0], 5, zones=["annexe_B"])
    print(json.dumps({
        "collection": coll, "mode": "serveur " + s.qdrant_url if s.qdrant_url else "embarqué (data/qdrant)",
        "points": len(chunks), "dimension": int(vecs.shape[1]), "construite": bool(built) or a.rebuild,
        "duree_s": round(t_build, 1), "top5_identique_a_numpy": f"{same}/{len(probes)}",
        "latence_p50_ms": round(float(np.median(lat)), 2),
        "filtre_zone_ok": all(chunks[i].zone == "annexe_B" for i, _ in zone)}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
