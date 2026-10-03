"""Exactitude du routeur sur eval/router_cases.jsonl.

    python -m eval.eval_router               # heuristique seule
    python -m eval.eval_router --llm         # + routeur LLM (fournisseur du .env)
    python -m eval.eval_router --llm --version 1

Écrit eval/results/router_<mode>.json et affiche les erreurs, à reporter dans
la fiche du prompt (failures_observed) et dans docs/failures.md.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from agents.router import route_heuristic, route_llm

HERE = Path(__file__).parent


def load_cases(path: Path = HERE / "router_cases.jsonl") -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def evaluate(router, cases: list[dict]) -> dict:
    errors, confusion = [], Counter()
    for c in cases:
        plan = router(c["request"], c["has_attachment"])
        confusion[(c["intent"], plan.intent.value)] += 1
        if plan.intent.value != c["intent"]:
            errors.append({"id": c["id"], "request": c["request"], "attendu": c["intent"],
                           "obtenu": plan.intent.value, "rationale": plan.rationale})
    n = len(cases)
    return {
        "n": n,
        "exactitude": round((n - len(errors)) / n, 3),
        "erreurs": errors,
        "confusion": {f"{a} -> {b}": k for (a, b), k in sorted(confusion.items())},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--version", type=int, default=None)
    args = ap.parse_args()

    cases = load_cases()
    runs = {"heuristique": route_heuristic}
    if args.llm:
        runs[f"llm_v{args.version or 'derniere'}"] = (
            lambda r, a: route_llm(r, a, version=args.version))

    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    for name, router in runs.items():
        res = evaluate(router, cases)
        (out_dir / f"router_{name}.json").write_text(
            json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n== {name} : exactitude {res['exactitude']:.0%} sur {res['n']} cas")
        for e in res["erreurs"]:
            print(f"  [{e['id']}] attendu {e['attendu']}, obtenu {e['obtenu']} — {e['request']}")


if __name__ == "__main__":
    main()
