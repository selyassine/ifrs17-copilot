"""Niveau 4 de la campagne (D-070) : robustesse de l'API en marche, comme en production.

L'API doit tourner (`.\\make.ps1 serve`). Le script envoie de vrais appels HTTP et vérifie que chaque cas
difficile reçoit une réponse claire (bon code HTTP, message lisible), jamais un plantage ni un silence.

    python -m eval.eval_robustesse                       # tests rapides, sans LLM
    python -m eval.eval_robustesse --dossiers 5          # + 5 dossiers à la suite (quota Groq : ~12 appels chacun)
    python -m eval.eval_robustesse --dossiers 5 --paralleles 3

Les cas qui demandent d'arrêter un service (API, n8n, quota) sont listés à la fin : à faire à la main,
résultat à noter dans le rapport (eval/robustesse_report.md).
"""

from __future__ import annotations

import argparse
import statistics
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx

from core.config import ROOT, get_settings

HERE = Path(__file__).parent
SAMPLES = [ROOT / "data" / "synth" / f"ext{i:02d}.pdf" for i in range(1, 16)]
MANUEL = [
    ("API arrêtée pendant qu'un e-mail arrive", "n8n envoie « votre dossier n'a pas pu être traité » au déposant et l'alerte à l'équipe ; "
     "le contrôle de santé envoie « API injoignable » dans les 15 minutes, puis « API rétablie »"),
    ("Clé Groq invalide ou quota épuisé (LLM_API_KEY faux dans .env, API relancée)",
     "réponse 502 « LLM indisponible : … » ; dossier inscrit en « erreur » au registre ; e-mail d'incident"),
    ("E-mail « IFRS17 » sans pièce jointe", "réponse « aucun document joint » au déposant"),
    ("E-mail avec 3 PDF", "3 dossiers distincts au registre ; 3 notes ou 3 formulaires de validation indépendants"),
    ("Formulaire n8n avec une image .png", "dossier traité en mode vision"),
    ("Valideur qui saisit « abc » dans une liste du formulaire", "e-mail « échec du dossier … n'est pas un nombre », aucune note fausse"),
    ("n8n arrêté pendant qu'un dossier est analysé sur le site", "le site affiche « e-mail non envoyé » ; le dossier reste au registre"),
]


def check(name: str, ok: bool, detail: str, rows: list) -> None:
    rows.append((name, "OK" if ok else "ÉCHEC", detail))
    print(f"  {'OK   ' if ok else 'ÉCHEC'} {name} — {detail}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--dossiers", type=int, default=0, help="dossiers complets envoyés l'un après l'autre")
    ap.add_argument("--paralleles", type=int, default=0, help="dossiers envoyés en même temps")
    args = ap.parse_args()
    token = get_settings().api_token
    head = {"X-API-Token": token} if token else {}
    rows: list[tuple[str, str, str]] = []
    timings: list[float] = []
    with httpx.Client(base_url=args.api, timeout=600, trust_env=False) as c:
        try:
            r = c.get("/health")
        except httpx.HTTPError as exc:
            raise SystemExit(f"API injoignable sur {args.api} ({type(exc).__name__}) : lancer .\\make.ps1 serve") from exc
        check("santé", r.status_code == 200, f"{r.status_code} {r.json().get('status')}", rows)
        if token:
            r = c.post("/v1/case", files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")})
            check("sans jeton", r.status_code == 401, f"{r.status_code} (attendu 401)", rows)
        r = c.post("/v1/case", headers=head, files={"file": ("note.txt", b"bonjour", "text/plain")})
        check("fichier texte", r.status_code == 415, f"{r.status_code} {r.json().get('detail', '')[:60]}", rows)
        r = c.post("/v1/case", headers=head, files={"file": ("vide.pdf", b"", "application/pdf")})
        check("fichier vide", r.status_code in (415, 422), f"{r.status_code} {str(r.json().get('detail', ''))[:60]}", rows)
        r = c.post("/v1/case", headers=head, files={"file": ("gros.pdf", b"%PDF-1.4\n" + b"0" * (10 * 1024 * 1024 + 10), "application/pdf")})
        check("fichier de plus de 10 Mo", r.status_code == 413, f"{r.status_code} {str(r.json().get('detail', ''))[:60]}", rows)
        r = c.post("/v1/case", headers=head, files={"file": ("casse.pdf", b"%PDF-1.4\n%%EOF corrompu", "application/pdf")})
        check("PDF corrompu", r.status_code == 422, f"{r.status_code} {str(r.json().get('detail', ''))[:60]}", rows)
        r = c.get("/v1/cases/inexistant/note.pdf", headers=head)
        check("note d'un dossier inconnu", r.status_code == 404, f"{r.status_code}", rows)
        r = c.get("/v1/audit/verify", headers=head)
        check("piste d'audit intacte", r.status_code == 200 and r.json().get("intacte") is True, f"{r.status_code} {r.json()}"[:90], rows)

        docs = [p for p in SAMPLES if p.exists()]
        for k, pdf in enumerate(docs[: args.dossiers]):
            t0 = time.perf_counter()
            r = c.post("/v1/case", headers=head, data={"source": "api", "submitter": "test-robustesse"},
                       files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")})
            timings.append(time.perf_counter() - t0)
            status = r.json().get("status") if r.status_code == 200 else str(r.json().get("detail", ""))[:60]
            check(f"dossier {k + 1} à la suite ({pdf.name})", r.status_code == 200, f"{r.status_code} {status}, {timings[-1]:.0f} s", rows)

    if args.paralleles:
        results: list[tuple[int, float]] = []

        def send(pdf: Path) -> None:
            t0 = time.perf_counter()
            with httpx.Client(base_url=args.api, timeout=900, trust_env=False) as cc:
                r = cc.post("/v1/case", headers=head, data={"source": "api", "submitter": "test-parallele"},
                            files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")})
            results.append((r.status_code, time.perf_counter() - t0))
        threads = [threading.Thread(target=send, args=(p,)) for p in [p for p in SAMPLES if p.exists()][5:5 + args.paralleles]]
        t0 = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        total = time.perf_counter() - t0
        check(f"{len(threads)} dossiers en même temps", all(s == 200 for s, _ in results),
              f"codes {[s for s, _ in results]}, durée totale {total:.0f} s", rows)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    lines = ["# Robustesse de l'API (niveau 4)", "", f"Généré le {stamp} par `python -m eval.eval_robustesse`.", "",
             "| Test | Résultat | Détail |", "| --- | --- | --- |"] + [f"| {a} | {b} | {c} |" for a, b, c in rows]
    if timings:
        lines += ["", f"Durée d'un dossier complet : médiane {statistics.median(timings):.0f} s, maximum {max(timings):.0f} s "
                  f"(critère : moins de 180 s)."]
    lines += ["", "## Tests à faire à la main (noter le résultat)", "", "| Situation | Comportement attendu | Constaté |", "| --- | --- | --- |"]
    lines += [f"| {a} | {b} | à remplir |" for a, b in MANUEL]
    (HERE / "robustesse_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\nÀ faire à la main :")
    for a, b in MANUEL:
        print(f"  - {a} → {b}")
    print("\n→ eval/robustesse_report.md")


if __name__ == "__main__":
    main()
