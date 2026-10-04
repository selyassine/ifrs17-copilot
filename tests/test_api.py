"""Tests de l'API (nécessitent fastapi + httpx, installés par requirements.txt)."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402
from core.config import Settings, get_settings  # noqa: E402


@pytest.fixture
def client(tmp_path):
    settings = Settings(llm_provider="fake", router_mode="heuristic", api_token="secret",
                        trace_path=tmp_path / "traces.jsonl", rag_strategy="B", rag_mode="bm25",
                        rag_embed_model="", rag_glossary=True)
    app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(app)
    app.dependency_overrides.clear()


AUTH = {"X-API-Token": "secret"}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_jeton_obligatoire(client):
    r = client.post("/v1/route", json={"request": "Qu'est-ce que le CSM ?"})
    assert r.status_code == 401


def test_route_question_norme(client):
    r = client.post("/v1/route", json={"request": "Qu'est-ce que le CSM ?"}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["plan"]["intent"] == "question_norme"
    assert "verificateur" in body["plan"]["steps"]


def test_csm_compute(client):
    payload = {"group_id": "G1", "premiums": [100, 0, 0], "outflows": [20, 20, 20],
               "coverage_units": [1, 1, 1]}
    r = client.post("/v1/csm/compute", json=payload, headers=AUTH)
    assert r.status_code == 200
    assert abs(r.json()["initial_csm"] - 40) < 0.01


def test_csm_donnees_invalides_422(client):
    payload = {"group_id": "G1", "premiums": [100, 0], "outflows": [20],
               "coverage_units": [1, 1]}
    r = client.post("/v1/csm/compute", json=payload, headers=AUTH)
    assert r.status_code == 422


def test_search_sans_index_503(client, monkeypatch):
    import api.main as main
    from rag.service import IndexMissing

    def missing(*a, **k):
        raise IndexMissing("chunks_B.jsonl introuvable")

    monkeypatch.setattr(main, "get_retriever", missing)
    r = client.post("/v1/search", json={"query": "CSM"}, headers=AUTH)
    assert r.status_code == 503


def test_search_renvoie_les_paragraphes(client, monkeypatch):
    import api.main as main
    from rag.chunking import chunk_structural
    from rag.ingest import Unit
    from rag.retrieve import Retriever

    units = [Unit(unit_id=f"T:{p}", doc_id="T", zone="norme", paragraph_id=p, heading="", section="",
                  text=t, page_start=1, page_end=1)
             for p, t in [("44", "ajustement de la marge sur services contractuels"),
                          ("36", "taux d'actualisation et valeur temps de l'argent")]]
    retriever = Retriever(chunk_structural(units, min_tokens=1))
    monkeypatch.setattr(main, "get_retriever", lambda *a, **k: retriever)
    r = client.post("/v1/search", json={"query": "Comment ajuster la CSM ?", "k": 1}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["hits"][0]["paragraph_ids"] == ["44"]


def test_ask_hors_perimetre_refuse_sans_appel_llm(client, monkeypatch):
    import agents.pipeline as pipeline

    def no_llm(*a, **k):
        raise AssertionError("le RAG ne doit pas être appelé")

    monkeypatch.setattr(pipeline, "answer_question", no_llm)
    r = client.post("/v1/ask", json={"question": "Donne-moi une recette de crêpes"}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["plan"]["intent"] == "hors_perimetre" and body["answer"]["refused"]


def test_ask_reponse_citee(client, monkeypatch, tmp_path):
    import json

    import api.main as main
    from core.config import Settings
    from core.llm import LLMClient
    from rag.chunking import chunk_structural
    from rag.ingest import Unit
    from rag.retrieve import Retriever

    units = [Unit(unit_id="T:B119", doc_id="T", zone="annexe_B", paragraph_id="B119", heading="",
                  section="", text="À chaque période, l'entité comptabilise en résultat net un montant "
                  "de la marge sur services contractuels.", page_start=1, page_end=1)]
    monkeypatch.setattr(main, "get_retriever", lambda *a, **k: Retriever(chunk_structural(units, min_tokens=1)))
    answer = {"answer": "La CSM est libérée en résultat à chaque période [B119].",
              "citations": [{"paragraph_id": "B119", "extrait": "E1", "quote": "À chaque période"}],
              "refused": False, "refusal_reason": None}
    fake = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl")
    monkeypatch.setattr(main, "make_client",
                        lambda s: LLMClient(fake, fake_responder=lambda m, model: json.dumps(answer)))
    r = client.post("/v1/ask", json={"question": "Comment la CSM est-elle libérée ?"}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["answer"]["citations"][0]["paragraph_id"] == "B119"
    assert body["sources"][0]["paragraph_ids"] == ["B119"]


GOOD_EXTRACTION = {"group_id": "AB-1", "currency": "EUR", "unit_multiplier": 1000,
                   "premiums": [100.0, 0.0], "outflows": [45.0, 50.0], "coverage_units": [1000, 900],
                   "discount_rates": 0.03, "risk_adjustment_pct": 0.05, "manquants": []}


def _pdf(tmp_path):
    pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    path = tmp_path / "doc.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    lines = ["Groupe AB-1 - en milliers d'euros. Taux : 3,00 %. Ajustement pour risque : 5,00 %.",
             "Primes 100,00 et 0,00. Sinistres 40,00 et 45,50. Frais 5,00 et 4,50.",
             "Contrats en vigueur 1000 et 900."]
    for k, line in enumerate(lines):
        c.drawString(50, 800 - 20 * k, line)
    c.save()
    return path.read_bytes()


def _fake_llm(monkeypatch, tmp_path, answer):
    import json

    import api.main as main
    from core.llm import LLMClient

    fake = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl")
    monkeypatch.setattr(main, "make_client",
                        lambda s: LLMClient(fake, fake_responder=lambda m, model: json.dumps(answer)))


def test_case_document_calcul_si_extraction_ok(client, monkeypatch, tmp_path):
    _fake_llm(monkeypatch, tmp_path, GOOD_EXTRACTION)
    r = client.post("/v1/case/document", headers=AUTH,
                    files={"file": ("etat.pdf", _pdf(tmp_path), "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok" and body["next_step"] == "calcul_fait"
    assert body["csm"]["group_id"] == "AB-1"


def test_case_document_validation_humaine_si_chiffre_invente(client, monkeypatch, tmp_path):
    _fake_llm(monkeypatch, tmp_path, {**GOOD_EXTRACTION, "premiums": [130.0, 0.0]})
    r = client.post("/v1/case/document", headers=AUTH,
                    files={"file": ("etat.pdf", _pdf(tmp_path), "application/pdf")})
    body = r.json()
    assert body["status"] == "a_verifier" and body["next_step"] == "validation_humaine"
    assert body["csm"] is None and any("premiums" in i for i in body["issues"])


def test_extract_image_passe_par_le_mode_vision(client, monkeypatch, tmp_path):
    import io
    import json

    import api.main as main
    from core.llm import LLMClient

    PIL = pytest.importorskip("PIL.Image")
    buf = io.BytesIO()
    PIL.new("RGB", (40, 20), "white").save(buf, format="PNG")
    transcription = ["Groupe AB-1 en milliers d'euros. Taux : 3,00 %. Ajustement pour risque : 5,00 %.",
                     "Période | Primes | Sinistres | Frais | Contrats",
                     "Année 1 | 100,00 | 40,00 | 5,00 | 1 000", "Année 2 | 0,00 | 45,50 | 4,50 | 900"]
    fake = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl")
    answer = {**GOOD_EXTRACTION, "transcription": transcription}
    monkeypatch.setattr(main, "make_vision_client",
                        lambda s: LLMClient(fake, fake_responder=lambda m, model: json.dumps(answer)))
    r = client.post("/v1/extract", headers=AUTH, files={"file": ("scan.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "vision" and r.json()["status"] == "ok"


def test_extract_refuse_un_fichier_qui_n_est_pas_un_pdf(client):
    r = client.post("/v1/extract", headers=AUTH, files={"file": ("x.txt", b"bonjour", "text/plain")})
    assert r.status_code == 415
