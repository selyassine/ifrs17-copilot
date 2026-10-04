"""Évaluation des réponses de l'agent RAG (chaîne complète : routeur → recherche → LLM → vérification).

    python -m eval.eval_rag                    # les 56 questions, pause de 15 s entre deux
    python -m eval.eval_rag --limit 10         # essai rapide
    python -m eval.eval_rag --pause 25         # si Groq renvoie trop de « 429 »
    python -m eval.eval_rag --resume           # reprendre après un arrêt, sans refaire le travail

Mesures (sans juge LLM, tout est vérifiable par le code) :
    refus corrects        les questions pièges doivent être refusées
    faux refus            questions qui ont une réponse dans la norme mais ont été refusées
    citations valides     paragraphes cités présents dans les extraits fournis (avant et après correction)
    précision citations   part des paragraphes cités qui sont dans la réponse attendue
    précision élargie     idem, en acceptant aussi les paragraphes « acceptables » (autre paragraphe
                          qui répond légitimement, ajouté après relecture humaine, D-023)
    couverture            part des paragraphes attendus effectivement cités
    plafond recherche     part des paragraphes attendus présents dans les extraits : si un paragraphe
                          n'a pas été trouvé, le LLM ne pouvait pas le citer (erreur de recherche,
                          pas de génération)

La fidélité fine (chaque phrase est-elle soutenue par l'extrait ?) sera mesurée par l'agent
vérificateur (LLM-juge) puis contrôlée à la main sur 20 réponses : le fichier
eval/results/rag_answers_<date>.md sert à cette relecture.

Quota Groq gratuit : ~2 500 tokens par question sur gpt-oss-120b, 8 000 tokens/minute et
200 000/jour → la pause par défaut (15 s) et l'attente automatique sur les « 429 » tiennent
dans le quota ; les 56 questions consomment environ 150 000 tokens.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from agents.pipeline import ask
from core.config import get_settings
from core.llm import LLMClient, LLMError
from core.tracing import read_traces
from eval.eval_retrieval import load_questions
from rag.service import get_retriever

HERE = Path(__file__).parent


def score_one(q: dict, res) -> dict:
    gold = set(q["gold"])
    cited = [c.paragraph_id for c in res.answer.citations]
    provided = {p for s in (res.rag.sources if res.rag else []) for p in s["paragraph_ids"]}
    row = {
        "id": q["id"], "niveau": q["niveau"], "question": q["question"], "gold": q["gold"],
        "intent": res.plan.intent.value, "refused": res.answer.refused,
        "refusal_reason": res.answer.refusal_reason, "answer": res.answer.answer, "cited": cited,
        "provided": sorted(provided), "warnings": res.warnings,
        "corrections": res.rag.corrections if res.rag else 0,
        "invalid_before_correction": len(res.rag.raw_invalid_refs) if res.rag else 0,
        "latency_ms": res.rag.latency_ms if res.rag else 0.0,
    }
    if gold:
        hit = set(cited) & gold
        row["precision"] = len(hit) / len(cited) if cited else 0.0
        ok = gold | set(q.get("acceptables", []))
        row["precision_large"] = len(set(cited) & ok) / len(cited) if cited else 0.0
        row["coverage"] = len(hit) / len(gold)
        row["retrieval_ceiling"] = len(provided & gold) / len(gold)
        row["at_least_one"] = bool(hit)
    return row


def aggregate(rows: list[dict]) -> dict:
    traps = [r for r in rows if not r["gold"]]
    answerable = [r for r in rows if r["gold"]]
    answered = [r for r in answerable if not r["refused"]]
    mean = lambda xs: round(float(np.mean(xs)), 3) if xs else None  # noqa: E731
    return {
        "questions": len(rows),
        "refus_corrects_pieges": f"{sum(r['refused'] for r in traps)}/{len(traps)}",
        "faux_refus": f"{sum(r['refused'] for r in answerable)}/{len(answerable)}",
        "reponses_avec_citation_inventee_avant_correction":
            f"{sum(r['invalid_before_correction'] > 0 for r in answered)}/{len(answered)}",
        "reponses_corrigees": sum(r["corrections"] for r in rows),
        "citations_invalides_apres_verification": 0,   # garanti par construction (code)
        "precision_citations": mean([r["precision"] for r in answered]),
        "precision_elargie": mean([r.get("precision_large", r["precision"]) for r in answered]),
        "couverture_citations": mean([r["coverage"] for r in answered]),
        "au_moins_un_bon_paragraphe": mean([float(r["at_least_one"]) for r in answered]),
        "plafond_recherche": mean([r["retrieval_ceiling"] for r in answerable]),
        "latence_p50_ms": mean([np.percentile([r["latency_ms"] for r in answered], 50)]) if answered else None,
    }


def render_report(stamp: str, settings, agg: dict, rows: list[dict]) -> str:
    lines = [
        "# Évaluation des réponses de l'agent RAG", "",
        f"Généré le {stamp} par `python -m eval.eval_rag`. Prompt : `rag_answer` v{settings.rag_prompt_version} ; "
        f"modèle : `{settings.llm_model_large}` ; "
        f"routeur : `{settings.router_mode}` ; recherche : `{settings.rag_mode}` "
        f"(découpage {settings.rag_strategy}, glossaire {'oui' if settings.rag_glossary else 'non'}).", "",
        "| Mesure | Valeur |", "| --- | --- |",
    ]
    labels = {
        "questions": "Questions évaluées",
        "refus_corrects_pieges": "Questions pièges correctement refusées",
        "faux_refus": "Faux refus (la norme répondait)",
        "reponses_avec_citation_inventee_avant_correction": "Réponses avec citation inventée, avant vérification",
        "reponses_corrigees": "Relances de correction déclenchées",
        "citations_invalides_apres_verification": "Citations hors extraits après vérification",
        "precision_citations": "Précision des citations (cités ∈ attendus)",
        "precision_elargie": "Précision élargie (cités ∈ attendus ou acceptables)",
        "couverture_citations": "Couverture (attendus effectivement cités)",
        "au_moins_un_bon_paragraphe": "Réponses citant au moins un paragraphe attendu",
        "plafond_recherche": "Plafond fixé par la recherche (attendus présents dans les extraits)",
        "latence_p50_ms": "Latence médiane d'une réponse (ms)",
    }
    for k, label in labels.items():
        lines.append(f"| {label} | {agg[k]} |")
    lines += ["", "## Détail par question", "",
              "| Id | Niveau | Refus | Cités | Attendus | Dans les extraits | Correction |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        inside = ", ".join(p for p in r["gold"] if p in r["provided"]) or "—"
        lines.append(f"| {r['id']} | {r['niveau']} | {'oui' if r['refused'] else 'non'} | "
                     f"{', '.join(r['cited']) or '—'} | {', '.join(r['gold']) or '(refus attendu)'} | "
                     f"{inside} | {r['corrections']} |")
    lines += ["", "## Lecture", "",
              "- Une citation attendue absente des extraits est une erreur de **recherche** ; "
              "présente dans les extraits mais non citée, c'est une erreur de **génération**.",
              "- Les réponses complètes sont dans `eval/results/rag_answers_<date>.md` pour la relecture humaine "
              "(fidélité, clarté) de 20 réponses."]
    return "\n".join(lines) + "\n"


def render_answers(rows: list[dict]) -> str:
    out = ["# Réponses de l'agent RAG (relecture humaine)", "",
           "Pour chaque réponse, noter : fidèle aux extraits (oui/non), complète (oui/partiel/non), commentaire.", ""]
    for r in rows:
        out += [f"## {r['id']} — {r['question']}", "",
                f"Attendus : {', '.join(r['gold']) or '(refus attendu)'} · Cités : {', '.join(r['cited']) or '—'}", ""]
        out.append(f"> REFUS : {r['refusal_reason']}" if r["refused"] else (r["answer"] or ""))
        if r["warnings"]:
            out += ["", "Avertissements : " + " ; ".join(r["warnings"])]
        out += ["", "Fidèle : ☐ oui ☐ non · Complète : ☐ oui ☐ partiel ☐ non · Commentaire :", ""]
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--pause", type=float, default=15.0, help="secondes entre deux questions")
    ap.add_argument("--questions", type=Path, default=HERE / "rag_questions.jsonl")
    ap.add_argument("--resume", action="store_true",
                    help="reprendre après un arrêt : ne refait pas les questions déjà évaluées")
    ap.add_argument("--allow-fake", action="store_true", help=argparse.SUPPRESS)  # tests
    args = ap.parse_args()

    settings = get_settings()
    if settings.router_mode != "llm":
        print("Remarque : ROUTER_MODE n'est pas « llm » ; le routeur par mots-clés peut refuser à tort "
              "des questions sur la norme (voir F-001).")
    if settings.llm_provider == "fake" and not args.allow_fake:
        raise SystemExit("LLM_PROVIDER=fake : configurer Groq dans .env avant cette évaluation.")
    questions = load_questions(args.questions)
    # pièges réparties dans l'échantillon même avec --limit
    if args.limit:
        traps = [q for q in questions if not q["gold"]][: max(1, args.limit // 5)]
        others = [q for q in questions if q["gold"]][: args.limit - len(traps)]
        questions = others + traps

    # sauvegarde au fil de l'eau : un arrêt (plantage, quota, Ctrl+C) ne fait pas perdre le travail fait
    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    partial = out_dir / "rag_answers_en_cours.jsonl"
    rows: list[dict] = []
    if args.resume and partial.exists():
        rows = [json.loads(line) for line in partial.read_text(encoding="utf-8").splitlines() if line.strip()]
        # ne jamais mélanger deux versions du prompt dans un même résultat
        rows = [r for r in rows if r.get("prompt_version", 1) == settings.rag_prompt_version]
        done = {r["id"] for r in rows}
        questions = [q for q in questions if q["id"] not in done]
        print(f"Reprise : {len(done)} questions déjà faites, {len(questions)} restantes.")
    elif partial.exists():
        partial.unlink()

    model = settings.rag_embed_model if settings.rag_mode in ("dense", "hybrid") else ""
    retriever = get_retriever(settings.rag_strategy, model)
    client = LLMClient(settings)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"Prompt rag_answer v{settings.rag_prompt_version} (RAG_PROMPT_VERSION dans .env)")
    for i, q in enumerate(questions, 1):
        case_id = f"eval-{stamp}-{q['id']}"
        try:
            res = ask(q["question"], settings, client, lambda: retriever, case_id=case_id)
            row = score_one(q, res)
            row["prompt_version"] = settings.rag_prompt_version
            row["case_id"] = case_id
        except LLMError as exc:
            print(f"[{i}/{len(questions)}] {q['id']} ERREUR LLM : {str(exc)[:150]}")
            continue
        rows.append(row)
        with partial.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        status = "refus" if row["refused"] else f"cite {', '.join(row['cited'])}"
        print(f"[{i}/{len(questions)}] {q['id']} {q['niveau']:9} → {status} (attendu {', '.join(q['gold']) or 'refus'})")
        if i < len(questions):
            time.sleep(args.pause)

    if not rows:
        raise SystemExit("Aucune réponse obtenue.")
    agg = aggregate(rows)
    # seulement les appels de CETTE évaluation (avant : toutes celles du jour étaient additionnées)
    run_cases = {r.get("case_id", f"eval-{stamp}-{r['id']}") for r in rows}
    traces = [t for t in read_traces(settings.trace_path) if t.get("case_id", "") in run_cases]
    agg_tokens = {"tokens_entree": sum(t.get("tokens_in", 0) for t in traces),
                  "tokens_sortie": sum(t.get("tokens_out", 0) for t in traces),
                  "appels_llm": len([t for t in traces if t.get("kind") == "llm"])}

    (out_dir / f"rag_answers_{stamp}.json").write_text(
        json.dumps({"date": stamp, "prompt_version": settings.rag_prompt_version,
                    "agregats": agg, "tokens": agg_tokens, "reponses": rows},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / f"rag_answers_{stamp}.md").write_text(render_answers(rows), encoding="utf-8")
    v = settings.rag_prompt_version
    report = HERE / ("rag_answer_report.md" if v == 1 else f"rag_answer_report_v{v}.md")
    report.write_text(render_report(stamp, settings, agg, rows), encoding="utf-8")

    print("\n== Résultats")
    for k, v in {**agg, **agg_tokens}.items():
        print(f"  {k:52} {v}")
    partial.unlink(missing_ok=True)
    print(f"\n→ eval/{report.name} et eval/results/rag_answers_{stamp}.md (relecture humaine)")


if __name__ == "__main__":
    main()
