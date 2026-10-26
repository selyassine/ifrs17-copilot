"""Campagne de tests « prêt pour la production ? » (D-070) : niveaux 1 à 3, mêmes mesures, critères fixés d'avance.

    python -m multimodal.volume                      # niveau 1 : 150 documents jamais vus (100 propres + 50 pièges)
    python -m eval.eval_production --jeu volume
    python -m multimodal.real_cas                    # niveau 3a : documents construits sur des données réelles (CAS)
    python -m eval.eval_production --jeu reel
    python -m eval.eval_production --jeu prospectif  # dossiers Chain Ladder à montants réels (actuariat.prospectif)
    python -m eval.eval_production --jeu excel       # classeurs Excel et CSV, dont 5 pièges (multimodal.excel_cases)
    python -m eval.eval_production --jeu photos      # niveau 2 : vos photos dans data/photos/ (<id>_*.jpg)
    python -m eval.eval_production --jeu independants  # niveau 3b : documents de camarades (data/independants/)
    python -m eval.eval_production --jeu volume --mode vision --limit 20   # lecture des images (quota Gemini)
    python -m eval.eval_production --jeu volume --chaine-complete 5         # + 5 dossiers de bout en bout

Ce qui est mesuré est ce qui décide du chiffre : Extracteur → contrôle d'ancrage → moteur (comme
eval_extraction, mais sur de nouveaux jeux). Avec --chaine-complete, quelques dossiers passent aussi par
toute la chaîne (norme, vérificateur, rédacteur) pour la durée et le coût d'un dossier complet.

Borne de confiance : avec 0 cas dangereux sur n documents, le vrai taux reste inférieur à la borne
supérieure de Clopper-Pearson à 95 % (≈ 3/n, « règle de trois ») ; 25 documents → 11,3 %, 150 → 2,0 %.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from datetime import datetime
from pathlib import Path

from agents.schemas import PortfolioData
from core.config import ROOT, get_settings
from core.llm import LLMClient, LLMError
from core.tracing import read_traces
from engine.csm import compute_csm
from eval.eval_extraction import run_case as extract_case
from eval.eval_extraction import score
from multimodal.vision import vision_client

HERE = Path(__file__).parent
JEUX = {"volume": ROOT / "data" / "volume" / "cases.jsonl", "reel": ROOT / "data" / "real_cas" / "cases.jsonl",
        "prospectif": ROOT / "data" / "prospectif" / "cases.jsonl",
        "excel": ROOT / "data" / "excel" / "cases.jsonl"}
PHOTOS = ROOT / "data" / "photos"
INDEP = ROOT / "data" / "independants"

# Critères d'acceptation, fixés AVANT la mesure (D-070)
CRITERES = {
    "cas_dangereux": ("0, et borne supérieure à 95 % sous 5 %", lambda a: a["cas_dangereux"] == 0 and a["borne_dangereux_95"] < 0.05),
    "feu_vert_fiable": ("100 % des documents acceptés sans humain ont la bonne CSM", lambda a: a["feu_vert_fiable_pct"] == 1.0),
    "fausses_alertes": ("au plus 15 % des documents justes envoyés à un humain", lambda a: a["fausses_alertes_pct"] <= 0.15),
    "erreurs_techniques": ("aucune exception ni réponse illisible", lambda a: a["erreurs_techniques"] == 0),
    "latence": ("lecture d'un document en moins de 60 s (95e centile)", lambda a: a["latence_p95_s"] <= 60),
}


def clopper_pearson_upper(k: int, n: int, conf: float = 0.95) -> float:
    """Borne supérieure unilatérale exacte d'une proportion (k succès sur n)."""
    if n == 0:
        return 1.0
    if k >= n:
        return 1.0
    alpha = 1 - conf

    def cdf(p: float) -> float:
        return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))
    lo, hi = k / n, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if cdf(mid) > alpha else (lo, mid)
    return hi


def _nums(s: str) -> list[float]:
    """« 2 400,00 | 0 » → [2400.0, 0.0] ; « 3,10 % » → 0.031 (un pourcentage devient une fraction)."""
    out = []
    for x in str(s).split("|"):
        x = x.strip().replace("\u202f", "").replace("\xa0", "").replace(" ", "")
        if not x:
            continue
        pc = x.endswith("%")
        v = float(x.rstrip("%").replace(",", "."))
        out.append(round(v / 100, 8) if pc else v)
    return out


def cases_photos(folder: Path = PHOTOS) -> list[dict]:
    """Photos prises au téléphone : <id du document>_<n'importe quoi>.jpg ; vérité = celle de l'original."""
    truth = {}
    for f in ("extraction_cases.jsonl", "extraction_hard_cases.jsonl"):
        for line in (HERE / f).read_text(encoding="utf-8").splitlines():
            if line.strip():
                c = json.loads(line)
                truth[c["id"]] = c
    out = []
    for img in sorted(p for p in folder.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png")):
        ref = truth.get(img.stem.split("_")[0])
        if ref is None:
            print(f"  ignorée : {img.name} (nom attendu : ext01_..., dur10_...)")
            continue
        out.append({**ref, "id": img.stem, "layout": f"photo de {ref['id']}", "scan": True,
                    "image": str(img.relative_to(ROOT)), "images": [str(img.relative_to(ROOT))]})
    return out


def cases_independants(folder: Path = INDEP) -> list[dict]:
    """Documents de camarades : attendus.csv (voir docs/consigne_documents_independants.md)."""
    out = []
    with (folder / "attendus.csv").open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            fichier = folder / r["fichier"].strip()
            expect = (r.get("attendu") or "exact").strip() or "exact"
            case = {"id": fichier.stem, "layout": "indépendant",
                    "scan": fichier.suffix.lower() not in (".pdf", ".xlsx", ".csv"),
                    "attendu": expect, "piege": r.get("commentaire", ""), "pdf": str(fichier.relative_to(ROOT)),
                    "image": str(fichier.relative_to(ROOT)), "truth": None, "csm_attendu": None, "perte_attendue": None}
            if expect == "exact":
                rates = _nums(r["taux"])
                p = PortfolioData(group_id=r["groupe"].strip(), currency=r["devise"].strip().upper(),
                                  unit_multiplier=int(float(r["unite"])), premiums=_nums(r["primes"]),
                                  outflows=_nums(r["sorties"]), coverage_units=_nums(r["unites_couverture"]),
                                  discount_rates=rates[0] if len(rates) == 1 else rates,
                                  risk_adjustment_pct=_nums(r["ajustement_risque"])[0])
                csm = compute_csm(p)
                case |= {"truth": p.model_dump(exclude={"field_confidence", "future_service_adjustments"}),
                         "csm_attendu": round(csm.initial_csm, 4), "perte_attendue": round(csm.initial_loss_component, 4)}
            out.append(case)
    return out


def load(jeu: str) -> list[dict]:
    if jeu == "photos":
        return cases_photos()
    if jeu == "independants":
        return cases_independants()
    path = JEUX[jeu]
    if not path.exists():
        gen = {"volume": "multimodal.volume", "reel": "multimodal.real_cas",
               "prospectif": "actuariat.prospectif data/cas/clrd.csv data/cas/clrd2025.csv",
               "excel": "multimodal.excel_cases"}[jeu]
        raise SystemExit(f"{path} absent : lancer d'abord `python -m {gen}`")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def aggregate(rows: list[dict]) -> dict:
    n = len(rows)
    exact = [r for r in rows if r["attendu"] == "exact"]
    ok = [r for r in exact if r["status"] == "ok"]
    right = [r for r in exact if r.get("all_ok")]
    danger = sum(r["verdict"] == "DANGEREUX" for r in rows)
    lat = sorted(r["latency_ms"] / 1000 for r in rows if r.get("latency_ms") is not None) or [0.0]
    return {
        "documents": n, "dont_pieges_ou_alertes": n - len(exact),
        "cas_dangereux": danger, "borne_dangereux_95": round(clopper_pearson_upper(danger, n), 4),
        "csm_juste": f"{sum(bool(r.get('csm_ok')) for r in exact)}/{len(exact)}",
        "feu_vert_fiable": f"{sum(bool(r.get('csm_ok')) for r in ok)}/{len(ok)}",
        "feu_vert_fiable_pct": round(sum(bool(r.get("csm_ok")) for r in ok) / len(ok), 4) if ok else 1.0,
        "fausses_alertes": f"{sum(r['status'] != 'ok' for r in right)}/{len(right)}",
        "fausses_alertes_pct": round(sum(r["status"] != "ok" for r in right) / len(right), 4) if right else 0.0,
        "alertes_levees": f"{sum(r['verdict'] == 'alerte levée' for r in rows)}/{n - len(exact)}",
        "erreurs_rattrapees": sum(r["verdict"] == "erreur rattrapée" for r in rows),
        "erreurs_techniques": sum(r.get("erreur_technique", False) for r in rows),
        "latence_mediane_s": round(statistics.median(lat), 1),
        "latence_p95_s": round(lat[min(len(lat) - 1, math.ceil(0.95 * len(lat)) - 1)], 1),
    }


def full_chain(cases: list[dict], k: int, settings, client) -> list[dict]:
    """Quelques dossiers de bout en bout (norme, vérificateur, rédacteur) : durée et coût réels."""
    from agents.orchestrator import run_case
    from multimodal.vision import detect_mime
    from rag.service import IndexMissing, get_retriever, retrieval_options

    model = settings.rag_embed_model if settings.rag_mode in ("dense", "hybrid") else ""
    try:
        get_retriever(settings.rag_strategy, model, **retrieval_options(settings))
        loader = lambda: get_retriever(settings.rag_strategy, model, **retrieval_options(settings))   # noqa: E731
    except IndexMissing:
        loader = None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = []
    for c in [c for c in cases if c["attendu"] == "exact"][:k]:
        pdf = (ROOT / c["pdf"]).read_bytes()
        cid = f"prod-{stamp}-{c['id']}"
        t0 = time.perf_counter()
        try:
            res = run_case(pdf, detect_mime(pdf, c["pdf"]), settings, lambda: client, lambda: vision_client(settings), loader, cid)
            status = res.status
        except LLMError as exc:
            status = f"erreur LLM : {str(exc)[:80]}"
        secs = round(time.perf_counter() - t0, 1)
        calls = [t for t in read_traces(settings.trace_path) if t.get("case_id") == cid and t.get("kind") == "llm"]
        out.append({"id": c["id"], "statut": status, "secondes": secs, "appels_llm": len(calls),
                    "tokens": sum(t.get("tokens_in", 0) + t.get("tokens_out", 0) for t in calls)})
        print(f"  dossier complet {c['id']} : {status}, {secs} s, {len(calls)} appels")
    return out


def rescore(path: Path) -> None:
    """Recalcule verdicts et critères d'un résultat enregistré, SANS appel au LLM (règles de comparaison
    corrigées) : les données extraites sont dans le fichier, la vérité dans les cas du jeu."""
    from eval.eval_extraction import FIELDS, same, verdict
    data = json.loads(path.read_text(encoding="utf-8"))
    truth = {c["id"]: c for c in load(data["jeu"])}
    for r in data["documents"]:
        c = truth.get(r["id"])
        if not c or r.get("attendu", "exact") != "exact" or not r.get("extracted") or not c.get("truth"):
            continue
        r["fields"] = {f: same(f, r["extracted"].get(f), c["truth"].get(f)) for f in FIELDS}
        r["all_ok"] = all(r["fields"].values())
        r["verdict"] = verdict("exact", r["status"], r["all_ok"])
    agg = {**data["agregats"], **aggregate(data["documents"])}
    data |= {"agregats": agg, "criteres": {k: ("OUI" if test(agg) else "NON", label) for k, (label, test) in CRITERES.items()},
             "recalcule": "règles de comparaison corrigées (taux unique = liste de taux égaux)"}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    write_report(data)


def write_report(data: dict) -> None:
    agg, verdicts, rows, chain, jeu = data["agregats"], data["criteres"], data["documents"], data.get("chaine_complete", []), data["jeu"]
    lines = [f"# Campagne « prêt pour la production ? » : jeu {jeu} (mode {data['mode']})", "",
             f"Généré le {data['date']} par `python -m eval.eval_production --jeu {jeu}`"
             + (f" ; {data['recalcule']}" if data.get("recalcule") else "") + ". Critères fixés avant la mesure (D-070).", "",
             "| Critère | Seuil | Atteint |", "| --- | --- | --- |"]
    lines += [f"| {k.replace('_', ' ')} | {label} | **{v}** |" for k, (v, label) in verdicts.items()]
    lines += ["", "| Mesure | Valeur |", "| --- | --- |"] + [f"| {k.replace('_', ' ')} | {v} |" for k, v in agg.items()]
    if chain:
        lines += ["", "## Dossiers de bout en bout", "", "| Dossier | Statut | Durée (s) | Appels LLM | Tokens |", "| --- | --- | --- | --- | --- |"]
        lines += [f"| {c['id']} | {c['statut']} | {c['secondes']} | {c['appels_llm']} | {c['tokens']} |" for c in chain]
    bad = [r for r in rows if r["verdict"] in ("DANGEREUX", "erreur rattrapée", "fausse alerte") or r.get("erreur_technique")]
    lines += ["", "## Documents à regarder (dangereux, rattrapés, fausses alertes, erreurs)", "",
              "| Document | Mise en page | Statut | Verdict | CSM juste | CSM lue / attendue | Champs faux | Problèmes |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in bad:
        wrong = [f for f, ok in (r.get("fields") or {}).items() if not ok]
        lines.append(f"| {r['id']} | {r['layout']} | {r['status']} | {r['verdict']} | {r.get('csm_ok')} | "
                     f"{r.get('csm')} / {r.get('csm_attendu')} | {', '.join(wrong)} | {'; '.join(r.get('issues') or [])[:160]} |")
    (HERE / f"production_report_{jeu}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    from eval import mode_mesure

    mode_mesure()
    ap = argparse.ArgumentParser()
    ap.add_argument("--jeu", choices=["volume", "reel", "prospectif", "excel", "photos", "independants"], default=None)
    ap.add_argument("--mode", choices=["texte", "vision"], default=None,
                    help="texte : couche texte du PDF (défaut) ; vision : image (défaut pour photos)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--pause", type=float, default=4.0)
    ap.add_argument("--chaine-complete", type=int, default=0, help="nombre de dossiers passés par toute la chaîne")
    ap.add_argument("--rescore", type=Path, default=None, help="recalculer un eval/results/production_*.json, sans LLM")
    args = ap.parse_args()
    if args.rescore:
        rescore(args.rescore)
        print(f"→ eval/production_report_{json.loads(args.rescore.read_text(encoding='utf-8'))['jeu']}.md")
        return
    if not args.jeu:
        raise SystemExit("--jeu est obligatoire (volume, reel, prospectif, excel, photos, independants)")
    settings = get_settings()
    if settings.llm_provider == "fake":
        raise SystemExit("LLM_PROVIDER=fake : configurer Groq dans .env avant cette évaluation.")
    mode = args.mode or ("vision" if args.jeu == "photos" else "texte")
    cases = load(args.jeu)[: args.limit]
    if not cases:
        raise SystemExit("Aucun document à évaluer.")
    client = LLMClient(settings) if mode == "texte" else vision_client(settings)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rows = []
    for i, case in enumerate(cases, 1):
        cid = f"prod-{stamp}-{case['id']}"
        if mode == "texte" and not case.get("pdf", "").lower().endswith((".pdf", ".xlsx", ".csv")):
            case_mode = "vision"
        else:
            case_mode = mode
        try:
            res = extract_case(case_mode, case, client if case_mode == mode else vision_client(settings), cid)
            row = score(case, res)
        except (LLMError, OSError, ValueError) as exc:
            row = {"id": case["id"], "layout": case["layout"], "attendu": case.get("attendu", "exact"), "status": "echec",
                   "verdict": "erreur rattrapée" if case.get("attendu", "exact") == "exact" else "alerte levée",
                   "all_ok": False, "csm_ok": False, "latency_ms": None, "erreur_technique": True,
                   "issues": [f"{type(exc).__name__} : {str(exc)[:200]}"]}
        row["case_id"] = cid
        rows.append(row)
        print(f"[{i}/{len(cases)}] {case['id']:10} {row['status']:10} {row['verdict']}")
        if i < len(cases):
            time.sleep(args.pause)

    agg = aggregate(rows)
    traces = [t for t in read_traces(settings.trace_path) if t.get("case_id", "").startswith(f"prod-{stamp}")]
    agg["tokens_par_document"] = round(sum(t.get("tokens_in", 0) + t.get("tokens_out", 0) for t in traces) / len(rows))
    agg["appels_llm_par_document"] = round(sum(t.get("kind") == "llm" for t in traces) / len(rows), 2)
    verdicts = {k: ("OUI" if test(agg) else "NON", label) for k, (label, test) in CRITERES.items()}
    chain = full_chain(cases, args.chaine_complete, settings, LLMClient(settings)) if args.chaine_complete else []
    data = {"date": stamp, "jeu": args.jeu, "mode": mode, "agregats": agg, "criteres": verdicts, "chaine_complete": chain,
            "documents": rows}
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / f"production_{args.jeu}_{stamp}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    write_report(data)
    print("\n== Critères")
    for k, (v, label) in verdicts.items():
        print(f"  {v:3}  {k:20} {label}")
    print(f"\n  cas dangereux {agg['cas_dangereux']}/{agg['documents']} (borne à 95 % : {agg['borne_dangereux_95']:.1%})")
    print(f"→ eval/production_report_{args.jeu}.md")


if __name__ == "__main__":
    main()
