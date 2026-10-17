"""Les tests ne dépendent pas du .env de la machine : les options mesurées et laissées
désactivées (ex. RAG_REWRITE=1 gardé après une mesure, D-045) changeraient le nombre d'appels LLM."""

import pytest

from core.config import get_settings

DEFAULTS = {"RAG_REWRITE": "0", "N8N_VALIDATION_URL": "", "RAG_AGENTIC": "0", "RAG_GRAPH": "0",
            "RAG_QUESTIONS": "0", "RAG_RERANK_MODEL": ""}


@pytest.fixture(autouse=True)
def _environnement_neutre(monkeypatch):
    for name, value in DEFAULTS.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
