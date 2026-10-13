"""Données d'entraînement pour le fine-tuning du modèle d'embedding BGE-M3 (D-046).

Le quiz du cours (D-044) montre que la recherche ne relie pas le vocabulaire d'un cours ou d'un
métier à celui de la norme, et que la réécriture de la question n'y change rien (D-045, F-012).
On adapte donc le modèle d'embedding avec des paires (question, passage) :

1. ``pairs``  : pour chaque passage du découpage B, le LLM écrit 4 questions de registres différents
   (prompt ``generate_questions``). Reprise automatique : les passages déjà traités sont sautés, on
   peut donc répartir le travail sur plusieurs jours ou plusieurs modèles (quota gratuit Groq).
2. ``export`` : filtre de fuite (aucune question proche d'une question des jeux de test), négatif
   difficile pris dans les résultats BM25, puis fichier ``train.jsonl`` (anchor, positive, negative)
   et un paquet ``colab_bundle.zip`` à déposer sur Google Drive pour le notebook 01.
3. ``stats``  : couverture et répartition, pour le rapport.

    python -m rag.finetune pairs --limit 20            # essai
    python -m rag.finetune pairs                       # tout (reprend où il s'est arrêté)
    python -m rag.finetune pairs --model large         # autre quota
    python -m rag.finetune export                      # → data/finetune/colab_bundle.zip
    python -m rag.finetune export --holdout-gold       # variante plus stricte (voir D-046)
    python -m rag.finetune stats

Les jeux de test (eval/rag_questions.jsonl, eval/course_quiz.jsonl) ne servent jamais à
l'entraînement : seul le texte de la norme est partagé, comme pour toute adaptation de domaine.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import zipfile
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from core.config import ROOT
from core.llm import LLMClient, LLMError
from core.prompts import load_prompt
from rag.chunking import Chunk, load_chunks
from rag.retrieve import BM25, analyze

PROCESSED = ROOT / "data" / "processed"
OUT_DIR = ROOT / "data" / "finetune"
TEST_SETS = (ROOT / "eval" / "rag_questions.jsonl", ROOT / "eval" / "course_quiz.jsonl")
REGISTERS = ("etudiant", "praticien", "recherche", "reformulee")
LEAK_THRESHOLD = 0.5          # Jaccard sur les mots normalisés (sans mots vides, racinisés)
MIN_TOKENS = 25               # passages trop courts (titres, renvois) : rien à apprendre
MAX_FAILURES = 3              # appels en échec d'affilée avant d'arrêter (quota du jour épuisé)


# --------------------------------------------------------------------------- #
# Lecture et contrôle des questions générées
# --------------------------------------------------------------------------- #
def parse_questions(data: object) -> list[dict]:
    """Garde les questions bien formées : registre connu, 3 à 300 caractères, sans doublon."""
    items = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    seen, out = set(), []
    for it in items:
        if not isinstance(it, dict):
            continue
        q = str(it.get("question", "")).strip()
        reg = str(it.get("registre", "")).strip().lower()
        if reg not in REGISTERS or not 3 <= len(q) <= 300 or q.lower() in seen:
            continue
        seen.add(q.lower())
        out.append({"registre": reg, "question": q})
    return out


def copied_span(question: str, passage: str, n: int = 6) -> bool:
    """Vrai si la question recopie au moins ``n`` mots consécutifs du passage (règle 1 du prompt,
    resserrée d'un cran : on tolère une courte expression consacrée)."""
    words = analyze(question)
    text = " ".join(analyze(passage))
    return any(" ".join(words[i:i + n]) in text for i in range(len(words) - n + 1))


def word_set(text: str) -> frozenset[str]:
    return frozenset(analyze(text))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def load_test_questions(paths: Iterable[Path] = TEST_SETS) -> list[dict]:
    out = []
    for p in paths:
        if p.exists():
            out += [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    return out


def leaks(question: str, test_sets: list[frozenset[str]], threshold: float = LEAK_THRESHOLD) -> bool:
    """Vrai si la question générée est trop proche d'une question de test (même sens, mêmes mots)."""
    ws = word_set(question)
    return any(jaccard(ws, t) >= threshold for t in test_sets)


def gold_paragraphs(tests: list[dict]) -> set[str]:
    return {p for q in tests for p in (q.get("gold") or []) + (q.get("acceptables") or [])}


# --------------------------------------------------------------------------- #
# 1. Génération des paires
# --------------------------------------------------------------------------- #
def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def generate_for_chunk(chunk: Chunk, client: LLMClient, model: str | None = None) -> dict:
    spec = load_prompt("generate_questions")
    resp = client.chat([{"role": "system", "content": spec.system},
                        {"role": "user", "content": spec.render(passage=chunk.embed_text)}],
                       model=model or spec.params.model, temperature=spec.params.temperature,
                       max_tokens=spec.params.max_tokens, json_mode=True,
                       trace={"agent": "chercheur_rag", "prompt_id": spec.id,
                              "prompt_version": spec.version, "case_id": f"ft:{chunk.chunk_id}"})
    try:
        data = resp.json()
    except ValueError:
        data = None
    return {"chunk_id": chunk.chunk_id, "model": resp.model, "questions": parse_questions(data)}


def generate_pairs(chunks: list[Chunk], client: LLMClient, out: Path, model: str | None = None,
                   limit: int | None = None, log=print) -> dict:
    """Ajoute à ``out`` une ligne par passage traité. Les passages déjà présents sont sautés."""
    done = {r["chunk_id"] for r in read_jsonl(out)}
    todo = [c for c in chunks if c.chunk_id not in done and c.n_tokens >= MIN_TOKENS]
    if limit is not None:
        todo = todo[:limit]
    out.parent.mkdir(parents=True, exist_ok=True)
    written, failures, n_questions = 0, 0, 0
    with out.open("a", encoding="utf-8") as f:
        for i, c in enumerate(todo, start=1):
            try:
                rec = generate_for_chunk(c, client, model)
            except LLMError as exc:
                failures += 1
                log(f"  [{i}/{len(todo)}] {c.chunk_id} : échec ({str(exc)[:120]})")
                if failures >= MAX_FAILURES:
                    log("  arrêt : quota du jour probablement épuisé. Relancez plus tard ou avec "
                        "--model large (l'autre modèle a son propre quota).")
                    break
                continue
            failures = 0
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            written += 1
            n_questions += len(rec["questions"])
            if i % 10 == 0 or i == len(todo):
                log(f"  [{i}/{len(todo)}] {n_questions} questions")
    return {"passages_traites": written, "questions": n_questions,
            "restants": len(todo) - written, "deja_faits": len(done)}


# --------------------------------------------------------------------------- #
# 2. Export : filtre de fuite, négatifs difficiles
# --------------------------------------------------------------------------- #
def hard_negative(question: str, positive: Chunk, chunks: list[Chunk], bm25: BM25,
                  depth: int = 10) -> Chunk | None:
    """Premier résultat BM25 qui ne partage aucun paragraphe avec le passage positif : un passage
    qui ressemble à la question par les mots mais ne contient pas la réponse."""
    pos_ids = set(positive.paragraph_ids)
    for i, _ in bm25.search(question, depth):
        c = chunks[i]
        if c.chunk_id != positive.chunk_id and not pos_ids & set(c.paragraph_ids):
            return c
    return None


def build_training_set(records: list[dict], chunks: list[Chunk], tests: list[dict],
                       holdout_gold: bool = False, seed: int = 42) -> tuple[list[dict], Counter]:
    by_id = {c.chunk_id: c for c in chunks}
    rng = random.Random(seed)
    bm25 = BM25([c.embed_text for c in chunks])
    test_sets = [word_set(q["question"]) for q in tests]
    held = gold_paragraphs(tests) if holdout_gold else set()
    rows, report = [], Counter()
    for rec in records:
        c = by_id.get(rec["chunk_id"])
        if c is None:
            report["passage_inconnu"] += len(rec["questions"])
            continue
        if held & set(c.paragraph_ids):
            report["passage_de_test_ecarte"] += len(rec["questions"])
            continue
        for q in rec["questions"]:
            text = q["question"]
            if leaks(text, test_sets):
                report["fuite_ecartee"] += 1
                continue
            if copied_span(text, c.text):
                report["recopie_ecartee"] += 1
                continue
            neg = hard_negative(text, c, chunks, bm25)
            if neg is None:                  # aucun mot en commun : négatif tiré au hasard
                others = [o for o in chunks if not set(o.paragraph_ids) & set(c.paragraph_ids)]
                if not others:
                    report["sans_negatif"] += 1
                    continue
                neg = rng.choice(others)
                report["negatif_aleatoire"] += 1
            rows.append({"anchor": text, "positive": c.embed_text, "negative": neg.embed_text,
                         "registre": q["registre"], "chunk_id": c.chunk_id, "negative_id": neg.chunk_id})
            report["gardees"] += 1
            report[f"registre_{q['registre']}"] += 1
    rng.shuffle(rows)
    return rows, report


def write_bundle(rows: list[dict], train_path: Path, bundle: Path, chunks_path: Path,
                 tests: Iterable[Path] = TEST_SETS) -> None:
    train_path.parent.mkdir(parents=True, exist_ok=True)
    with train_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({k: r[k] for k in ("anchor", "positive", "negative")}, ensure_ascii=False) + "\n")
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(train_path, "train.jsonl")
        z.write(chunks_path, "chunks_B.jsonl")
        for p in tests:
            z.write(p, p.name)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pairs", help="générer les questions (reprise automatique)")
    p.add_argument("--model", default=None, help="small, large ou un nom exact (défaut : celui du prompt)")
    p.add_argument("--limit", type=int, default=None, help="nombre maximal de passages à traiter")
    e = sub.add_parser("export", help="filtrer, ajouter les négatifs, écrire le paquet pour Colab")
    e.add_argument("--holdout-gold", action="store_true",
                   help="écarter aussi les passages qui contiennent une réponse des jeux de test")
    sub.add_parser("stats", help="couverture et répartition")
    for s in (p, e, sub.choices["stats"]):
        s.add_argument("--strategy", default="B")
    args = ap.parse_args(argv)

    chunks_path = PROCESSED / f"chunks_{args.strategy}.jsonl"
    if not chunks_path.exists():
        print(f"{chunks_path} absent : lancez d'abord .\\make.ps1 ingest", file=sys.stderr)
        return 1
    chunks = load_chunks(chunks_path)
    pairs_path = OUT_DIR / "pairs.jsonl"

    if args.cmd == "pairs":
        res = generate_pairs(chunks, LLMClient(), pairs_path, model=args.model, limit=args.limit)
        print(json.dumps(res, ensure_ascii=False))
        print(f"→ {pairs_path.relative_to(ROOT)}")
        return 0

    records = read_jsonl(pairs_path)
    if args.cmd == "stats":
        eligible = [c for c in chunks if c.n_tokens >= MIN_TOKENS]
        regs = Counter(q["registre"] for r in records for q in r["questions"])
        models = Counter(r["model"] for r in records)
        print(json.dumps({"passages_eligibles": len(eligible), "passages_traites": len(records),
                          "passages_sans_question": sum(not r["questions"] for r in records),
                          "questions": sum(regs.values()), "registres": regs, "modeles": models},
                         ensure_ascii=False, indent=1))
        return 0

    tests = load_test_questions()
    rows, report = build_training_set(records, chunks, tests, holdout_gold=args.holdout_gold)
    suffix = "_holdout" if args.holdout_gold else ""
    train_path = OUT_DIR / f"train{suffix}.jsonl"
    bundle = OUT_DIR / f"colab_bundle{suffix}.zip"
    write_bundle(rows, train_path, bundle, chunks_path)
    (OUT_DIR / f"export_report{suffix}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                                         encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"→ {bundle.relative_to(ROOT)} ({len(rows)} paires) : à déposer dans Mon Drive/ifrs17_copilot/finetune/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
