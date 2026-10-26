"""Diagnostic de la latence et des refus (D-092) : où part le temps, et quelles questions échouent.

Deux parties, à lancer sur le poste qui a la clé Groq :

    python -m eval.diagnostic                       # 1. analyse des traces existantes (aucun appel au modèle)
    python -m eval.diagnostic --questions           # 2. + batterie de questions à l'assistant normatif (≈ 6 appels
                                                    #    au modèle par question : à lancer une fois, quota frais)
    python -m eval.diagnostic --depuis 2026-10-25   # seulement les traces depuis cette date

Rapport : ``eval/diagnostic_report.md`` (à envoyer tel quel ; il ne contient ni clé ni document).

Lecture : un appel au modèle dure normalement 1 à 5 s. Un appel de plus de 20 s attend presque toujours : quota par
minute (HTTP 429, champ ``quota_wait_s`` depuis D-091), délai dépassé puis nouvel essai, ou passage au modèle de
secours. Le rapport sépare ces causes, agent par agent et modèle par modèle.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SLOW_S = 20.0

# Questions écrites comme un utilisateur (abréviations, fautes, « c quoi ») : elles ne viennent d'aucun jeu de test.
QUESTIONS = [
    ("c quoi le PAA", "norme"), ("C quoi le LRC et comment le calculer", "norme"), ("c quoi le CSM", "norme"),
    ("c quoi le LIC", "norme"), ("c'est quoi le BEL", "norme"), ("qu'est-ce que le RA ?", "norme"),
    ("Comment la marge sur services contractuels est-elle libérée en résultat ?", "norme"),
    ("Quand un groupe de contrats est-il déficitaire ?", "norme"), ("definir un contrat d'assurance", "norme"),
    ("quelle différence entre LRC et LIC", "norme"), ("comment on calcule l'ajustement pour risque", "norme"),
    ("c quoi la VFA", "norme"), ("quel taux d'actualisation utiliser selon IFRS 17", "norme"),
    ("Donne-moi une recette de crêpes", "hors_perimetre"), ("Comment comptabiliser un leasing selon IFRS 16 ?", "hors_perimetre"),
]


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    v = sorted(values)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]


def load(path: Path, since: str = "", offset: int = 0) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open("rb") as f:
        f.seek(offset)
        text = f.read().decode("utf-8", errors="replace")
    for line in text.splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("kind") == "llm" and (not since or str(r.get("ts", "")) >= since):
            out.append(r)
    return out


def cause(r: dict) -> str:
    """Cause probable d'un appel lent."""
    if r.get("wait_budget_exceeded"):
        return "budget d'attente dépassé : échec rapide, réponse de repli (D-093)"
    if r.get("quota_switch") or r.get("quota_skipped"):
        return "quota du principal : passé au secours sans attendre (D-092)"
    if r.get("quota_wait_s"):
        return "attente du quota (429)"
    if r.get("fallback"):
        return "passage au modèle de secours"
    if r.get("retries"):
        return "erreur ou délai dépassé, nouvel essai"
    if r.get("status") == "error":
        return "échec"
    if (r.get("tokens_out") or 0) > 2500:
        return "réponse très longue"
    return "attente non enregistrée (traces d'avant D-091 : quota ou réseau probable)"


def analyse(rows: list[dict]) -> dict:
    by_agent: dict[str, list[dict]] = defaultdict(list)
    by_model: dict[str, list[dict]] = defaultdict(list)
    by_case: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_agent[f"{r.get('agent') or '?'}{' (' + r['mode'] + ')' if r.get('mode') else ''}"].append(r)
        by_model[str(r.get("model") or "?")].append(r)
        by_case[str(r.get("case_id") or "?")].append(r)

    def stats(rs: list[dict]) -> dict:
        lat = [float(r.get("latency_ms") or 0) / 1000 for r in rs]
        slow = [r for r in rs if float(r.get("latency_ms") or 0) / 1000 > SLOW_S]
        return {"appels": len(rs), "total_s": round(sum(lat), 1), "mediane_s": round(statistics.median(lat), 1) if lat else 0,
                "p90_s": round(_pct(lat, 0.9), 1), "max_s": round(max(lat, default=0), 1), "lents": len(slow),
                "quota_s": round(sum(float(r.get("quota_wait_s") or 0) for r in rs), 1),
                "secours": sum(1 for r in rs if r.get("fallback")), "erreurs": sum(1 for r in rs if r.get("status") == "error"),
                "tokens_in_moyen": round(statistics.mean([r.get("tokens_in") or 0 for r in rs])) if rs else 0}

    causes: dict[str, int] = defaultdict(int)
    for r in rows:
        if float(r.get("latency_ms") or 0) / 1000 > SLOW_S:
            causes[cause(r)] += 1
    cases = sorted(((cid, sum(float(r.get("latency_ms") or 0) for r in rs) / 1000, rs) for cid, rs in by_case.items()),
                   key=lambda x: -x[1])[:12]
    return {"total": stats(rows), "agents": {k: stats(v) for k, v in sorted(by_agent.items())},
            "modeles": {k: stats(v) for k, v in sorted(by_model.items())}, "causes": dict(causes),
            "requetes": [{"case_id": cid, "modele_s": round(s, 1), "appels": len(rs),
                          "detail": ", ".join(f"{a} {n}" for a, n in sorted(
                              {a: sum(1 for r in rs if (r.get('agent') or '?') == a) for a in {r.get('agent') or '?' for r in rs}}.items()))}
                         for cid, s, rs in cases],
            "plus_lents": [{"ts": r.get("ts", "")[:19], "agent": r.get("agent"), "mode": r.get("mode", ""),
                            "modele": r.get("model"), "s": round(float(r.get("latency_ms") or 0) / 1000, 1),
                            "tokens_in": r.get("tokens_in"), "cause": cause(r),
                            "principal": str(r.get("primary_error") or "")[:140]}
                           for r in sorted(rows, key=lambda r: -float(r.get("latency_ms") or 0))[:15]]}


def run_questions(n: int, settings=None) -> list[dict]:
    """Batterie de questions à l'assistant normatif, avec la configuration du .env (vraie clé)."""
    import uuid

    from agents import pipeline
    from core.config import get_settings
    from core.llm import LLMClient
    from core.registry import llm_timing
    from rag.service import get_retriever, retrieval_options

    s = settings or get_settings()

    def offset() -> int:
        return s.trace_path.stat().st_size if s.trace_path.exists() else 0

    def timing(cid: str, off: int, t0: float) -> dict:          # même calcul que l'API (D-091)
        total = (time.perf_counter() - t0) * 1000
        t = llm_timing(s.trace_path, cid, off)
        return {**t, "total_ms": round(total, 1), "index_ms": 0.0,
                "autre_ms": round(max(0.0, total - t["modele_ms"]), 1)}
    model = s.rag_embed_model if s.rag_mode in ("dense", "hybrid") else ""
    t_load = time.perf_counter()        # D-094 : chargement de l'index et du modèle d'embedding, mesuré à part
    try:
        r = get_retriever(s.rag_strategy, model, **retrieval_options(s))
        if r.encoder is not None:
            r.encoder.encode(["préchauffage"], is_query=True)
    except Exception as exc:  # noqa: BLE001
        print(f"  index non chargé : {exc}")
    load_s = time.perf_counter() - t_load
    print(f"  chargement de l'index de la norme : {load_s:.1f} s (payé une fois ; l'API le fait au démarrage)")
    out = []
    for q, expected in QUESTIONS[:n]:
        cid, t0, off = f"diag-{uuid.uuid4().hex[:8]}", time.perf_counter(), offset()
        try:
            res = pipeline.ask(q, s, LLMClient(s), lambda: get_retriever(s.rag_strategy, model, **retrieval_options(s)),
                          case_id=cid)
            a = res.answer
            row = {"question": q, "attendu": expected, "intention": res.plan.intent.value, "refus": a.refused,
                   "paragraphes": [c.paragraph_id for c in a.citations],
                   "verdict": res.verdict.status.value if res.verdict else "", "reponse": (a.answer or a.refusal_reason or "")[:220]}
        except Exception as exc:  # noqa: BLE001 — un diagnostic note l'échec et continue
            row = {"question": q, "attendu": expected, "erreur": f"{type(exc).__name__}: {exc}"[:300]}
        row["duree"] = timing(cid, off, t0)
        row["chargement_index_s"] = round(load_s, 1) if not out else 0.0
        out.append(row)
        state = "ERREUR" if "erreur" in row else "refus " if row.get("refus") else "ok    "
        print(f"  {row['duree']['total_ms'] / 1000:6.1f} s  {state}  {q}"
              + (f"\n           {row['erreur'][:160]}" if "erreur" in row else ""))
    return out


def configuration(s) -> list[str]:
    """Réglages qui décident de la latence, sans aucune clé (D-093)."""
    from urllib.parse import urlparse

    host = lambda u: urlparse(u).netloc or "(même que le principal)"   # noqa: E731
    same = bool(s.llm_fallback_model) and (not s.llm_fallback_base_url or host(s.llm_fallback_base_url) == host(s.llm_base_url))
    vision_same = host(s.vision_base_url)
    lines = ["## Configuration (sans clé)", "",
             f"- texte : {host(s.llm_base_url)} — petit {s.llm_model_small or '—'}, grand {s.llm_model_large or '—'}",
             f"- secours texte : {s.llm_fallback_model or 'aucun'} chez {host(s.llm_fallback_base_url) if s.llm_fallback_model else '—'}",
             f"- vision : {s.vision_model} chez {vision_same}, secours {s.vision_fallback_model}",
             f"- délai par appel {s.llm_timeout_s:.0f} s, nouveaux essais {s.llm_max_retries}, bascule si quota > "
             f"{s.llm_quota_max_wait_s:.0f} s, attente totale permise {s.llm_max_wait_s:.0f} s",
             f"- recherche : {s.rag_mode}, {s.rag_embed_model or 'sans embedding'}, agent {'oui' if s.rag_agentic else 'non'}, "
             f"prompt de réponse v{s.rag_prompt_version}"]
    if same:
        lines.append("- **⚠ le secours est chez le même fournisseur que le principal : il subit le même genre de quota. "
                     "Mettre un secours chez un autre fournisseur (voir .env.example).**")
    if not s.llm_fallback_model:
        lines.append("- **⚠ aucun secours : chaque quota épuisé fait attendre.**")
    return lines + [""]


def report(a: dict, qs: list[dict] | None, since: str, settings=None) -> str:
    t = a["total"]
    lines = ["# Diagnostic de la latence et des refus", "", *(configuration(settings) if settings else []),
             f"Traces analysées : {t['appels']} appels au modèle{f' depuis {since}' if since else ''} ; temps total "
             f"{t['total_s']} s ; médiane {t['mediane_s']} s par appel ; 90 % des appels sous {t['p90_s']} s ; "
             f"**{t['lents']} appels de plus de {SLOW_S:.0f} s** ; attente du quota enregistrée {t['quota_s']} s ; "
             f"{t['secours']} passages au modèle de secours ; {t['erreurs']} échecs.", "",
             "## Causes des appels lents", ""]
    lines += [f"- {k} : {v}" for k, v in sorted(a["causes"].items(), key=lambda x: -x[1])] or ["- aucun appel lent"]
    for title, key in (("Par agent", "agents"), ("Par modèle", "modeles")):
        lines += ["", f"## {title}", "", "| | appels | total (s) | médiane (s) | p90 (s) | max (s) | > 20 s | quota (s) | secours | échecs | jetons entrée |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        lines += [f"| {k} | {v['appels']} | {v['total_s']} | {v['mediane_s']} | {v['p90_s']} | {v['max_s']} | {v['lents']} | "
                  f"{v['quota_s']} | {v['secours']} | {v['erreurs']} | {v['tokens_in_moyen']} |" for k, v in a[key].items()]
    lines += ["", "## Requêtes et dossiers les plus longs (temps passé dans le modèle)", "",
              "| identifiant | modèle (s) | appels | détail |", "| --- | ---: | ---: | --- |"]
    lines += [f"| {r['case_id']} | {r['modele_s']} | {r['appels']} | {r['detail']} |" for r in a["requetes"]]
    lines += ["", "## Les 15 appels les plus lents", "",
              "| date | agent | modèle | s | jetons entrée | cause probable | erreur du modèle principal |",
              "| --- | --- | --- | ---: | ---: | --- | --- |"]
    lines += [f"| {r['ts']} | {r['agent']}{' ' + r['mode'] if r['mode'] else ''} | {r['modele']} | {r['s']} | {r['tokens_in']} | "
              f"{r['cause']} | {r['principal'].replace('|', '/')} |" for r in a["plus_lents"]]
    if qs is not None:
        ok = [q for q in qs if "erreur" not in q]
        wrong = [q for q in ok if (q["attendu"] == "norme") == bool(q["refus"])]
        lines += ["", "## Batterie de questions (assistant normatif)", "",
                  f"{len(ok)} questions exécutées ; **{len(wrong)} mal traitées** (refus d'une question sur la norme, ou "
                  f"réponse à une question hors périmètre) ; durée médiane "
                  f"{statistics.median([q['duree']['total_ms'] / 1000 for q in qs]) if qs else 0:.1f} s.", "",
                  "| question | résultat | paragraphes | durée (s) | appels | quota (s) | détail | réponse ou motif du refus |",
                  "| --- | --- | --- | ---: | ---: | ---: | --- | --- |"]
        for q in qs:
            d = q["duree"]
            res = q.get("erreur") or ("refus" if q["refus"] else f"réponse ({q['verdict']})")
            detail = ", ".join(f"{k} {v['appels']}×{v['ms'] / 1000:.1f} s" for k, v in d.get("par_agent", {}).items())
            lines.append(f"| {q['question']} | {res}{' ⚠' if q in wrong else ''} | {', '.join(q.get('paragraphes', []))} | "
                         f"{d['total_ms'] / 1000:.1f} | {d['appels']} | {d['attente_quota_s']} | {detail} | "
                         f"{str(q.get('reponse', '')).replace('|', '/').replace(chr(10), ' ')[:160]} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--traces", type=Path, default=None, help="fichier de traces (défaut : TRACE_PATH du .env)")
    ap.add_argument("--depuis", default="", help="date ISO en UTC : traces depuis cette date (ex. 2026-10-25) ; "
                    "avec --questions et sans --depuis : seulement les traces de cette exécution")
    ap.add_argument("--questions", action="store_true", help="lancer aussi la batterie de questions (appels au modèle)")
    ap.add_argument("-n", type=int, default=len(QUESTIONS), help="nombre de questions de la batterie")
    ap.add_argument("--mesure", action="store_true", help="mode mesure (D-096) : un seul modèle, sans secours ni budget "
                    "d'attente ; pour comparer deux versions de prompt sur la batterie")
    args = ap.parse_args(argv)
    if args.mesure:
        from eval import mode_mesure

        mode_mesure()
    from core.config import get_settings

    path = args.traces or get_settings().trace_path
    qs = None
    start = path.stat().st_size if path.exists() else 0
    if args.questions:
        print(f"Batterie de {min(args.n, len(QUESTIONS))} questions (une par une ; le quota peut imposer des pauses) :")
        qs = run_questions(args.n)
    # sans --depuis, la batterie n'analyse que les traces qu'elle vient d'écrire (la date des traces est en UTC)
    rows = load(path, args.depuis, 0 if (args.depuis or not args.questions) else start)
    a = analyse(rows)
    out = HERE / "diagnostic_report.md"
    out.write_text(report(a, qs, args.depuis, get_settings()), encoding="utf-8")
    t = a["total"]
    print(f"{t['appels']} appels analysés ; {t['lents']} de plus de {SLOW_S:.0f} s ; quota {t['quota_s']} s ; "
          f"secours {t['secours']} ; rapport : {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
