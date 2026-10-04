"""Extracteur multimodal : documents synthétiques, lecture PDF, ancrage des chiffres, relance."""

import json

import pytest

from agents.schemas import PortfolioData
from core.config import Settings
from core.llm import LLMClient
from eval.eval_extraction import load_cases, same, score
from multimodal.documents import DocumentText, numbers_in_text, parse_number
from multimodal.extract import NumberIndex, extract_from_text, grounding_issues


def test_parse_number_formats_francais():
    assert parse_number("1 234,50") == 1234.5
    assert parse_number("865 606,58") == 865606.58
    assert parse_number("2,50 %") == 2.5
    assert parse_number("0.035") == 0.035
    assert parse_number("—") is None
    assert 0.0428 in [round(v, 4) for v in numbers_in_text("taux de 4,28 % retenu")]


DOC = DocumentText(
    text="Groupe AB-1 · en milliers d'euros. Taux : 3,00 %. Ajustement pour risque : 5,00 %.\n"
         "Période | Primes | Sinistres | Frais | Produits financiers | Contrats\n"
         "Année 1 | 100,00 | 40,00 | 5,00 | 2,00 | 1 000\n"
         "Année 2 | 0,00 | 45,50 | 4,50 | 1,00 | 900",
    table_numbers=[100.0, 40.0, 5.0, 2.0, 1000.0, 0.0, 45.5, 4.5, 1.0, 900.0],
    text_numbers=[3.0, 0.03, 5.0, 0.05],
)
GOOD = {"group_id": "AB-1", "currency": "EUR", "unit_multiplier": 1000,
        "premiums": [100.0, 0.0], "outflows": [45.0, 50.0], "coverage_units": [1000, 900],
        "discount_rates": 0.03, "risk_adjustment_pct": 0.05, "manquants": [], "remarques": ""}


def test_ancrage_accepte_les_sommes_et_rejette_l_invente():
    idx = NumberIndex(DOC)
    ok = PortfolioData(**{k: v for k, v in GOOD.items() if k not in ("manquants", "remarques")})
    assert grounding_issues(ok, idx) == []
    invented = ok.model_copy(update={"premiums": [110.0, 0.0]})
    assert any("premiums" in i for i in grounding_issues(invented, idx))
    with_income = ok.model_copy(update={"outflows": [47.0, 51.0]})   # + produits financiers : 3 termes
    assert any("outflows" in i for i in grounding_issues(with_income, idx))


def client(tmp_path, *answers):
    calls = []

    def respond(messages, model):
        calls.append(messages)
        return json.dumps(answers[min(len(calls) - 1, len(answers) - 1)], ensure_ascii=False)

    s = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl")
    return LLMClient(s, fake_responder=respond), calls


def test_extraction_juste_feu_vert(tmp_path):
    c, calls = client(tmp_path, GOOD)
    res = extract_from_text(DOC, c)
    assert res.status == "ok" and res.corrections == 0 and res.issues == []
    assert res.portfolio.outflows == [45.0, 50.0]
    assert "<document>" in calls[0][1]["content"]


def test_chiffre_invente_relance_puis_corrige(tmp_path):
    wrong = {**GOOD, "premiums": [110.0, 0.0]}
    c, calls = client(tmp_path, wrong, GOOD)
    res = extract_from_text(DOC, c)
    assert res.status == "ok" and res.corrections == 1
    assert any("premiums[0]" in i for i in res.first_attempt_issues)
    assert "contrôle automatique" in calls[1][-1]["content"]


def test_erreur_persistante_a_verifier(tmp_path):
    wrong = {**GOOD, "premiums": [110.0, 0.0]}
    c, _ = client(tmp_path, wrong, wrong)
    res = extract_from_text(DOC, c)
    assert res.status == "a_verifier" and res.portfolio is not None and res.issues


def test_listes_incoherentes_echec(tmp_path):
    bad = {**GOOD, "outflows": [45.0]}
    c, _ = client(tmp_path, bad, bad)
    res = extract_from_text(DOC, c)
    assert res.status == "echec" and res.portfolio is None
    assert any("periodes" in i or "périodes" in i for i in res.issues)


def test_champ_manquant_a_verifier(tmp_path):
    c, _ = client(tmp_path, {**GOOD, "discount_rates": 0.0, "manquants": ["discount_rates"]})
    res = extract_from_text(DOC, c)
    assert res.status == "a_verifier" and res.missing == ["discount_rates"]


def test_comparaison_des_champs():
    assert same("group_id", " ab-1", "AB-1")
    assert same("outflows", [45.0, 50.004], [45.0, 50.0])
    assert not same("outflows", [45.0], [45.0, 50.0])
    assert not same("discount_rates", 0.03, [0.03, 0.03])


def test_documents_synthetiques_reproductibles(tmp_path):
    """Le générateur redonne exactement la vérité versionnée (même graine)."""
    pytest.importorskip("reportlab")
    from multimodal.synth import generate

    generate(n_docs=3, out_dir=tmp_path, cases_path=tmp_path / "cases.jsonl", images=False)
    regenerated = [json.loads(line) for line in (tmp_path / "cases.jsonl").read_text(encoding="utf-8").splitlines()]
    committed = load_cases()[:3]
    for a, b in zip(regenerated, committed, strict=True):
        assert a["truth"] == b["truth"] and a["csm_attendu"] == b["csm_attendu"]


def test_lecture_pdf_et_score_bout_en_bout(tmp_path):
    """PDF généré → texte et tableaux → extraction (LLM factice qui recopie la vérité) → score."""
    pytest.importorskip("reportlab")
    from multimodal.documents import pdf_text
    from multimodal.synth import generate

    generate(n_docs=1, out_dir=tmp_path, cases_path=tmp_path / "cases.jsonl", images=False)
    case = json.loads((tmp_path / "cases.jsonl").read_text(encoding="utf-8"))
    doc = pdf_text(tmp_path / f"{case['id']}.pdf")
    assert "| Sinistres |" in doc.text or "Sinistres |" in doc.text
    c, _ = client(tmp_path, {**case["truth"], "manquants": []})
    res = extract_from_text(doc, c)
    row = score(case, res)
    assert res.status == "ok" and row["all_ok"] and row["csm_ok"]
