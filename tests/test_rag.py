"""Tests du RAG sur des données synthétiques (la CI n'a pas le PDF du corpus).

Un test d'intégration sur le vrai règlement s'exécute seulement si le PDF est présent.
"""

from pathlib import Path

import pytest

from eval.eval_retrieval import mrr, ndcg, recall_at, recall_at_budget
from rag.chunking import Chunk, chunk_fixed, chunk_structural, pack, sentence_spans
from rag.ingest import Line, Unit, parse_units
from rag.query import expand_glossary
from rag.retrieve import BM25, HashingEncoder, Retriever, analyze, rrf


# --------------------------------------------------------------------------- ingestion
def L(text, x0=95.0, size=9.6, font="regular", gap=10.7, page=1, words=None):  # noqa: N802
    return Line(text=text, page=page, x0=x0, top=100.0, size=size, font=font, gap=gap,
                words=words or [])


def W(text, x0):  # noqa: N802
    return {"text": text, "x0": x0}


def synthetic_lines():
    return [
        L("(1) Premier considérant du règlement.", x0=68),
        L("(2) Second considérant,", x0=68),
        L("qui continue ici.", x0=94),
        L("Article premier", x0=280),
        L("Le texte de l'article premier."),
        L("ANNEXE", x0=282, size=8.5),
        L("OBJECTIF", x0=68, size=8.5),
        L("1 La norme établit des principes.", x0=68, font="bold", gap=20),
        L("Suite du paragraphe un.", font="bold"),
        L("Marge sur services contractuels", font="bold", gap=21),
        L("2 La marge représente le profit non acquis.", x0=68, gap=20),
        L("5 % des primes ne sont pas un paragraphe.", x0=95),
        L("99 Saut trop grand : pas un paragraphe.", x0=68),
        L("2A Paragraphe inséré.", x0=68, gap=20),
        L("Annexe A", x0=68, font="italic"),
        L("marge sur services Composante de la valeur comptable",
          x0=68, words=[W("marge", 68), W("sur", 95), W("services", 115),
                        W("Composante", 190), W("de", 250), W("la", 262), W("valeur", 272),
                        W("comptable", 310)]),
        L("contractuels du groupe.", x0=68, words=[W("contractuels", 68), W("du", 190), W("groupe.", 205)]),
        L("risque financier Risque d'une variation future.",
          x0=68, words=[W("risque", 68), W("financier", 100), W("Risque", 190), W("d'une", 225),
                        W("variation", 250), W("future.", 290)]),
        L("Annexe B", x0=68, font="italic"),
        L("B1 Guide d'application.", x0=68, gap=20),
        L("Annexe D", x0=68, font="italic"),
        L("B1 Paragraphe d'une autre norme, à ignorer.", x0=68, gap=20),
    ]


def test_parse_units_zones_et_identifiants():
    units = parse_units(synthetic_lines(), "T")
    ids = [u.paragraph_id for u in units]
    assert ids == ["cons-1", "cons-2", "art-1", "1", "2", "2A",
                   "def:marge sur services contractuels", "def:risque financier", "B1"]
    by = {u.paragraph_id: u for u in units}
    assert by["cons-2"].text == "Second considérant, qui continue ici."
    assert by["1"].text == "La norme établit des principes. Suite du paragraphe un."
    assert by["1"].section == "OBJECTIF"
    assert by["2"].heading == "Marge sur services contractuels"
    assert "5 % des primes" in by["2"].text and "Saut trop grand" in by["2"].text
    assert by["def:marge sur services contractuels"].text == "Composante de la valeur comptable du groupe."
    assert all(u.zone != "annexe_D" for u in units)


# --------------------------------------------------------------------------- découpage
def units_fixture(n=12, words=60):
    return [Unit(unit_id=f"T:{i}", doc_id="T", zone="norme", paragraph_id=str(i),
                 heading="Titre" if i < 6 else "Autre", section="ÉVALUATION",
                 text=" ".join(f"mot{i}_{j}." if j % 15 == 14 else f"mot{i}_{j}" for j in range(words)),
                 page_start=i, page_end=i) for i in range(1, n + 1)]


def test_sentence_spans_couvrent_le_texte():
    text = "Première phrase. Deuxième ; troisième\nquatrième"
    assert [text[s:e] for s, e in sentence_spans(text)] == [
        "Première phrase.", "Deuxième ;", "troisième", "quatrième"]


def test_pack_respecte_taille_et_chevauchement():
    text = " ".join(f"Phrase numéro {i} avec quelques mots." for i in range(200))
    windows = pack(text, max_tokens=100, overlap=20)
    assert len(windows) > 5
    assert all(len(text[s:e].split()) * 1.4 <= 100 + 15 for s, e in windows)
    assert all(windows[i + 1][0] < windows[i][1] for i in range(len(windows) - 1))  # chevauchement


def test_chunk_fixed_couvre_tous_les_paragraphes():
    units = units_fixture()
    chunks = chunk_fixed(units, max_tokens=200, overlap=30)
    covered = {p for c in chunks for p in c.paragraph_ids}
    assert covered == {u.paragraph_id for u in units}
    assert all(c.n_tokens <= 230 for c in chunks)


def test_chunk_structural_un_chunk_par_paragraphe_avec_entete():
    units = units_fixture()
    chunks = chunk_structural(units)
    assert [c.paragraph_ids for c in chunks] == [[u.paragraph_id] for u in units]
    assert chunks[0].embed_text.startswith("IFRS 17 > Évaluation > Titre\nParagraphe 1\n")
    assert chunks[0].text == units[0].text


def test_chunk_structural_fusionne_les_courts_et_coupe_les_longs():
    units = units_fixture(n=4, words=10)
    units[2].text = " ".join(["long"] * 1200) + "."
    chunks = chunk_structural(units, min_tokens=20, max_tokens=300)
    assert chunks[0].paragraph_ids == ["1", "2"]                 # fusion
    parts = [c for c in chunks if c.paragraph_ids == ["3"]]
    assert len(parts) >= 5 and parts[0].chunk_id.endswith("#1")  # découpe


# --------------------------------------------------------------------------- recherche
def test_analyseur_francais():
    assert analyze("Les unités de couverture") == analyze("unité couverture")
    assert "b119" in analyze("voir le paragraphe B119")


def test_bm25_classe_le_bon_document_en_tete():
    docs = ["le chat dort sur le canapé", "la marge sur services contractuels est libérée",
            "le taux d'actualisation reflète la valeur temps"]
    top = BM25(docs).search("libération de la marge sur services contractuels", k=3)
    assert top[0][0] == 1


def test_rrf_favorise_les_documents_presents_dans_les_deux_listes():
    fused = rrf([[(1, 9.0), (2, 8.0)], [(3, 0.9), (2, 0.8)]])
    assert fused[0][0] == 2


def test_retriever_modes_et_filtre_de_zone():
    units = units_fixture()
    units[0].zone = "annexe_B"
    chunks = chunk_structural(units)
    r = Retriever(chunks, encoder=HashingEncoder())
    for mode in ("bm25", "dense", "hybrid"):
        hits = r.search("mot3_4 mot3_5", k=3, mode=mode)
        assert hits[0].chunk.paragraph_ids == ["3"]
    only_b = r.search("mot3_4", k=5, mode="hybrid", zones=["annexe_B"])
    assert {h.chunk.zone for h in only_b} == {"annexe_B"}


def test_mode_dense_sans_index_refuse():
    r = Retriever(chunk_structural(units_fixture()))
    with pytest.raises(RuntimeError):
        r.search("x", mode="dense")


def test_glossaire():
    assert "marge sur services contractuels" in expand_glossary("Comment libérer la CSM ?")
    assert expand_glossary("Question sans sigle") == "Question sans sigle"


# --------------------------------------------------------------------------- métriques
def C(pids, n=100):  # noqa: N802
    return Chunk(chunk_id="-".join(pids), strategy="B", doc_id="T", text="", embed_text="",
                 paragraph_ids=pids, zone="norme", n_tokens=n)


def test_metriques_de_retrieval():
    ranked = [C(["9"]), C(["44"]), C(["45", "46"])]
    gold = {"44", "45"}
    assert recall_at(ranked, gold, 1) == 0
    assert recall_at(ranked, gold, 3) == 1
    assert mrr(ranked, gold) == 0.5
    assert 0 < ndcg(ranked, gold, ranked + [C(["44", "45"])]) < 1
    assert recall_at_budget([C(["44"], 600), C(["45"], 600)], gold, 1000) == 0.5


# --------------------------------------------------------------------------- intégration
PDF = Path(__file__).resolve().parent.parent / "data" / "corpus" / "C002_reg_2021_2036_fr.pdf"


@pytest.mark.skipif(not PDF.exists(), reason="PDF du règlement absent (data/corpus/)")
def test_integration_reglement_2021_2036():
    pytest.importorskip("pdfplumber")
    from rag.ingest import ingest

    units = ingest(PDF, "C002")
    count = {z: sum(1 for u in units if u.zone == z) for z in
             ("reglement", "norme", "annexe_A", "annexe_B", "annexe_C")}
    assert count == {"reglement": 20, "norme": 148, "annexe_A": 22, "annexe_B": 156, "annexe_C": 51}
    by = {u.paragraph_id: u for u in units}
    assert by["44"].text.startswith("Dans le cas des contrats d'assurance sans éléments")
    assert by["B119"].heading.startswith("Comptabilisation de la marge sur services contractuels")
