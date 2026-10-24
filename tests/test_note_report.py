"""Note actuarielle (D-055) : projection, sensibilités, rendu complet et contrôle des textes du LLM."""

import json

import pytest

from agents.note_report import num, render_note
from agents.schemas import PortfolioData
from agents.writer import NoteContext, facts, synthesis_issues, write_note
from core.config import Settings
from core.llm import LLMClient
from engine.analysis import csm_movements, projection, sensitivities, shocked
from engine.csm import compute_csm

GOOD = PortfolioData(group_id="G1", premiums=[100, 0, 0], outflows=[30, 30, 30],
                     coverage_units=[3, 2, 1], discount_rates=[0.02, 0.025, 0.03], risk_adjustment_pct=0.05)
BAD = PortfolioData(group_id="G2", premiums=[100, 0, 0], outflows=[50, 50, 50],
                    coverage_units=[1, 1, 1], discount_rates=0.05, risk_adjustment_pct=0.05)
# recouvrements (B65 k, D-071) : bénéficiaire grâce à eux, et déficitaire malgré eux
REC = PortfolioData(group_id="G3", premiums=[100, 0, 0], outflows=[40, 40, 40], recoveries=[0, 15, 10],
                    coverage_units=[3, 2, 1], discount_rates=[0.02, 0.025, 0.03], risk_adjustment_pct=0.05)
REC_BAD = PortfolioData(group_id="G4", premiums=[100, 0, 0], outflows=[50, 50, 50], recoveries=[0, 5, 5],
                        coverage_units=[1, 1, 1], discount_rates=0.05, risk_adjustment_pct=0.05)


@pytest.mark.parametrize("p", [GOOD, BAD, REC, REC_BAD])
def test_projection_rapprochee_et_eteinte(p):
    r = compute_csm(p)
    pr = projection(p, r)
    lrc = pr.opening_lrc
    for x in pr.rows:          # clôture = ouverture + primes − sorties + charges financières − libérations
        assert x.lrc_closing == pytest.approx(lrc + x.premium - x.outflow + x.recovery + x.insurance_finance_expense
                                              - x.ra_release - x.csm_release, abs=1e-9)
        lrc = x.lrc_closing
    last = pr.rows[-1]
    for v in (last.bel_closing, last.ra_closing, last.csm_closing, last.loss_component_closing):
        assert v == pytest.approx(0, abs=1e-9)


@pytest.mark.parametrize("outflows", [[30, 30, 30], [50, 50, 50]])
def test_sans_actualisation_les_produits_egalent_les_primes(outflows):
    p = PortfolioData(group_id="Z", premiums=[100, 0, 0], outflows=outflows, coverage_units=[1, 1, 1],
                      discount_rates=0.0, risk_adjustment_pct=0.05)
    pr = projection(p, compute_csm(p))
    assert pr.totals["insurance_revenue"] == pytest.approx(100)
    assert pr.totals["insurance_service_result"] == pytest.approx(100 - sum(outflows))


def test_projection_absente_si_ajustements_de_service_futur():
    p = GOOD.model_copy(update={"future_service_adjustments": [0, 5, 0]})
    assert projection(p, compute_csm(p)) is None


def test_mouvements_de_la_csm():
    r = compute_csm(GOOD)
    mv = csm_movements(r)
    assert mv.initial + mv.interest + mv.future_service - mv.release == pytest.approx(mv.closing, abs=1e-9)


def test_sensibilites_et_seuil_de_bascule():
    r = compute_csm(GOOD)
    rep = sensitivities(GOOD, r)
    keys = {s.key: s for s in rep.items}
    assert keys["sorties_plus_10"].delta_result_at_inception < 0 < keys["sorties_moins_10"].delta_result_at_inception
    # au seuil, les flux d'exécution s'annulent
    k = 1 + rep.outflow_breakeven
    from engine.analysis import shocked
    assert compute_csm(shocked(GOOD, outflows=k)).fulfilment_cash_flows == pytest.approx(0, abs=1e-9)


def test_rendu_complet_de_la_note():
    r = compute_csm(BAD)
    ctx = NoteContext(case_id="c9", app_version="0.7.0", source_name="ext.pdf", source_sha256="ab" * 32,
                      prompt_versions={"write_note": 2})
    md, page = render_note(BAD, r, "Synthèse.", "Commentaire.", "llm", [], ["extraction : un champ"], ["ok"],
                           sensitivities(BAD, r), projection(BAD, r), ctx)
    for title in ("1. Résumé exécutif", "4. Hypothèses", "7. Projection", "8. Sensibilités", "10. Contrôles",
                  "Annexe A. Traçabilité", "Annexe B. Glossaire"):
        assert title in md
    assert "À VALIDER" in page and "@page" in page and "composante de perte" in page
    assert "<svg" in page and "http://" not in page.replace("http://www.w3.org/2000/svg", "")   # autonome


def test_format_des_montants():
    assert num(-1234.5) == "−1 234,50" and num(0.001) == "0,00" and num(12) == "12,00"


def test_controle_du_commentaire():
    r = compute_csm(GOOD)
    f = facts(GOOD, r, [], sensitivities(GOOD, r), projection(GOOD, r))
    s = f["sensibilites"][2]
    ok = f"Une hausse des sinistres de 10 % fait varier le résultat de {s['variation_du_resultat_a_l_origine']}."
    assert synthesis_issues(ok, f, set()) == []
    assert synthesis_issues("La CSM baisse de 42,42.", f, set()) == ["nombre absent des faits : 42,42"]


def test_note_avec_llm_factice(tmp_path):
    def respond(messages, model):
        f = json.loads(messages[1]["content"].split("<faits>")[1].split("</faits>")[0])
        return json.dumps({"synthese": f"Le groupe est bénéficiaire : CSM initiale de {f['csm_initiale']}.",
                           "commentaire_sensibilites": "Le commentaire invente 999,99."}, ensure_ascii=False)
    s = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl")
    note = write_note(GOOD, compute_csm(GOOD), [], [], ["ok"], LLMClient(s, fake_responder=respond), "c1")
    assert note.synthesis_source == "code" and "999,99" not in note.html      # commentaire faux : repli
    assert "Sensibilités" in note.html


def test_double_negation_refusee():
    r = compute_csm(GOOD)
    f = facts(GOOD, r, [], sensitivities(GOOD, r), projection(GOOD, r))
    down = f["sensibilites"][1]["variation_du_resultat_a_l_origine"]          # « -x,xx »
    bad = f"Une baisse de 100 pb le diminue de {down}."
    assert any(i.startswith("double négation") for i in synthesis_issues(bad, f, set()))
    good = f"Une baisse de 100 pb le fait varier de {down}."
    assert synthesis_issues(good, f, set()) == []
    assert synthesis_issues(f"Le résultat diminue de {down.lstrip('-')}.", f, set()) == []


def test_recouvrements_b65k():
    """D-071 : recouvrements = entrées en fin de période ; sans actualisation, produits = primes et
    résultat = primes − (sorties − recouvrements) ; seuil de bascule exact ; affichés dans la note."""
    flat = REC.model_copy(update={"discount_rates": 0.0})
    r = compute_csm(flat)
    assert r.pv_recoveries == pytest.approx(25) and r.pv_inflows == pytest.approx(125)
    pr = projection(flat, r)
    assert pr.totals["insurance_revenue"] == pytest.approx(100)
    assert pr.totals["insurance_service_result"] == pytest.approx(100 - (120 - 25))
    s = sensitivities(REC)
    k = 1 + s.outflow_breakeven
    assert compute_csm(shocked(REC, outflows=k)).fulfilment_cash_flows == pytest.approx(0, abs=1e-9)
    with pytest.raises(ValueError):
        PortfolioData(**{**REC.model_dump(), "recoveries": [0, -1, 0]})
    note = write_note(REC, compute_csm(REC), [], [], ["ok"],
                      LLMClient(Settings(llm_provider="fake", llm_max_retries=0), fake_responder=lambda m, mo: "{}"), "c")
    assert "Recouvrements (fin)" in note.html and "B65 k)" in note.html


def test_hypotheses_declarees_par_le_document_d082():
    """D-082 : la volatilité et le niveau de confiance annoncés par le document sont rapprochés du calcul et du
    registre ; le calcul garde le registre, l'écart est signalé à l'actuaire."""
    from engine.risk import confidence_level, declared_risk_check, ra_at_level

    pv = 1000.0
    ra = ra_at_level(pv, 0.12, 0.75)                  # un RA exactement au quantile 75 % pour un CV de 12 %
    ok = declared_risk_check(pv, ra, 0.12, 0.12, 0.75)
    assert ok.level_with_declared_cv == pytest.approx(0.75) and not ok.cv_disagrees and not ok.confidence_disagrees
    gap = declared_risk_check(pv, ra, 0.35, 0.12, 0.75)   # registre à 35 % : même RA, niveau plus bas
    assert gap.cv_disagrees and gap.cv_gap == pytest.approx(0.12 / 0.35 - 1)
    assert gap.level_with_registry_cv == pytest.approx(confidence_level(pv, 0.35, ra))
    assert gap.level_with_registry_cv < 0.75
    assert not gap.confidence_disagrees               # l'annonce est juste avec SA volatilité
    faux = declared_risk_check(pv, ra, 0.12, 0.12, 0.90)  # le document annonce 90 % : son RA ne les atteint pas
    assert faux.confidence_disagrees
    assert declared_risk_check(pv, ra, 0.35, None, None) is None

    client = LLMClient(Settings(llm_provider="fake", llm_max_retries=0), fake_responder=lambda m, mo: "{}")
    doc = GOOD.model_copy(update={"declared_cv": 0.15, "declared_confidence": 0.75})
    note = write_note(doc, compute_csm(doc), [], [], ["ok"], client, "c", NoteContext(case_id="c", ra_cv=0.35))
    assert "Le document annonce une volatilité" in note.markdown and "Écart d'hypothèse" in note.markdown
    assert "grille, point H3" in note.markdown and "callout warn" in note.html
    sans = write_note(GOOD, compute_csm(GOOD), [], [], ["ok"], client, "c", NoteContext(case_id="c", ra_cv=0.35))
    assert "Le document annonce" not in sans.markdown
