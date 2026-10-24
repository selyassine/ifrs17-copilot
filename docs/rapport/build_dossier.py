"""(python docs/rapport/build_dossier.py) Dossier complet du projet : chronologie, composants, techniques,
tests, rejets, avec en annexe le registre des décisions et le journal des échecs, lus dans le dépôt."""

import ast
import re
import sys
from pathlib import Path

import markdown

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
from build import CSS  # noqa: E402

from core.pdf import find_browser, html_to_pdf  # noqa: E402

EXTRA = """
.sommaire ol{columns:2;column-gap:24pt;margin:2pt 0 4pt;padding-left:16pt;font-family:'IBM Plex Sans';font-size:9pt}
.sommaire p{font-family:'IBM Plex Sans';font-size:8.5pt;color:var(--sourd)}
ol.etapes li,ul.lecons li{margin-bottom:2.5pt;text-align:left}
h3{color:var(--petrole)}
.annexe-dec table{font-size:6.9pt;line-height:1.28;break-inside:auto}
.annexe-dec tr{break-inside:avoid}
.annexe-dec td:first-child{white-space:nowrap;font-weight:600}
.annexe-dec h2,.annexe-ech h2{break-before:page}
.annexe-ech h2{font-size:11pt;border-top:1pt solid var(--trait);break-before:auto;margin-top:10pt}
.annexe-ech h2.titre-annexe{break-before:page;font-size:13pt;border-top:1.5pt solid var(--petrole)}
.annexe-ech li,.annexe-ech p{font-size:8.6pt;text-align:left}
td.n{text-align:right}
"""


def tests_table() -> str:
    rows, total = [], 0
    for f in sorted((ROOT / "tests").glob("test_*.py")):
        src = f.read_text(encoding="utf-8")
        n = len(re.findall(r"^\s*(?:async )?def test_", src, flags=re.M))
        total += n
        doc = (ast.get_docstring(ast.parse(src)) or "").split("\n")[0]
        rows.append(f"<tr><td><code>{f.name}</code></td><td class='n'>{n}</td><td>{doc}</td></tr>")
    return ("<table><thead><tr><th>Fichier</th><th>Tests</th><th>Ce qui est vérifié</th></tr></thead><tbody>"
            + "".join(rows) + f"<tr><td><strong>Total</strong></td><td class='n'><strong>{total}</strong></td>"
            "<td>fonctions de test ; 297 cas exécutés avec les tests paramétrés (1 sauté sans les données CAS)</td></tr></tbody></table>")


def inline(md: str) -> str:
    return markdown.markdown(md).removeprefix("<p>").removesuffix("</p>")


def decisions() -> str:
    lines = (ROOT / "docs/decisions.md").read_text(encoding="utf-8").splitlines()
    rows = []
    for line in lines:
        if not re.match(r"^\| D-\d{3} \|", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
        if len(cells) < 8:
            continue
        ident, date, dec, opts, crit, preuve, statut = cells[:7]
        rows.append(f"<tr><td>{ident}</td><td>{date[5:].replace('-', '/')}</td><td>{inline(dec)}</td><td>{inline(opts)}</td>"
                    f"<td>{inline(crit)}</td><td>{inline(preuve)}</td><td>{inline(statut)}</td></tr>")
    return ("<section class='annexe-dec'><h2>Annexe A. Registre complet des décisions</h2>"
            "<p>Reproduit de <code>docs/decisions.md</code>. Règle des trois preuves : une source, une mesure ou un test, une "
            f"décision écrite. {len(rows)} décisions.</p><table><thead><tr><th>ID</th><th>Date</th><th>Décision</th>"
            "<th>Options comparées</th><th>Critères</th><th>Preuve (source, mesure)</th><th>Statut</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></section>")


def failures() -> str:
    md = (ROOT / "docs/failures.md").read_text(encoding="utf-8")
    body = md.split("\n## ", 1)[1]
    blocks = [b.strip() for b in re.split(r"\n(?=## )", "## " + body) if b.strip()]
    keep = [b for b in blocks if not b.startswith("## Gabarit") and "<titre court>" not in b]
    keep.sort(key=lambda b: int(re.search(r"F-(\d+)", b).group(1)) if re.search(r"F-(\d+)", b) else 999)
    html = markdown.markdown("\n\n".join(keep), extensions=["tables", "fenced_code"])
    return ("<section class='annexe-ech'><h2 class='titre-annexe'>Annexe B. Journal complet des échecs</h2>"
            "<p>Reproduit de <code>docs/failures.md</code> : attendu, obtenu, cause, décision, leçon.</p>" + html + "</section>")


def main() -> None:
    corps = (HERE / "dossier_corps.html").read_text(encoding="utf-8")
    fig1 = re.findall(r"<figure.*?</figure>", (HERE / "corps.html").read_text(encoding="utf-8"), flags=re.S)[0]
    corps = corps.replace("{FIG1}", fig1).replace("{TESTS}", tests_table())
    doc = (f"<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>IFRS 17 Copilot — dossier complet</title>"
           f"<style>{CSS}{EXTRA}</style></head><body>{corps}{decisions()}{failures()}</body></html>")
    pdf = html_to_pdf(doc, find_browser())
    out = HERE / "IFRS17_Copilot_dossier_complet.pdf"
    out.write_bytes(pdf)
    print("écrit", out, len(pdf))


if __name__ == "__main__":
    main()
