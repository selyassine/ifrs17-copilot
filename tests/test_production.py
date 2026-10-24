"""Campagne « prêt pour la production ? » (D-070) : générateurs de lots, données réelles CAS, mesure et bornes."""

import csv
import io
import json

import pytest

from eval.eval_production import aggregate, cases_independants, clopper_pearson_upper
from multimodal.real_cas import cohorts, portfolio, read_cas


def test_borne_de_confiance_regle_de_trois():
    assert clopper_pearson_upper(0, 25) == pytest.approx(0.113, abs=0.002)     # 25 documents sans erreur : < 11,3 %
    assert clopper_pearson_upper(0, 150) == pytest.approx(0.0198, abs=0.001)   # 150 documents : < 2 %
    assert clopper_pearson_upper(2, 100) > 0.02 and clopper_pearson_upper(5, 5) == 1.0


def test_agregats_et_criteres():
    rows = [{"attendu": "exact", "status": "ok", "verdict": "réussi", "all_ok": True, "csm_ok": True, "latency_ms": 1200}] * 8
    rows += [{"attendu": "exact", "status": "a_verifier", "verdict": "fausse alerte", "all_ok": True, "csm_ok": True, "latency_ms": 3000},
             {"attendu": "alerte", "status": "a_verifier", "verdict": "alerte levée", "all_ok": True, "csm_ok": None, "latency_ms": 900}]
    a = aggregate(rows)
    assert a["cas_dangereux"] == 0 and a["feu_vert_fiable"] == "8/8" and a["fausses_alertes"] == "1/9"
    assert a["alertes_levees"] == "1/1" and a["latence_p95_s"] == 3.0


def _csv(rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["GRCODE", "GRNAME", "AccidentYear", "DevelopmentLag", "CumPaidLoss_D", "EarnedPremNet_D", "Single"])
    w.writerows(rows)
    return buf.getvalue()


def test_cohortes_cas_et_verite_sur_valeurs_affichees():
    ok = [[1, "A INS", 1990, k, 100 * k, 5000, 1] for k in range(1, 11)]
    neg = [[2, "B INS", 1990, k, 100 * k if k != 4 else 250, 5000, 1] for k in range(1, 11)]      # paiement négatif
    court = [[3, "C INS", 1990, k, 100 * k, 5000, 1] for k in range(1, 6)]                          # 5 années seulement
    keep, dropped = cohorts(read_cas(_csv(ok + neg + court)), "wkcomp")
    assert len(keep) == 1 and dropped == 1 and keep[0]["sinistres"] == [100.0] * 10
    p = portfolio(keep[0], [0.041234 + 0.001 * k for k in range(10)], 0.03)
    assert p.discount_rates[0] == 0.0412 and p.premiums[0] == 5000 and p.coverage_units[0] == 1000.0
    assert p.group_id == "WC-1990-1"


def test_documents_independants(tmp_path, monkeypatch):
    import eval.eval_production as prod
    monkeypatch.setattr(prod, "ROOT", tmp_path)
    folder = tmp_path / "independants"
    folder.mkdir()
    (folder / "attendus.csv").write_text(
        "fichier;groupe;devise;unite;primes;sorties;unites_couverture;taux;ajustement_risque;attendu;commentaire\n"
        "doc_a.pdf;G1;EUR;1000;100 | 0 | 0;30 | 30 | 30;1 | 1 | 1;3,10 % | 3,30 % | 3,50 %;5 %;exact;\n"
        "doc_b.pdf;;;;;;;;;alerte;deux groupes\n", encoding="utf-8")
    cases = cases_independants(folder)
    assert cases[0]["truth"]["premiums"] == [100.0, 0.0, 0.0] and cases[0]["csm_attendu"] > 0
    assert cases[0]["truth"]["discount_rates"] == [0.031, 0.033, 0.035] and cases[0]["truth"]["risk_adjustment_pct"] == 0.05
    assert cases[1]["attendu"] == "alerte" and cases[1]["truth"] is None


def test_lot_de_volume(tmp_path):
    from multimodal.volume import generate
    path = generate(4, 1, out_dir=tmp_path / "volume", images=False)
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(cases) == 14 and cases[0]["id"] == "v001" and cases[-1]["id"] == "s1_dur10"
    from pathlib import Path
    ref = {json.loads(line)["id"] for line in Path("eval/extraction_cases.jsonl").read_text(encoding="utf-8").splitlines()}
    assert not ref & {c["id"] for c in cases}            # aucun identifiant des jeux de référence


def test_taux_unique_egal_a_une_courbe_plate():
    from eval.eval_extraction import same
    assert same("discount_rates", 0.04, [0.04] * 10) and same("discount_rates", [0.04] * 3, 0.04)
    assert not same("discount_rates", 0.04, [0.04, 0.05])


def test_tableau_sans_grille_colonnes_separees(tmp_path):
    from multimodal.documents import pdf_text
    from multimodal.extract import NumberIndex, grounding_issues
    from multimodal.real_cas import portfolio, render_libre
    from multimodal.synth import SynthDoc
    c = {"ligne": "wkcomp", "grcode": "1", "nom": "X", "annee": 1990, "prime": 110.0,
         "sinistres": [20.0, 15, 12, 9, 7, 5, 4, 3, 2, 1]}
    p = portfolio(c, [0.04] * 10, 0.03)
    render_libre(SynthDoc("r1", "libre", False, p, list(p.outflows), [0.0] * 10, [0.0] * 10, "X"), tmp_path / "r.pdf", "n")
    doc = pdf_text(tmp_path / "r.pdf")
    assert "Année 1 | 110,00" in doc.text            # et non « Année 1 110,00 », lu 1 110
    assert grounding_issues(p, NumberIndex(doc)) == []


def test_recalcul_sans_llm(tmp_path, monkeypatch):
    import eval.eval_production as prod
    truth = {"group_id": "G", "currency": "USD", "unit_multiplier": 1000, "premiums": [100.0, 0.0],
             "outflows": [40.0, 40.0], "coverage_units": [2.0, 1.0], "discount_rates": [0.04, 0.04], "risk_adjustment_pct": 0.03}
    monkeypatch.setattr(prod, "load", lambda jeu: [{"id": "r1", "truth": truth}])
    monkeypatch.setattr(prod, "HERE", tmp_path)
    row = {"id": "r1", "layout": "lignes", "attendu": "exact", "status": "ok", "verdict": "DANGEREUX", "all_ok": False,
           "csm_ok": True, "latency_ms": 1000, "extracted": {**truth, "discount_rates": 0.04}}
    res = tmp_path / "production_reel_x.json"
    res.write_text(json.dumps({"date": "x", "jeu": "reel", "mode": "texte", "agregats": {}, "criteres": {},
                               "documents": [row]}), encoding="utf-8")
    prod.rescore(res)
    data = json.loads(res.read_text(encoding="utf-8"))
    assert data["documents"][0]["verdict"] == "réussi" and data["agregats"]["cas_dangereux"] == 0
    assert (tmp_path / "production_report_reel.md").exists()
