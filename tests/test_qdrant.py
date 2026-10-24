"""Base vectorielle Qdrant en mode embarqué (D-052) : mêmes résultats que NumPy, filtre par zone, collection réutilisée."""

import numpy as np
import pytest

from rag.chunking import chunk_structural
from rag.ingest import Unit
from rag.retrieve import HashingEncoder, Retriever

pytest.importorskip("qdrant_client")

TEXTS = {"44": "La marge sur services contractuels est ajustée pour les services futurs.",
         "B119": "La marge est libérée selon les unités de couverture du groupe.",
         "36": "Les taux d'actualisation reflètent la valeur temps de l'argent.",
         "62": "Les contrats de réassurance détenus sont comptabilisés à la date la plus tardive."}


def chunks():
    zones = {"44": "norme", "B119": "annexe_B", "36": "norme", "62": "norme"}
    units = [Unit(unit_id=f"T:{p}", doc_id="T", zone=zones[p], paragraph_id=p, heading="Titre",
                  section="", text=t, page_start=1, page_end=1) for p, t in TEXTS.items()]
    return chunk_structural(units, min_tokens=1)


def test_qdrant_comme_numpy_et_filtre(tmp_path):
    cs, enc = chunks(), HashingEncoder()
    vecs = enc.encode([c.embed_text for c in cs])
    ref = Retriever(cs, encoder=enc, vectors=vecs)
    qd = Retriever(cs, encoder=enc, vectors=vecs, store="qdrant", qdrant_path=tmp_path / "q", collection="t")
    for q in ("marge services futurs", "taux d'actualisation", "réassurance détenue"):
        a = ref.search(q, k=3, mode="dense")
        b = qd.search(q, k=3, mode="dense")
        assert a[0].chunk.chunk_id == b[0].chunk.chunk_id                         # même premier résultat
        assert np.allclose([h.score for h in a], [h.score for h in b], atol=1e-4)  # mêmes scores (ex æquo possibles)
    hits = qd.search("marge", k=3, mode="dense", zones=["annexe_B"])
    assert hits and all(h.chunk.zone == "annexe_B" for h in hits)


def test_collection_reutilisee(tmp_path):
    from rag.retrieve import QdrantStore
    cs = chunks()
    vecs = HashingEncoder().encode([c.embed_text for c in cs])
    st = QdrantStore("t", path=tmp_path / "q")
    assert st.ensure(vecs, cs) is True and st.ensure(vecs, cs) is False
    assert np.isclose(st.search(vecs[0], 1)[0][1], 1.0, atol=1e-4)
