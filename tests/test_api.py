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
                        trace_path=tmp_path / "traces.jsonl")
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
