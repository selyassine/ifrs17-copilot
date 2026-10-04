"""Évaluation du vérificateur (LLM-juge) contre la relecture humaine.

Le juge relit les 48 réponses de l'agent RAG déjà relues à la main (eval/rag_human_labels.jsonl,
réponses eval/results/rag_answers_20261004-015143.json) avec les mêmes extraits. On mesure s'il
signale les 7 réponses fausses sans bloquer les 41 justes.

    python -m eval.eval_verifier                    # gpt-oss-120b (modèle « large »)
    python -m eval.eval_verifier --model small      # comparaison avec gpt-oss-20b
    python -m eval.eval_verifier --limit 5

Mesures :
    erreurs détectées     réponses fausses (relecture) que le juge rejette   → rappel
    fausses alertes       réponses justes que le juge rejette                → coût (humain dérangé)
    précision du rejet    parmi les rejets, part de vraies erreurs
    kappa de Cohen        accord juge / humain corrigé du hasard (0 = hasard, 1 = parfait)
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from agents.rag_agent import format_extracts
from agents.schemas import VerdictStatus
from agents.verifier import judge
from core.config import ROOT, get_settings
from core.llm import LLMClient, LLMError
from core.prompts import load_prompt
from core.tracing import read_traces
from rag.chunking import load_chunks
from rag.retrieve import Hit

HERE = Path(__file__).parent


def rebuild_extracts(paragraph_ids: list[str], chunks) -> str:
    """Extraits fournis à l'agent, reconstitués depuis les chunks B (avec leur chemin)."""
    by_pid = {}
    for c in chunks:
        for p in c.paragraph_ids:
            by_pid.setdefault(p, c)
    seen, hits = set(), []
    for p in paragraph_ids:
        c = by_pid.get(p)
        if c is not None and c.chunk_id not in seen:
            seen.add(c.chunk_id)
            hits.append(Hit(rank=len(hits) + 1, score=0.0, chunk=c))
    return format_extracts(hits, with_path=True)[0]


def kappa(tp: int, fp: int, fn: int, tn: int) -> float:
    n = tp + fp + fn + tn
    if n == 0:
        return 0.0
    po = (tp + tn) / n
    pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / (n * n)
    return round((po - pe) / (1 - pe), 3) if pe < 1 else 1.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", type=Path, default=HERE / "results" / "rag_answers_20261004-015143.json")
    ap.add_argument("--labels", type=Path, default=HERE / "rag_human_labels.jsonl")
    ap.add_argument("--model", default="large", help="large | small | nom exact du modèle")
    ap.add_argument("--version", type=int, default=None, help="version du prompt verify_answer (défaut : la dernière)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--pause", type=float, default=8.0)
    args = ap.parse_args()

    settings = get_settings()
    if settings.llm_provider == "fake":
        raise SystemExit("LLM_PROVIDER=fake : configurer Groq dans .env avant cette évaluation.")
    if not args.answers.exists():
        raise SystemExit(f"{args.answers} introuvable : ce fichier vient de l'évaluation RAG du 04/10 "
                         "(git pull ou relancer eval_rag puis refaire la relecture)")
    answers = {r["id"]: r for r in json.loads(args.answers.read_text(encoding="utf-8"))["reponses"]}
    labels = [json.loads(line) for line in args.labels.read_text(encoding="utf-8").splitlines() if line.strip()]
    labels = [lab for lab in labels if lab.get("fidele") is not None][: args.limit]
    chunks = load_chunks(ROOT / "data" / "processed" / f"chunks_{settings.rag_strategy}.jsonl")
    client = LLMClient(settings)
    model_name = {"large": settings.llm_model_large, "small": settings.llm_model_small}.get(args.model, args.model)
    spec = load_prompt("verify_answer", args.version)
    spec = spec.model_copy(update={"params": spec.params.model_copy(update={"model": args.model})})

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rows = []
    for i, lab in enumerate(labels, 1):
        ans = answers.get(lab["id"])
        if not ans or not ans.get("answer"):
            print(f"[{i}/{len(labels)}] {lab['id']} absent ou refusé dans {args.answers.name} : ignoré")
            continue
        case_id = f"verif-{stamp}-{lab['id']}"
        extracts = rebuild_extracts(ans.get("provided", []), chunks)
        try:
            res = judge(ans["question"], ans["answer"], extracts, client, case_id=case_id,
                        spec_override=spec)
        except LLMError as exc:
            print(f"[{i}/{len(labels)}] {lab['id']} ERREUR LLM : {str(exc)[:150]}")
            continue
        flagged = res.verdict.status != VerdictStatus.OK
        truth_bad = not lab["fidele"]
        outcome = ("erreur détectée" if truth_bad and flagged else "erreur manquée" if truth_bad
                   else "fausse alerte" if flagged else "juste acceptée")
        rows.append({"id": lab["id"], "case_id": case_id, "humain_fidele": lab["fidele"],
                     "humain_complete": lab.get("complete"), "humain_note": lab.get("note", ""),
                     "verdict": res.verdict.status.value, "issues": [f"{x.kind} : {x.detail}" for x in res.verdict.issues],
                     "outcome": outcome, "latency_ms": res.latency_ms, "error": res.error})
        print(f"[{i}/{len(labels)}] {lab['id']} humain {'fidèle' if lab['fidele'] else 'FAUX  '} → "
              f"juge {res.verdict.status.value:18} {outcome}")
        if i < len(labels):
            time.sleep(args.pause)
    if not rows:
        raise SystemExit("Aucun jugement obtenu.")

    tp = sum(r["outcome"] == "erreur détectée" for r in rows)
    fn = sum(r["outcome"] == "erreur manquée" for r in rows)
    fp = sum(r["outcome"] == "fausse alerte" for r in rows)
    tn = sum(r["outcome"] == "juste acceptée" for r in rows)
    fp_incomplete = sum(r["outcome"] == "fausse alerte" and r["humain_complete"] is False for r in rows)
    run_cases = {r["case_id"] for r in rows}
    traces = [t for t in read_traces(settings.trace_path) if t.get("case_id") in run_cases]
    agg = {
        "reponses_jugees": len(rows),
        "erreurs_detectees": f"{tp}/{tp + fn}",
        "fausses_alertes": f"{fp}/{fp + tn}",
        "dont_reponses_incompletes": fp_incomplete,
        "precision_du_rejet": round(tp / (tp + fp), 3) if tp + fp else None,
        "kappa": kappa(tp, fp, fn, tn),
        "tokens_entree": sum(t.get("tokens_in", 0) for t in traces),
        "tokens_sortie": sum(t.get("tokens_out", 0) for t in traces),
    }
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    tag = f"v{spec.version}_{args.model}"
    (out / f"verifier_{tag}_{stamp}.json").write_text(
        json.dumps({"date": stamp, "model": model_name, "prompt_version": spec.version, "agregats": agg, "jugements": rows},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# Vérificateur (LLM-juge, prompt v{spec.version}) contre la relecture humaine — {model_name}", "",
             f"Généré le {stamp} par `python -m eval.eval_verifier --model {args.model}` sur "
             f"`{args.answers.name}` et `{args.labels.name}`.", "",
             "| Mesure | Valeur |", "| --- | --- |"]
    lines += [f"| {k.replace('_', ' ')} | {v} |" for k, v in agg.items()]
    lines += ["", "| Id | Humain | Juge | Résultat | Problèmes signalés par le juge | Note de la relecture |",
              "| --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['id']} | {'fidèle' if r['humain_fidele'] else 'faux'} | {r['verdict']} | {r['outcome']} | "
                     f"{'; '.join(r['issues'])[:220] or '—'} | {r['humain_note']} |")
    (HERE / f"verifier_report_{tag}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n== Résultats")
    for k, v in agg.items():
        print(f"  {k:28} {v}")
    print(f"\n→ eval/verifier_report_{tag}.md")


if __name__ == "__main__":
    main()
