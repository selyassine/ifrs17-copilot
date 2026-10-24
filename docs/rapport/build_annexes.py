"""(python docs/rapport/build_annexes.py) Livrables séparés exigés par le sujet :
- la bibliothèque de prompts complète (toutes les fiches) en PDF : prompt_library.pdf ;
- la courte évaluation de la recherche (requêtes de test, résultats, commentaires) : evaluation_recherche.pdf.
Mise en page et polices identiques au rapport (build.py)."""

import json
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
.doc h2{break-before:auto}
.doc .fiche{break-before:auto;margin-top:10pt}
.doc details{display:block}
.doc pre{font-family:'IBM Plex Mono',monospace;font-size:6.9pt;line-height:1.32;background:var(--fond);
  border:.5pt solid var(--trait);padding:5pt 6pt;white-space:pre-wrap;word-break:break-word;margin:3pt 0 6pt}
.doc pre code{background:none;padding:0;font-size:inherit}
.doc li,.doc p{text-align:left}
.doc blockquote{margin:2pt 0 5pt;padding:2pt 8pt;border-left:2pt solid var(--trait);color:var(--sourd)}
.doc table{break-inside:auto}.doc tr{break-inside:avoid}
td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
"""


def page(title: str, body: str) -> str:
    return (f"<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>{title}</title>"
            f"<style>{CSS}{EXTRA}</style></head><body class='doc'>{body}</body></html>")


def header(titre: str, sous: str) -> str:
    return ("<header class='titre'><p class='ecole'>ESPRIT · 5DS · Advanced Deep Learning · Projet final : AI Automation</p>"
            f"<h1>{titre}</h1><p class='sous'>{sous}</p>"
            "<p class='equipe'>IFRS 17 Copilot · Selmi Yassine · Yasmine Attyaoui · Maha Aloui</p>"
            "<p class='meta'>Octobre 2026 · données fictives uniquement</p></header>")


# --------------------------------------------------------------------------- prompt library
def prompt_library() -> str:
    md = (ROOT / "prompt_library.md").read_text(encoding="utf-8")
    md = md.split("\n", 2)[2]                                   # sans le titre (repris dans l'en-tête)
    md = md.replace("<details><summary>Prompt système et gabarit</summary>", "**Prompt système et gabarit**").replace("</details>", "")
    html = markdown.markdown(md, extensions=["fenced_code", "tables"])
    n_files = len(re.findall(r"^### `[a-z_]+` v\d+", md, flags=re.M))
    n_ids = len(set(re.findall(r"^### `([a-z_]+)` v\d+", md, flags=re.M)))
    return page("Bibliothèque de prompts", header("Bibliothèque de prompts",
                f"Les {n_files} fiches versionnées des {n_ids} prompts du système : rôle, techniques, échecs observés, "
                "corrections et scores mesurés") + html)


# --------------------------------------------------------------------------- évaluation de la recherche
def table(path: Path) -> dict[str, dict[str, str]]:
    rows = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    i = next(k for k, ligne in enumerate(lines) if ligne.startswith("| Configuration | Recall@1"))
    cols = [c.strip() for c in lines[i].strip("|").split("|")]
    for line in lines[i + 2:]:
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows[cells[0]] = dict(zip(cols, cells, strict=True))
    return rows


def fr(x: str) -> str:
    return x.replace(".", ",")


def exemples(fichier: str, ids: list[str]) -> str:
    out = []
    for line in (ROOT / "eval" / fichier).read_text(encoding="utf-8").splitlines():
        q = json.loads(line)
        if q["id"] in ids:
            attendu = ", ".join(q.get("gold") or []) or "aucun (piège : refus attendu)"
            out.append(f"<tr><td>{q['id']}</td><td>{q['question']}</td><td>{attendu}</td></tr>")
    return "".join(out)


def evaluation() -> str:
    E = ROOT / "eval"
    mp, cp, qz = table(E / "retrieval_report.md"), table(E / "retrieval_report_cas_pratiques.md"), table(E / "retrieval_report_course_quiz.md")
    dec = [
        ("A · bm25", "A · bm25"), ("B · bm25", "B · bm25"),
        ("A · dense · bge-m3", "A · dense"), ("B · dense · bge-m3", "B · dense"),
        ("A · hybrid · bge-m3", "A · hybride"), ("B · hybrid · bge-m3", "B · hybride"),
    ]
    t1 = "".join(f"<tr><td>{lab}</td>" + "".join(
        f"<td class='n'>{fr(r[k][m])}</td>" for r in (mp, cp) for m in ("Recall@5", "Recall @1000 tokens", "MRR@10"))
        + f"<td class='n'>{mp[k]['tokens@5']}</td></tr>" for k, lab in dec)
    opts = [("B · bm25+glossaire", "BM25 + glossaire (référence lexicale)"),
            ("B · hybrid+glossaire · bge-m3", "Hybride BGE-M3 + glossaire (recherche en un coup)"),
            ("B · hybrid+glossaire+questions · bge-m3", "… + index de questions"),
            ("B · hybrid+glossaire+graphe · bge-m3", "… + graphe des renvois"),
            ("B · hybrid+glossaire+questions+graphe · bge-m3", "… + index de questions + graphe (mode rapide)")]
    t2 = "".join(f"<tr><td>{lab}</td>" + "".join(f"<td class='n'>{fr(r[k]['Recall@5'])}</td>" for r in (mp, qz, cp)) + "</tr>"
                 for k, lab in opts)
    t2 += ("<tr><td>… + reranker bge-reranker-v2-m3 (D-053)</td><td class='n'>0,853</td><td class='n'>—</td><td class='n'>0,617</td></tr>"
           "<tr><td><strong>Agent de recherche LangGraph</strong> (retenu, D-050)</td><td class='n'><strong>0,883</strong></td>"
           "<td class='n'><strong>0,400</strong></td><td class='n'><strong>0,750</strong></td></tr>"
           "<tr><td>Agent + reranker (D-054, rejeté)</td><td class='n'>0,953*</td><td class='n'>0,467</td><td class='n'>0,650</td></tr>")
    body = header("Évaluation de la recherche",
                  "Requêtes de test, résultats et commentaires : comment le système retrouve les paragraphes d'IFRS 17")
    body += f"""
<h2>1. Ce qui est mesuré, et comment</h2>
<p>La recherche doit remettre au LLM, parmi les 380 paragraphes indexés du règlement (UE) 2021/2036, ceux qui répondent à la
question. Chaque requête de test porte un ou plusieurs paragraphes attendus (<em>gold</em>), parfois des paragraphes
« acceptables » qui répondent aussi. Mesures : <strong>Recall@5</strong> (part des paragraphes attendus parmi les 5 remis au
LLM), <strong>MRR</strong> (rang du premier bon paragraphe), et <strong>rappel à budget de 1 000 tokens</strong> : à nombre de
morceaux égal, un découpage en grandes fenêtres gagne mécaniquement en envoyant plus de texte ; à budget égal, la comparaison
est juste (D-014). Les écarts sont donnés avec un intervalle de confiance à 95 % (bootstrap apparié).</p>
<table><thead><tr><th>Jeu</th><th>Taille</th><th>Rôle</th><th>Origine</th></tr></thead><tbody>
<tr><td>Mise au point</td><td>56 questions (50 notées, 6 pièges)</td><td>Développer et régler</td><td>Rédigées avec Claude dans le vocabulaire de la norme</td></tr>
<tr><td>Quiz du cours</td><td>15 questions</td><td>Test hors échantillon</td><td>Quiz du cours IFRS 17 de l'équipe (EAM 2024), vocabulaire d'enseignant</td></tr>
<tr><td>Cas pratiques</td><td>30 questions</td><td>Test, mesuré une fois par méthode</td><td>Rédigés avec Claude, relus et validés par l'équipe (30/30), <strong>gelés dans Git avant tout développement</strong> (D-047)</td></tr>
</tbody></table>

<h2>2. Exemples de requêtes de test</h2>
<table><thead><tr><th>Id</th><th>Question</th><th>Paragraphe attendu</th></tr></thead><tbody>
{exemples("rag_questions.jsonl", ["q01", "q02", "q25", "q46"])}
{exemples("course_quiz.jsonl", ["c01", "c02", "c06"])}
{exemples("cas_pratiques.jsonl", ["p01", "p02", "p14", "p23"])}
</tbody></table>
<p>Les pièges du jeu de mise au point (hors IFRS 17, ou réponse absente de la norme) servent au test de refus de l'agent RAG :
6/6 refusés, 0 faux refus sur les 50 autres questions.</p>

<h2>3. Deux stratégies de découpage</h2>
<p><strong>A</strong> : fenêtres de 512 tokens, chevauchement de 64 (138 morceaux). <strong>B</strong> : un morceau par paragraphe
de la norme, sans chevauchement, précédé de son chemin (annexe, section, intertitres) : 380 morceaux, 127 tokens en médiane.</p>
<table><thead><tr><th rowspan="2">Configuration</th><th colspan="3">Mise au point (50)</th><th colspan="3">Cas pratiques (30)</th><th rowspan="2">Tokens pour 5 résultats</th></tr>
<tr><th>Recall@5</th><th>Rappel 1 000 t.</th><th>MRR</th><th>Recall@5</th><th>Rappel 1 000 t.</th><th>MRR</th></tr></thead>
<tbody>{t1}</tbody></table>
<p><strong>Commentaire.</strong> À budget égal, B l'emporte nettement sur le jeu de mise au point (dense : rappel à 1 000 tokens
0,757 contre 0,493) en envoyant deux fois moins de texte, et il permet de citer le paragraphe exact. Sur les cas pratiques, l'écart
va dans le même sens mais n'est pas significatif (dense, rappel à 1 000 tokens : +0,133, IC [−0,067 ; +0,333]) : 30 questions, c'est peu. B est retenu
pour la citation et le coût, pas pour un gain de rappel prouvé sur tous les jeux.</p>

<h2>4. Améliorations essayées (Recall@5, découpage B)</h2>
<table><thead><tr><th>Configuration</th><th>Mise au point</th><th>Quiz du cours</th><th>Cas pratiques</th></tr></thead>
<tbody>{t2}</tbody></table>
<p style="font-size:8pt;color:#4A5B66">* exécution faite avec l'index des questions et le graphe actifs (D-054). Le reranker n'a pas été
mesuré sur le quiz. Recherche par défaut : 30 candidats denses et 30 BM25 fusionnés par RRF (k = 60), top-k = 5, filtre de zone
dans Qdrant ; reranker sur les 20 premiers candidats quand un GPU est disponible.</p>

<h2>5. Commentaires</h2>
<p><strong>Ce qui marche.</strong> L'agent de recherche LangGraph (planifier en nommant le mécanisme d'IFRS 17 en jeu, chercher, noter
chaque passage, au plus une nouvelle recherche) est la seule méthode qui gagne significativement sur les cas pratiques :
Recall@5 +0,233 [+0,100 ; +0,367], MRR 0,351 → 0,668. Exemples : p04 et p05 (séparer une composante d'épargne ou un service
accessoire, §11 et §12), p14 (groupe déficitaire en PAA, §57), p23 (ajustement de la CSM pour services futurs, B96) passent de 0 à
1. Coût : 2,2 appels LLM et environ 10 s de plus par question ; l'agent relance une recherche dans 6 cas sur 30.</p>
<p><strong>Ce qui ne marche pas, et pourquoi.</strong> Le quiz du cours reste bas (0,400 au mieux) : un enseignant écrit « maille »
là où la norme dit « niveau d'agrégation », ou « option OCI » là où elle décrit le choix de ventiler les produits et charges financiers (F-012). Deux remèdes ont
été rejetés par la mesure : la réécriture de requête par le LLM (plafond inchangé à 0,267, tokens +46 %, D-045) et le fine-tuning
contrastif de BGE-M3 sur un T4 (0,200 → 0,200, D-046) ; régler le glossaire sur le quiz aurait été de l'ajustement sur le jeu de
test. Le glossaire de sigles aide sur la mise au point (BM25 : +0,09, IC [+0,02 ; +0,16]) mais pas sur les cas pratiques (F-014).
Les améliorations ne s'additionnent pas : l'agent avec le reranker recule à 0,650 sur les cas pratiques (D-054), et l'agent avec
l'index de questions et le graphe ne fait pas mieux que l'agent seul (D-051).</p>
<p><strong>Configuration retenue.</strong> Agent LangGraph sur la recherche hybride BGE-M3 + BM25 + glossaire, découpage B, Qdrant.
Mode rapide sans appel LLM pour la recherche : index de questions + graphe des renvois (cas pratiques 0,683).
<strong>Limites.</strong> Jeux petits (15 à 56 questions) et rédigés en partie avec l'aide d'un LLM ; un seul document indexé ;
la qualité des réponses complètes est mesurée à part (relecture humaine de 50 réponses : 43 sans erreur, 37 complètes).</p>
<p style="font-size:8pt;color:#4A5B66">Sources : eval/retrieval_report.md, eval/retrieval_report_cas_pratiques.md,
eval/retrieval_report_course_quiz.md, eval/agentic_report_*.md ; décisions D-013 à D-017, D-045 à D-054 (docs/decisions.md).
Reproduire : <code>python -m eval.eval_retrieval</code> et <code>python -m eval.eval_agentic</code>.</p>
"""
    return page("Évaluation de la recherche", body)


def main() -> None:
    browser = find_browser()
    for name, html in (("prompt_library.pdf", prompt_library()), ("evaluation_recherche.pdf", evaluation())):
        pdf = html_to_pdf(html, browser)
        (HERE / name).write_bytes(pdf)
        print("écrit", HERE / name, len(pdf))


if __name__ == "__main__":
    main()
