"""Évaluation de l'agent Extracteur sur les documents synthétiques (vérité connue).

    python -m multimodal.synth                       # une fois : génère data/synth/ (15 documents)
    python -m eval.eval_extraction --mode texte      # PDF → texte + tableaux → LLM
    python -m eval.eval_extraction --mode texte --limit 3
    python -m eval.eval_extraction --mode vision     # image seule (PNG, ou JPEG « scanné ») → Gemini
    python -m eval.eval_extraction --mode hybride    # PDF : couche texte + image de la page → Gemini
    python -m multimodal.synth_hard                  # une fois : 10 documents piégés (data/synth_hard/)
    python -m eval.eval_extraction --mode texte --jeu difficile

Mesures :
    exactitude par champ      part des documents où le champ est exactement juste
                              (listes : même longueur et chaque valeur à 1 centime près)
    documents justes          tous les champs justes
    CSM juste                 CSM recalculé à partir de l'extraction = CSM attendu (à 0,01 % près)
    feu vert fiable           parmi les documents marqués « ok », part réellement justes
                              (une erreur marquée « ok » partirait au calcul sans contrôle humain)
    alertes                   parmi les documents faux, part marqués « à vérifier » ou « échec »

Jeu difficile (pièges) : chaque document reçoit un verdict
    réussi            données justes et statut « ok »
    fausse alerte     données justes mais « à vérifier » (sûr, mais un humain travaille pour rien)
    erreur rattrapée  données fausses mais « à vérifier » / « échec » (la sécurité a fonctionné)
    alerte levée      cas qui DOIT être signalé (information absente, ambiguïté) et qui l'est
    DANGEREUX         données fausses, ou cas à signaler, marqués « ok » : le calcul partirait seul
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

from core.config import ROOT, get_settings
from core.llm import LLMClient, LLMError
from core.tracing import read_traces
from engine.csm import compute_csm
from multimodal.documents import pdf_text
from multimodal.extract import ExtractionResult, extract_from_images, extract_from_text
from multimodal.vision import normalize_image, pdf_page_images, vision_client

HERE = Path(__file__).parent
FIELDS = ("group_id", "currency", "unit_multiplier", "premiums", "outflows", "coverage_units",
          "discount_rates", "risk_adjustment_pct")


def load_cases(path: Path = HERE / "extraction_cases.jsonl") -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def same(field: str, got, want) -> bool:
    if field == "group_id":
        return str(got).strip().upper() == str(want).strip().upper()
    if field in ("currency", "unit_multiplier"):
        return got == want
    tol = 1e-6 if field in ("discount_rates", "risk_adjustment_pct") else 0.011
    if isinstance(want, list) or isinstance(got, list):
        if not (isinstance(want, list) and isinstance(got, list)) or len(got) != len(want):
            return False
        return all(abs(a - b) <= tol for a, b in zip(got, want, strict=True))
    return abs(got - want) <= tol


def verdict(expect: str, status: str, all_ok: bool) -> str:
    if expect == "alerte":
        return "alerte levée" if status != "ok" else "DANGEREUX"
    if all_ok:
        return "réussi" if status == "ok" else "fausse alerte"
    return "erreur rattrapée" if status != "ok" else "DANGEREUX"


def score(case: dict, res: ExtractionResult) -> dict:
    expect = case.get("attendu", "exact")
    row = {"id": case["id"], "layout": case["layout"], "scan": case.get("scan", False),
           "attendu": expect, "piege": case.get("piege", ""),
           "status": res.status, "grounding": res.grounding, "reads": res.reads, "groups": res.groups,
           "corrections": res.corrections, "issues": res.issues, "first_issues": res.first_attempt_issues,
           "missing": res.missing, "warnings": res.warnings, "latency_ms": res.latency_ms}
    if expect == "alerte":
        row.update({"fields": {}, "all_ok": res.status != "ok", "csm_ok": None, "csm": None,
                    "extracted": res.portfolio.model_dump(include=set(FIELDS)) if res.portfolio else None,
                    "verdict": verdict(expect, res.status, False)})
        return row
    if res.portfolio is None:
        row.update({"fields": {f: False for f in FIELDS}, "all_ok": False, "csm_ok": False,
                    "csm": None, "extracted": None, "verdict": verdict(expect, res.status, False)})
        return row
    got = res.portfolio.model_dump()
    fields = {f: same(f, got[f], case["truth"][f]) for f in FIELDS}
    csm = compute_csm(res.portfolio)
    want = case["csm_attendu"] if case["csm_attendu"] > 0 else -case["perte_attendue"]
    have = csm.initial_csm if csm.initial_csm > 0 else -csm.initial_loss_component
    row.update({"fields": fields, "all_ok": all(fields.values()),
                "csm_ok": abs(have - want) <= max(0.01, abs(want) * 1e-4),
                "csm": round(have, 4), "csm_attendu": want,
                "extracted": {f: got[f] for f in FIELDS},
                "verdict": verdict(expect, res.status, all(fields.values()))})
    return row


def aggregate(rows: list[dict]) -> dict:
    n = len(rows)
    exact = [r for r in rows if r.get("attendu", "exact") == "exact"]
    ne = max(len(exact), 1)
    ok = [r for r in exact if r["status"] == "ok"]
    wrong = [r for r in exact if not r["all_ok"]]
    verdicts: dict[str, int] = {}
    for r in rows:
        verdicts[r["verdict"]] = verdicts.get(r["verdict"], 0) + 1
    return {
        "documents": n,
        "verdicts": verdicts,
        "dangereux": verdicts.get("DANGEREUX", 0),
        "exactitude_par_champ": {f: round(sum(r["fields"][f] for r in exact) / ne, 3) for f in FIELDS},
        "documents_justes": f"{sum(r['all_ok'] for r in exact)}/{len(exact)}",
        "dont_scans_justes": f"{sum(r['all_ok'] for r in exact if r['scan'])}/{sum(r['scan'] for r in exact)}",
        "csm_juste": f"{sum(bool(r['csm_ok']) for r in exact)}/{len(exact)}",
        "statuts": {s: sum(r["status"] == s for r in rows) for s in ("ok", "a_verifier", "echec")},
        "feu_vert_fiable": f"{sum(r['all_ok'] for r in ok)}/{len(ok)}" if ok else "—",
        "alertes_sur_documents_faux": f"{sum(r['status'] != 'ok' for r in wrong)}/{len(wrong)}" if wrong else "—",
        "relances": sum(r["corrections"] for r in rows),
        "latence_mediane_ms": round(statistics.median(r["latency_ms"] for r in rows), 1),
    }


def render_report(stamp: str, mode: str, model: str, agg: dict, rows: list[dict]) -> str:
    lines = [
        f"# Évaluation de l'extracteur — mode {mode}", "",
        f"Généré le {stamp} par `python -m eval.eval_extraction --mode {mode}`. Modèle : "
        f"`{model}` ; documents : `eval/extraction_cases.jsonl` (synthétiques, vérité connue).", "",
        "| Mesure | Valeur |", "| --- | --- |",
        f"| Documents | {agg['documents']} |",
        f"| **Cas dangereux** (faux ou à signaler, mais marqués « ok ») | **{agg['dangereux']}** |",
        f"| Verdicts | {', '.join(f'{k} : {v}' for k, v in agg['verdicts'].items())} |",
        f"| Documents entièrement justes | {agg['documents_justes']} |",
        f"| … dont images « scannées » justes | {agg['dont_scans_justes']} |",
        f"| CSM recalculé juste | {agg['csm_juste']} |",
        f"| Statuts ok / à vérifier / échec | {agg['statuts']['ok']} / {agg['statuts']['a_verifier']} / {agg['statuts']['echec']} |",
        f"| Feu vert fiable (justes parmi les « ok ») | {agg['feu_vert_fiable']} |",
        f"| Alertes sur les documents faux | {agg['alertes_sur_documents_faux']} |",
        f"| Relances de correction | {agg['relances']} |",
        f"| Latence médiane (ms) | {agg['latence_mediane_ms']} |",
        "", "## Exactitude par champ", "", "| Champ | Exactitude |", "| --- | --- |",
    ]
    lines += [f"| {f} | {v} |" for f, v in agg["exactitude_par_champ"].items()]
    lines += ["", "## Détail", "", "| Id | Mise en page / piège | Scan | Statut | Verdict | Champs faux | CSM obtenu | CSM attendu | Problèmes signalés |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        bad = ", ".join(f for f, ok in r["fields"].items() if not ok) or "—"
        issues = "; ".join(r["issues"])[:200] or "—"
        lines.append(f"| {r['id']} | {r['layout']} | {'oui' if r['scan'] else 'non'} | {r['status']} | {r['verdict']} | {bad} | {r.get('csm')} | "
                     f"{r.get('csm_attendu', '')} | {issues} |")
    return "\n".join(lines) + "\n"


def run_case(mode: str, case: dict, client: LLMClient, case_id: str) -> ExtractionResult:
    if mode == "texte":
        return extract_from_text(pdf_text(ROOT / case["pdf"]), client, case_id=case_id)
    if mode == "vision":
        paths = case.get("images") or [case["image"]]
        images = [normalize_image((ROOT / p).read_bytes()) for p in paths]
        return extract_from_images(images, client, case_id=case_id)
    pdf = (ROOT / case["pdf"]).read_bytes()
    return extract_from_images(pdf_page_images(pdf, max_pages=2), client, doc=pdf_text(pdf),
                               case_id=case_id)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["texte", "vision", "hybride"], default="texte")
    ap.add_argument("--jeu", choices=["facile", "difficile"], default="facile",
                    help="facile : 15 documents propres ; difficile : 10 documents piégés")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--pause", type=float, default=8.0, help="secondes entre deux documents")
    ap.add_argument("--allow-fake", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    settings = get_settings()
    if settings.llm_provider == "fake" and not args.allow_fake:
        raise SystemExit("LLM_PROVIDER=fake : configurer Groq dans .env avant cette évaluation.")
    hard = args.jeu == "difficile"
    cases = load_cases(HERE / ("extraction_hard_cases.jsonl" if hard else "extraction_cases.jsonl"))[: args.limit]
    missing = [c["pdf"] for c in cases if not (ROOT / c["pdf"]).exists()]
    if missing:
        gen = "multimodal.synth_hard" if hard else "multimodal.synth"
        raise SystemExit(f"{len(missing)} documents absents : lancer d'abord `python -m {gen}`")
    suffix = f"{args.mode}_difficile" if hard else args.mode

    client = LLMClient(settings) if args.mode == "texte" else vision_client(settings)
    model_used = settings.llm_model_large if args.mode == "texte" else settings.vision_model
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rows = []
    for i, case in enumerate(cases, 1):
        case_id = f"ext-{stamp}-{case['id']}"
        try:
            res = run_case(args.mode, case, client, case_id)
        except LLMError as exc:
            print(f"[{i}/{len(cases)}] {case['id']} ERREUR LLM : {str(exc)[:150]}")
            continue
        row = score(case, res)
        row["case_id"] = case_id
        rows.append(row)
        bad = [f for f, ok in row["fields"].items() if not ok]
        detail = row["verdict"] if hard else ("tout juste" if not bad else "faux : " + ", ".join(bad))
        if hard and bad:
            detail += " — faux : " + ", ".join(bad)
        print(f"[{i}/{len(cases)}] {case['id']} {case['layout']:8} {res.status:10} {detail}"
              f"{'' if not res.corrections else ' (1 relance)'}")
        if i < len(cases):
            time.sleep(args.pause)
    if not rows:
        raise SystemExit("Aucune extraction obtenue.")

    agg = aggregate(rows)
    run_cases = {r["case_id"] for r in rows}
    traces = [t for t in read_traces(settings.trace_path) if t.get("case_id") in run_cases]
    agg["tokens_entree"] = sum(t.get("tokens_in", 0) for t in traces)
    agg["tokens_sortie"] = sum(t.get("tokens_out", 0) for t in traces)
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    (out / f"extraction_{suffix}_{stamp}.json").write_text(
        json.dumps({"date": stamp, "mode": args.mode, "agregats": agg, "documents": rows},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / f"extraction_report_{suffix}.md").write_text(
        render_report(stamp, suffix, model_used, agg, rows), encoding="utf-8")
    print("\n== Résultats")
    for k, v in agg.items():
        print(f"  {k:28} {v}")
    print(f"\n→ eval/extraction_report_{suffix}.md")


if __name__ == "__main__":
    main()
