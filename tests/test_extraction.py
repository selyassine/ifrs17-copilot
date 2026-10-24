"""Extracteur multimodal : documents synthétiques, lecture PDF, ancrage des chiffres, relance."""

import json

import pytest

from agents.schemas import PortfolioData
from core.config import Settings
from core.llm import LLMClient
from eval.eval_extraction import load_cases, same, score
from multimodal.documents import DocumentText, numbers_in_text, parse_number
from multimodal.extract import (
    NumberIndex,
    extract_from_text,
    grounding_issues,
    unit_evidence,
    unit_issues,
)


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
    # D-070 : un taux unique et une courbe plate au même taux donnent la même CSM : même donnée
    assert same("discount_rates", 0.03, [0.03, 0.03])
    assert not same("discount_rates", 0.03, [0.03, 0.035])


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


def test_mode_vision_ancrage_sur_la_transcription(tmp_path):
    """Sans couche texte, les chiffres saisis sont vérifiés contre la transcription du modèle."""
    from multimodal.extract import extract_from_images
    from multimodal.vision import vision_client

    transcription = ["Groupe AB-1 · en milliers d'euros. Taux : 3,00 %. Ajustement pour risque : 5,00 %.",
                     "Période | Primes | Sinistres | Frais | Contrats",
                     "Année 1 | 100,00 | 40,00 | 5,00 | 1 000",
                     "Année 2 | 0,00 | 45,50 | 4,50 | 900"]
    calls = []

    def respond(messages, model):
        calls.append(messages)
        answer = {**GOOD, "transcription": transcription}
        if len(calls) == 1:
            answer["premiums"] = [120.0, 0.0]        # absent de sa propre lecture
        return json.dumps(answer, ensure_ascii=False)

    s = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl")
    res = extract_from_images([(b"\xff\xd8\xff fausse image", "image/jpeg")], vision_client(s, respond))
    assert res.mode == "vision" and res.grounding == "transcription"
    assert res.status == "ok" and res.corrections == 1
    assert any("premiums[0]" in i for i in res.first_attempt_issues)
    content = calls[0][1]["content"]
    assert content[1]["type"] == "image_url" and content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_mode_vision_sans_transcription_a_verifier(tmp_path):
    from multimodal.extract import extract_from_images
    from multimodal.vision import vision_client

    s = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl")
    res = extract_from_images([(b"x", "image/png")], vision_client(s, lambda m, model: json.dumps(GOOD)))
    assert res.status == "a_verifier" and "transcription" in res.issues[0]


def test_mode_hybride_ancre_sur_la_couche_texte(tmp_path):
    from multimodal.extract import extract_from_images
    from multimodal.vision import vision_client

    s = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl")
    res = extract_from_images([(b"x", "image/png")], vision_client(s, lambda m, model: json.dumps(GOOD)),
                              doc=DOC)
    assert res.mode == "hybride" and res.grounding == "document" and res.status == "ok"


def test_detection_du_format():
    from multimodal.vision import detect_mime

    assert detect_mime(b"%PDF-1.7") == "application/pdf"
    assert detect_mime(b"\x89PNG\r\n") == "image/png"
    assert detect_mime(b"\xff\xd8\xff\xe0") == "image/jpeg"
    assert detect_mime(b"bonjour") is None


def test_verdicts_du_jeu_difficile():
    from eval.eval_extraction import verdict

    assert verdict("exact", "ok", True) == "réussi"
    assert verdict("exact", "a_verifier", True) == "fausse alerte"
    assert verdict("exact", "a_verifier", False) == "erreur rattrapée"
    assert verdict("exact", "ok", False) == "DANGEREUX"
    assert verdict("alerte", "a_verifier", False) == "alerte levée"
    assert verdict("alerte", "ok", True) == "DANGEREUX"


def test_jeu_difficile_reproductible_et_ancre(tmp_path):
    """Les 10 documents piégés se régénèrent à l'identique et leur vérité est ancrée dans le PDF."""
    pytest.importorskip("reportlab")
    from eval.eval_extraction import HERE
    from multimodal.documents import pdf_text
    from multimodal.synth_hard import generate

    cases = generate(out_dir=tmp_path / "synth_hard", cases_path=tmp_path / "hard.jsonl", images=False)
    committed = load_cases(HERE / "extraction_hard_cases.jsonl")
    assert [c["truth"] for c in cases] == [c["truth"] for c in committed]
    assert sum(c["attendu"] == "alerte" for c in cases) == 3
    for c in cases:
        if c["truth"]:
            doc = pdf_text(tmp_path / "synth_hard" / f"{c['id']}.pdf")
            assert grounding_issues(PortfolioData(**c["truth"]), NumberIndex(doc)) == [], c["id"]


def test_plusieurs_groupes_validation_humaine(tmp_path):
    c, _ = client(tmp_path, {**GOOD, "groupes_detectes": ["AB-1", "CD-2"]})
    res = extract_from_text(DOC, c)
    assert res.status == "a_verifier" and res.groups == ["AB-1", "CD-2"]
    assert any("plusieurs groupes" in i for i in res.issues)


def _vision_answers(*answers):
    calls = []

    def respond(messages, model):
        calls.append(messages)
        return json.dumps(answers[min(len(calls) - 1, len(answers) - 1)], ensure_ascii=False)

    return respond, calls


TRANSCRIPTION = ["Groupe AB-1 · en milliers d'euros. Taux : 3,00 %. Ajustement pour risque : 5,00 %.",
                 "Période | Primes | Sinistres | Frais | Contrats",
                 "Année 1 | 100,00 | 40,00 | 5,00 | 1 000", "Année 2 | 0,00 | 45,50 | 4,50 | 900"]


def test_double_lecture_concordante_ok(tmp_path):
    pytest.importorskip("PIL")
    import io

    from PIL import Image

    from multimodal.extract import extract_from_images
    from multimodal.vision import vision_client

    buf = io.BytesIO()
    Image.new("RGB", (60, 30), "white").save(buf, format="JPEG")
    same = {**GOOD, "transcription": TRANSCRIPTION}
    respond, calls = _vision_answers(same, same)
    s = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl")
    res = extract_from_images([(buf.getvalue(), "image/jpeg")], vision_client(s, respond))
    assert res.reads == 2 and len(calls) == 2 and res.status == "ok"


def test_double_lecture_divergente_validation_humaine(tmp_path):
    """Chiffre mal lu des deux côtés (transcription et saisie) : seule la seconde lecture le voit."""
    pytest.importorskip("PIL")
    import io

    from PIL import Image

    from multimodal.extract import extract_from_images
    from multimodal.vision import vision_client

    buf = io.BytesIO()
    Image.new("RGB", (60, 30), "white").save(buf, format="JPEG")
    misread = {**GOOD, "outflows": [45.0, 56.0],
               "transcription": [*TRANSCRIPTION[:3], "Année 2 | 0,00 | 51,50 | 4,50 | 900"]}
    good = {**GOOD, "transcription": TRANSCRIPTION}
    respond, _ = _vision_answers(misread, good)
    s = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl")
    res = extract_from_images([(buf.getvalue(), "image/jpeg")], vision_client(s, respond))
    assert res.status == "a_verifier"
    assert any("divergent" in i and "outflows[1]" in i for i in res.issues)


# --------------------------------------------------------------------------- #
# D-081 : l'unité des montants doit être écrite dans le document
# --------------------------------------------------------------------------- #
def _doc(text: str) -> DocumentText:
    return DocumentText(text=text, table_numbers=DOC.table_numbers, text_numbers=DOC.text_numbers)


def _p(**upd) -> PortfolioData:
    base = {k: v for k, v in GOOD.items() if k not in ("manquants", "remarques")}
    return PortfolioData(**{**base, **upd})


@pytest.mark.parametrize("text, found", [
    ("Montants en milliers d'euros", {1000}),
    ("Primes (k€) | Sinistres (k€)", {1000}),
    ("Montants en | milliers", {1000}),
    ("Amounts in thousands of USD", {1000}),
    ("Chiffres en KTND", {1000}),
    ("Montants en millions (euros)", {1_000_000}),
    ("Montants en M€", {1_000_000}),
    ("Montants en unités (dollars américains)", {1}),
    ("Montants en dinars tunisiens", {1}),
    ("Nombre d'unités de couverture", set()),         # « unités de couverture » n'est pas une unité de montant
    ("Des milliers d'assurés nous font confiance", set()),
])
def test_unite_reconnue_dans_le_texte(text, found):
    assert unit_evidence(text) == found


def test_unite_absente_du_document_signalee():
    assert unit_issues(_p(unit_multiplier=1000), _doc("Groupe AB-1. Montants en milliers d'euros.")) == []
    assert unit_issues(_p(unit_multiplier=1), _doc("Groupe AB-1. Aucune unité indiquée.")) == []
    inventee = unit_issues(_p(unit_multiplier=1000), _doc("Groupe AB-1. Aucune unité indiquée."))
    assert inventee and "aucune mention" in inventee[0]
    contraire = unit_issues(_p(unit_multiplier=1), _doc("Groupe AB-1. Montants en milliers d'euros."))
    assert contraire and "milliers" in contraire[0]


def test_unite_lue_dans_la_partie_du_groupe():
    """Deux groupes, deux unités (comme dur10) : chaque groupe est jugé sur sa propre partie."""
    text = ("Groupe de contrats : AB-1 · Montants en milliers (dollars)\nAnnée 1 | 100,00\n"
            "Groupe de contrats : CD-2 · Montants en unités (dollars)\nAnnée 1 | 604 261,58")
    assert unit_issues(_p(unit_multiplier=1000), _doc(text)) == []
    assert unit_issues(_p(unit_multiplier=1), _doc(text))
    assert unit_issues(_p(group_id="CD-2", unit_multiplier=1), _doc(text)) == []
    assert unit_issues(_p(group_id="CD-2", unit_multiplier=1000), _doc(text))


def test_unite_inventee_relance_puis_validation_humaine(tmp_path):
    doc = _doc(DOC.text.replace("en milliers d'euros", "montants en euros"))
    c, calls = client(tmp_path, GOOD, GOOD)                     # le LLM maintient « milliers »
    res = extract_from_text(doc, c)
    assert res.status == "a_verifier" and res.corrections == 1
    assert any("unit_multiplier" in i for i in res.issues)
    c2, _ = client(tmp_path, GOOD, {**GOOD, "unit_multiplier": 1})   # il corrige après la relance
    assert extract_from_text(doc, c2).status == "ok"


def test_volatilite_declaree_ancree_dans_le_document(tmp_path):
    """D-082 : declared_cv et declared_confidence sont facultatifs, convertis en décimal et ancrés."""
    text = DOC.text + "\nVolatilité des sinistres (CV) : 12,00 %. Niveau de confiance : 75,00 %."
    doc = DocumentText(text=text, table_numbers=DOC.table_numbers,
                       text_numbers=DOC.text_numbers + [12.0, 0.12, 75.0, 0.75])
    c, _ = client(tmp_path, {**GOOD, "declared_cv": "12 %", "declared_confidence": 0.75})
    res = extract_from_text(doc, c)
    assert res.status == "ok" and res.portfolio.declared_cv == pytest.approx(0.12)
    assert res.portfolio.declared_confidence == 0.75
    c2, _ = client(tmp_path, {**GOOD, "declared_cv": 0.2}, {**GOOD, "declared_cv": 0.2})   # 20 % n'est pas écrit
    res2 = extract_from_text(doc, c2)
    assert res2.status == "a_verifier" and any("declared_cv" in i for i in res2.issues)
    c3, _ = client(tmp_path, {**GOOD, "declared_cv": None})
    assert extract_from_text(doc, c3).portfolio.declared_cv is None
