"""Recouvrements (IFRS 17 B65 k, D-071) : lecture, ancrage, comparaison et documents réels CAS."""

import json

import pytest

from agents.schemas import PortfolioData
from core.config import Settings
from core.llm import LLMClient
from eval.eval_extraction import same
from multimodal.documents import pdf_text
from multimodal.extract import clean, compare_portfolios, extract_from_text
from multimodal.real_cas import cohorts, portfolio, render_libre
from multimodal.synth import SynthDoc, render_pdf

ROWS = [{"GRCODE": "1", "GRNAME": "A", "AccidentYear": "1990", "DevelopmentLag": str(k + 1), "Single": "1",
         "EarnedPremNet": "1000", "CumPaidLoss": str(c)} for k, c in enumerate([300, 500, 450, 600])]


def test_cohortes_avec_recouvrements():
    assert cohorts(ROWS, "wkcomp", lags=4) == ([], 1)                 # D-070 : écartée
    kept, dropped = cohorts(ROWS, "wkcomp", lags=4, recouvrements=True)
    assert dropped == 0 and kept[0]["sinistres"] == [300, 200, -50, 150]
    p = portfolio(kept[0], [0.04] * 4, 0.05)
    assert p.outflows == [300, 200, 0, 150] and p.recoveries == [0, 0, 50, 0]
    assert p.coverage_units == [650, 350, 150, 150]


def _doc(layout: str, column: bool) -> SynthDoc:
    c = cohorts(ROWS, "wkcomp", lags=4, recouvrements=True)[0][0]
    p = portfolio(c, [0.04] * 4, 0.05)
    claims = list(p.outflows) if column else [o - r for o, r in zip(p.outflows, p.recoveries, strict=True)]
    return SynthDoc(doc_id="x", layout=layout, scan=False, truth=p, claims=claims, expenses=[0.0] * 4,
                    investment_income=[0.0] * 4, insurer="A", recovery_column=column)


@pytest.mark.parametrize("layout", ["lignes", "recit", "libre"])
@pytest.mark.parametrize("column", [True, False])
@pytest.mark.parametrize("sign", [1, -1])
def test_ancrage_colonne_ou_sinistre_negatif(tmp_path, layout, column, sign):
    d = _doc(layout, column)
    pdf = tmp_path / "x.pdf"
    render_libre(d, pdf, "note") if layout == "libre" else render_pdf(d, pdf)
    doc = pdf_text(pdf)
    assert ("Recouvrements" in doc.text) == column and ("-50,00" in doc.text) == (not column)
    t = d.truth.model_dump(exclude={"field_confidence", "future_service_adjustments"})
    t["recoveries"] = [sign * x for x in t["recoveries"]]           # le LLM recopie parfois le signe
    resp = json.dumps(t | {"manquants": [], "remarques": "", "groupes_detectes": [t["group_id"]]})
    res = extract_from_text(doc, LLMClient(Settings(llm_provider="fake", llm_max_retries=0),
                                           fake_responder=lambda m, mo: resp))
    assert res.status == "ok" and res.portfolio.recoveries == d.truth.recoveries
    assert "Recouvrements" in res.provenance


def test_recouvrement_invente_signale(tmp_path):
    d = _doc("lignes", True)
    render_pdf(d, tmp_path / "x.pdf")
    t = d.truth.model_dump(exclude={"field_confidence", "future_service_adjustments"}) | {"recoveries": [0, 0, 77, 0]}
    resp = json.dumps(t | {"manquants": [], "remarques": "", "groupes_detectes": [t["group_id"]]})
    res = extract_from_text(pdf_text(tmp_path / "x.pdf"),
                            LLMClient(Settings(llm_provider="fake", llm_max_retries=0), fake_responder=lambda m, mo: resp))
    assert res.status != "ok"


def test_nettoyage_et_comparaison():
    f, *_ = clean({"recoveries": [0, 0, 0]})
    assert "recoveries" not in f
    f, _, _, notes = clean({"recoveries": [0, -12.5]})
    assert f["recoveries"] == [0, 12.5] and notes
    a = PortfolioData(group_id="G", premiums=[100, 0], outflows=[30, 30], coverage_units=[1, 1])
    assert compare_portfolios(a, a.model_copy(update={"recoveries": [0.0, 0.0]})) == []
    assert compare_portfolios(a, a.model_copy(update={"recoveries": [0.0, 5.0]}))
    assert same("recoveries", None, [0, 0]) and same("recoveries", None, None)
    assert not same("recoveries", None, [0, 5])
