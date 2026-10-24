"""Les tests ne dépendent pas du .env de la machine : les options mesurées et laissées
désactivées (ex. RAG_REWRITE=1 gardé après une mesure, D-045) changeraient le nombre d'appels LLM."""

import pytest

from core.config import get_settings

DEFAULTS = {"RAG_REWRITE": "0", "N8N_VALIDATION_URL": "", "RAG_AGENTIC": "0", "RAG_GRAPH": "0",
            "RAG_QUESTIONS": "0", "RAG_RERANK_MODEL": ""}


@pytest.fixture(autouse=True)
def _environnement_neutre(monkeypatch, tmp_path):
    for name, value in DEFAULTS.items():
        monkeypatch.setenv(name, value)
    # registre et comptes : une base neuve par test, jamais data/registry.db (D-058)
    monkeypatch.setenv("REGISTRY_PATH", str(tmp_path / "registry.db"))
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    monkeypatch.setenv("COPILOT_CHECKPOINTS", str(tmp_path / "checkpoints.db"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
