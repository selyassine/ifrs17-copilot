"""Évaluation de l'agent de recherche LangGraph (D-050) contre la recherche en un coup.

Même mesure que eval_retrieval (Recall@5, MRR, à partir des paragraphes attendus), sur les passages
que chaque méthode donnerait à l'agent RAG. Écarts appariés avec intervalle de confiance bootstrap.

    python -m eval.eval_agentic --questions eval/rag_questions.jsonl   # mise au point
    python -m eval.eval_agentic --questions eval/cas_pratiques.jsonl   # test (gelé, D-047)
    python -m eval.eval_agentic --questions eval/course_quiz.jsonl     # test (quiz du cours)
    python -m eval.eval_agentic --limit 5                              # essai

Coût : 2 à 3 appels LLM par question (planifier en grand modèle, évaluer en petit). Les passages de
la recherche simple et de l'agent sont mesurés avec le même moteur (.env : RAG_MODE, RAG_EMBED_MODEL,
options avancées), seule la stratégie change.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from agents.agentic_rag import agentic_search
from core.config import get_settings
from core.llm import LLMClient
from eval.eval_retrieval import bootstrap_diff, load_questions, mrr, recall_at
from rag.service import get_retriever, retrieval_options

HERE = Path(__file__).parent


def main() -> None:
    from eval import mode_mesure

    mode_mesure()
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", type=Path, default=HERE / "rag_questions.jsonl")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--pause", type=float, default=4.0, help="secondes entre deux questions (quota Groq)")
    args = ap.parse_args()

    s = get_settings()
    if s.llm_provider == "fake":
        raise SystemExit("LLM_PROVIDER=fake : configurer Groq dans .env avant cette évaluation.")
    model = s.rag_embed_model if s.rag_mode in ("dense", "hybrid") else ""
    retriever = get_retriever(s.rag_strategy, model, **retrieval_options(s))
    client = LLMClient(s)
    questions = [q for q in load_questions(args.questions) if q["gold"]][: args.limit]

    rows = []
    for n, q in enumerate(questions, start=1):
        gold = set(q["gold"])
        base = [h.chunk for h in retriever.search(q["question"], k=5, mode=s.rag_mode, expand=s.rag_glossary)]
        res = agentic_search(q["question"], retriever, client, mode=s.rag_mode, k=5, case_id=f"eval:{q['id']}")
        agent = [h.chunk for h in res.hits]
        rows.append({"id": q["id"], "question": q["question"], "gold": q["gold"],
                     "base_r5": recall_at(base, gold, 5), "agent_r5": recall_at(agent, gold, 5) if agent else 0.0,
                     "base_mrr": mrr(base, gold, 5), "agent_mrr": mrr(agent, gold, 5) if agent else 0.0,
                     "base_top": [c.paragraph_ids[:3] for c in base], "agent_top": [c.paragraph_ids[:3] for c in agent],
                     "requetes": res.queries, "etapes": res.steps, "appels_llm": res.llm_calls,
                     "latence_ms": res.latency_ms})
        r = rows[-1]
        print(f"[{n}/{len(questions)}] {q['id']}  R@5 {r['base_r5']:.2f} → {r['agent_r5']:.2f}  "
              f"({res.llm_calls} appels, {res.latency_ms / 1000:.1f} s)")
        time.sleep(args.pause)

    agg = {m: round(float(np.mean([r[m] for r in rows])), 3) for m in ("base_r5", "agent_r5", "base_mrr", "agent_mrr")}
    agg["ecart_r5"] = [round(x, 3) for x in bootstrap_diff([r["base_r5"] for r in rows], [r["agent_r5"] for r in rows])]
    agg["ecart_mrr"] = [round(x, 3) for x in bootstrap_diff([r["base_mrr"] for r in rows], [r["agent_mrr"] for r in rows])]
    agg["appels_llm_moyens"] = round(float(np.mean([r["appels_llm"] for r in rows])), 2)
    agg["latence_p50_s"] = round(float(np.percentile([r["latence_ms"] for r in rows], 50)) / 1000, 1)
    agg["relances"] = sum(any(e.get("noeud") == "chercher" for e in r["etapes"][2:]) for r in rows)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / f"agentic_{args.questions.stem}_{stamp}.json").write_text(
        json.dumps({"date": stamp, "moteur": {"mode": s.rag_mode, "modele": model, **retrieval_options(s)},
                    "global": agg, "questions": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    fmt = lambda v: f"{v[0]:+.3f} [{v[1]:+.3f} ; {v[2]:+.3f}]"  # noqa: E731
    lines = [f"# Agent de recherche LangGraph : {args.questions.name}", "",
             f"Généré le {stamp} par `python -m eval.eval_agentic`. {len(rows)} questions. Moteur : "
             f"{s.rag_mode} {model or ''}, options {retrieval_options(s)}.", "",
             "| Méthode | Recall@5 | MRR@5 |", "| --- | --- | --- |",
             f"| Recherche en un coup | {agg['base_r5']:.3f} | {agg['base_mrr']:.3f} |",
             f"| Agent LangGraph (planifier, chercher, évaluer) | {agg['agent_r5']:.3f} | {agg['agent_mrr']:.3f} |", "",
             f"Écart Recall@5 : {fmt(agg['ecart_r5'])} ; écart MRR : {fmt(agg['ecart_mrr'])} (IC bootstrap 95 %).",
             f"Coût : {agg['appels_llm_moyens']} appels LLM par question, latence médiane {agg['latence_p50_s']} s, "
             f"{agg['relances']} nouvelles recherches décidées par l'agent.", "", "## Questions qui changent", ""]
    for r in rows:
        if r["base_r5"] != r["agent_r5"]:
            mec = next((e.get("mecanismes") for e in r["etapes"] if e.get("noeud") == "planifier"), [])
            lines.append(f"- **{r['id']}** {r['base_r5']:.2f} → {r['agent_r5']:.2f} · attendu {', '.join(r['gold'])} · "
                         f"mécanismes : {'; '.join(mec or [])}")
    report = HERE / f"agentic_report_{args.questions.stem}.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n→ {report.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
