"""Options de recherche avancées (D-048, D-049) : reranker, index de questions, graphe des renvois."""

import json
from pathlib import Path

from rag.chunking import chunk_structural
from rag.graph import chunk_graph, paragraph_graph, parse_references
from rag.ingest import Unit
from rag.qindex import collect
from rag.retrieve import QuestionIndex, Retriever, rrf

TEXTS = {
    "44": "La marge sur services contractuels est ajustée pour tenir compte des variations des flux de "
          "trésorerie d'exécution afférents aux services futurs (voir paragraphes B96 à B100).",
    "B96": "Les variations liées aux services futurs comprennent les ajustements liés à l'expérience "
           "découlant des primes reçues au cours de la période.",
    "B97": "L'entité ne doit pas ajuster la marge pour l'effet de la valeur temps de l'argent.",
    "B98": "Paragraphe technique sans rapport direct.",
    "B99": "Autre paragraphe technique.",
    "B100": "Dernier paragraphe de la plage.",
    "36": "Les taux d'actualisation reflètent la valeur temps de l'argent (voir paragraphe 7 d'IFRS 15).",
}
KNOWN = list(TEXTS)


def units():
    return [Unit(unit_id=f"T:{p}", doc_id="T", zone="norme", paragraph_id=p, heading="Évaluation",
                 section="", text=t, page_start=1, page_end=1) for p, t in TEXTS.items()]


def chunks():
    return chunk_structural(units(), min_tokens=1)


def test_renvois_extraits_et_autres_normes_ignorees():
    assert parse_references("voir paragraphes B96 à B100", KNOWN) == ["B96", "B97", "B98", "B99", "B100"]
    assert parse_references("selon le paragraphe 44(c)", KNOWN) == ["44"]
    assert parse_references("voir paragraphe 7 d'IFRS 15", KNOWN) == []
    assert parse_references("paragraphes 36 à B100", KNOWN) == []          # plage trop large : ignorée


def test_graphe_des_morceaux():
    cs = chunks()
    pg = paragraph_graph([{"paragraph_id": p, "text": t} for p, t in TEXTS.items()])
    assert pg["44"][:2] == ["B96", "B97"] and "36" not in pg
    cg = chunk_graph(cs, pg)
    i44 = next(i for i, c in enumerate(cs) if "44" in c.paragraph_ids)
    assert {cs[j].paragraph_ids[0] for j in cg[i44]} >= {"B96", "B97"}


def test_graphe_ne_passe_pas_devant_le_resultat_qui_cite():
    cs = chunks()
    pg = paragraph_graph([{"paragraph_id": p, "text": t} for p, t in TEXTS.items()])
    r = Retriever(cs, graph=chunk_graph(cs, pg))
    hits = r.search("ajustement de la marge sur services contractuels services futurs", k=4, mode="bm25", graphe=True)
    ids = [h.chunk.paragraph_ids[0] for h in hits]
    assert ids[0] == "44" and "B96" in ids


class FakeReranker:
    """Préfère les passages qui contiennent « valeur temps »."""

    def __init__(self):
        self.calls = 0

    def score(self, query, texts):
        self.calls += 1
        return [1.0 if "valeur temps" in t else 0.0 for t in texts]


def test_reranker_reordonne_les_candidats():
    rk = FakeReranker()
    r = Retriever(chunks(), reranker=rk)
    base = r.search("marge sur services contractuels", k=3, mode="bm25")
    reranked = r.search("marge sur services contractuels", k=3, mode="bm25", rerank=True)
    assert rk.calls == 1 and "valeur temps" in reranked[0].chunk.text
    assert [h.chunk.chunk_id for h in base] != [h.chunk.chunk_id for h in reranked]


def test_options_par_defaut_et_desactivation():
    rk = FakeReranker()
    r = Retriever(chunks(), reranker=rk, options={"rerank": True})
    r.search("marge", k=2, mode="bm25")
    r.search("marge", k=2, mode="bm25", rerank=False)
    assert rk.calls == 1


def test_index_de_questions_remonte_le_bon_morceau():
    cs = chunks()
    target = next(i for i, c in enumerate(cs) if "36" in c.paragraph_ids)
    qi = QuestionIndex(["Quelle courbe utiliser pour escompter des rentes viagères illiquides ?"], [target])
    r = Retriever(cs, qindex=qi)
    q = "courbe pour escompter des rentes viagères"
    assert not r.search(q, k=1, mode="bm25")              # aucun mot commun avec la norme
    assert r.search(q, k=1, mode="bm25", questions=True)[0].chunk.paragraph_ids == ["36"]


def test_index_de_questions_filtre_les_questions_de_test():
    cs = chunks()
    records = [{"chunk_id": cs[0].chunk_id, "questions": [
        {"registre": "etudiant", "question": "Comment la marge est-elle ajustée pour les services futurs ?"},
        {"registre": "recherche", "question": "ajustement marge services futurs"},
        {"registre": "praticien", "question": "Faut-il revoir la CSM si les primes futures changent ?"}]}]
    tests = [{"question": "Comment la marge est-elle ajustée pour les services futurs ?"}]
    qs, ids, removed = collect(records, cs, tests)
    # la version mots-clés a les mêmes mots (racinisés) que la question de test : écartée aussi
    assert removed == 2 and qs == ["Faut-il revoir la CSM si les primes futures changent ?"]
    assert ids == [cs[0].chunk_id]


def test_rrf_pondere():
    fused = rrf([[(1, 0), (2, 0)], [(2, 0), (1, 0)]], weights=[1.0, 0.1])
    assert fused[0][0] == 1


def test_jeu_cas_pratiques_gele():
    path = Path(__file__).resolve().parent.parent / "eval" / "cas_pratiques.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 30 and all(r["gold"] for r in rows)
    assert len({r["id"] for r in rows}) == 30
