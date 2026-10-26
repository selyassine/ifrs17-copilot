"""(python docs/rapport/build.py) Imprime le rapport (8 pages au plus, vérifié) et, dans un fichier séparé, ses annexes
(A : bibliothèque de prompts ; B : reproduire les mesures)."""

import html
import re
import sys
from pathlib import Path

import markdown

HERE = Path(__file__).parent
ROOT = Path(__file__).resolve().parents[2]
FONTS = ROOT / "api/web/assets/fonts"
sys.path.insert(0, str(ROOT))
from core.pdf import find_browser, html_to_pdf  # noqa: E402

CSS = f"""
@font-face{{font-family:'Source Serif 4';src:url('{(FONTS/'source-serif-4.woff2').as_uri()}') format('woff2');font-weight:200 900;font-style:normal}}
@font-face{{font-family:'Source Serif 4';src:url('{(FONTS/'source-serif-4-italic.woff2').as_uri()}') format('woff2');font-weight:200 900;font-style:italic}}
@font-face{{font-family:'IBM Plex Sans';src:url('{(FONTS/'plex-sans.woff2').as_uri()}') format('woff2');font-weight:100 700}}
@font-face{{font-family:'IBM Plex Mono';src:url('{(FONTS/'plex-mono.woff2').as_uri()}') format('woff2')}}
@page{{size:A4;margin:15mm 16mm 16mm 16mm;
  @bottom-center{{content:counter(page);font:9pt 'IBM Plex Sans';color:#5B6B76}}}}
:root{{--encre:#1B2A33;--sourd:#4A5B66;--trait:#C9D3D8;--petrole:#00767A;--laiton:#9A6A16;--fond:#F3F6F7}}
*{{box-sizing:border-box}}
html{{font-family:'Source Serif 4',Georgia,serif;font-size:9.9pt;line-height:1.42;color:var(--encre)}}
body{{margin:0}}
p{{margin:0 0 5pt;text-align:justify;hyphens:auto}}
h1,h2,h3{{font-family:'IBM Plex Sans',sans-serif;color:var(--encre);break-after:avoid}}
h2{{font-size:12pt;font-weight:600;margin:12pt 0 5pt;padding-top:3pt;border-top:1.5pt solid var(--petrole)}}
h3{{font-size:10pt;font-weight:600;margin:8pt 0 3pt}}
code{{font-family:'IBM Plex Mono',monospace;font-size:8pt;background:var(--fond);padding:0 2pt;border-radius:2pt}}
em{{font-style:italic}}
table{{width:100%;border-collapse:collapse;margin:4pt 0 8pt;font-family:'IBM Plex Sans',sans-serif;font-size:8.4pt;line-height:1.32;break-inside:avoid}}
th{{text-align:left;font-weight:600;color:var(--sourd);border-bottom:1pt solid var(--encre);padding:3pt 4pt}}
td{{border-bottom:.5pt solid var(--trait);padding:2.6pt 4pt;vertical-align:top}}
.titre{{margin:0 0 8pt;padding:2pt 0 9pt;border-bottom:.6pt solid var(--trait)}}
.titre .ecole{{font-family:'IBM Plex Sans';font-size:8.5pt;color:var(--petrole);margin:0 0 4pt;text-align:left}}
.titre h1{{font-size:24pt;margin:0 0 3pt;letter-spacing:-.3pt;font-weight:600}}
.titre .sous{{font-size:11pt;color:var(--sourd);margin:0 0 6pt;text-align:left;font-style:italic}}
.titre .equipe{{font-family:'IBM Plex Sans';font-size:10pt;font-weight:600;margin:0;text-align:left}}
.titre .meta{{font-family:'IBM Plex Sans';font-size:8.5pt;color:var(--sourd);margin:1pt 0 0;text-align:left}}
.resume{{background:var(--fond);border-left:2.5pt solid var(--laiton);padding:6pt 9pt;margin:0 0 4pt}}
.resume p{{margin:0}}
figure{{margin:6pt 0 8pt;break-inside:avoid}}
figure svg{{width:100%;height:auto;display:block}}
figcaption{{font-family:'IBM Plex Sans';font-size:7.8pt;color:var(--sourd);margin-top:3pt}}
.annexe{{break-before:page}}
.annexe h2{{font-size:13pt}}
.annexe h3{{font-size:10.5pt;margin-top:12pt;border-bottom:.5pt solid var(--trait);padding-bottom:2pt}}
.annexe p,.annexe li{{font-size:8.6pt;text-align:left}}
.annexe ul{{margin:2pt 0 5pt;padding-left:14pt}}
.annexe blockquote{{margin:2pt 0 5pt;padding:2pt 8pt;border-left:2pt solid var(--trait);color:var(--sourd);font-size:8.4pt}}
.annexe pre{{font-family:'IBM Plex Mono',monospace;font-size:6.9pt;line-height:1.32;background:var(--fond);border:.5pt solid var(--trait);
  padding:5pt 6pt;white-space:pre-wrap;word-break:break-word;margin:3pt 0 6pt}}
.annexe pre code{{background:none;padding:0;font-size:inherit}}
.annexe table{{font-size:7.2pt;break-inside:auto}}
.annexe tr{{break-inside:avoid}}
.annexe .fiche{{break-before:page}}
.annexe .fiche:first-of-type{{break-before:auto}}
"""


def annexe() -> str:
    md = (ROOT / "prompt_library.md").read_text(encoding="utf-8")
    intro, rest = md.split("## Vue d'ensemble", 1)
    overview, body = rest.split("\n## ", 1)
    sections = re.split(r"\n(?=### `)", "\n## " + body)
    fiches: dict[str, list[tuple[int, str]]] = {}
    for s in sections:
        m = re.match(r"### `([a-z_]+)` v(\d+)", s.strip())
        if m:
            s = re.sub(r"\n## [^\n]+\n", "\n", s)          # titres d'agent intercalés
            fiches.setdefault(m[1], []).append((int(m[2]), s.strip()))
    rows, full = [], []
    for pid, versions in fiches.items():
        versions.sort()
        for v, s in versions:
            change = re.search(r"\*\*Ce qui a changé\.\*\* (.+)", s)
            scores = re.search(r"scores : (.+)", s)
            rows.append(f"<tr><td><code>{pid}</code></td><td>v{v}</td><td>{html.escape(change[1] if change else '')}</td>"
                        f"<td>{html.escape(scores[1] if scores else '')}</td></tr>")
        v, s = versions[-1]
        s = s.replace("<details><summary>Prompt système et gabarit</summary>", "**Prompt système et gabarit**").replace("</details>", "")
        s = re.sub(r"^### `([a-z_]+)` v(\d+)", r"### `\1` v\2 (version en service)", s)
        full.append('<div class="fiche">' + markdown.markdown(s, extensions=["fenced_code", "tables"]) + "</div>")
    intro_html = markdown.markdown(intro.split("\n", 2)[2].split("\n\n", 1)[1].strip(), extensions=["tables"])
    return (
        '<section class="annexe"><h2>Annexe A. Bibliothèque de prompts</h2>'
        + intro_html
        + f"<p>La bibliothèque complète ({sum(len(v) for v in fiches.values())} fiches YAML versionnées, générées en <code>prompt_library.md</code>) est dans le dépôt, "
          "dossier <code>prompts/</code>. Cette annexe donne la vue d'ensemble, l'historique de chaque version avec ce qui a changé "
          f"et les scores mesurés, puis le texte intégral de la version en service de chacun des {len(fiches)} prompts.</p>"
        + "<h3>A.1 Vue d'ensemble</h3>" + markdown.markdown(overview.strip(), extensions=["tables"])
        + "<h3>A.2 Historique des versions</h3><table><thead><tr><th>Prompt</th><th>Version</th><th>Ce qui a changé</th>"
          "<th>Scores mesurés</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        + '<h3 style="break-before:page">A.3 Prompts en service, texte intégral</h3>' + "".join(full) + "</section>")


REPRO = [  # (mesure, commande, résultat publié) : annexe B
    ("Tests unitaires et d'intégration", "python -m pytest -q", "330 tests passés"),
    ("Routeur (20 cas)", "python -m eval.eval_router --llm", "LLM 20/20, heuristique 19/20"),
    ("Recherche (3 jeux)", "python -m eval.eval_retrieval ; python -m eval.eval_agentic", "agent LangGraph : cas pratiques Recall@5 0,750"),
    ("Extraction, jeu facile", "python -m eval.eval_extraction --mode texte", "15/15 justes, 0 dangereux"),
    ("Extraction, jeu piégé", "python -m eval.eval_extraction --mode texte --jeu difficile", "7 réussis, 3 alertes, 0 dangereux"),
    ("Campagne de production", "python -m eval.eval_production --jeu volume | reel | excel | independants",
     "0 dangereux sur 320 documents jamais vus (borne 0,9 %)"),
    ("Appel unique contre chaîne", "python -m eval.eval_monolithique", "3/22 contre 22/22 au centime ; 19 contre 0 dangereux"),
    ("Double calcul R / Python", "python -m actuariat.prospectif --camarade …", "50/50 identiques au centime"),
    ("Sinistres survenus (LIC)", "python -m multimodal.lic_cases ; python -m eval.eval_lic",
     "triangle 7/7, LIC 7/7 au centime, 0 dangereux ; Mack (1993) reproduit"),
    ("Copilot, jeu gelé v3", "python -m eval.eval_copilot --jeu test", "9/10 (8/10 relu)"),
    ("Copilot v4, jeu gelé neuf", "python -m eval.eval_copilot --jeu test2", "8/10, piège obéi (F-023)"),
    ("Copilot, pièges neufs", "python -m eval.eval_copilot --jeu injections", "5/5 refusés"),
    ("Copilot d'un dossier LIC", "python -m eval.eval_copilot --jeu lic", "chiffre 6/6, piège 1/1, relecture 3/6"),
    ("Voix", "python -m eval.eval_speech", "WER 0,9 %, termes 8/8"),
]


def annexe_b() -> str:
    rows = "".join(f"<tr><td>{html.escape(a)}</td><td><code>{html.escape(b)}</code></td><td>{html.escape(c)}</td></tr>"
                   for a, b, c in REPRO)
    return ('<section class="annexe" style="break-before:page"><h2>Annexe B. Reproduire les mesures</h2>'
            "<p>Chaque chiffre du rapport vient d'une commande du dépôt ; les jeux de test gelés sont protégés par leur "
            "empreinte SHA-256 (tests/test_eval_sets.py). Les mesures qui appellent un LLM demandent une clé Groq dans "
            "<code>.env</code> ; les jeux gelés ne s'exécutent qu'une fois. Les registres complets des décisions "
            "(D-001 à D-088) et des échecs (F-001 à F-028) sont dans <code>docs/</code> et dans le dossier complet.</p>"
            "<table><thead><tr><th>Mesure</th><th>Commande</th><th>Résultat publié</th></tr></thead><tbody>"
            + rows + "</tbody></table></section>")


ANNEX_HEADER = ("<header class='titre'><p class='ecole'>ESPRIT · 5DS · Advanced Deep Learning · Projet final : AI Automation</p>"
                "<h1>IFRS 17 Copilot — annexes du rapport</h1>"
                "<p class='sous'>Annexe A : bibliothèque de prompts (vue d'ensemble, historique des versions, texte intégral "
                "des versions en service). Annexe B : reproduire les mesures.</p>"
                "<p class='equipe'>Selmi Yassine · Yasmine Attyaoui · Maha Aloui</p>"
                "<p class='meta'>Octobre 2026 · fichier séparé du rapport (8 pages au plus)</p></header>")
MAX_PAGES = 8


def _pages(pdf: bytes) -> int:
    import io

    from pypdf import PdfReader
    return len(PdfReader(io.BytesIO(pdf)).pages)


def main() -> None:
    corps = (HERE / "corps.html").read_text(encoding="utf-8")
    head = "<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>{t}</title><style>{c}</style></head><body>"
    doc = head.format(t="IFRS 17 Copilot — rapport", c=CSS) + corps + "</body></html>"
    (HERE / "rapport.html").write_text(doc, encoding="utf-8")
    browser = find_browser()
    pdf = html_to_pdf(doc, browser)
    n = _pages(pdf)
    out = HERE / "IFRS17_Copilot_rapport.pdf"
    out.write_bytes(pdf)
    print("écrit", out, f"{n} pages")
    if n > MAX_PAGES:
        raise SystemExit(f"le rapport fait {n} pages : {MAX_PAGES} au plus")
    annex = (head.format(t="IFRS 17 Copilot — annexes", c=CSS) + ANNEX_HEADER
             + annexe().replace('<section class="annexe">', '<section class="annexe" style="break-before:auto">', 1)
             + annexe_b() + "</body></html>")
    (HERE / "annexes.html").write_text(annex, encoding="utf-8")
    pdf = html_to_pdf(annex, browser)
    out = HERE / "IFRS17_Copilot_annexes.pdf"
    out.write_bytes(pdf)
    print("écrit", out, f"{_pages(pdf)} pages")
    old = HERE / "IFRS17_Copilot_rapport_technique.pdf"      # ancien fichier (rapport + annexe ensemble)
    if old.exists():
        old.unlink()


if __name__ == "__main__":
    main()
