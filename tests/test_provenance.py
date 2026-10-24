"""Page et tableau où chaque donnée extraite a été lue (D-067), affichés dans la note."""

import random

import pytest

from agents.schemas import PortfolioData
from engine.csm import compute_csm
from multimodal.documents import pdf_text
from multimodal.extract import provenance

pytest.importorskip("reportlab")


def test_provenance_sur_un_document_synthetique(tmp_path):
    from multimodal.synth import draw, render_pdf

    d = draw(0, random.Random(17))
    path = tmp_path / "doc.pdf"
    render_pdf(d, path)
    doc = pdf_text(path)
    where = provenance(d.truth, doc)
    assert where["Primes"].startswith("page 1") and "tableau" in where["Primes"]
    assert "Unités de couverture" in where and "Ajustement pour risque" in where


def test_provenance_somme_et_note(tmp_path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    path = tmp_path / "d.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    c.drawString(50, 800, "Groupe AB-1. Ajustement pour risque : 5,00 %.")
    c.showPage()
    c.drawString(50, 800, "Primes 100,00 et 0,00. Sinistres 40,00 et 45,50. Frais 5,00 et 4,50. Contrats 1000 et 900.")
    c.save()
    doc = pdf_text(path)
    p = PortfolioData(group_id="AB-1", premiums=[100, 0], outflows=[45, 50], coverage_units=[1000, 900],
                      discount_rates=0.0, risk_adjustment_pct=0.05)
    where = provenance(p, doc)
    assert where["Primes"] == "page 2, texte" and where["Ajustement pour risque"] == "page 1, texte"
    assert "somme de deux colonnes" in where["Sinistres et frais"]

    from agents.writer import NoteContext, write_note
    from core.config import Settings
    from core.llm import LLMClient

    s = Settings(llm_provider="fake", llm_max_retries=0, trace_path=tmp_path / "t.jsonl")
    note = write_note(p, compute_csm(p), [], [], ["ok"], LLMClient(s, fake_responder=lambda m, mo: "{}"), "c1",
                      context=NoteContext(case_id="c1", extraction_mode="texte", grounding="document", provenance=where))
    assert "Où chaque donnée a été lue" in note.html and "page 2, texte" in note.html
