"""Note HTML → PDF avec le navigateur déjà installé (D-065).

Microsoft Edge est présent sur tout Windows 10/11, Chrome ou Chromium ailleurs : le mode « headless »
imprime la page exactement comme l'aperçu avant impression (graphiques SVG, polices, règles @media print
de la note). Aucune dépendance Python ni installation de plus (WeasyPrint demanderait GTK sous Windows,
xhtml2pdf ne sait pas dessiner les graphiques SVG).

Chemin forcé : NOTE_PDF_BROWSER dans .env (chemin complet de msedge.exe, chrome.exe ou chromium).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class PdfUnavailable(RuntimeError):
    """Aucun navigateur trouvé, ou l'impression a échoué."""


def _candidates() -> list[str]:
    if sys.platform.startswith("win"):
        roots = [os.environ.get(k, "") for k in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
        rel = [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"]
        return [str(Path(r) / p) for p in rel for r in roots if r]
    if sys.platform == "darwin":
        return ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    found = [shutil.which(n) for n in ("chromium", "chromium-browser", "google-chrome", "microsoft-edge")]
    pw = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers"))
    found += [str(p) for p in sorted(pw.glob("chromium-*/chrome-linux/chrome"))] if pw.exists() else []
    return [f for f in found if f]


def find_browser(configured: str = "") -> str | None:
    """Le navigateur utilisé pour l'impression : NOTE_PDF_BROWSER, sinon Edge, Chrome ou Chromium."""
    if configured:
        return configured if Path(configured).exists() else None
    return next((c for c in _candidates() if Path(c).exists()), None)


def html_to_pdf(html: str, browser: str | None, timeout: float = 90) -> bytes:
    """Imprime ``html`` en PDF (A4, marges de la feuille de style de la note)."""
    if not browser:
        raise PdfUnavailable("aucun navigateur trouvé (Edge, Chrome ou Chromium) : renseigner NOTE_PDF_BROWSER dans .env")
    with tempfile.TemporaryDirectory(prefix="ifrs17_pdf_") as tmp:
        src, out = Path(tmp) / "note.html", Path(tmp) / "note.pdf"
        src.write_text(html, encoding="utf-8")
        cmd = [browser, "--headless=new", "--disable-gpu", "--no-first-run", "--disable-extensions",
               f"--user-data-dir={Path(tmp) / 'profil'}",  # profil à part : Edge déjà ouvert ne gêne pas
               "--no-pdf-header-footer", "--print-to-pdf-no-header", "--virtual-time-budget=4000",
               f"--print-to-pdf={out}", src.as_uri()]
        if sys.platform.startswith("linux") and hasattr(os, "geteuid") and os.geteuid() == 0:
            cmd.insert(1, "--no-sandbox")
        try:
            run = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PdfUnavailable(f"impression PDF impossible : {type(exc).__name__}") from exc
        if not out.exists() or out.stat().st_size < 500:
            detail = (run.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1:] or ["sans message"]
            raise PdfUnavailable(f"le navigateur n'a pas produit de PDF ({detail[0][:200]})")
        return out.read_bytes()
