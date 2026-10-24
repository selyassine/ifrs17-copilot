"""(python docs/rapport/build.py) Assemble le rapport technique (corps + annexe prompt library) et l'imprime en PDF."""

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


def main() -> None:
    corps = (HERE / "corps.html").read_text(encoding="utf-8")
    doc = (f"<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>IFRS 17 Copilot — rapport technique</title>"
           f"<style>{CSS}</style></head><body>{corps}{annexe()}</body></html>")
    (HERE / "rapport.html").write_text(doc, encoding="utf-8")
    pdf = html_to_pdf(doc, find_browser())
    out = HERE / "IFRS17_Copilot_rapport_technique.pdf"
    out.write_bytes(pdf)
    print("écrit", out, len(pdf))


if __name__ == "__main__":
    main()
