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
    # D-091 : la durée affichée est celle de toute la requête, avec sa décomposition
    assert body["latency_ms"] == body["duree"]["total_ms"] > 0 and {"appels", "par_agent", "autre_ms"} <= set(body["duree"])


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


def test_site_web_et_documents_exemple(client):
    home = client.get("/", follow_redirects=False)
    assert home.status_code == 200 and "IFRS 17 Copilot" in home.text and "/app/" in home.text
    page = client.get("/app/")
    assert page.status_code == 200 and "IFRS 17 Copilot" in page.text
    for asset in ("assets/js/app.js", "assets/js/core.js", "assets/js/views/case.js", "assets/css/app.css",
                  "assets/fonts/plex-sans.woff2", "assets/img/logo.svg"):
        assert client.get(f"/app/{asset}").status_code == 200, asset
    samples = client.get("/v1/samples").json()
    assert isinstance(samples, list)
    assert client.get("/v1/samples/../../.env").status_code == 404
    assert client.get("/v1/samples/zzz99").status_code == 404


def test_dossier_en_flux(client, monkeypatch, tmp_path):
    """/v1/case/stream : événements start, étapes (début puis fin), résultat final."""
    import json

    import api.main as main
    from core.llm import LLMClient

    def respond(messages, model):
        system = messages[0]["content"]
        if "rédige la synthèse" in system:
            return json.dumps({"synthese": "Le groupe AB-1 est bénéficiaire."})
        return json.dumps(GOOD_EXTRACTION)

    fake = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl")
    monkeypatch.setattr(main, "make_client", lambda s: LLMClient(fake, fake_responder=respond))
    monkeypatch.setattr(main, "_retriever_loader", lambda s: None)
    r = client.post("/v1/case/stream", headers=AUTH,
                    files={"file": ("etat.pdf", _pdf(tmp_path), "application/pdf")})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    assert events[0]["type"] == "start" and events[-1]["type"] == "result"
    steps = [e for e in events if e["type"] == "step"]
    assert steps[0]["agent"] == "extracteur" and steps[0]["status"] == "en cours"
    assert {e["agent"] for e in steps} >= {"extracteur", "calculateur", "redacteur"}
    assert events[-1]["data"]["csm"]["group_id"] == "AB-1" and events[-1]["data"]["note_html"]


def test_flux_validation_humaine_envoie_l_email_par_n8n(client, monkeypatch, tmp_path):
    """Dossier du site en validation humaine : l'API transmet le dossier au workflow n8n 06 (D-041)."""
    import json

    import api.main as main

    _fake_llm(monkeypatch, tmp_path, {**GOOD_EXTRACTION, "premiums": [130.0, 0.0]})
    monkeypatch.setattr(main, "_retriever_loader", lambda s: None)
    sent = []
    monkeypatch.setattr(main, "notify_validation",
                        lambda payload, s: sent.append(payload) or {"envoyee": True, "detail": "ok"})
    r = client.post("/v1/case/stream", headers=AUTH,
                    files={"file": ("etat.pdf", _pdf(tmp_path), "application/pdf")})
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    result = events[-1]["data"]
    assert result["status"] == "validation_humaine" and result["notification"]["envoyee"]
    assert any(e["type"] == "notification" for e in events)
    assert sent and sent[0]["case_id"] == result["case_id"] and sent[0]["controls"]


def test_notification_sans_url_ne_bloque_pas():
    from api.main import notify_validation

    out = notify_validation({"case_id": "x"}, Settings(n8n_validation_url=""))
    assert out["envoyee"] is False and "N8N_VALIDATION_URL" in out["detail"]


def test_rollforward_bba_exemple_du_cours(client):
    """POST /v1/csm/rollforward : l'exemple du cours (p. 32 à 36) passe par l'API."""
    body = {"group_id": "COURS", "single_premium": 1000000, "expected_claims": [200000] * 4,
            "actual_claims": [200000, 220000, 220000, 220000], "rates": [0.042, 0.043, 0.044, 0.035, 0.03],
            "ra_initial": 50000, "ra_changes": [0, 5000, 0, 0], "coverage_units": [100] * 4,
            "claim_revisions": [{"at_end_of_year": 3, "expected_claims": [200000, 200000, 200000, 220000]}]}
    r = client.post("/v1/csm/rollforward", json=body, headers=AUTH)
    assert r.status_code == 200
    y1 = r.json()["years"][0]
    assert round(y1["bel_close"]) == 551873 and round(y1["csm_close"]) == 177736
    bad = client.post("/v1/csm/rollforward", json={**body, "rates": [0.04]}, headers=AUTH)
    assert bad.status_code == 422


def test_paa_position(client):
    body = {"contract": {"premium": 1000, "coverage_start": "2025-07-01", "coverage_months": 12,
                         "acquisition_costs": 30, "expense_acquisition_costs": False},
            "at": ["2025-12-31", "2026-06-30"]}
    r = client.post("/v1/paa/position", json=body, headers=AUTH)
    assert r.status_code == 200
    first, second = r.json()
    assert first["lrc"] == 485 and second["lrc"] == 0



def test_copilot_api(client, monkeypatch):
    import json

    import api.main as main
    from core.llm import LLMClient

    def respond(messages, model):
        if any("<resultat" in m["content"] for m in messages if m["role"] == "user"):
            return json.dumps({"action": "repondre", "reponse": "Le groupe est bénéficiaire : flux d'exécution -20,00."})
        return json.dumps({"action": "outil", "outil": "donnees_du_dossier", "arguments": {}})

    monkeypatch.setattr(main, "make_client", lambda s: LLMClient(s, fake_responder=respond))
    body = {"question": "Le groupe est-il bénéficiaire ?", "portfolio": {
        "group_id": "G1", "premiums": [100, 0], "outflows": [40, 40], "coverage_units": [1, 1]}}
    r = client.post("/v1/copilot", json=body, headers=AUTH)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["source"] == "llm" and d["tools"][0]["outil"] == "donnees_du_dossier"
    assert client.post("/v1/copilot", json=body).status_code == 401


# --------------------------------------------------------------------------- #
# Registre, comptes et rôles (D-058)
# --------------------------------------------------------------------------- #
def _users(client):
    import api.main as main

    reg = main.registry(get_settings() if not app.dependency_overrides else app.dependency_overrides[get_settings]())
    for name, role in (("ana", "analyste"), ("val", "valideur"), ("adm", "admin")):
        reg.add_user(name, f"{name}-motdepasse", role)

    def bearer(name):
        r = client.post("/v1/auth/login", json={"username": name, "password": f"{name}-motdepasse"})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['token']}"}
    return reg, bearer


def test_connexion_et_roles(client):
    reg, bearer = _users(client)
    assert client.post("/v1/auth/login", json={"username": "ana", "password": "faux"}).status_code == 401
    ana, val, adm = bearer("ana"), bearer("val"), bearer("adm")
    assert client.get("/v1/auth/me", headers=ana).json()["role"] == "analyste"
    assert client.get("/v1/cases", headers=ana).status_code == 200
    assert client.get("/v1/users", headers=ana).status_code == 403
    assert client.get("/v1/users", headers=adm).status_code == 200
    assert client.get("/v1/audit/verify", headers=val).status_code == 403
    assert client.get("/v1/audit/verify", headers=adm).json()["intacte"]
    body = {"portfolio": {"group_id": "G1", "premiums": [100, 0], "outflows": [40, 40], "coverage_units": [1, 1]}}
    assert client.post("/v1/case/validated", headers=ana, json=body).status_code == 403
    assert client.get("/v1/cases", headers={"Authorization": "Bearer faux"}).status_code == 401
    r = client.post("/v1/users", headers=adm, json={"username": "eve", "password": "court", "role": "analyste"})
    assert r.status_code == 422
    assert client.post("/v1/users", headers=adm, json={"username": "eve", "password": "assez-long-1",
                                                        "role": "analyste"}).status_code == 201
    client.post("/v1/auth/logout", headers=ana)
    assert client.get("/v1/cases", headers=ana).status_code == 401


def test_dossier_enregistre_puis_rejete(client, monkeypatch, tmp_path):
    _fake_llm(monkeypatch, tmp_path, {**GOOD_EXTRACTION, "premiums": [130.0, 0.0]})
    import api.main as main
    monkeypatch.setattr(main, "_retriever_loader", lambda s: None)
    reg, bearer = _users(client)
    ana, val = bearer("ana"), bearer("val")
    r = client.post("/v1/case", headers=ana, data={"case_id": "dos-1"},
                    files={"file": ("etat.pdf", _pdf(tmp_path), "application/pdf")})
    assert r.status_code == 200 and r.json()["status"] == "validation_humaine"
    listing = client.get("/v1/cases?status=validation_humaine", headers=ana).json()
    assert listing["total"] == 1 and listing["dossiers"][0]["source"] == "site"
    assert listing["dossiers"][0]["submitter"] == "ana"
    detail = client.get("/v1/cases/dos-1", headers=ana).json()
    assert [e["action"] for e in detail["evenements"]][:2] == ["depot", "analyse"]
    assert client.get("/v1/cases/dos-1/note", headers=ana).text.startswith("<!doctype html>")
    assert client.post("/v1/cases/dos-1/reject", headers=ana, json={"comment": "taux faux"}).status_code == 403
    r = client.post("/v1/cases/dos-1/reject", headers=val, json={"comment": "taux de la période 2 faux"})
    assert r.status_code == 200 and r.json()["status"] == "rejetee" and r.json()["validated_by"] == "val"
    assert client.post("/v1/cases/dos-1/events", headers=AUTH,
                       json={"action": "email_rejet_envoye", "detail": {"a": "x@y.fr"}}).status_code == 200
    d = client.get("/v1/dashboard", headers=ana).json()
    assert d["par_statut"]["rejetee"] == 1 and d["taux_validation_humaine"] == 1.0
    assert reg.verify_chain()["intacte"]


def test_n8n_enregistre_la_source_et_le_valideur(client, monkeypatch, tmp_path):
    _fake_llm(monkeypatch, tmp_path, GOOD_EXTRACTION)
    import api.main as main
    monkeypatch.setattr(main, "_retriever_loader", lambda s: None)
    r = client.post("/v1/case", headers=AUTH, data={"case_id": "n8n-1", "source": "n8n-email",
                                                     "submitter": "client@assureur.fr"},
                    files={"file": ("etat.pdf", _pdf(tmp_path), "application/pdf")})
    assert r.status_code == 200
    body = {"case_id": "n8n-1", "portfolio": r.json()["portfolio"], "validated_by": "valideur@assureur.fr"}
    assert client.post("/v1/case/validated", headers=AUTH, json=body).status_code == 200
    case = client.get("/v1/cases/n8n-1", headers=AUTH).json()
    assert case["source"] == "n8n-email" and case["submitter"] == "client@assureur.fr"
    assert case["validated_by"] == "valideur@assureur.fr" and case["status"] in ("validee", "validation_humaine")


def test_copilot_memoire_et_historique(client, monkeypatch):
    """Deuxième question : le premier échange (contrôlé) est dans le contexte ; historique consultable."""
    import json

    import api.main as main
    from core.llm import LLMClient

    seen = []

    def respond(messages, model):
        seen.append(messages[1]["content"])
        if any("<resultat" in m["content"] for m in messages if m["role"] == "user"):
            return json.dumps({"action": "repondre", "reponse": "Le groupe est bénéficiaire : flux d'exécution -20,00."})
        return json.dumps({"action": "outil", "outil": "donnees_du_dossier", "arguments": {}})

    monkeypatch.setattr(main, "make_client", lambda s: LLMClient(s, fake_responder=respond))
    port = {"group_id": "G1", "premiums": [100, 0], "outflows": [40, 40], "coverage_units": [1, 1]}
    r1 = client.post("/v1/copilot", json={"question": "Le groupe est-il bénéficiaire ?", "portfolio": port,
                                          "case_id": "M-1"}, headers=AUTH)
    assert r1.status_code == 200 and r1.json()["memory_used"] == 0
    r2 = client.post("/v1/copilot", json={"question": "Et maintenant ?", "portfolio": port, "case_id": "M-1"}, headers=AUTH)
    assert r2.json()["memory_used"] == 1 and "Le groupe est bénéficiaire" in seen[-1] and "<memoire>" in seen[-1]
    assert "Résultats d'outils : donnees_du_dossier" in seen[-1]          # chiffres du moteur gardés en mémoire
    h = client.get("/v1/copilot/M-1", headers=AUTH).json()
    assert [e["question"] for e in h["echanges"]] == ["Le groupe est-il bénéficiaire ?", "Et maintenant ?"]
    # D-090 : les résultats d'outils sont gardés avec l'échange, pour redessiner les graphes après un rechargement
    assert h["echanges"][0]["observations"][0]["outil"] == "donnees_du_dossier"
    assert "calcul_de_la_csm" in h["echanges"][0]["observations"][0]["resultat"]
    assert client.delete("/v1/copilot/M-1/memoire", headers=AUTH).json()["effaces"] == 2


def test_note_en_pdf(client, monkeypatch, tmp_path):
    """GET /v1/cases/{id}/note.pdf (D-065) : la note imprimée par le navigateur, pièce jointe des e-mails n8n."""
    _fake_llm(monkeypatch, tmp_path, {**GOOD_EXTRACTION, "premiums": [130.0, 0.0]})
    import api.main as main
    import api.registry_routes as routes
    from core.pdf import PdfUnavailable
    monkeypatch.setattr(main, "_retriever_loader", lambda s: None)
    reg, bearer = _users(client)
    ana = bearer("ana")
    assert client.get("/v1/cases/inconnu/note.pdf", headers=AUTH).status_code == 404
    client.post("/v1/case", headers=ana, data={"case_id": "dos-pdf"},
                files={"file": ("etat.pdf", _pdf(tmp_path), "application/pdf")})
    vu = {}

    def imprimer(html, browser):
        vu["html"] = html
        return b"%PDF-1.4 note"
    monkeypatch.setattr(routes, "html_to_pdf", imprimer)
    r = client.get("/v1/cases/dos-pdf/note.pdf", headers=AUTH)       # jeton d'API : appel de n8n
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert 'filename="note_IFRS17_' in r.headers["content-disposition"] and vu["html"].startswith("<!doctype html>")
    assert "note_pdf_generee" in [e["action"] for e in client.get("/v1/cases/dos-pdf", headers=ana).json()["evenements"]]

    def sans_navigateur(html, browser):
        raise PdfUnavailable("aucun navigateur trouvé")
    monkeypatch.setattr(routes, "html_to_pdf", sans_navigateur)
    r = client.get("/v1/cases/dos-pdf/note.pdf", headers=AUTH)
    assert r.status_code == 503 and "navigateur" in r.json()["detail"]


def test_modifications_du_valideur_dans_la_note(client, monkeypatch, tmp_path):
    """Un changement d'unité (ou de tout champ) par le valideur est écrit dans la note et la piste d'audit (D-067)."""
    _fake_llm(monkeypatch, tmp_path, GOOD_EXTRACTION)
    import api.main as main
    monkeypatch.setattr(main, "_retriever_loader", lambda s: None)
    r = client.post("/v1/case", headers=AUTH, data={"case_id": "u-1"},
                    files={"file": ("etat.pdf", _pdf(tmp_path), "application/pdf")})
    portfolio = r.json()["portfolio"]
    assert main.validator_changes(portfolio, main.PortfolioData(**portfolio)) == []
    body = {"case_id": "u-1", "portfolio": {**portfolio, "unit_multiplier": 1_000_000}, "validated_by": "v@x.fr"}
    r = client.post("/v1/case/validated", headers=AUTH, json=body)
    assert r.status_code == 200
    assert "unité : 1000 → 1000000" in r.json()["note_html"] and "Modifications du valideur" in r.json()["note_html"]
    ev = [e for e in client.get("/v1/cases/u-1", headers=AUTH).json()["evenements"] if e["action"] == "validation_approuvee"]
    assert ev and ev[-1]["detail"]["modifications"] == ["unité : 1000 → 1000000"]


def test_fichiers_du_site_reverifies(client):
    """Un module JavaScript mis à jour n'est pas gardé en cache à côté d'un ancien (export introuvable)."""
    r = client.get("/app/assets/js/charts.js")
    assert r.status_code == 200 and "export function columns" in r.text
    assert r.headers["cache-control"] == "no-cache"


def test_prechauffage_de_l_index(tmp_path, monkeypatch):
    """D-094 : l'index de la norme est chargé au démarrage ; son état est visible dans /health."""
    import api.main as main

    calls = []
    monkeypatch.setattr(main, "get_retriever", lambda *a, **k: calls.append(a) or type("R", (), {"encoder": None})())
    main.warm_up(Settings(llm_provider="fake", rag_mode="bm25", trace_path=tmp_path / "t.jsonl"))
    assert calls and main.WARMUP["etat"] == "prêt" and main.WARMUP["duree_s"] is not None
