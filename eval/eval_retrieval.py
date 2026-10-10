"""Évaluation du retrieval : découpage (A, B) × mode de recherche (bm25, dense, hybrid).

    python -m eval.eval_retrieval                          # BM25 seul (aucun modèle requis)
    python -m eval.eval_retrieval --model BAAI/bge-m3      # + dense et hybride
    python -m eval.eval_retrieval --model BAAI/bge-m3 --model Qwen/Qwen3-Embedding-0.6B

Métriques (questions avec réponse attendue ; les questions « piège » servent au test de refus) :
    Recall@k  part des paragraphes attendus présents dans les k premiers chunks
    MRR@10    1 / rang du premier chunk contenant un paragraphe attendu
    nDCG@5    gain = nouveaux paragraphes attendus couverts par le chunk ; idéal calculé par
              couverture gloutonne, pour ne pas avantager les gros chunks qui se chevauchent
    tokens@5  taille du contexte envoyé au LLM avec 5 chunks (coût et bruit)

Les écarts entre configurations sont donnés avec un intervalle de confiance bootstrap à 95 %
(questions rééchantillonnées), pour ne pas conclure sur une différence due au hasard.

Écrit eval/results/retrieval_<horodatage>.json et eval/retrieval_report.md.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from rag.chunking import Chunk, load_chunks
from rag.retrieve import HashingEncoder, Retriever, load_dense

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).parent
PROCESSED = ROOT / "data" / "processed"
INDEX_DIR = ROOT / "data" / "index"
KS = (1, 3, 5, 10)
BUDGETS = (1000, 2000)


def load_questions(path: Path = HERE / "rag_questions.jsonl") -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --------------------------------------------------------------------------- #
# Métriques
# --------------------------------------------------------------------------- #
def recall_at(ranked: list[Chunk], gold: set[str], k: int) -> float:
    found = set().union(*(set(c.paragraph_ids) for c in ranked[:k])) if ranked[:k] else set()
    return len(found & gold) / len(gold)


def recall_at_budget(ranked: list[Chunk], gold: set[str], budget: int) -> float:
    """Rappel à budget de contexte égal : on prend des chunks tant que le total reste ≤ budget.

    Indispensable pour comparer A (gros chunks) et B (petits) : à k égal, A envoie 2,5 fois
    plus de texte au LLM et « gagne » mécaniquement en rappel.
    """
    kept, total = [], 0
    for c in ranked:
        if kept and total + c.n_tokens > budget:
            break
        kept.append(c)
        total += c.n_tokens
    return recall_at(kept, gold, len(kept))


def mrr(ranked: list[Chunk], gold: set[str], k: int = 10) -> float:
    for i, c in enumerate(ranked[:k], start=1):
        if gold & set(c.paragraph_ids):
            return 1.0 / i
    return 0.0


def _dcg(gains: list[float]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg(ranked: list[Chunk], gold: set[str], all_chunks: list[Chunk], k: int = 5) -> float:
    covered: set[str] = set()
    gains = []
    for c in ranked[:k]:
        new = (set(c.paragraph_ids) & gold) - covered
        gains.append(len(new))
        covered |= new
    # idéal : couverture gloutonne des paragraphes attendus par les chunks existants
    remaining, ideal = set(gold), []
    candidates = [set(c.paragraph_ids) & gold for c in all_chunks]
    for _ in range(k):
        best = max(candidates, key=lambda s: len(s & remaining), default=set())
        gain = len(best & remaining)
        if gain == 0:
            break
        ideal.append(gain)
        remaining -= best
    idcg = _dcg(ideal)
    return _dcg(gains) / idcg if idcg else 0.0


def bootstrap_diff(a: list[float], b: list[float], n: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """Différence moyenne b - a et IC 95 % (questions appariées)."""
    a_, b_ = np.array(a), np.array(b)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(a_), size=(n, len(a_)))
    diffs = (b_[idx] - a_[idx]).mean(axis=1)
    return float((b_ - a_).mean()), float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


# --------------------------------------------------------------------------- #
# Exécution
# --------------------------------------------------------------------------- #
def run_config(retriever: Retriever, chunks: list[Chunk], questions: list[dict], mode: str,
               expand: bool = False) -> dict:
    per_q, lat = [], []
    for q in questions:
        gold = set(q["gold"])
        t0 = time.perf_counter()
        hits = retriever.search(q["question"], k=10, mode=mode, expand=expand)
        lat.append((time.perf_counter() - t0) * 1000)
        ranked = [h.chunk for h in hits]
        row = {"id": q["id"], "niveau": q["niveau"],
               "top3": [{"chunk": c.chunk_id, "paragraphes": c.paragraph_ids[:6]} for c in ranked[:3]],
               "tokens@5": sum(c.n_tokens for c in ranked[:5])}
        if gold:
            row.update({f"recall@{k}": recall_at(ranked, gold, k) for k in KS})
            row.update({f"recall@{b}tok": recall_at_budget(ranked, gold, b) for b in BUDGETS})
            row["mrr@10"] = mrr(ranked, gold)
            row["ndcg@5"] = ndcg(ranked, gold, chunks)
        per_q.append(row)

    scored = [r for r in per_q if "mrr@10" in r]
    agg = {m: round(float(np.mean([r[m] for r in scored])), 3)
           for m in [f"recall@{k}" for k in KS] + [f"recall@{b}tok" for b in BUDGETS]
           + ["mrr@10", "ndcg@5"]}
    agg["tokens@5"] = round(float(np.mean([r["tokens@5"] for r in per_q])))
    agg["latence_p50_ms"] = round(float(np.percentile(lat, 50)), 1)
    agg["latence_p95_ms"] = round(float(np.percentile(lat, 95)), 1)
    by_level = {}
    for lvl in sorted({r["niveau"] for r in scored}):
        rows = [r for r in scored if r["niveau"] == lvl]
        by_level[lvl] = {"n": len(rows), "recall@5": round(float(np.mean([r["recall@5"] for r in rows])), 3),
                         "mrr@10": round(float(np.mean([r["mrr@10"] for r in rows])), 3)}
    return {"global": agg, "par_niveau": by_level, "questions": per_q}


def build_configs(models: list[str], encoder_name: str | None) -> list[tuple[str, str, str | None]]:
    configs = [(s, "bm25", None) for s in ("A", "B", "B0")] + [("B", "bm25+glossaire", None)]
    for m in models + ([encoder_name] if encoder_name else []):
        for s in ("A", "B", "B0"):
            configs += [(s, "dense", m), (s, "hybrid", m)]
        configs += [("B", "hybrid+glossaire", m)]
    return configs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", action="append", default=[], help="modèle d'embedding (sentence-transformers)")
    ap.add_argument("--encoder", choices=["hashing"], default=None,
                    help="encodeur factice pour tester la chaîne sans modèle")
    ap.add_argument("--questions", type=Path, default=HERE / "rag_questions.jsonl")
    args = ap.parse_args()

    questions = load_questions(args.questions)
    chunks = {s: load_chunks(PROCESSED / f"chunks_{s}.jsonl") for s in ("A", "B")}
    # ablation : mêmes chunks B, mais sans l'en-tête de contexte dans le texte indexé
    chunks["B0"] = [Chunk(**{**c.__dict__, "embed_text": c.text}) for c in chunks["B"]]
    results: dict[str, dict] = {}
    retrievers: dict[tuple[str, str | None], Retriever] = {}
    encoders: dict[str, object] = {}

    for strategy, mode, model in build_configs(args.model, args.encoder):
        key = (strategy, model)
        if key not in retrievers:
            if model is None:
                retrievers[key] = Retriever(chunks[strategy])
            elif model == "hashing":
                retrievers[key] = Retriever(chunks[strategy], encoder=HashingEncoder())
            else:
                from rag.retrieve import SentenceTransformerEncoder, save_dense
                if model not in encoders:          # un seul exemplaire du modèle en mémoire
                    encoders[model] = SentenceTransformerEncoder(model)
                enc = encoders[model]
                vecs = load_dense(INDEX_DIR, strategy, model, chunks[strategy], strict=False)
                if vecs is None:                   # absent ou périmé (ex. B0) : encodé puis mis en cache
                    print(f"  encodage de {len(chunks[strategy])} chunks {strategy} ({model})…")
                    vecs = enc.encode([c.embed_text for c in chunks[strategy]])
                    save_dense(INDEX_DIR, strategy, model, vecs, chunks[strategy])
                retrievers[key] = Retriever(chunks[strategy], encoder=enc, vectors=vecs)
        name = f"{strategy} · {mode}" + (f" · {model.split('/')[-1]}" if model else "")
        base_mode, _, extra = mode.partition("+")
        results[name] = run_config(retrievers[key], chunks[strategy], questions, base_mode,
                                   expand=extra == "glossaire")
        g = results[name]["global"]
        print(f"{name:34} R@5 {g['recall@5']:.3f}  R@1000tok {g['recall@1000tok']:.3f}  "
              f"MRR {g['mrr@10']:.3f}  nDCG@5 {g['ndcg@5']:.3f}  tokens@5 {g['tokens@5']}")

    # comparaisons appariées A → B pour chaque mode
    comparisons = {}
    for name in results:
        if name.startswith("A ·"):
            other = "B ·" + name[3:]
            if other in results:
                qa = [r for r in results[name]["questions"] if "mrr@10" in r]
                qb = [r for r in results[other]["questions"] if "mrr@10" in r]
                comparisons[f"{name} → {other}"] = {
                    m: [round(x, 3) for x in bootstrap_diff([r[m] for r in qa], [r[m] for r in qb])]
                    for m in ("recall@5", "recall@1000tok", "mrr@10")}
        if name.startswith("B ·"):
            other = "B0 ·" + name[3:]
            if other in results:
                qa = [r for r in results[name]["questions"] if "mrr@10" in r]
                qb = [r for r in results[other]["questions"] if "mrr@10" in r]
                comparisons[f"{name} → {other}"] = {
                    m: [round(x, 3) for x in bootstrap_diff([r[m] for r in qa], [r[m] for r in qb])]
                    for m in ("recall@5", "recall@1000tok", "mrr@10")}

    for base, variant in [("B · bm25", "B · bm25+glossaire")] + [
            (n, n.replace("hybrid", "hybrid+glossaire")) for n in results if n.startswith("B · hybrid ·")]:
        if base in results and variant in results:
            qa = [r for r in results[base]["questions"] if "mrr@10" in r]
            qb = [r for r in results[variant]["questions"] if "mrr@10" in r]
            comparisons[f"{base} → {variant}"] = {
                m: [round(x, 3) for x in bootstrap_diff([r[m] for r in qa], [r[m] for r in qb])]
                for m in ("recall@5", "recall@1000tok", "mrr@10")}

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    payload = {"date": stamp, "n_questions": len(questions),
               "chunks": {s: len(c) for s, c in chunks.items() if s != "B0"},
               "resultats": results, "comparaisons": comparisons}
    (out_dir / f"retrieval_{stamp}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                                     encoding="utf-8")
    # un autre jeu de questions (quiz du cours…) n'écrase pas le rapport principal
    suffix = "" if args.questions.name == "rag_questions.jsonl" else f"_{args.questions.stem}"
    report = HERE / f"retrieval_report{suffix}.md"
    report.write_text(render_report(payload, questions), encoding="utf-8")
    print(f"\n→ eval/{report.name} et eval/results/retrieval_{stamp}.json")


def render_report(p: dict, questions: list[dict]) -> str:
    res = p["resultats"]
    scored_q = [q for q in questions if q["gold"]]
    lines = [
        "# Évaluation du retrieval",
        "",
        f"Généré le {p['date']} par `python -m eval.eval_retrieval`. "
        f"{len(scored_q)} questions notées sur {p['n_questions']} "
        f"({sum(1 for q in questions if not q['gold'])} questions pièges réservées au test de refus). "
        f"Chunks : A = {p['chunks']['A']}, B = {p['chunks']['B']}.",
        "",
        "## Résultats globaux",
        "",
        "A = taille fixe (512 tokens, chevauchement 64) ; B = un chunk par paragraphe avec en-tête de "
        "contexte ; B0 = chunks B indexés sans l'en-tête (ablation).",
        "",
        "| Configuration | Recall@1 | Recall@5 | Recall@10 | Recall @1000 tokens | Recall @2000 tokens "
        "| MRR@10 | nDCG@5 | tokens@5 | p50 (ms) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, r in res.items():
        g = r["global"]
        lines.append(f"| {name} | {g['recall@1']:.3f} | {g['recall@5']:.3f} | {g['recall@10']:.3f} | "
                     f"{g['recall@1000tok']:.3f} | {g['recall@2000tok']:.3f} | {g['mrr@10']:.3f} | "
                     f"{g['ndcg@5']:.3f} | {g['tokens@5']} | {g['latence_p50_ms']} |")
    lines += ["", "## Par niveau de question", "",
              "| Configuration | Niveau | n | Recall@5 | MRR@10 |", "| --- | --- | --- | --- | --- |"]
    for name, r in res.items():
        for lvl, v in r["par_niveau"].items():
            lines.append(f"| {name} | {lvl} | {v['n']} | {v['recall@5']:.3f} | {v['mrr@10']:.3f} |")
    if p["comparaisons"]:
        lines += ["", "## Écarts appariés (moyenne et IC bootstrap 95 %)", "",
                  "| Comparaison | Δ Recall@5 | Δ Recall @1000 tokens | Δ MRR@10 |", "| --- | --- | --- | --- |"]
        fmt = lambda v: f"{v[0]:+.3f} [{v[1]:+.3f} ; {v[2]:+.3f}]"  # noqa: E731
        for name, c in p["comparaisons"].items():
            lines.append(f"| {name} | {fmt(c['recall@5'])} | {fmt(c['recall@1000tok'])} | {fmt(c['mrr@10'])} |")
        lines += ["", "Un intervalle qui ne contient pas 0 indique une différence robuste sur ce jeu de questions."]

    best = max(res, key=lambda n: res[n]["global"]["mrr@10"])
    fails = [r for r in res[best]["questions"] if r.get("recall@10", 1) == 0]
    qtext = {q["id"]: q for q in questions}
    lines += ["", f"## Échecs de la meilleure configuration ({best})", "",
              "Questions dont aucun paragraphe attendu n'est dans les 10 premiers résultats :", ""]
    if not fails:
        lines.append("Aucune.")
    for r in fails:
        q = qtext[r["id"]]
        got = ", ".join("/".join(t["paragraphes"][:3]) for t in r["top3"])
        lines.append(f"- **{r['id']}** « {q['question']} » — attendu {', '.join(q['gold'])} ; obtenu {got}")
    lines += ["", "## Limites", "",
              "- Questions rédigées et annotées par une seule personne (biais lexical possible) : "
              "à compléter par des questions écrites par l'équipe sans regarder le texte.",
              "- Un seul document (règlement UE 2021/2036) ; les résultats changeront avec le corpus complet.",
              "- Le nombre de tokens est une approximation (1,4 token par mot)."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
