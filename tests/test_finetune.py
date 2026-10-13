"""Données du fine-tuning de BGE-M3 (D-046) : génération reprise, filtre de fuite, négatifs difficiles."""

import json
import zipfile

from core.config import Settings
from core.llm import LLMClient
from rag.chunking import chunk_structural
from rag.finetune import (
    build_training_set,
    copied_span,
    generate_pairs,
    hard_negative,
    leaks,
    parse_questions,
    read_jsonl,
    word_set,
    write_bundle,
)
from rag.ingest import Unit
from rag.retrieve import BM25

TEXTS = {
    "44": "Dans le cas des contrats sans éléments de participation directe, la valeur comptable de la marge "
          "sur services contractuels est ajustée pour tenir compte de l'intérêt capitalisé et des variations "
          "des flux de trésorerie d'exécution afférents aux services futurs, à la date de clôture.",
    "B119": "À chaque période, l'entité comptabilise en résultat net un montant de la marge sur services "
            "contractuels pour refléter les services fournis, selon les unités de couverture du groupe, "
            "en répartissant la marge à la fin de la période de manière égale.",
    "36": "Les taux d'actualisation appliqués aux estimations des flux de trésorerie futurs reflètent la "
          "valeur temps de l'argent, les caractéristiques des flux et celles de la liquidité des contrats.",
}


def chunks():
    units = [Unit(unit_id=f"T:{p}", doc_id="T", zone="norme", paragraph_id=p, heading="Évaluation",
                  section="", text=t, page_start=1, page_end=1) for p, t in TEXTS.items()]
    return chunk_structural(units, min_tokens=1)


def client(tmp_path, responder) -> LLMClient:
    s = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl")
    return LLMClient(s, fake_responder=responder)


QS = {"questions": [
    {"registre": "etudiant", "question": "Comment on relâche la CSM chaque année ?"},
    {"registre": "praticien", "question": "Quel montant de marge passer en résultat à la clôture ?"},
    {"registre": "recherche", "question": "libération CSM unités couverture"},
    {"registre": "inconnu", "question": "registre hors liste"},
    {"registre": "etudiant", "question": "Comment on relâche la CSM chaque année ?"},
]}


def test_questions_mal_formees_ecartees():
    got = parse_questions(QS)
    assert [q["registre"] for q in got] == ["etudiant", "praticien", "recherche"]
    assert parse_questions({"questions": "pas une liste"}) == [] and parse_questions(None) == []


def test_generation_reprend_ou_elle_s_est_arretee(tmp_path):
    calls = []

    def respond(messages, model):
        calls.append(messages)
        return json.dumps(QS, ensure_ascii=False)

    out = tmp_path / "pairs.jsonl"
    cs = chunks()
    first = generate_pairs(cs, client(tmp_path, respond), out, limit=1, log=lambda *_: None)
    assert first["passages_traites"] == 1 and len(calls) == 1
    assert "<passage>" in calls[0][1]["content"]           # passage délimité (garde-fou d'injection)
    second = generate_pairs(cs, client(tmp_path, respond), out, log=lambda *_: None)
    assert second["deja_faits"] == 1 and second["passages_traites"] == len(cs) - 1
    assert len(read_jsonl(out)) == len(cs) and len(calls) == len(cs)


def test_quota_epuise_arrete_proprement(tmp_path):
    def respond(messages, model):
        raise __import__("core.llm", fromlist=["LLMError"]).LLMError("429 quota")

    out = tmp_path / "pairs.jsonl"
    res = generate_pairs(chunks() * 3, client(tmp_path, respond), out, log=lambda *_: None)
    assert res["passages_traites"] == 0 and not out.read_text()


def test_filtre_de_fuite():
    tests = [word_set("À quelle date comptabilise-t-on un groupe de traités de réassurance détenus ?")]
    assert leaks("A quelle date comptabiliser un groupe de traités de réassurance détenus", tests)
    assert not leaks("Quand reconnaître une quote-part chez le cédant ?", tests)


def test_recopie_du_passage_detectee():
    assert copied_span("est ajustée pour tenir compte de l'intérêt capitalisé et des variations", TEXTS["44"])
    assert not copied_span("Comment évolue la CSM d'une année sur l'autre ?", TEXTS["44"])


def test_negatif_difficile_ne_contient_pas_la_reponse():
    cs = chunks()
    pos = next(c for c in cs if "B119" in c.paragraph_ids)
    neg = hard_negative("marge sur services contractuels en résultat", pos, cs, BM25([c.embed_text for c in cs]))
    assert neg is not None and "B119" not in neg.paragraph_ids and "contractuels" in neg.embed_text


def test_export_sans_question_de_test_et_variante_stricte(tmp_path):
    cs = chunks()
    pos = next(c for c in cs if "B119" in c.paragraph_ids)
    records = [{"chunk_id": pos.chunk_id, "model": "fake", "questions": parse_questions(QS)}]
    tests = [{"question": "Comment on relâche la CSM chaque année ?", "gold": ["B119"]}]
    rows, rep = build_training_set(records, cs, tests)
    assert rep["fuite_ecartee"] == 1 and rep["gardees"] == 2 and rep["negatif_aleatoire"] == 1
    assert all(r["positive"] == pos.embed_text and r["negative"] != pos.embed_text for r in rows)
    _, strict = build_training_set(records, cs, tests, holdout_gold=True)
    assert strict["passage_de_test_ecarte"] == 3 and strict["gardees"] == 0

    chunks_path = tmp_path / "chunks_B.jsonl"
    chunks_path.write_text("{}\n", encoding="utf-8")
    t1 = tmp_path / "q.jsonl"
    t1.write_text("{}\n", encoding="utf-8")
    write_bundle(rows, tmp_path / "train.jsonl", tmp_path / "b.zip", chunks_path, [t1])
    names = zipfile.ZipFile(tmp_path / "b.zip").namelist()
    assert names == ["train.jsonl", "chunks_B.jsonl", "q.jsonl"]
    line = json.loads((tmp_path / "train.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert set(line) == {"anchor", "positive", "negative"}
