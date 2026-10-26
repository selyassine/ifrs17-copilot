"""Cache de la recherche dans la norme pour le Copilot (D-089) : même réponse, sans refaire la chaîne."""

from types import SimpleNamespace

import pytest

import agents.pipeline as pipeline
from agents.copilot import clear_norm_cache, norm_search_with
from core.config import Settings


def _result(status="ok", refused=False):
    cit = SimpleNamespace(paragraph_id="§42", quote="comptabiliser les variations")
    answer = SimpleNamespace(refused=refused, refusal_reason="hors corpus" if refused else "",
                             answer="Le LIC est le passif au titre des sinistres survenus.", citations=[cit])
    return SimpleNamespace(answer=answer, verdict=SimpleNamespace(status=SimpleNamespace(value=status)))


@pytest.fixture
def calls(monkeypatch):
    clear_norm_cache()
    box = {"n": 0, "status": "ok", "refused": False}

    def fake(question, settings, client, retriever, case_id=""):
        box["n"] += 1
        return _result(box["status"], box["refused"])
    monkeypatch.setattr(pipeline, "verified_answer", fake)
    yield box
    clear_norm_cache()


def test_meme_question_reutilise_la_reponse(calls):
    s = Settings(llm_provider="fake")
    search = norm_search_with(s, None, lambda: None, "c1")
    first = search("Qu'est-ce que le LIC ?")
    again = search("  qu'est-ce que le LIC  ")             # casse, espaces et « ? » ignorés
    assert calls["n"] == 1
    assert again["reponse"] == first["reponse"] and again["citations"] == first["citations"]
    assert again.get("cache") is True and "cache" not in first
    again["citations"].append("modifié")                   # la copie renvoyée ne touche pas le cache
    assert len(search("Qu'est-ce que le LIC ?")["citations"]) == 1


def test_autre_configuration_autre_cle(calls):
    norm_search_with(Settings(llm_provider="fake", rag_prompt_version=2), None, lambda: None)("Le LIC ?")
    norm_search_with(Settings(llm_provider="fake", rag_prompt_version=1), None, lambda: None)("Le LIC ?")
    assert calls["n"] == 2


@pytest.mark.parametrize("status,refused", [("a_corriger", False), ("validation_humaine", False), ("ok", True)])
def test_refus_et_reponses_a_corriger_jamais_gardes(calls, status, refused):
    calls.update(status=status, refused=refused)
    search = norm_search_with(Settings(llm_provider="fake"), None, lambda: None)
    search("Le LIC ?")
    search("Le LIC ?")
    assert calls["n"] == 2


def test_evaluation_sans_cache(calls):
    search = norm_search_with(Settings(llm_provider="fake"), None, lambda: None, cache=False)
    search("Le LIC ?")
    search("Le LIC ?")
    assert calls["n"] == 2
