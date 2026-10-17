"""Agent de recherche LangGraph (D-050) avec un LLM factice : plan, recherche, notation, boucle bornée."""

import json

import pytest

from agents.agentic_rag import MAX_ROUNDS, AgenticSearch
from core.config import Settings
from core.llm import LLMClient
from rag.chunking import chunk_structural
from rag.ingest import Unit
from rag.retrieve import Retriever

TEXTS = {
    "47": "Un contrat d'assurance est déficitaire à la date de comptabilisation initiale si les flux de "
          "trésorerie d'exécution affectés au contrat représentent une sortie nette.",
    "57": "Si les faits et circonstances indiquent qu'un groupe de contrats évalué selon la méthode "
          "d'affectation des primes est déficitaire, l'entité calcule l'écart avec les flux d'exécution.",
    "83": "Les produits des activités d'assurance traduisent la fourniture de services.",
    "36": "Les taux d'actualisation reflètent la valeur temps de l'argent.",
}
QUESTION = "Nos contrats auto annuels affichent un ratio sinistres sur primes de 120 %. Que faire ?"


def retriever():
    units = [Unit(unit_id=f"T:{p}", doc_id="T", zone="norme", paragraph_id=p, heading="Titre",
                  section="", text=t, page_start=1, page_end=1) for p, t in TEXTS.items()]
    return Retriever(chunk_structural(units, min_tokens=1))


def scripted(*answers):
    calls = []

    def respond(messages, model):
        calls.append(messages)
        a = answers[min(len(calls) - 1, len(answers) - 1)]
        if isinstance(a, Exception):
            raise a
        return json.dumps(a, ensure_ascii=False)

    return respond, calls


def client(tmp_path, responder):
    return LLMClient(Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl"),
                     fake_responder=responder)


PLAN = {"situation": "groupe PAA dont les sinistres dépassent les primes",
        "mecanismes": ["groupe de contrats déficitaire en méthode d'affectation des primes"],
        "requetes": ["groupe déficitaire méthode d'affectation des primes"]}


def drive(agent, question):
    """Mêmes transitions que build_graph (le test complet avec LangGraph est plus bas)."""
    st = {"question": question, "round": 0, "steps": [], "llm_calls": 0}
    for node in (agent.plan, agent.search, agent.grade):
        st.update(node(st))
    while agent.route(st) == "rechercher":
        st.update(agent.requery(st))
        st.update(agent.search(st))
        st.update(agent.grade(st))
    st.update(agent.finish(st))
    return st


def grades_for(agent, st, wanted):
    """Réponse de l'évaluateur : « pertinent » pour les morceaux dont le paragraphe est dans wanted."""
    pool = agent._pool(st)
    return [{"extrait": f"E{i}", "pertinence": "pertinent" if agent.by_id[c].paragraph_ids[0] in wanted else "hors_sujet"}
            for i, c in enumerate(pool, start=1)]


def test_plan_puis_passages_pertinents_en_tete(tmp_path):
    r = retriever()
    agent0 = AgenticSearch(r, None, mode="bm25")
    st0 = {"question": QUESTION, "pending": [QUESTION, *PLAN["requetes"]]}
    st0.update(agent0.search(st0))
    grade = {"notes": grades_for(agent0, st0, {"57"}), "suffisant": True, "manque": "", "nouvelle_requete": None}
    respond, calls = scripted(PLAN, grade)
    agent = AgenticSearch(r, client(tmp_path, respond), mode="bm25")
    st = drive(agent, QUESTION)
    assert len(calls) == 2 and st["llm_calls"] == 2
    assert agent.hits(st)[0].chunk.paragraph_ids == ["57"]
    assert all(agent.by_id[c].paragraph_ids[0] != "36" for c in st["final"])   # hors sujet retiré
    assert "<question>" in calls[0][1]["content"]                                # données délimitées
    assert [s["noeud"] for s in st["steps"]] == ["planifier", "chercher", "evaluer", "conclure"]


def test_nouvelle_recherche_bornee(tmp_path):
    insufficient = {"notes": [], "suffisant": False, "manque": "la règle", "nouvelle_requete": "valeur temps de l'argent"}
    respond, calls = scripted(PLAN, insufficient, insufficient, insufficient)
    agent = AgenticSearch(retriever(), client(tmp_path, respond), mode="bm25")
    st = drive(agent, QUESTION)
    assert st["round"] == MAX_ROUNDS and len(calls) == 2 + MAX_ROUNDS
    assert "valeur temps de l'argent" in st["queries"]


def test_llm_indisponible_ne_bloque_pas(tmp_path):
    from core.llm import LLMError
    respond, _ = scripted(LLMError("panne"), LLMError("panne"))
    agent = AgenticSearch(retriever(), client(tmp_path, respond), mode="bm25")
    st = drive(agent, "déficitaire méthode d'affectation des primes")
    assert st["queries"] == ["déficitaire méthode d'affectation des primes"]   # repli : la question seule
    assert st["final"]                                                          # l'ordre de la recherche est gardé


def test_notes_invalides_ignorees(tmp_path):
    bad = {"notes": [{"extrait": "E99", "pertinence": "pertinent"}, {"extrait": "E1", "pertinence": "excellent"},
                     "texte"], "suffisant": True}
    respond, _ = scripted(PLAN, bad)
    agent = AgenticSearch(retriever(), client(tmp_path, respond), mode="bm25")
    st = drive(agent, QUESTION)
    assert st["grades"] == {} and st["sufficient"] is False


def test_graphe_langgraph_complet(tmp_path):
    pytest.importorskip("langgraph")
    from agents.agentic_rag import agentic_search
    respond, calls = scripted(PLAN, {"notes": [{"extrait": "E1", "pertinence": "pertinent"}], "suffisant": True})
    res = agentic_search(QUESTION, retriever(), client(tmp_path, respond), mode="bm25", k=3)
    assert res.hits and res.llm_calls == 2 and len(calls) == 2
    assert [s["noeud"] for s in res.steps][0] == "planifier"
