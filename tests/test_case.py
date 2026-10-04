"""Dossier complet (orchestrateur + rédacteur) avec un LLM factice qui joue les 4 agents."""

import json
import re

import pytest

from agents.orchestrator import BASE_QUESTIONS, ONEROUS_QUESTION, run_case
from agents.schemas import PortfolioData
from agents.writer import facts, synthesis_issues
from core.config import Settings
from core.llm import LLMClient
from engine.csm import compute_csm
from tests.test_rag_agent import GOOD, retriever

JUDGE_OK = {"analyse": [], "repond_a_la_question": True, "verdict": "ok", "problemes": []}
PORTFOLIO = PortfolioData(group_id="G1", premiums=[100, 0, 0], outflows=[30, 30, 30],
                          coverage_units=[1, 1, 1], discount_rates=0.05, risk_adjustment_pct=0.05)


def agents_llm(tmp_path, extraction=None, synthesis=None):
    calls = {"extracteur": 0, "rag": 0, "juge": 0, "redacteur": 0}

    def respond(messages, model):
        system = messages[0]["content"]
        if "saisit les données" in system:
            calls["extracteur"] += 1
            return json.dumps(extraction)
        if "réviseur IFRS 17" in system:
            calls["juge"] += 1
            return json.dumps(JUDGE_OK)
        if "rédige la synthèse" in system:
            calls["redacteur"] += 1
            f = json.loads(re.search(r"<faits>\s*(\{.*\})\s*</faits>", messages[1]["content"], re.S).group(1))
            text = synthesis(f) if synthesis else (
                f"Le groupe est bénéficiaire : la CSM initiale est de {f['csm_initiale']} et sera "
                f"libérée selon les unités de couverture [B119].")
            return json.dumps({"synthese": text}, ensure_ascii=False)
        calls["rag"] += 1
        return json.dumps(GOOD)

    s = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl",
                 router_mode="heuristic", rag_mode="bm25", verifier_enabled=True,
                 norm_reference_path=tmp_path / "ref.json")
    client = LLMClient(s, fake_responder=respond)
    return s, (lambda: client), calls


def test_dossier_complet_note_prete(tmp_path):
    s, client, calls = agents_llm(tmp_path)
    out = run_case(b"", "", s, client, client, retriever, "c1", portfolio=PORTFOLIO)
    assert out.status == "note_prete" and not out.controls
    assert [st.agent for st in out.steps] == ["extracteur", "calculateur", "chercheur_rag+verificateur",
                                              "chercheur_rag+verificateur", "redacteur"]
    assert calls["rag"] == len(BASE_QUESTIONS) and calls["redacteur"] == 1
    note = out.note
    assert note.synthesis_source == "llm" and "14,22" in note.synthesis
    assert "<svg" in note.html and "| CSM initiale (§38) | 14,22 |" in note.markdown
    assert "[§B119]" in note.markdown


def test_synthese_avec_nombre_invente_remplacee_par_le_code(tmp_path):
    s, client, calls = agents_llm(tmp_path, synthesis=lambda f: "La CSM vaut 15,00 [B119].")
    out = run_case(b"", "", s, client, client, retriever, "c2", portfolio=PORTFOLIO)
    assert calls["redacteur"] == 2                         # une relance
    assert out.note.synthesis_source == "code"
    assert "14,22" in out.note.synthesis and "15,00" not in out.note.synthesis
    assert any("rejetée" in w for w in out.warnings)


def test_groupe_deficitaire_question_supplementaire(tmp_path):
    onerous = PortfolioData(group_id="G2", premiums=[100, 0, 0], outflows=[50, 50, 50],
                            coverage_units=[1, 1, 1], discount_rates=0.05, risk_adjustment_pct=0.05)
    s, client, calls = agents_llm(tmp_path, synthesis=lambda f: (
        f"Le groupe est déficitaire : perte immédiate de {f['perte_initiale']} [B119]."))
    out = run_case(b"", "", s, client, client, retriever, "c3", portfolio=onerous)
    assert out.csm.onerous and calls["rag"] == len(BASE_QUESTIONS) + 1
    assert out.norm[-1].question == ONEROUS_QUESTION


def test_extraction_a_verifier_validation_humaine(tmp_path):
    pytest.importorskip("reportlab")
    from multimodal.synth import generate

    generate(n_docs=1, out_dir=tmp_path, cases_path=tmp_path / "c.jsonl", images=False)
    case = json.loads((tmp_path / "c.jsonl").read_text(encoding="utf-8"))
    wrong = {**case["truth"], "premiums": [p * 1.5 + 1 for p in case["truth"]["premiums"]]}
    s, client, _ = agents_llm(tmp_path, extraction=wrong)
    pdf = (tmp_path / f"{case['id']}.pdf").read_bytes()
    out = run_case(pdf, "application/pdf", s, client, client, retriever, "c4")
    assert out.extraction.status == "a_verifier" and out.status == "validation_humaine"
    assert out.note is not None and "À VALIDER" in out.note.markdown
    assert any(c.startswith("extraction :") for c in out.controls)


def test_controle_de_la_synthese():
    f = facts(PORTFOLIO, compute_csm(PORTFOLIO), [])
    refs = {"38", "B119"}
    assert synthesis_issues(f"La CSM initiale est de {f['csm_initiale']} sur 3 périodes [§38].", f, refs) == []
    assert synthesis_issues("La CSM est de 99,99 [§38].", f, refs) == ["nombre absent des faits : 99,99"]
    assert synthesis_issues(f"CSM de {f['csm_initiale']} [§47].", f, refs) == [
        "paragraphe cité hors des passages fournis : 47"]


def test_reponses_de_reference_reutilisees(tmp_path):
    """Une référence acceptée par le vérificateur ou validée par un humain évite les appels RAG."""
    from agents.reference import BASE_QUESTIONS as QS
    from agents.reference import usable

    s, client, calls = agents_llm(tmp_path)
    ok = {"question": QS[0], "answer": {"answer": "La CSM… [§38]", "citations": [
        {"paragraph_id": "38", "doc": "C002", "quote": "profit non acquis", "chunk_id": "B:C002:38"}],
        "refused": False, "refusal_reason": None}, "verdict": "ok", "valide": False}
    doubtful = {**ok, "question": QS[1], "verdict": "validation_humaine", "valide": False}
    (tmp_path / "ref.json").write_text(json.dumps([ok, doubtful]), encoding="utf-8")
    assert usable(ok) is not None and usable(doubtful) is None
    assert usable({**doubtful, "valide": True}) is not None
    out = run_case(b"", "", s, client, client, retriever, "c5", portfolio=PORTFOLIO)
    assert calls["rag"] == 1                                  # seule la réponse douteuse est recalculée
    assert out.steps[2].agent == "chercheur_rag" and out.steps[2].status == "reference"
