"""Questions de définition et relances courtes (D-092, F-032) ; diagnostic de la latence."""

from agents.copilot import off_topic
from eval.diagnostic import analyse, cause
from rag.chunking import Chunk
from rag.query import definition_targets
from rag.retrieve import Retriever

DEFS = ["def:passif au titre de la couverture restante", "def:passif au titre des sinistres survenus",
        "def:marge sur services contractuels", "def:groupe de contrats d'assurance", "def:contrat d'assurance",
        "def:ajustement au titre du risque non financier"]


def test_definition_visee_par_l_abreviation():
    """Essai du 25/10 : « c quoi le LRC » refusé, la définition de l'annexe A n'était pas dans les 5 passages."""
    assert definition_targets("C quoi le LRC et comment le calculer", DEFS)[0] == [DEFS[0]]
    assert definition_targets("c quoi le CSM", DEFS)[0] == [DEFS[2]]
    assert definition_targets("qu'est-ce que le RA ?", DEFS)[0] == [DEFS[5]]
    assert definition_targets("c quoi un groupe de contrats", DEFS)[0] == [DEFS[3]]
    assert definition_targets("c quoi le PAA", DEFS) == ([], ["53"])
    assert definition_targets("Comment la CSM est-elle libérée ?", DEFS) == ([], [])     # pas une définition


def _chunk(pid, text):
    return Chunk(chunk_id=pid, strategy="B", doc_id="T", text=text, embed_text=text, paragraph_ids=[pid], zone="norme")


def test_la_definition_passe_en_tete():
    chunks = [_chunk("57", "passif au titre de la couverture restante évaluation calcul couverture restante passif"),
              _chunk("46", "couverture restante passif ajustements"),
              _chunk(DEFS[0], "Obligation de l'entité d'instruire les demandes au titre de la couverture restante."),
              _chunk("10", "autre sujet")]
    r = Retriever(chunks)
    hits = r.search("C quoi le LRC", k=3, mode="bm25", expand=True)
    assert hits[0].chunk.paragraph_ids == [DEFS[0]]
    assert len({h.chunk.chunk_id for h in hits}) == 3                     # sans doublon
    plain = r.search("C quoi le LRC", k=3, mode="bm25", expand=False)      # sans glossaire : classement inchangé
    assert not plain or plain[0].chunk.paragraph_ids != [DEFS[0]]


def test_relance_courte_avec_memoire_f032():
    """« seulement $1 ?? » après une réponse : relance, pas hors sujet ; Messi reste refusé même avec mémoire."""
    assert not off_topic("seulement $1 ??", True) and not off_topic("pourquoi ?", True)
    assert off_topic("seulement $1 ??", False)
    assert off_topic("parler moi sur lionel messi", True) and off_topic("qui a gagné la coupe du monde 2022 ?", True)


def test_diagnostic_separe_les_causes():
    rows = [{"kind": "llm", "agent": "chercheur_rag", "model": "m", "latency_ms": 65_000, "quota_wait_s": 60, "case_id": "a"},
            {"kind": "llm", "agent": "extracteur", "mode": "vision", "model": "g", "latency_ms": 125_000, "retries": 2,
             "case_id": "b"},
            {"kind": "llm", "agent": "verificateur", "model": "m", "latency_ms": 1_200, "case_id": "a"}]
    a = analyse(rows)
    assert a["total"]["lents"] == 2 and a["total"]["quota_s"] == 60
    assert a["causes"] == {"attente du quota (429)": 1, "erreur ou délai dépassé, nouvel essai": 1}
    assert a["agents"]["extracteur (vision)"]["max_s"] == 125.0 and a["requetes"][0]["case_id"] == "b"
    assert cause({"latency_ms": 30_000}).startswith("attente non enregistrée")


def test_batterie_du_diagnostic_s_execute(tmp_path, monkeypatch):
    """Le diagnostic importait une fonction inexistante (run_ask) : la batterie doit vraiment tourner."""
    from types import SimpleNamespace

    import agents.pipeline as pipeline
    from core.config import Settings
    from eval.diagnostic import report, run_questions

    def fake_ask(question, settings, client, loader, case_id=""):
        a = SimpleNamespace(refused=False, citations=[], answer="ok", refusal_reason="")
        return SimpleNamespace(answer=a, plan=SimpleNamespace(intent=SimpleNamespace(value="question_norme")), verdict=None)
    monkeypatch.setattr(pipeline, "ask", fake_ask)
    rows = run_questions(2, Settings(llm_provider="fake", trace_path=tmp_path / "t.jsonl", rag_mode="bm25"))
    assert len(rows) == 2 and all("erreur" not in r and r["duree"]["total_ms"] >= 0 for r in rows)
    assert "Batterie de questions" in report(analyse([]), rows, "")


def test_diagnostic_lit_depuis_un_decalage(tmp_path):
    """Avec --questions, seules les traces écrites pendant l'exécution sont analysées (date des traces en UTC)."""
    import json as _json

    from eval.diagnostic import load

    p = tmp_path / "t.jsonl"
    p.write_text(_json.dumps({"kind": "llm", "ts": "2026-10-25T10:00:00", "latency_ms": 1}) + "\n", encoding="utf-8")
    start = p.stat().st_size
    with p.open("a", encoding="utf-8") as f:
        f.write(_json.dumps({"kind": "llm", "ts": "2026-10-25T16:00:00", "latency_ms": 2}) + "\n")
    assert [r["latency_ms"] for r in load(p, "", start)] == [2] and len(load(p)) == 2


def test_qdrant_local_occupe_recherche_en_memoire(monkeypatch):
    """D-095 : l'API préchauffée garde Qdrant local ouvert ; une évaluation lancée à côté ne doit pas planter."""
    import numpy as np

    import rag.retrieve as rr

    class Busy:
        def __init__(self, *a, **k):
            raise RuntimeError("Storage folder data/qdrant is already accessed by another instance of Qdrant client.")
    monkeypatch.setattr(rr, "QdrantStore", Busy)

    class Enc:
        def encode(self, texts, is_query=False):
            return np.array([[1.0, 0.0] if "couverture" in t else [0.0, 1.0] for t in texts])
    chunks = [_chunk("A", "couverture restante"), _chunk("B", "autre sujet")]
    r = Retriever(chunks, encoder=Enc(), store="qdrant")
    assert isinstance(r.store, rr.NumpyStore) and r.store_fallback.startswith("numpy")
    assert r.search("couverture", k=1, mode="dense")[0].chunk.chunk_id == "A"
