"""Vérificateur (LLM-juge) et boucle de correction de l'orchestrateur, avec un LLM factice."""

import json

from agents.pipeline import ask
from agents.schemas import GroundedAnswer, VerdictStatus
from agents.verifier import to_verdict, verify_answer
from core.config import Settings
from core.llm import LLMClient
from tests.test_rag_agent import GOOD, retriever

QUESTION = "Comment la CSM est-elle libérée selon les unités de couverture ?"
JUDGE_OK = {"analyse": [{"phrase": "La CSM…", "paragraphes": ["B119"], "soutenue": True,
                         "portee_respectee": True, "commentaire": ""}],
            "repond_a_la_question": True, "verdict": "ok", "problemes": []}
JUDGE_FIX = {"analyse": [], "repond_a_la_question": True, "verdict": "a_corriger",
             "problemes": [{"type": "hors_portee", "paragraphe": "B119",
                            "detail": "paragraphe propre à un cas particulier présenté comme général"}]}


def scripted(tmp_path, rag_answers, judge_answers):
    """Répond selon l'agent appelé (prompt système du juge ou de l'agent RAG)."""
    calls = {"rag": [], "juge": []}

    def respond(messages, model):
        who = "juge" if "réviseur IFRS 17" in messages[0]["content"] else "rag"
        calls[who].append(messages)
        seq = judge_answers if who == "juge" else rag_answers
        return json.dumps(seq[min(len(calls[who]) - 1, len(seq) - 1)], ensure_ascii=False)

    s = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl",
                 router_mode="heuristic", rag_mode="bm25", verifier_enabled=True, verifier_max_rounds=1)
    return s, LLMClient(s, fake_responder=respond), calls


def test_traduction_du_jugement():
    assert to_verdict(JUDGE_OK).status == VerdictStatus.OK
    v = to_verdict(JUDGE_FIX)
    assert v.status == VerdictStatus.FIX and v.issues[0].kind == "hors_portee"
    assert "[B119]" in v.issues[0].detail
    assert to_verdict({"verdict": "ok", "repond_a_la_question": False}).status == VerdictStatus.FIX
    assert to_verdict({"verdict": "a_corriger"}).issues[0].kind == "autre"


def test_un_refus_n_est_pas_juge(tmp_path):
    s, client, calls = scripted(tmp_path, [GOOD], [JUDGE_FIX])
    res = verify_answer("q", GroundedAnswer(answer=None, refused=True, refusal_reason="hors sujet"),
                        "", client)
    assert res.verdict.status == VerdictStatus.OK and not calls["juge"]


def test_correction_acceptee_au_second_tour(tmp_path):
    s, client, calls = scripted(tmp_path, [GOOD, GOOD], [JUDGE_FIX, JUDGE_OK])
    res = ask(QUESTION, s, client, retriever, k=3)
    assert res.first_verdict.status == VerdictStatus.FIX
    assert res.verdict.status == VerdictStatus.OK and res.rounds == 1
    second_prompt = calls["rag"][1][1]["content"]
    assert "rejetée par le vérificateur" in second_prompt and "hors_portee" in second_prompt
    assert "<extraits>" in calls["juge"][0][1]["content"] and "B119" in calls["juge"][0][1]["content"]


def test_probleme_persistant_validation_humaine(tmp_path):
    s, client, calls = scripted(tmp_path, [GOOD, GOOD], [JUDGE_FIX, JUDGE_FIX])
    res = ask(QUESTION, s, client, retriever, k=3)
    assert res.verdict.status == VerdictStatus.HUMAN and res.rounds == 1
    assert any("valider par un humain" in w for w in res.warnings)
    assert len(calls["rag"]) == 2 and len(calls["juge"]) == 2      # boucle bornée


def test_verificateur_desactive(tmp_path):
    s, client, calls = scripted(tmp_path, [GOOD], [JUDGE_FIX])
    s = Settings(**{**s.__dict__, "verifier_enabled": False})
    res = ask(QUESTION, s, LLMClient(s, fake_responder=client._fake), retriever, k=3)
    assert res.verdict is None and not calls["juge"]


def test_juge_illisible_validation_humaine(tmp_path):
    def respond(messages, model):
        return "pas du json" if "réviseur IFRS 17" in messages[0]["content"] else json.dumps(GOOD)

    s = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl",
                 router_mode="heuristic", rag_mode="bm25", verifier_enabled=True)
    res = ask(QUESTION, s, LLMClient(s, fake_responder=respond), retriever, k=3)
    assert res.verdict.status == VerdictStatus.HUMAN


def test_kappa_et_extraits_reconstitues():
    from eval.eval_verifier import kappa, rebuild_extracts
    from rag.chunking import chunk_structural
    from rag.ingest import Unit

    assert kappa(7, 0, 0, 41) == 1.0
    assert kappa(0, 0, 7, 41) == 0.0
    units = [Unit(unit_id="T:65", doc_id="T", zone="norme", paragraph_id="65",
                  heading="Contrats de réassurance détenus > Évaluation", section="ÉVALUATION",
                  text="Pour la réassurance détenue, la CSM est égale à la somme…", page_start=1, page_end=1)]
    text = rebuild_extracts(["65", "inconnu"], chunk_structural(units, min_tokens=1))
    assert text.startswith("[E1] Paragraphe(s) §65") and "Contrats de réassurance détenus" in text


def test_juge_ancre_preuve_dans_le_mauvais_paragraphe():
    """v2 : contenu juste mais cité sous le mauvais paragraphe → « non soutenu » (q28, q45, q46)."""
    from agents.verifier import evidence_issues, paragraph_texts

    extracts = ("[E1] Paragraphe(s) §44 — IFRS 17 > Évaluation ultérieure\n"
                "La valeur comptable de la marge est ajustée de l'intérêt capitalisé.\n\n"
                "[E2] Paragraphe(s) B119 — IFRS 17, annexe B\n"
                "L'entité répartit la marge entre les unités de couverture fournies.")
    texts = paragraph_texts(extracts)
    assert set(texts) == {"44", "B119"}
    good = [{"phrase": "La marge est répartie…", "paragraphes": ["B119"],
             "preuve": "répartit la marge entre les unités de couverture", "soutenue": True}]
    wrong = [{"phrase": "La marge est répartie…", "paragraphes": ["§44"],
              "preuve": "répartit la marge entre les unités de couverture", "soutenue": True}]
    assert evidence_issues(good, texts) == []
    issues = evidence_issues(wrong, texts)
    assert issues and issues[0].kind == "non_soutenu" and "[44]" in issues[0].detail
    # v1 (pas de champ « preuve ») : aucun contrôle supplémentaire
    assert evidence_issues([{"phrase": "x", "paragraphes": ["44"], "soutenue": True}], texts) == []


def test_politesse_sans_appel_llm(tmp_path):
    from agents.pipeline import SMALL_TALK_MESSAGE, THANKS_MESSAGE, small_talk
    s, client, calls = scripted(tmp_path, [GOOD], [JUDGE_OK])
    res = ask("salut", s, client, lambda: (_ for _ in ()).throw(AssertionError("RAG appelé")))
    assert res.small_talk and res.answer.refusal_reason == SMALL_TALK_MESSAGE
    assert not calls["rag"] and not calls["juge"]
    assert small_talk("comment vous êtes cv") == SMALL_TALK_MESSAGE
    assert small_talk("Merci beaucoup !") == THANKS_MESSAGE
    # une vraie question qui commence par une salutation suit la chaîne normale
    assert small_talk("Bonjour, comment la CSM est-elle libérée ?") is None
    assert small_talk("Donne-moi une recette de crêpes.") is None
