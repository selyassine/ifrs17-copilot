"""Évaluation de la branche LIC (D-083) : lecture du triangle par le LLM et calcul du passif, sur le jeu
``eval/lic_cases.jsonl`` (``python -m multimodal.lic_cases``) et, en option, sur d'autres dossiers sans vérité
(``--fichier dossier_C.pdf``, résultats affichés pour comparaison avec le calcul attendu).

    python -m eval.eval_lic                       # 8 triangles CAS (6 propres, 2 pièges)
    python -m eval.eval_lic --fichier chemin\\vers\\dossier_C_farmbureau_cloture_1997.pdf

Mesures : triangle juste (toutes les cellules), LIC juste au centime, alertes levées sur les pièges et
**cas dangereux** (statut « ok » avec un LIC faux de plus d'un centime). Rapport : eval/lic_report.md.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from agents.schemas import TriangleData
from core.config import ROOT, get_settings
from core.llm import LLMClient, LLMError
from engine.lic import compute_lic
from multimodal.documents import pdf_text
from multimodal.spreadsheet import CSV_MIME, XLSX_MIME, spreadsheet_text
from multimodal.triangle import TriangleResult, extract_triangle

HERE = Path(__file__).parent


def read_document(path: Path):
    data = path.read_bytes()
    if path.suffix.lower() == ".xlsx":
        return spreadsheet_text(data, XLSX_MIME), "tableur"
    if path.suffix.lower() == ".csv":
        return spreadsheet_text(data, CSV_MIME), "tableur"
    return pdf_text(data), "texte"


def lic_of(t: TriangleData, default_level: float = 0.75):
    return compute_lic(t.cumulative_triangle(), t.discount_rates, t.confidence_level or default_level,
                       cv=t.declared_cv, tail=t.tail_factor)


def score(case: dict, res: TriangleResult) -> dict:
    truth = TriangleData(**case["truth"])
    row = {"id": case["id"], "piege": case["piege"], "attendu": case["attendu"], "statut": res.status,
           "double_lecture": res.double_read, "relances": res.corrections,
           "problemes": res.issues[:5] + [f"absent : {m}" for m in res.missing]}
    if res.data is None:
        row |= {"triangle_juste": False, "lic_juste": False, "lic": None, "verdict": "echec sur"}
        return row
    tri_ok = (res.data.cumulative_triangle() == truth.cumulative_triangle()
              and res.data.unit_multiplier == truth.unit_multiplier)
    lic = lic_of(res.data).lic
    lic_ok = abs(lic - case["lic_attendu"]) <= 0.01
    row |= {"triangle_juste": tri_ok, "lic_juste": lic_ok, "lic": round(lic, 2), "lic_attendu": case["lic_attendu"]}
    if case["attendu"] == "alerte":
        row["verdict"] = "alerte levee" if res.status != "ok" else "DANGEREUX (piège non signalé)"
    elif res.status == "ok":
        row["verdict"] = "juste" if lic_ok and tri_ok else "DANGEREUX"
    else:
        row["verdict"] = "juste mais a verifier" if lic_ok else "echec sur"
    return row


def render(stamp: str, model: str, rows: list[dict], extra: list[dict]) -> str:
    n = len(rows)
    clean = [r for r in rows if r["attendu"] == "exact"]
    traps = [r for r in rows if r["attendu"] == "alerte"]
    danger = sum(r["verdict"].startswith("DANGEREUX") for r in rows)
    lines = [f"# Évaluation LIC (triangles) — {stamp}", "",
             f"Modèle : {model} · prompt extract_triangle · {n} documents ({len(clean)} propres, {len(traps)} pièges)", "",
             f"- Triangle juste (toutes les cellules) : {sum(r['triangle_juste'] for r in clean)}/{len(clean)}",
             f"- LIC juste au centime : {sum(r['lic_juste'] for r in clean)}/{len(clean)}",
             f"- Statut « ok » sur les propres : {sum(r['statut'] == 'ok' for r in clean)}/{len(clean)}",
             f"- Alertes levées sur les pièges : {sum(r['statut'] != 'ok' for r in traps)}/{len(traps)}",
             f"- **Cas dangereux : {danger}**", "",
             "| Document | Piège | Statut | Double lecture | LIC lu | LIC attendu | Verdict | Problèmes |",
             "| --- | --- | --- | --- | ---: | ---: | --- | --- |"]
    lines += [f"| {r['id']} | {r['piege'] or '—'} | {r['statut']} | {r['double_lecture']} | {r['lic']} | "
              f"{r.get('lic_attendu', '—')} | {r['verdict']} | {'; '.join(r['problemes'])[:220] or '—'} |" for r in rows]
    if extra:
        lines += ["", "## Dossiers sans vérité dans le jeu", "",
                  "| Fichier | Statut | Double lecture | Provision | BEL | RA | LIC | Problèmes |",
                  "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |"]
        lines += [f"| {e['fichier']} | {e['statut']} | {e['double_lecture']} | {e.get('provision', '—')} | "
                  f"{e.get('bel', '—')} | {e.get('ra', '—')} | {e.get('lic', '—')} | {'; '.join(e['problemes'])[:200]} |"
                  for e in extra]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fichier", action="append", default=[], help="dossier supplémentaire sans vérité (répétable)")
    ap.add_argument("--pause", type=float, default=6.0)
    ap.add_argument("--allow-fake", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    settings = get_settings()
    if settings.llm_provider == "fake" and not args.allow_fake:
        raise SystemExit("LLM_PROVIDER=fake : configurer Groq dans .env avant cette évaluation.")
    cases_path = HERE / "lic_cases.jsonl"
    if not cases_path.exists():
        raise SystemExit("jeu absent : lancer d'abord `python -m multimodal.lic_cases`")
    cases = [json.loads(x) for x in cases_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    if any(not (ROOT / c["fichier"]).exists() for c in cases):
        raise SystemExit("documents absents : lancer d'abord `python -m multimodal.lic_cases`")
    client = LLMClient(settings)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rows, extra = [], []
    for i, case in enumerate(cases, 1):
        doc, mode = read_document(ROOT / case["fichier"])
        try:
            res = extract_triangle(doc, client, case_id=f"lic-{stamp}-{case['id']}", mode=mode)
        except LLMError as exc:
            print(f"[{i}/{len(cases)}] {case['id']} ERREUR LLM : {str(exc)[:150]}")
            continue
        row = score(case, res)
        rows.append(row)
        print(f"[{i}/{len(cases)}] {case['id']} {res.status:10} double lecture {res.double_read:11} {row['verdict']}")
        time.sleep(args.pause)
    for f in args.fichier:
        path = Path(f)
        doc, mode = read_document(path)
        res = extract_triangle(doc, client, case_id=f"lic-{stamp}-{path.stem}", mode=mode)
        e = {"fichier": path.name, "statut": res.status, "double_lecture": res.double_read, "problemes": res.issues}
        if res.data is not None:
            r = lic_of(res.data)
            e |= {"provision": round(r.reserve, 2), "bel": round(r.bel, 2), "ra": round(r.risk_adjustment, 2),
                  "lic": round(r.lic, 2), "erreur_mack": round(r.mack_se, 2)}
        extra.append(e)
        print(f"{path.name} : {e}")
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    (out / f"lic_{stamp}.json").write_text(json.dumps({"date": stamp, "documents": rows, "autres": extra},
                                                      ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / "lic_report.md").write_text(render(stamp, settings.llm_model_large, rows, extra), encoding="utf-8")
    print("\n→ eval/lic_report.md")


if __name__ == "__main__":
    main()
