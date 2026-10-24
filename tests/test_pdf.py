"""Impression de la note en PDF par le navigateur (D-065)."""

import pytest

from core.pdf import PdfUnavailable, find_browser, html_to_pdf


def test_sans_navigateur_message_clair():
    with pytest.raises(PdfUnavailable, match="NOTE_PDF_BROWSER"):
        html_to_pdf("<p>x</p>", None)
    assert find_browser("/chemin/inexistant/msedge.exe") is None


@pytest.mark.skipif(find_browser() is None, reason="ni Edge, ni Chrome, ni Chromium sur cette machine")
def test_impression_reelle():
    pdf = html_to_pdf("<!doctype html><meta charset='utf-8'><h1>Note IFRS 17</h1><p>CSM initiale : 397,89</p>"
                      "<svg width='200' height='50'><rect width='120' height='40' fill='#1E3A5F'/></svg>", find_browser())
    assert pdf.startswith(b"%PDF") and len(pdf) > 1000
