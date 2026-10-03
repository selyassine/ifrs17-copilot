"""Agent RAG avec un LLM factice : citations vérifiées, correction bornée, refus."""

import json

from agents.rag_agent import answer_question, check, format_extracts, normalize_ref
from core.config import Settings
from core.llm import LLMClient
from rag.chunking import chunk_structural
from rag.ingest import Unit
from rag.retrieve import Retriever

TEXTS = {
    "44": "Dans le cas des contrats sans éléments de participation directe, la marge sur services "
          "contractuels est ajustée pour tenir compte de l'intérêt capitalisé et des variations "
          "des flux de trésorerie d'exécution afférents aux services futurs.",
    "B119": "À chaque période, l'entité comptabilise en résultat net un montant de la marge sur "
            "services contractuels selon les unités de couverture fournies.",
    "36": "Les taux d'actualisation reflètent la valeur temps de l'argent.",
}


def retriever() -> Retriever:
    units = [Unit(unit_id=f"T:{p}", doc_id="T", zone="norme", paragraph_id=p, heading="Titre",
                  section="", text=t, page_start=1, page_end=1) for p, t in TEXTS.items()]
    return Retriever(chunk_structural(units, min_tokens=1))


def scripted(*answers):
    """LLM factice qui renvoie les réponses dans l'ordre et garde les messages reçus."""
    calls = []

    def respond(messages, model):
        calls.append(messages)
        return json.dumps(answers[min(len(calls) - 1, len(answers) - 1)], ensure_ascii=False)

    return respond, calls


def client(tmp_path, responder) -> LLMClient:
    s = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl")
    return LLMClient(s, fake_responder=responder)


GOOD = {"answer": "La CSM est libérée selon les unités de couverture [B119].",
        "citations": [{"paragraph_id": "B119", "extrait": "E1",
                       "quote": "l'entité comptabilise en résultat net un montant"}],
        "refused": False, "refusal_reason": None}


def test_normalize_ref():
    assert normalize_ref("§44(c)") == ["44"]
    assert normalize_ref("B119 ; C5") == ["B119", "C5"]
    assert normalize_ref("article premier") == ["art-1"]


def test_reponse_correcte_acceptee(tmp_path):
    respond, calls = scripted(GOOD)
    res = answer_question("Comment la CSM est-elle libérée selon les unités de couverture ?",
                          retriever(), client(tmp_path, respond), k=3, mode="bm25")
    assert not res.answer.refused
    assert [c.paragraph_id for c in res.answer.citations] == ["B119"]
    assert res.corrections == 0 and not res.warnings
    prompt = calls[0][1]["content"]
    assert "[E1]" in prompt and "Paragraphes que tu as le droit de citer" in prompt


def test_citation_inventee_corrigee_en_une_relance(tmp_path):
    bad = {**GOOD, "answer": "La CSM est libérée [B119] et ajustée selon [§99]."}
    respond, calls = scripted(bad, GOOD)
    res = answer_question("libération de la CSM unités de couverture", retriever(),
                          client(tmp_path, respond), k=3, mode="bm25")
    assert res.corrections == 1 and len(calls) == 2
    assert "§99" not in res.answer.answer
    assert res.raw_invalid_refs  # l'erreur initiale reste mesurable
    assert "99" in calls[1][-1]["content"]  # le retour d'erreur est envoyé au LLM


def test_citation_inventee_persistante_retiree(tmp_path):
    bad = {**GOOD, "answer": "La CSM est libérée [B119] et ajustée selon [§99]."}
    respond, calls = scripted(bad, bad)
    res = answer_question("libération de la CSM unités de couverture", retriever(),
                          client(tmp_path, respond), k=3, mode="bm25")
    assert len(calls) == 2  # correction bornée à une relance
    assert "[§99]" not in res.answer.answer and "[B119]" in res.answer.answer
    assert any("99" in w for w in res.warnings)


def test_reponse_sans_source_valide_devient_refus(tmp_path):
    bad = {"answer": "Voir le paragraphe [§99].", "citations": [{"paragraph_id": "99"}],
           "refused": False, "refusal_reason": None}
    respond, _ = scripted(bad, bad)
    res = answer_question("question", retriever(), client(tmp_path, respond), k=3, mode="bm25")
    assert res.answer.refused


def test_refus_du_llm(tmp_path):
    refus = {"answer": None, "citations": [], "refused": True,
             "refusal_reason": "Hors du champ d'IFRS 17."}
    respond, calls = scripted(refus)
    res = answer_question("Donne-moi une recette de crêpes", retriever(),
                          client(tmp_path, respond), k=3, mode="bm25")
    assert res.answer.refused and len(calls) == 1


def test_citation_fausse_extrait_remplace(tmp_path):
    cite = {**GOOD, "citations": [{"paragraph_id": "B119", "extrait": "E1",
                                   "quote": "phrase totalement inventée sans rapport"}]}
    respond, _ = scripted(cite)
    res = answer_question("libération CSM unités de couverture", retriever(),
                          client(tmp_path, respond), k=3, mode="bm25")
    assert res.answer.citations[0].quote.startswith("À chaque période")
    assert any("non retrouvé" in w for w in res.warnings)


def test_reponse_illisible(tmp_path):
    res = answer_question("question", retriever(),
                          client(tmp_path, lambda m, model: "pas du JSON"), k=3, mode="bm25")
    assert res.answer.refused and "illisible" in res.warnings[0]


def test_check_detecte_mauvais_extrait():
    hits = retriever().search("marge services contractuels unités couverture", k=3, mode="bm25")
    _, by_id, allowed = format_extracts(hits)
    eid_b119 = next(e for e, h in by_id.items() if "B119" in h.chunk.paragraph_ids)
    other = next(e for e in by_id if e != eid_b119)
    problems = check({"answer": "x [B119]", "citations": [{"paragraph_id": "B119", "extrait": other}]},
                     by_id, allowed)
    assert any("attribuée" in p for p in problems)


def test_prompt_v2_montre_la_portee(tmp_path):
    """v2 affiche le chemin dans la norme (annexe, section) ; v1 garde le titre court (D-024)."""
    units = [Unit(unit_id="T:C13", doc_id="T", zone="annexe_C", paragraph_id="C13",
                  heading="Détermination de la marge", section="DISPOSITIONS TRANSITOIRES",
                  text="L'entité doit déterminer les taux d'actualisation à la date de transition.",
                  page_start=1, page_end=1)]
    r = Retriever(chunk_structural(units, min_tokens=1))
    for version, attendu, absent in [(1, "— Détermination de la marge", "annexe C"),
                                     (2, "IFRS 17, annexe C (entrée en vigueur et transition) > "
                                         "Dispositions transitoires > Détermination de la marge", None)]:
        respond, calls = scripted({"answer": None, "citations": [], "refused": True,
                                   "refusal_reason": "test"})
        answer_question("Quels taux d'actualisation à la transition ?", r,
                        client(tmp_path, respond), k=1, mode="bm25", version=version)
        prompt = calls[0][1]["content"]
        assert attendu in prompt
        if absent:
            assert absent not in prompt
        if version == 2:
            assert "portée" in calls[0][0]["content"]
