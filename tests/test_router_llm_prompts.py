"""Routeur, client LLM (fournisseur factice), bibliothèque de prompts et traces."""

import json

from agents.router import route_heuristic, route_llm
from agents.schemas import Intent
from core.config import Settings
from core.llm import LLMClient, extract_json
from core.prompts import all_prompt_files, load_prompt, load_prompt_file
from core.tracing import read_traces
from eval.eval_router import evaluate, load_cases


def fake_client(tmp_path, answer: str) -> LLMClient:
    s = Settings(llm_provider="fake", trace_path=tmp_path / "t.jsonl", llm_max_retries=0)
    return LLMClient(s, fake_responder=lambda messages, model: answer)


# ---------------------------------------------------------------- prompts
def test_toutes_les_fiches_de_prompt_sont_valides():
    files = all_prompt_files()
    assert files, "aucune fiche de prompt trouvée"
    for f in files:
        load_prompt_file(f)  # lève une erreur si la fiche est invalide


def test_gabarit_route_accepte_les_accolades():
    spec = load_prompt("route", 1)
    assert spec.variables() == {"request", "has_attachment"}
    out = spec.render(request='données {"a": 1}', has_attachment="non")
    assert '{"a": 1}' in out


# ---------------------------------------------------------------- routeur
def test_routeur_heuristique_seuil_minimal():
    """Garde-fou de régression : l'heuristique ne doit pas descendre sous 90 %."""
    assert evaluate(route_heuristic, load_cases())["exactitude"] >= 0.9


def test_fichier_joint_force_traitement_document():
    assert route_heuristic("bonjour", has_attachment=True).intent == Intent.DOCUMENT


def test_routeur_llm_utilise_la_reponse(tmp_path):
    c = fake_client(tmp_path, '```json\n{"intent": "calcul", "confidence": 0.9, "rationale": "ok"}\n```')
    plan = route_llm("Quelle est la météo ?", client=c)
    assert plan.intent == Intent.CALCULATION          # le LLM l'emporte quand sa sortie est valide
    assert plan.steps[-1].value == "redacteur"         # mais les étapes viennent du code


def test_routeur_llm_repli_si_json_invalide(tmp_path):
    c = fake_client(tmp_path, "je pense que c'est une question")
    plan = route_llm("Qu'est-ce que le CSM ?", client=c)
    assert plan.intent == Intent.NORM_QUESTION
    assert plan.rationale.startswith("repli heuristique")


def test_routeur_llm_repli_si_intention_inconnue(tmp_path):
    c = fake_client(tmp_path, '{"intent": "autre_chose", "confidence": 1}')
    assert route_llm("Qu'est-ce que le CSM ?", client=c).rationale.startswith("repli")


# ---------------------------------------------------------------- LLM + traces
def test_extract_json_texte_autour():
    assert extract_json('Voici : {"a": [1, 2]} merci') == {"a": [1, 2]}


def test_trace_ecrite_pour_chaque_appel(tmp_path):
    c = fake_client(tmp_path, '{"intent": "calcul", "confidence": 0.9, "rationale": "ok"}')
    route_llm("calcule le CSM", client=c, case_id="abc")
    traces = read_traces(tmp_path / "t.jsonl")
    assert len(traces) == 1
    t = traces[0]
    assert t["agent"] == "routeur" and t["prompt_id"] == "route" and t["case_id"] == "abc"
    assert t["status"] == "ok" and t["latency_ms"] >= 0 and t["tokens_in"] > 0
    json.dumps(t)


def test_bibliotheque_de_prompts_generee():
    from core.prompt_library import render
    from core.prompts import all_prompt_files, load_prompt_file

    specs = [load_prompt_file(p) for p in all_prompt_files()]
    text = render(specs)
    for s in specs:
        assert f"### `{s.id}` v{s.version}" in text
    assert "## Vue d'ensemble" in text and "llm_as_judge" in text
