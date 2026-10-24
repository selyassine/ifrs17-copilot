"""Périmètre actuariel élargi : PAA (D-073), frais d'acquisition (D-075), première clôture (D-076),
plusieurs groupes par document (D-078), nouveaux champs de l'extracteur et du formulaire n8n."""

import json
import random

import pytest

from agents.schemas import PortfolioData
from engine.analysis import projection, sensitivities, shocked
from engine.cloture import ClosingInput, close_first_period
from engine.csm import compute_csm
from engine.paa import coverage_months, paa_view

GOOD = PortfolioData(group_id="G1", premiums=[100, 0, 0], outflows=[30, 30, 30], coverage_units=[3, 2, 1],
                     discount_rates=[0.02, 0.025, 0.03], risk_adjustment_pct=0.05)
BAD = PortfolioData(group_id="G2", premiums=[100, 0, 0], outflows=[50, 50, 50], coverage_units=[1, 1, 1],
                    discount_rates=0.05, risk_adjustment_pct=0.05)
ACQ = PortfolioData(group_id="G3", premiums=[100, 20, 0], outflows=[30, 30, 30], coverage_units=[3, 2, 1],
                    acquisition_costs=[8, 2, 0], recoveries=[0, 5, 0], discount_rates=[0.02, 0.025, 0.03],
                    risk_adjustment_pct=0.05)
ANNUAL = PortfolioData(group_id="WC", premiums=[1000, 0, 0, 0], outflows=[200, 300, 150, 50],
                       coverage_units=[1000, 0, 0, 0], discount_rates=[0.04, 0.045, 0.05, 0.05],
                       risk_adjustment_pct=0.03, acquisition_costs=[60, 0, 0, 0], coverage_months=12,
                       line_of_business="Accidents du travail")
ALL = [GOOD, BAD, ACQ, ANNUAL]


# --------------------------------------------------------------------------- frais d'acquisition
def test_frais_d_acquisition_reduisent_la_csm():
    flat = GOOD.model_copy(update={"discount_rates": 0.0, "acquisition_costs": [3, 0, 0]})
    r0, r1 = compute_csm(GOOD.model_copy(update={"discount_rates": 0.0})), compute_csm(flat)
    assert r1.pv_acquisition == 3 and r0.initial_csm - r1.initial_csm == pytest.approx(3)
    worse = compute_csm(flat.model_copy(update={"acquisition_costs": [10, 0, 0]}))     # au-delà de la CSM : perte
    assert worse.onerous and worse.initial_loss_component == pytest.approx(10 - r0.initial_csm)
    with pytest.raises(ValueError):
        PortfolioData(**{**GOOD.model_dump(), "acquisition_costs": [1, -1, 0]})
    with pytest.raises(ValueError):
        PortfolioData(**{**GOOD.model_dump(), "acquisition_costs": [1, 0]})


@pytest.mark.parametrize("p", ALL)
def test_projection_rapprochee_avec_frais_d_acquisition(p):
    r = compute_csm(p)
    pr = projection(p, r)
    lrc = pr.opening_lrc
    for x in pr.rows:
        assert x.lrc_closing == pytest.approx(lrc + x.premium - x.acquisition - x.outflow + x.recovery
                                              + x.insurance_finance_expense - x.ra_release - x.csm_release, abs=1e-9)
        lrc = x.lrc_closing
    assert pr.rows[-1].lrc_closing == pytest.approx(0, abs=1e-9)
    # B125 : la part des primes qui couvre les frais d'acquisition est en produits et en charges, sans effet net
    assert pr.totals["acquisition_amortisation"] == pytest.approx(sum(p.acquisition_costs or [0]))


@pytest.mark.parametrize("p", ALL)
def test_seuil_de_bascule_exact_avec_frais(p):
    s = sensitivities(p)
    if s.outflow_breakeven is not None:
        assert compute_csm(shocked(p, outflows=1 + s.outflow_breakeven)).fulfilment_cash_flows == pytest.approx(0, abs=1e-8)


# --------------------------------------------------------------------------- PAA
def test_duree_de_couverture_lue_ou_deduite():
    assert coverage_months(ANNUAL) == (12, "indiquée dans le document")
    assert coverage_months(GOOD)[0] == 36
    assert coverage_months(ANNUAL.model_copy(update={"coverage_months": None}))[0] == 12


@pytest.mark.parametrize("p", [ANNUAL, ANNUAL.model_copy(update={"premiums": [400, 0, 0, 0]})])
def test_paa_meme_resultat_total_que_le_modele_general(p):
    r = compute_csm(p)
    pr = projection(p, r)
    v = paa_view(p, r, [x.insurance_service_result for x in pr.rows])
    assert v.eligible and v.lrc_initial == pytest.approx(sum(p.premiums) - 60)
    paa_total = sum(y.service_result - y.finance_expense for y in v.years)
    bba_total = sum(x.insurance_service_result - x.insurance_finance_expense for x in pr.rows) - r.initial_loss_component * 0
    assert paa_total == pytest.approx(bba_total, abs=1e-9)
    assert paa_total == pytest.approx(sum(p.premiums) - 60 - sum(p.outflows), abs=1e-9)
    assert v.onerous_loss == pytest.approx(r.initial_loss_component)
    # l'écart de l'année de couverture vient de la capitalisation de la CSM (§44(b)), absente en PAA
    if not r.onerous:
        assert -v.first_year_gap == pytest.approx(r.rollforward[0].interest_accretion, abs=1e-9)


def test_paa_non_admissible_au_dela_d_un_an():
    r = compute_csm(GOOD)
    assert not paa_view(GOOD, r, None).eligible


# --------------------------------------------------------------------------- première clôture
@pytest.mark.parametrize("p", ALL)
def test_cloture_sans_ecart_egale_la_projection(p):
    r = compute_csm(p)
    row = projection(p, r).rows[0]
    c = close_first_period(p, ClosingInput(actual_outflow=p.outflows[0]), r)
    assert c.reconciliation_gap == pytest.approx(0, abs=1e-9)
    assert c.closing_liability == pytest.approx(row.lrc_closing, abs=1e-9)
    assert c.insurance_service_result == pytest.approx(row.insurance_service_result, abs=1e-9)
    assert c.insurance_finance_expense == pytest.approx(row.insurance_finance_expense, abs=1e-9)
    assert c.experience_adjustment == 0 and c.csm_close == pytest.approx(r.rollforward[0].closing)


@pytest.mark.parametrize("p", ALL)
def test_cloture_toujours_rapprochee(p):
    rng = random.Random(7)
    for _ in range(25):
        n = p.n_periods
        ci = ClosingInput(actual_outflow=p.outflows[0] * rng.uniform(0.5, 1.6),
                          actual_premium=p.premiums[0] * rng.uniform(0.8, 1.1),
                          revised_outflows=[x * rng.uniform(0.5, 1.8) for x in p.outflows[1:]],
                          closing_rates=[rng.uniform(0.0, 0.08) for _ in range(n - 1)])
        c = close_first_period(p, ci)
        assert c.reconciliation_gap == pytest.approx(0, abs=1e-8)
        assert c.csm_close >= -1e-12 and c.loss_component_close >= -1e-9


def test_cloture_services_passes_ou_futurs():
    # couverture d'un an achevée : la révision va en charges (services passés), la CSM n'est pas touchée
    c = close_first_period(ANNUAL, ClosingInput(actual_outflow=200, revised_outflows=[400, 150, 50]))
    assert c.past_service_change > 0 and c.csm_adjustment == 0 and not c.future_coverage
    # couverture restante : la révision défavorable réduit la CSM (§44(c)), puis devient une perte (§48)
    c = close_first_period(GOOD, ClosingInput(actual_outflow=30, revised_outflows=[33, 33]))
    assert c.future_coverage and c.csm_adjustment < 0 and c.new_loss == 0 and c.past_service_change == 0
    c = close_first_period(GOOD, ClosingInput(actual_outflow=30, revised_outflows=[80, 80]))
    assert c.csm_close == pytest.approx(0, abs=1e-12) and c.new_loss > 0
    # groupe déficitaire, révision favorable : reprise de la composante de perte d'abord (§50(b))
    c = close_first_period(BAD, ClosingInput(actual_outflow=50, revised_outflows=[45, 45]))
    assert c.loss_reversal > 0
    # écart d'expérience : en résultat (B97(c)), jamais dans la CSM
    a = close_first_period(GOOD, ClosingInput(actual_outflow=40))
    b = close_first_period(GOOD, ClosingInput(actual_outflow=30))
    assert a.experience_adjustment == pytest.approx(-10) and a.csm_close == pytest.approx(b.csm_close)
    assert a.insurance_service_result == pytest.approx(b.insurance_service_result - 10)


def test_note_de_cloture():
    from agents.closing_report import render_closing_note
    r = compute_csm(ANNUAL)
    c = close_first_period(ANNUAL, ClosingInput(actual_outflow=230, revised_outflows=[320, 150, 50], as_of="31/12/2025"), r)
    md, page = render_closing_note(ANNUAL, r, c, "t1")
    assert "Première clôture du groupe WC au 31/12/2025" in page and "B97(c)" in page and "services passés" in page
    assert "Écart de rapprochement" in page and "0,000000" in page


# --------------------------------------------------------------------------- note : PAA, frais, RA calibré
def test_note_paa_frais_et_volatilite_calibree():
    from agents.writer import NoteContext, write_note
    from core.config import Settings
    from core.llm import LLMClient
    cl = LLMClient(Settings(llm_provider="fake", llm_max_retries=0), fake_responder=lambda m, mo: "{}")
    ctx = NoteContext(case_id="c", ra_cv=0.35, ra_cv_source="volatilité calibrée sur 53 cohortes", ra_target_level=0.75,
                      registry_version="2")
    note = write_note(ANNUAL, compute_csm(ANNUAL), [], [], ["ok"], cl, "c", context=ctx)
    h = note.html
    assert "Méthode simplifiée (PAA)" in h and "§53(b)" in h and "Frais d&#x27;acquisition (début)" in h
    assert "volatilité calibrée sur 53 cohortes" in h and "Niveau de confiance cible" in h and "à revoir" in h
    assert "registre.json" in h


# --------------------------------------------------------------------------- extracteur
def _doc(text: str):
    from multimodal.documents import DocumentText, numbers_in_text
    nums = numbers_in_text(text)
    return DocumentText(text=text, table_numbers=nums, text_numbers=[])


def _extract(text, answer, target=None):
    from core.config import Settings
    from core.llm import LLMClient
    from multimodal.extract import extract_from_text
    seen = []

    def responder(messages, model):
        seen.append(messages[-1]["content"])
        return json.dumps(answer(messages[-1]["content"]) if callable(answer) else answer)
    res = extract_from_text(_doc(text), LLMClient(Settings(llm_provider="fake", llm_max_retries=0),
                                                 fake_responder=responder), target_group=target)
    return res, seen


BASE = {"currency": "EUR", "unit_multiplier": 1, "premiums": [100.0, 0.0], "outflows": [40.0, 45.0],
        "coverage_units": [10, 9], "discount_rates": 0.03, "risk_adjustment_pct": 0.05, "manquants": []}
TEXT = ("Groupe A et groupe B. Branche : Auto particuliers. Taux 3,00 %. Ajustement 5,00 %. Primes 100,00 0,00. "
        "Sinistres 40,00 45,00. Contrats 10 9. Commissions d'acquisition 7,00. Groupe B : primes 200,00 0,00 "
        "sinistres 90,00 80,00 contrats 20 18.")


def test_extraction_groupe_demande_et_champs_facultatifs():
    ans = {**BASE, "group_id": "B", "premiums": [200.0, 0.0], "outflows": [90.0, 80.0], "coverage_units": [20, 18],
           "groupes_detectes": ["A", "B"], "acquisition_costs": [7.0, 0.0], "line_of_business": "Auto particuliers",
           "coverage_months": "12"}
    res, seen = _extract(TEXT, ans, target="B")
    assert "Groupe à saisir : B" in seen[0]
    assert res.status == "ok", res.issues
    p = res.portfolio
    assert p.acquisition_costs == [7.0, 0.0] and p.coverage_months == 12 and p.line_of_business == "Auto particuliers"
    res, _ = _extract(TEXT, {**ans, "group_id": "A"}, target="B")          # mauvais groupe saisi : signalé
    assert any("au lieu du groupe demandé" in i for i in res.issues)
    res, _ = _extract(TEXT, {**ans, "line_of_business": "Vie entière"}, target="B")   # branche inventée : ignorée
    assert res.portfolio.line_of_business is None and any("introuvable" in w for w in res.warnings)
    res, _ = _extract(TEXT, {**ans, "acquisition_costs": [13.5, 0.0]}, target="B")     # frais inventés : signalés
    assert res.status != "ok"


# --------------------------------------------------------------------------- plusieurs groupes
def _two_group_pdf(tmp_path):
    pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    path = tmp_path / "deux.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    for k, line in enumerate(["Groupe AUTO-A : primes 100,00 et 0,00 ; sinistres 40,00 et 45,00 ; contrats 10 et 9.",
                              "Groupe AUTO-B : primes 200,00 et 0,00 ; sinistres 150,00 et 80,00 ; contrats 20 et 18.",
                              "Taux d'actualisation 3,00 %. Ajustement pour risque 5,00 %. Montants en euros."]):
        c.drawString(40, 800 - 20 * k, line)
    c.save()
    return path.read_bytes()


def _answers(content: str) -> dict:
    a = {**BASE, "group_id": "AUTO-A", "groupes_detectes": ["AUTO-A", "AUTO-B"]}
    if "Groupe à saisir : AUTO-B" in content:
        a |= {"group_id": "AUTO-B", "premiums": [200.0, 0.0], "outflows": [150.0, 80.0], "coverage_units": [20, 18]}
    return a


def test_un_document_deux_groupes_deux_notes(tmp_path):
    from agents.orchestrator import run_case
    from core.config import Settings
    from core.llm import LLMClient
    settings = Settings(llm_provider="fake", llm_max_retries=0)

    def client():
        return LLMClient(settings, fake_responder=lambda m, mo: json.dumps(_answers(m[-1]["content"]))
                         if "<document>" in m[-1]["content"] or "Groupe à saisir" in m[-1]["content"] else "{}")
    out = run_case(_two_group_pdf(tmp_path), "application/pdf", settings, client, client, None, "multi")
    assert [g.portfolio.group_id for g in out.groups] == ["AUTO-A", "AUTO-B"]
    assert out.status == "note_prete", out.controls
    assert out.groups[1].csm.onerous and not out.groups[0].csm.onerous      # testés séparément (§16)
    assert "2 groupes de contrats" in out.note.html and out.note.html.count("Évaluation IFRS 17 du groupe") == 2
    # ancien comportement disponible : un humain choisit le groupe
    old = run_case(_two_group_pdf(tmp_path), "application/pdf", Settings(llm_provider="fake", llm_max_retries=0,
                                                                         multi_group=False),
                   client, client, None, "un")
    assert old.status == "validation_humaine" and any("plusieurs groupes" in c for c in old.controls)


# --------------------------------------------------------------------------- API et n8n
def test_api_cloture(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from api.main import app
    from core.config import Settings, get_settings
    s = Settings(llm_provider="fake", api_token="secret", trace_path=tmp_path / "t.jsonl",
                 registry_path=tmp_path / "reg.sqlite")
    app.dependency_overrides[get_settings] = lambda: s
    try:
        c = TestClient(app)
        body = {"portfolio": ANNUAL.model_dump(), "cloture": {"actual_outflow": 230, "revised_outflows": [320, 150, 50]}}
        r = c.post("/v1/case/cloture", json=body, headers={"X-API-Token": "secret"})
        assert r.status_code == 200, r.text
        assert abs(r.json()["result"]["reconciliation_gap"]) < 1e-6 and "Première clôture" in r.json()["note_html"]
        r = c.post("/v1/case/cloture", json={"case_id": "inconnu", "cloture": {"actual_outflow": 1}},
                   headers={"X-API-Token": "secret"})
        assert r.status_code == 404
        r = c.post("/v1/case/cloture", json={**body, "cloture": {"actual_outflow": 1, "revised_outflows": [1]}},
                   headers={"X-API-Token": "secret"})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_formulaire_n8n_nouveaux_champs():
    from core.config import ROOT
    wf = json.loads((ROOT / "workflows" / "ifrs17_copilot.json").read_text(encoding="utf-8"))
    code = {n["name"]: n["parameters"].get("jsCode", "") for n in wf["nodes"]}
    prep, apply_ = code["Préparer la validation"], code["Appliquer les corrections"]
    for label in ("Frais d'acquisition par période (facultatif)", "Durée de couverture en mois (facultatif)",
                  "Branche (facultatif)", "Recouvrements par période (facultatif)"):
        assert label in prep and label in apply_
    assert "autres_groupes" in prep and "other_groups" in apply_
    http = next(n for n in wf["nodes"] if n["name"] == "Appel API /v1/case/validated")
    assert "other_groups" in http["parameters"]["jsonBody"]
