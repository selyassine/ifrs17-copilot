"""Évaluation de bout en bout d'un dossier (« golden cases ») : document → note finale.

Chaque dossier fait travailler les 6 agents : extracteur, calculateur, chercheur RAG,
vérificateur (2 à 3 questions sur la norme), rédacteur. Environ 25 000 tokens Groq par dossier :
3 dossiers par défaut.

    python -m eval.eval_case                       # 3 documents du jeu facile (PDF, mode texte)
    python -m eval.eval_case --limit 5 --jeu difficile

Mesures :
    statut final            note prête / validation humaine / illisible (attendu du jeu difficile)
    CSM de la note juste    le CSM affiché = le CSM calculé sur la vérité
    synthèse vérifiée       la synthèse du LLM a passé le contrôle (nombres + paragraphes), sans repli
    réponses validées       questions sur la norme acceptées par le vérificateur
    durée, tokens           par dossier
Les notes HTML sont enregistrées dans eval/results/notes/ (utiles pour la démo et le rapport).
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
from multimodal.vision import detect_mime, vision_client
from rag.service import IndexMissing, get_retriever, retrieval_options

HERE = Path(__file__).parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jeu", choices=["facile", "difficile"], default="facile")
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--pause", type=float, default=10.0)
    args = ap.parse_args()

    from agents.orchestrator import run_case

    settings = get_settings()
    if settings.llm_provider == "fake":
        raise SystemExit("LLM_PROVIDER=fake : configurer Groq dans .env avant cette évaluation.")
    path = HERE / ("extraction_hard_cases.jsonl" if args.jeu == "difficile" else "extraction_cases.jsonl")
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()][: args.limit]
    model = settings.rag_embed_model if settings.rag_mode in ("dense", "hybrid") else ""
    try:
        get_retriever(settings.rag_strategy, model, **retrieval_options(settings))
        loader = lambda: get_retriever(settings.rag_strategy, model, **retrieval_options(settings))   # noqa: E731
    except IndexMissing:
        raise SystemExit("index RAG absent : lancer .\\make.ps1 index-dense") from None
    client = LLMClient(settings)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    notes_dir = HERE / "results" / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, case in enumerate(cases, 1):
        pdf = (ROOT / case["pdf"]).read_bytes()
        cid = f"case-{stamp}-{case['id']}"
        t0 = time.perf_counter()
        try:
            out = run_case(pdf, detect_mime(pdf), settings, lambda: client, lambda: vision_client(settings),
                           loader, cid, source_name=Path(case["pdf"]).name)
        except LLMError as exc:
            print(f"[{i}/{len(cases)}] {case['id']} ERREUR LLM : {str(exc)[:150]}")
            continue
        seconds = round(time.perf_counter() - t0, 1)
        expected = case.get("attendu", "exact")
        csm_ok = None
        if case.get("truth") and out.csm is not None:
            want = case["csm_attendu"] if case["csm_attendu"] > 0 else -case["perte_attendue"]
            have = out.csm.initial_csm if out.csm.initial_csm > 0 else -out.csm.initial_loss_component
            csm_ok = abs(have - want) <= max(0.01, abs(want) * 1e-4)
        status_ok = (out.status != "note_prete") if expected == "alerte" else None
        norm_ok = sum(n.verdict == "ok" for n in out.norm)
        if out.note:
            (notes_dir / f"{case['id']}.html").write_text(out.note.html, encoding="utf-8")
            (notes_dir / f"{case['id']}.md").write_text(out.note.markdown, encoding="utf-8")
        rows.append({"id": case["id"], "case_id": cid, "attendu": expected, "statut": out.status,
                     "csm_juste": csm_ok, "statut_attendu_respecte": status_ok,
                     "synthese": out.note.synthesis_source if out.note else None,
                     "reponses_validees": f"{norm_ok}/{len(out.norm)}", "controles": out.controls,
                     "etapes": [f"{s.agent}:{s.status}" for s in out.steps], "secondes": seconds})
        print(f"[{i}/{len(cases)}] {case['id']} {out.status:18} CSM {'juste' if csm_ok else ('—' if csm_ok is None else 'FAUX')}  "
              f"synthèse {rows[-1]['synthese']}  norme {norm_ok}/{len(out.norm)}  {seconds} s")
        if i < len(cases):
            time.sleep(args.pause)
    if not rows:
        raise SystemExit("Aucun dossier traité.")

    run_cases = {r["case_id"] for r in rows}
    traces = [t for t in read_traces(settings.trace_path) if t.get("case_id") in run_cases]
    exact = [r for r in rows if r["csm_juste"] is not None]
    agg = {
        "dossiers": len(rows),
        "statuts": {s: sum(r["statut"] == s for r in rows) for s in ("note_prete", "validation_humaine", "document_illisible")},
        "csm_de_la_note_juste": f"{sum(r['csm_juste'] for r in exact)}/{len(exact)}",
        "syntheses_verifiees_du_llm": f"{sum(r['synthese'] == 'llm' for r in rows)}/{len(rows)}",
        "reponses_norme_validees": f"{sum(int(r['reponses_validees'].split('/')[0]) for r in rows)}/"
                                   f"{sum(int(r['reponses_validees'].split('/')[1]) for r in rows)}",
        "duree_mediane_s": statistics.median(r["secondes"] for r in rows),
        "appels_llm_par_dossier": round(sum(t.get("kind") == "llm" for t in traces) / len(rows), 1),
        "tokens_entree_par_dossier": round(sum(t.get("tokens_in", 0) for t in traces) / len(rows)),
    }
    (HERE / "results" / f"case_{args.jeu}_{stamp}.json").write_text(
        json.dumps({"date": stamp, "agregats": agg, "dossiers": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# Dossiers de bout en bout — jeu {args.jeu}", "", f"Généré le {stamp} par `python -m eval.eval_case`.", "",
             "| Mesure | Valeur |", "| --- | --- |"] + [f"| {k.replace('_', ' ')} | {v} |" for k, v in agg.items()]
    lines += ["", "| Dossier | Statut | CSM juste | Synthèse | Norme validée | Durée (s) | Étapes |", "| --- | --- | --- | --- | --- | --- | --- |"]
    lines += [f"| {r['id']} | {r['statut']} | {r['csm_juste']} | {r['synthese']} | {r['reponses_validees']} | "
              f"{r['secondes']} | {' → '.join(r['etapes'])} |" for r in rows]
    (HERE / f"case_report_{args.jeu}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n== Résultats")
    for k, v in agg.items():
        print(f"  {k:28} {v}")
    print(f"\n→ eval/case_report_{args.jeu}.md ; notes dans eval/results/notes/")


if __name__ == "__main__":
    main()
