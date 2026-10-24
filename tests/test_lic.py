"""D-083 : passif pour sinistres survenus (LIC) à partir d'un triangle — moteur, lecture, orchestrateur, API."""

import json

import pytest

from agents.schemas import TriangleData
from core.config import Settings
from core.llm import LLMClient
from engine.lic import TriangleError, compute_lic, development_factors, mack
from engine.risk import ra_at_level
from multimodal.documents import DocumentText
from multimodal.triangle import extract_triangle, looks_like_triangle, parse_triangle

# Taylor et Ashe (1983), exemple de Mack (1993) : paiements de l'année
GENINS = [[357848, 766940, 610542, 482940, 527326, 574398, 146342, 139950, 227229, 67948],
          [352118, 884021, 933894, 1183289, 445745, 320996, 527804, 266172, 425046],
          [290507, 1001799, 926219, 1016654, 750816, 146923, 495992, 280405],
          [310608, 1108250, 776189, 1562400, 272482, 352053, 206286],
          [443160, 693190, 991983, 769488, 504851, 470639],
          [396132, 937085, 847498, 805037, 705960],
          [440832, 847631, 1131398, 1063269],
          [359480, 1061648, 1443370],
          [376686, 986608],
          [344014]]

# Farm Bureau Of MI Grp, accidents du travail, CAS Schedule P (dossier C du camarade), paiements cumulés
FARM = [[1346, 3389, 4666, 5331, 5719, 6097, 6126, 6292, 6368, 6415], [1411, 3641, 4729, 5352, 5935, 6032, 6061, 6222, 6292],
        [1424, 4460, 5791, 6949, 6966, 7324, 7596, 7730], [2355, 6208, 8191, 8368, 8895, 9162, 9564],
        [2544, 7554, 8008, 9684, 10637, 10825], [3512, 6745, 9173, 10286, 10789], [2708, 7360, 10084, 11434],
        [2609, 6240, 8280], [2652, 5332], [2192]]
FARM_PREM = [7122, 7588, 10232, 12731, 16847, 21327, 21686, 24955, 22316, 20975]
FARM_RATES = [0.0559, 0.0574, 0.0576, 0.0578, 0.0580, 0.0583, 0.0587, 0.0586, 0.0585]
YEARS = [str(y) for y in range(1988, 1998)]


def _cum(inc):
    return [[sum(r[:k + 1]) for k in range(len(r))] for r in inc]


def test_mack_reproduit_l_exemple_publie():
    """Mack (1993), tableau de l'article : provision 18 680 856, erreur de prédiction totale 2 447 095."""
    f, _, _, res, se, total = mack(_cum(GENINS))
    assert sum(res) == pytest.approx(18_680_856, abs=1)
    assert total == pytest.approx(2_447_095, abs=1)
    assert [round(x) for x in se[1:]] == [75535, 121699, 133549, 261406, 411010, 558317, 875328, 971258, 1363155]
    assert [round(x, 3) for x in f] == [3.491, 1.747, 1.457, 1.174, 1.104, 1.086, 1.054, 1.077, 1.018]


def test_lic_du_dossier_c():
    r = compute_lic(FARM, FARM_RATES, 0.75, labels=YEARS, premiums=FARM_PREM)
    assert r.reserve == pytest.approx(18322.18, abs=0.01)
    assert r.mack_se == pytest.approx(2805.54, abs=0.01) and r.cv == pytest.approx(r.mack_se / r.reserve)
    assert r.bel == pytest.approx(16099.31, abs=0.01)
    assert r.risk_adjustment == pytest.approx(ra_at_level(r.bel, r.cv, 0.75)) == pytest.approx(1535.42, abs=0.01)
    assert r.lic == pytest.approx(17634.74, abs=0.01)
    assert sum(r.cash_flows) == pytest.approx(r.reserve) and len(r.cash_flows) == 9
    assert [lic for _, _, lic in r.levels] == sorted(lic for _, _, lic in r.levels)
    low, high = r.rate_shocks
    assert low[1] > r.bel > high[1]                    # taux plus bas → BEL plus élevé
    assert r.rows[0].reserve == pytest.approx(0) and r.rows[-1].loss_ratio == pytest.approx(r.rows[-1].ultimate / 20975)


def test_actualisation_nulle_et_facteur_de_queue():
    r0 = compute_lic(FARM, 0.0, 0.75)
    assert r0.bel == pytest.approx(r0.reserve) and r0.discount_effect == pytest.approx(0)
    rq = compute_lic(FARM, 0.0, 0.75, tail=1.02)
    assert rq.reserve == pytest.approx(r0.reserve + 0.02 * sum(x.ultimate / 1.02 for x in rq.rows))
    r_imp = compute_lic(FARM, FARM_RATES, 0.75, cv=0.30, cv_source="imposée")
    assert r_imp.cv == 0.30 and r_imp.risk_adjustment > compute_lic(FARM, FARM_RATES, 0.75).risk_adjustment


def test_triangles_invalides_refuses():
    with pytest.raises(TriangleError):
        development_factors([[1, 2], [1]])                       # moins de 3 survenances
    with pytest.raises(TriangleError):
        compute_lic([[1, 2, 3], [1, 2, 3], [1]])                 # pas en escalier
    with pytest.raises(ValueError):
        TriangleData(portfolio_id="X", origin_years=["1", "2", "3"], triangle=[[1, 2, 3], [1], [1]])
    t = TriangleData(portfolio_id="X", origin_years=["1", "2", "3"], triangle=[[1, 1, 1], [2, 2], [3]], cumulative=False)
    assert t.cumulative_triangle() == [[1, 2, 3], [2, 4], [3]]


def _doc_c(text_extra: str = "", cells: list[list[float]] | None = None) -> DocumentText:
    cells = cells or FARM
    lines = ["Farm Bureau Of MI Grp — Dossier de clôture au 31/12/1997",
             "Portefeuille : accidents du travail (États-Unis) · Devise : USD · Montants en milliers de dollars américains",
             "Objet : évaluation du passif pour sinistres survenus (LIC) au 31/12/1997.",
             "Survenance Prime nette Ret. 1 | Ret. 2 | Ret. 3 | Ret. 4 | Ret. 5 | Ret. 6 | Ret. 7 | Ret. 8 | Ret. 9 | Ret. 10"]
    lines += [f"{YEARS[i]} | {FARM_PREM[i]} | " + " | ".join(str(v) for v in cells[i]) for i in range(10)]
    lines += ["Ajustement au titre du risque non financier : quantile 75 % d'une loi lognormale.",
              "Échéance (ans) | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9",
              "Taux spot | 5,59 % | 5,74 % | 5,76 % | 5,78 % | 5,80 % | 5,83 % | 5,87 % | 5,86 % | 5,85 %", text_extra]
    text = "\n".join(lines)
    from multimodal.documents import numbers_in_text
    nums = numbers_in_text(text)
    return DocumentText(text=text, table_numbers=nums, text_numbers=nums)


GOOD = {"portfolio_id": "Farm Bureau Of MI Grp — accidents du travail", "currency": "USD", "unit_multiplier": 1000,
        "line_of_business": "accidents du travail", "valuation_date": "31/12/1997", "origin_years": YEARS,
        "premiums": FARM_PREM, "triangle": FARM, "cumulative": True, "discount_rates": FARM_RATES,
        "confidence_level": 0.75, "tail_factor": 1, "manquants": [], "remarques": ""}


def _client(tmp_path, *answers):
    calls = []

    def respond(messages, model):
        calls.append(messages)
        return json.dumps(answers[min(len(calls) - 1, len(answers) - 1)], ensure_ascii=False)
    s = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl")
    return LLMClient(s, fake_responder=respond), calls


def test_relecture_et_detection_du_triangle():
    doc = _doc_c()
    p = parse_triangle(doc)
    assert p.years == YEARS and p.premiums == FARM_PREM and p.triangle == FARM
    assert looks_like_triangle(doc)
    # état de portefeuille avec un triangle en annexe (dossier A) : reste un dossier de CSM
    lrc = DocumentText(text="Période | Primes | Sinistres\nAnnée 1 | 100,00 | 40,00\nAnnée 2 | 0,00 | 30,00\n" + doc.text)
    assert not looks_like_triangle(lrc)


def test_lecture_du_triangle_juste(tmp_path):
    c, calls = _client(tmp_path, GOOD)
    res = extract_triangle(_doc_c(), c)
    assert res.status == "ok" and res.double_read == "concordante" and res.corrections == 0
    assert res.data.cumulative_triangle() == FARM and "<document>" in calls[0][1]["content"]


def test_cellule_inventee_relance_puis_validation_humaine(tmp_path):
    bad = json.loads(json.dumps(GOOD))
    bad["triangle"][3][2] = 8911                                 # 8191 mal recopié
    c, calls = _client(tmp_path, bad, bad)
    res = extract_triangle(_doc_c(), c)
    assert res.status == "a_verifier" and res.corrections == 1
    assert any("introuvable" in i for i in res.issues) and any(i.startswith("double lecture") for i in res.issues)
    c2, _ = _client(tmp_path, bad, GOOD)
    assert extract_triangle(_doc_c(), c2).status == "ok"


def test_coquille_du_document_et_unite_signalees(tmp_path):
    cells = [list(r) for r in FARM]
    cells[3][2] = 3100                                           # le document lui-même : un cumul qui recule
    ans = {**GOOD, "triangle": cells}
    c, _ = _client(tmp_path, ans, ans)
    res = extract_triangle(_doc_c(cells=cells), c)
    assert res.status == "a_verifier" and any("recule" in i for i in res.issues)
    c2, _ = _client(tmp_path, {**GOOD, "unit_multiplier": 1}, {**GOOD, "unit_multiplier": 1})
    assert any("unit_multiplier" in i for i in extract_triangle(_doc_c(), c2).issues)


def _pdf_c(tmp_path):
    pytest.importorskip("reportlab")
    from multimodal.lic_cases import _pdf

    path = tmp_path / "dossier_c.pdf"
    header = ["Survenance", "Prime nette"] + [f"Ret. {k + 1}" for k in range(10)]
    rows = [[YEARS[i], f"{FARM_PREM[i]:,}".replace(",", " ")] + [f"{v:,}".replace(",", " ") for v in FARM[i]]
            for i in range(10)]
    _pdf(path, "Farm Bureau Of MI Grp — Dossier de clôture au 31/12/1997", header, rows,
         ["Portefeuille : accidents du travail · Devise : USD · Montants en milliers de dollars américains",
          "Objet : évaluation du passif pour sinistres survenus (LIC) au 31/12/1997."],
         ["Taux spot par échéance (1 à 9 ans) : " + " ; ".join(f"{r * 100:.2f} %".replace(".", ",") for r in FARM_RATES),
          "Ajustement au titre du risque : quantile 75 % d'une loi lognormale."])
    return path.read_bytes()


def test_dossier_lic_de_bout_en_bout(tmp_path):
    from agents.orchestrator import run_case

    c, _ = _client(tmp_path, GOOD)
    s = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl")
    out = run_case(_pdf_c(tmp_path), "application/pdf", s, lambda: c, lambda: c, None, "lic-1", source_name="c.pdf")
    assert out.kind == "lic" and out.status == "note_prete", out.controls
    assert out.lic.lic == pytest.approx(17634.74, abs=0.01) and out.portfolio is None
    assert [st.agent for st in out.steps] == ["extracteur", "calculateur", "redacteur"]
    assert "17 634,74" in out.note.markdown and "Mack" in out.note.html and "§40(b)" in out.note.markdown
    # triangle validé par un humain : pas de lecture, même calcul
    out2 = run_case(b"", "", s, lambda: c, lambda: c, None, "lic-2",
                    triangle=TriangleData(**{k: v for k, v in GOOD.items() if k not in ("manquants", "remarques")}),
                    human_changes=["triangle : 1 cellule corrigée"], validated_by="v@x.fr")
    assert out2.steps[0].status == "saute" and out2.lic.lic == pytest.approx(out.lic.lic)
    assert "Modifications du valideur" in out2.note.markdown


def test_api_dossier_lic_puis_validation(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    import api.main as main
    from core.config import get_settings

    settings = Settings(llm_provider="fake", router_mode="heuristic", api_token="secret",
                        trace_path=tmp_path / "traces.jsonl", rag_strategy="B", rag_mode="bm25", rag_embed_model="",
                        registry_path=tmp_path / "reg.db")
    main.app.dependency_overrides[get_settings] = lambda: settings
    fake = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl")
    monkeypatch.setattr(main, "make_client", lambda s: LLMClient(fake, fake_responder=lambda m, mo: json.dumps(GOOD)))
    monkeypatch.setattr(main, "_retriever_loader", lambda s: None)
    try:
        client = TestClient(main.app)
        auth = {"X-API-Token": "secret"}
        r = client.post("/v1/case", headers=auth, data={"case_id": "c-lic"},
                        files={"file": ("dossier_c.pdf", _pdf_c(tmp_path), "application/pdf")})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["kind"] == "lic" and body["lic"]["lic"] == pytest.approx(17634.74, abs=0.01)
        case = client.get("/v1/cases/c-lic", headers=auth).json()
        assert case["portfolio"]["kind"] == "lic" and case["group_id"].startswith("Farm Bureau")
        tri = {**body["triangle"]}
        tri["triangle"][3][2] = 8200
        r = client.post("/v1/case/validated", headers=auth,
                        json={"case_id": "c-lic", "triangle": tri, "validated_by": "v@x.fr"})
        assert r.status_code == 200 and r.json()["kind"] == "lic"
        assert "1991, retard 3 : 8191 → 8200" in r.json()["note_markdown"]
        assert client.post("/v1/case/validated", headers=auth, json={"case_id": "x"}).status_code == 422
    finally:
        main.app.dependency_overrides.clear()
