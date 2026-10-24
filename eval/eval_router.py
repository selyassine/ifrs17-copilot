"""Exactitude du routeur sur eval/router_cases.jsonl.

    python -m eval.eval_router               # heuristique seule
    python -m eval.eval_router --llm         # + routeur LLM (fournisseur du .env)
    python -m eval.eval_router --llm --version 1
    python -m eval.eval_router --llm --jeu externe   # 20 cas écrits par un autre membre (F-001, D-085)

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


JEUX = {"equipe": HERE / "router_cases.jsonl", "externe": HERE / "router_cases_externes.jsonl"}
INTENTS = {"question_norme", "traitement_document", "calcul", "hors_perimetre"}


def check_cases(cases: list[dict]) -> list[str]:
    """Format d'un jeu écrit à la main : champs, intentions connues, identifiants uniques."""
    problems, seen = [], set()
    for k, c in enumerate(cases, 1):
        missing = {"id", "request", "has_attachment", "intent"} - set(c)
        if missing:
            problems.append(f"ligne {k} : champs manquants {sorted(missing)}")
            continue
        if c["intent"] not in INTENTS:
            problems.append(f"ligne {k} ({c['id']}) : intention inconnue « {c['intent']} »")
        if c["id"] in seen:
            problems.append(f"ligne {k} : identifiant en double {c['id']}")
        seen.add(c["id"])
    return problems


def evaluate(router, cases: list[dict]) -> dict:
    errors, confusion, fallbacks = [], Counter(), []
    for c in cases:
        plan = router(c["request"], c["has_attachment"])
        if plan.rationale.startswith("repli heuristique"):
            fallbacks.append({"id": c["id"], "raison": plan.rationale})
        confusion[(c["intent"], plan.intent.value)] += 1
        if plan.intent.value != c["intent"]:
            errors.append({"id": c["id"], "request": c["request"], "attendu": c["intent"],
                           "obtenu": plan.intent.value, "rationale": plan.rationale})
    n = len(cases)
    return {
        "n": n,
        "exactitude": round((n - len(errors)) / n, 3),
        "replis": fallbacks,
        "erreurs": errors,
        "confusion": {f"{a} -> {b}": k for (a, b), k in sorted(confusion.items())},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--version", type=int, default=None)
    ap.add_argument("--jeu", choices=sorted(JEUX), default="equipe",
                    help="equipe : 20 cas de l'équipe ; externe : 20 cas d'un autre membre, sans voir les règles")
    args = ap.parse_args()

    path = JEUX[args.jeu]
    if not path.exists():
        raise SystemExit(f"{path.name} absent : voir docs/protocole_mesures_equipe.md (partie 1)")
    cases = load_cases(path)
    problems = check_cases(cases)
    if problems:
        raise SystemExit("jeu mal formé :\n- " + "\n- ".join(problems))
    import hashlib
    digest = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    print(f"jeu {args.jeu} : {len(cases)} cas, SHA-256 {digest} (à noter dans docs/decisions.md avant la mesure)")
    runs = {"heuristique": route_heuristic}
    if args.llm:
        runs[f"llm_v{args.version}" if args.version else "llm"] = (
            lambda r, a: route_llm(r, a, version=args.version))

    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    for name, router in runs.items():
        res = evaluate(router, cases)
        (out_dir / f"router_{name}{'' if args.jeu == 'equipe' else '_' + args.jeu}.json").write_text(
            json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n== {name} : exactitude {res['exactitude']:.0%} sur {res['n']} cas")
        if res["replis"]:
            # sans ce compteur, un LLM en panne passerait inaperçu : le repli renvoie
            # exactement les réponses de l'heuristique (voir docs/failures.md, F-008)
            print(f"  ATTENTION : {len(res['replis'])} cas sur {res['n']} ont basculé sur l'heuristique.")
            print(f"  Première raison : {res['replis'][0]['raison']}")
        for e in res["erreurs"]:
            print(f"  [{e['id']}] attendu {e['attendu']}, obtenu {e['obtenu']} — {e['request']}")


if __name__ == "__main__":
    main()
