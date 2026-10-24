"""Comparaison « appel unique » contre la chaîne (D-066) : lecture de la réponse et verdicts."""

import json

from core.config import Settings
from core.llm import LLMClient
from eval.eval_monolithique import judge_monolithic, monolithic, verdict

CASE = {"id": "x", "attendu": "exact", "csm_attendu": 397.89, "perte_attendue": 0.0}


def _client(tmp_path, answer):
    s = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl")
    return LLMClient(s, fake_responder=lambda messages, model: answer)


def test_reponse_lue_et_jugee(tmp_path):
    m = monolithic("doc", _client(tmp_path, json.dumps({"groupe": "G", "csm_initiale": 396.0, "perte_initiale": 0,
                                                        "statut": "ok", "raison": "r"})), "c")
    row = judge_monolithic(CASE, m)
    assert row["csm_ok"] is False and row["csm_ok_1pc"] is True and row["verdict"] == "DANGEREUX"
    m = monolithic("doc", _client(tmp_path, '{"csm_initiale": 397.89, "perte_initiale": 0, "statut": "ok"}'), "c")
    assert judge_monolithic(CASE, m)["verdict"] == "réussi"


def test_reponse_illisible_et_alertes(tmp_path):
    m = monolithic("doc", _client(tmp_path, "pas de JSON"), "c")
    assert m["statut"] == "illisible" and judge_monolithic(CASE, m)["verdict"] == "erreur rattrapée"
    assert verdict("alerte", flagged=False, right=False) == "DANGEREUX"
    assert verdict("alerte", flagged=True, right=False) == "alerte levée"
    assert verdict("exact", flagged=True, right=True) == "fausse alerte"
