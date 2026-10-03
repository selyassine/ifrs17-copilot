"""Les schémas doivent refuser les sorties d'agent incohérentes."""

import pytest
from pydantic import ValidationError

from agents.schemas import (
    AgentName,
    Citation,
    GroundedAnswer,
    Intent,
    Plan,
    PortfolioData,
    Verdict,
    VerdictStatus,
)


def test_plan_doit_passer_par_le_verificateur():
    with pytest.raises(ValidationError):
        Plan(intent=Intent.NORM_QUESTION, steps=[AgentName.RAG], confidence=0.9, rationale="x")


def test_plan_hors_perimetre_sans_agent():
    p = Plan(intent=Intent.OUT_OF_SCOPE, steps=[], confidence=0.8, rationale="météo")
    assert p.steps == []
    with pytest.raises(ValidationError):
        Plan(intent=Intent.OUT_OF_SCOPE, steps=[AgentName.RAG, AgentName.VERIFIER],
             confidence=0.8, rationale="x")


def test_champ_inconnu_refuse():
    with pytest.raises(ValidationError):
        Plan(intent=Intent.CALCULATION, steps=[AgentName.CALCULATOR, AgentName.VERIFIER],
             confidence=0.9, rationale="x", invente="oui")


def test_portefeuille_longueurs_incoherentes():
    with pytest.raises(ValidationError, match="outflows"):
        PortfolioData(group_id="G", premiums=[1, 2], outflows=[1], coverage_units=[1, 1])


def test_portefeuille_montant_negatif():
    with pytest.raises(ValidationError):
        PortfolioData(group_id="G", premiums=[-1], outflows=[1], coverage_units=[1])


def test_portefeuille_courbe_de_mauvaise_longueur():
    with pytest.raises(ValidationError, match="discount_rates"):
        PortfolioData(group_id="G", premiums=[1, 0], outflows=[1, 1],
                      coverage_units=[1, 1], discount_rates=[0.02])


def test_reponse_sans_citation_interdite():
    with pytest.raises(ValidationError):
        GroundedAnswer(answer="Le CSM est ajusté…", citations=[])


def test_reponse_citee_acceptee():
    a = GroundedAnswer(
        answer="Le CSM est ajusté pour les variations liées au service futur.",
        citations=[Citation(paragraph_id="44", doc="IFRS 17", quote="…", chunk_id="c-44-0")],
    )
    assert a.citations[0].paragraph_id == "44"


def test_refus_doit_etre_motive():
    with pytest.raises(ValidationError):
        GroundedAnswer(answer=None, refused=True)


def test_verdict_negatif_sans_probleme_refuse():
    with pytest.raises(ValidationError):
        Verdict(status=VerdictStatus.FIX)
