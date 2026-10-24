"""Méthodes actuarielles (D-072 à D-077) : Chain Ladder, double calcul avec le script R, calibration du RA,
registre des hypothèses, dossiers prospectifs et back-testing."""

import csv
import json
import math
from pathlib import Path

import pytest

from actuariat import donnees
from actuariat.calibration import calibrate_branch
from actuariat.chain_ladder import project, reproject_after_year1, select, triangles
from actuariat.registre import DEFAULT, load_registry, save_registry
from core.config import ROOT
from engine.risk import ra_at_level

CAS = ROOT / "data" / "cas"
REF = ROOT / "eval" / "reference_script_R_50.csv"


def _rows(code="1", name="A", base=100.0, growth=(1.0, 0.5, 0.25), premium=200.0, years=None):
    """Triangle complet : paiements incrémentaux base × (1, 0,5, 0,25) pour chaque survenance."""
    years = range(2000, 2004) if years is None else years
    rows = []
    for a in years:
        cum = 0.0
        for k, g in enumerate(growth, start=1):
            cum += base * g
            rows.append({"GRCODE": code, "GRNAME": name, "AccidentYear": str(a), "DevelopmentLag": str(k),
                         "CumPaidLoss": str(cum), "EarnedPremNet": str(premium), "Single": "1"})
    return rows


def test_chain_ladder_a_la_main(monkeypatch):
    import actuariat.chain_ladder as cl
    monkeypatch.setattr(cl, "LAGS", 3)
    t = triangles(_rows())["1"]
    pr = project(t, 2003)
    # facteurs : 150/100 = 1,5 ; queue = facteur précédent ; cadence et S/P attendu recalculés à la main
    assert pr.factors[0] == pytest.approx(1.5)
    assert pr.factors[1] == pytest.approx(1.5)          # queue : facteur 2→3 pris égal au facteur 1→2
    ult_share = [1 / (1.5 * 1.5), 1 / 1.5, 1.0]
    assert pr.pattern == pytest.approx([ult_share[0], ult_share[1] - ult_share[0], 1 - ult_share[1]])
    # S/P : années 2000-2002 connues au 31/12/2002 aux retards 3, 2, 1 → ultimes projetés
    ult = 175 * 1 + 150 * 1.5 + 100 * 2.25
    assert pr.elr == pytest.approx(ult / 600)
    assert sum(pr.expected) == pytest.approx(200 * ult / 600)
    assert pr.actual == pytest.approx([100, 50, 25])


def test_rien_du_futur_dans_la_projection(monkeypatch):
    """Changer les paiements postérieurs à la date d'évaluation ne change pas les flux attendus."""
    import actuariat.chain_ladder as cl
    monkeypatch.setattr(cl, "LAGS", 3)
    rows = _rows()
    a = project(triangles(rows)["1"], 2003)
    for r in rows:
        if int(r["AccidentYear"]) + int(r["DevelopmentLag"]) - 1 > 2002:
            r["CumPaidLoss"] = str(float(r["CumPaidLoss"]) * 3)
    b = project(triangles(rows)["1"], 2003)
    assert a.expected == pytest.approx(b.expected) and a.actual != b.actual


def test_branches_lues_librement():
    assert donnees.lob_code("Accidents du travail") == "WC"
    assert donnees.lob_code("Workers' compensation") == "WC"
    assert donnees.lob_code("Auto particuliers (RC)") == "PA" and donnees.lob_code("PPA") == "PA"
    assert donnees.lob_code("Responsabilité médicale") == "MM"
    assert donnees.lob_code("Responsabilité civile générale") == "OL"
    assert donnees.lob_code("Auto commerciale (RC)") == "CA"
    assert donnees.lob_code("Vie entière") is None and donnees.lob_code(None) is None


def test_calibration_retrouve_une_volatilite_connue():
    """Réalisés tirés autour de l'attendu avec un σ connu : la calibration retrouve le CV attendu."""
    import random

    import actuariat.calibration as cal
    rng = random.Random(1)
    sigma = 0.3
    obs = [math.exp(rng.gauss(-sigma * sigma / 2, sigma)) for _ in range(400)]

    class P:
        def __init__(self, x):
            self.expected, self.actual, self.premium = [1000.0] + [0.0] * 9, [1000.0 * x] + [0.0] * 9, 5000.0
    old = cal.all_projections
    try:
        cal.all_projections = lambda tris: [(None, P(x)) for x in obs]
        res = calibrate_branch("WC", [[]])
    finally:
        cal.all_projections = old
    assert res.cv == pytest.approx(math.sqrt(math.exp(sigma ** 2) - 1), rel=0.12)
    assert res.ra_pct["0.75"] == pytest.approx(ra_at_level(1.0, res.cv, 0.75), abs=1e-5)


def test_registre_versionne(tmp_path, monkeypatch):
    import copy

    import actuariat.registre as reg_mod
    path = tmp_path / "registre.json"
    reg = save_registry(copy.deepcopy(DEFAULT), path, change="création")
    assert reg["version"] == "1"
    reg["ajustement_risque"]["branches"]["WC"] = {"cv": 0.3, "kept": 40, "label": "Accidents du travail"}
    reg = save_registry(reg, path, change="calibration")
    assert load_registry(path)["version"] == "2" and len(load_registry(path)["historique"]) == 2
    monkeypatch.setattr(reg_mod, "REGISTRE", path)
    reg_mod.current.cache_clear()
    try:
        cv, why, code = reg_mod.ra_volatility("Accidents du travail")
        assert (cv, code) == (0.3, "WC") and "calibrée sur 40 cohortes" in why
        cv, why, code = reg_mod.ra_volatility("Responsabilité médicale")      # connue, non calibrée : prudence
        assert cv == 0.3 and code == "MM" and why.startswith("volatilité prudente")
        cv, why, code = reg_mod.ra_volatility(None, default_cv=0.15)
        assert cv == 0.15 and code is None and "non indiquée" in why
    finally:
        reg_mod.current.cache_clear()


def test_registre_du_depot_coherent():
    reg = load_registry()
    assert int(reg["version"]) >= 1 and reg["historique"]
    for code, c in reg["ajustement_risque"]["branches"].items():
        assert code in donnees.LOB_LABELS and 0 < c["cv"] < 2 and c["kept"] >= 30
        assert c["ra_pct"]["0.75"] == pytest.approx(ra_at_level(1.0, c["cv"], 0.75), abs=1e-5)


def test_reprojection_bornhuetter_ferguson(monkeypatch):
    import actuariat.chain_ladder as cl
    monkeypatch.setattr(cl, "LAGS", 3)
    t = triangles(_rows())["1"]
    pr = project(t, 2003)
    rp = reproject_after_year1(t, pr)
    assert rp.paid_year1 == 100
    # BF : payé + prime × S/P × (1 − part payée au retard 1)
    share1 = 1 / (1.5 * 1.5)
    assert rp.ultimate == pytest.approx(100 + 200 * pr.elr * (1 - share1))
    assert sum(rp.revised_future) == pytest.approx(rp.ultimate - 100)


@pytest.mark.skipif(not (CAS / "clrd.csv").exists() or not (CAS / "clrd2025.csv").exists(),
                    reason="données CAS absentes (data/cas/clrd.csv et clrd2025.csv)")
def test_double_calcul_script_R():
    """Les 50 dossiers du script R de l'équipe sont retrouvés à l'identique (sélection, S/P, sinistres attendus)."""
    from actuariat.prospectif import EIOPA_2026_09, build
    ds = build([CAS / "clrd.csv", CAS / "clrd2025.csv"], lambda c: ([x / 100 for x in EIOPA_2026_09], ""))
    ref = list(csv.DictReader(REF.open(encoding="utf-8")))
    assert [d.group for d in ds] == [r["groupe"] for r in ref]
    for d, r in zip(ds, ref, strict=True):
        assert round(d.proj.elr, 4) == pytest.approx(float(r["sp_attendu"]))
        assert round(sum(d.proj.expected), 2) == pytest.approx(float(r["sinistres_attendus_total"]), abs=0.006)


def test_dossier_prospectif_lu_et_calcule(tmp_path, monkeypatch):
    """PDF prospectif → couche texte → extraction (LLM factice qui recopie la vérité) : statut ok, CSM juste,
    branche et durée de couverture retrouvées."""
    pytest.importorskip("reportlab")
    import actuariat.chain_ladder as cl
    from actuariat.prospectif import Dossier, case_row, displayed, render
    from core.config import Settings
    from core.llm import LLMClient
    from multimodal.documents import pdf_text
    from multimodal.extract import extract_from_text

    rows = []
    for a in range(1988, 1998):
        cum = 0.0
        for k in range(1, 11):
            if a + k - 1 > 1997:
                break
            cum += 1000.0 / k
            rows.append({"GRCODE": "77", "GRNAME": "Test Mut Ins Co", "AccidentYear": str(a), "DevelopmentLag": str(k),
                         "CumPaidLoss": str(cum), "EarnedPremNet": "5000", "Single": "1"})
    t = triangles(rows)["77"]
    (tri, pr), = select({"77": t}, require_actual=False)
    p = displayed(pr, [0.045] * 10, 0.03, "WC", "WC-1997-77")
    d = Dossier(lob="WC", triangle=tri, proj=pr, portfolio=p, rates_source="test")
    render(d, tmp_path / "p001.pdf")
    doc = pdf_text(tmp_path / "p001.pdf")
    truth = case_row(d, "p001", "x")["truth"]
    assert truth["coverage_months"] == 12 and truth["line_of_business"] == "Accidents du travail"
    resp = json.dumps(truth | {"manquants": [], "remarques": "", "groupes_detectes": ["WC-1997-77"]})
    res = extract_from_text(doc, LLMClient(Settings(llm_provider="fake", llm_max_retries=0),
                                           fake_responder=lambda m, mo: resp))
    assert res.status == "ok", res.issues
    assert res.portfolio.line_of_business == "Accidents du travail"
    del cl


def test_reference_du_script_R_versionnee():
    rows = list(csv.DictReader(REF.open(encoding="utf-8")))
    assert len(rows) == 50 and {r["duree_couverture"] for r in rows} == {"1"}
    assert Path(REF).name == "reference_script_R_50.csv"
