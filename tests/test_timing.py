"""Temps de réponse réel et sa décomposition (D-091) : l'assistant normatif affichait 0,9 s (rédaction seule) pour une
requête de près de 2 minutes."""

import json

import pytest

import core.llm as llm
from core.config import Settings
from core.llm import LLMClient, LLMRateLimit, LLMResponse
from core.registry import llm_timing


def test_attente_du_quota_dans_la_trace(tmp_path, monkeypatch):
    s = Settings(llm_provider="fake", llm_max_retries=1, trace_path=tmp_path / "t.jsonl")
    client = LLMClient(s, fake_responder=lambda m, model: "{}")
    calls = {"n": 0}

    def once(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise LLMRateLimit("HTTP 429", wait=0.0)
        return LLMResponse(text="{}", model="m", tokens_in=1, tokens_out=1)
    monkeypatch.setattr(client, "_call_once", once)
    monkeypatch.setattr(llm.time, "sleep", lambda x: None)
    client.chat([{"role": "user", "content": "x"}], trace={"agent": "verificateur", "case_id": "q1"})
    rec = json.loads((tmp_path / "t.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert rec["quota_waits"] == 1 and "quota_wait_s" in rec


def test_decomposition_par_agent(tmp_path):
    path = tmp_path / "t.jsonl"
    rows = [{"kind": "llm", "case_id": "q1", "agent": "routeur", "latency_ms": 800},
            {"kind": "llm", "case_id": "q1", "agent": "chercheur_rag", "latency_ms": 61_000, "quota_wait_s": 58.5},
            {"kind": "llm", "case_id": "q1", "agent": "chercheur_rag", "latency_ms": 900},
            {"kind": "llm", "case_id": "q1", "agent": "verificateur", "latency_ms": 1_200, "fallback": True},
            {"kind": "llm", "case_id": "autre", "agent": "routeur", "latency_ms": 99_000},
            {"kind": "tool", "case_id": "q1", "latency_ms": 5}]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    t = llm_timing(path, "q1")
    assert t["appels"] == 4 and t["modele_ms"] == 63_900 and t["attente_quota_s"] == 58.5 and t["secours"] == 1
    assert t["par_agent"]["recherche et rédaction"] == {"appels": 2, "ms": 61_900}
    assert llm_timing(tmp_path / "absent.jsonl", "q1")["appels"] == 0


def _client(tmp_path, monkeypatch, fallback="secours"):
    llm._BLOCKED.clear()
    s = Settings(llm_provider="fake", llm_max_retries=1, trace_path=tmp_path / "t.jsonl", llm_model_large="principal",
                 llm_fallback_model=fallback, llm_quota_max_wait_s=10)
    client = LLMClient(s, fake_responder=lambda m, model: "{}")
    seen, slept = [], []

    def once(messages, model, *a, **k):
        seen.append(model)
        if model == "principal":
            raise LLMRateLimit("HTTP 429", wait=40.0)
        return LLMResponse(text="{}", model=model)
    monkeypatch.setattr(client, "_call_once", once)
    monkeypatch.setattr(llm.time, "sleep", slept.append)
    return client, seen, slept


def test_quota_long_bascule_tout_de_suite_au_secours(tmp_path, monkeypatch):
    """D-092 : « attendez 40 s » avec un secours configuré → secours immédiat, puis le principal est évité."""
    client, seen, slept = _client(tmp_path, monkeypatch)
    assert client.chat([{"role": "user", "content": "x"}], model="large").model == "secours"
    assert client.chat([{"role": "user", "content": "y"}], model="large").model == "secours"
    assert seen == ["principal", "secours", "secours"] and slept == []          # aucune attente, principal évité
    recs = [json.loads(x) for x in (tmp_path / "t.jsonl").read_text(encoding="utf-8").splitlines()]
    assert recs[0]["quota_switch"] and recs[1]["quota_skipped"] and all(r["fallback"] for r in recs)
    llm._BLOCKED.clear()


def test_sans_secours_on_attend_comme_avant(tmp_path, monkeypatch):
    client, seen, slept = _client(tmp_path, monkeypatch, fallback="")
    with pytest.raises(llm.LLMError):
        client.chat([{"role": "user", "content": "x"}], model="large")
    assert set(seen) == {"principal"} and slept and slept[0] == 40.0
    llm._BLOCKED.clear()


def test_budget_d_attente_secours_bloque_aussi(tmp_path, monkeypatch):
    """Mesure du 25/10 : secours sur le même fournisseur, bloqué lui aussi → 300 s d'attente par appel. Avec le budget
    (LLM_MAX_WAIT_S), l'appel échoue vite et l'agent répond par son repli."""
    llm._BLOCKED.clear()
    s = Settings(llm_provider="fake", trace_path=tmp_path / "t.jsonl", llm_model_large="principal",
                 llm_fallback_model="secours", llm_quota_max_wait_s=10, llm_max_wait_s=45)
    client = LLMClient(s, fake_responder=lambda m, model: "{}")
    slept = []

    def once(messages, model, *a, **k):
        raise LLMRateLimit("HTTP 429", wait=60.0)
    monkeypatch.setattr(client, "_call_once", once)
    monkeypatch.setattr(llm.time, "sleep", slept.append)
    with pytest.raises(llm.LLMError):
        client.chat([{"role": "user", "content": "x"}], model="large")
    assert sum(slept) <= 45
    rec = json.loads((tmp_path / "t.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert rec["wait_budget_exceeded"] and rec["status"] == "error"
    llm._BLOCKED.clear()


def test_mode_mesure_un_seul_modele(monkeypatch):
    """D-096 : une évaluation n'a ni secours ni budget d'attente, quel que soit le .env."""
    from core.config import get_settings
    from eval import mode_mesure

    monkeypatch.setenv("LLM_FALLBACK_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setenv("LLM_MAX_WAIT_S", "5")
    mode_mesure()
    s = get_settings()
    assert s.llm_fallback_model == "" and s.llm_max_wait_s == -1 and s.llm_quota_max_wait_s == -1
    monkeypatch.setenv("IFRS17_MESURE_PROD", "1")
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "gemini-3.5-flash-lite")
    mode_mesure()
    get_settings.cache_clear()
    assert get_settings().llm_fallback_model == "gemini-3.5-flash-lite"


def test_rapport_rag_signale_une_mesure_incomplete():
    """Mesure du 25/10 : v2 sur les jeux de test, 3 et 5 questions perdues sur le quota, sans avertissement."""
    from types import SimpleNamespace

    from eval.eval_rag import render_report

    s = SimpleNamespace(rag_prompt_version=2, llm_model_large="m", router_mode="llm", rag_mode="hybrid",
                        rag_strategy="B", rag_glossary=True)
    from eval.eval_rag import aggregate

    agg = aggregate([])
    assert "Mesure incomplète" in render_report("x", s, agg, [], ["p21", "p25"], 0)
    assert "Mesure incomplète" in render_report("x", s, agg, [], [], 4)
    assert "Mesure incomplète" not in render_report("x", s, agg, [], [], 0)
