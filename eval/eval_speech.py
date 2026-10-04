"""Évaluation de la question vocale : transcription Whisper (Groq), avec et sans vocabulaire IFRS 17.

Préparation (une fois) : chaque membre de l'équipe enregistre les phrases de
eval/speech_cases.jsonl avec son téléphone (dictaphone), à voix naturelle, et dépose les fichiers
dans data/audio/ (v01.m4a … v08.m4a ; mp3, wav, ogg acceptés : changer l'extension dans le
fichier ou nommer le fichier pareil). Les voix ne sont jamais versionnées (data/ est hors Git).

    python -m eval.eval_speech

Mesures, pour chaque version (avec / sans vocabulaire) :
    WER                 taux d'erreur sur les mots (0 = transcription parfaite)
    termes reconnus     sigles et termes IFRS 17 correctement écrits (CSM, B119, PAA…)
    routage             la transcription est-elle classée « question sur la norme » par le routeur
                        configuré dans .env (ROUTER_MODE), comme en production ?
"""

from __future__ import annotations

import json
import statistics
import time
from datetime import datetime
from pathlib import Path

from agents.router import route_heuristic, route_llm
from agents.schemas import Intent
from core.config import ROOT, get_settings
from core.llm import LLMClient, LLMError
from multimodal.speech import terms_found, transcribe, wer

HERE = Path(__file__).parent


def resolve(path: str) -> Path | None:
    """Accepte v01.m4a, v01.mp3, v01.wav… quel que soit le format enregistré."""
    p = ROOT / path
    if p.exists():
        return p
    for ext in (".m4a", ".mp3", ".wav", ".ogg", ".webm", ".flac", ".mp4"):
        q = p.with_suffix(ext)
        if q.exists():
            return q
    return None


def main() -> None:
    settings = get_settings()
    if settings.llm_provider == "fake":
        raise SystemExit("LLM_PROVIDER=fake : configurer Groq dans .env avant cette évaluation.")
    cases = [json.loads(line) for line in (HERE / "speech_cases.jsonl").read_text(encoding="utf-8").splitlines()
             if line.strip()]
    present = [(c, resolve(c["fichier"])) for c in cases]
    missing = [c["id"] for c, p in present if p is None]
    if missing:
        print(f"Fichiers absents (ignorés) : {', '.join(missing)} — à enregistrer dans data/audio/")
    present = [(c, p) for c, p in present if p is not None]
    if not present:
        raise SystemExit("Aucun enregistrement dans data/audio/ : voir l'en-tête de ce fichier.")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    client = LLMClient(settings)

    def route(text: str) -> Intent:
        if settings.router_mode == "llm":
            return route_llm(text, False, client=client, case_id=f"speech-{stamp}").intent
        return route_heuristic(text, False).intent

    rows = []
    for c, path in present:
        row = {"id": c["id"], "fichier": path.name, "texte": c["texte"]}
        for label, vocab in (("avec_vocabulaire", True), ("sans_vocabulaire", False)):
            try:
                tr = transcribe(path.read_bytes(), path.name, settings, with_vocabulary=vocab)
            except LLMError as exc:
                print(f"{c['id']} {label} : ERREUR {str(exc)[:120]}")
                continue
            found = terms_found(c["termes"], tr.text)
            intent = route(tr.text)
            row[label] = {"transcription": tr.text, "wer": round(wer(c["texte"], tr.text), 3),
                          "termes": f"{len(found)}/{len(c['termes'])}", "termes_ok": len(found) == len(c["termes"]),
                          "routage_ok": intent == Intent.NORM_QUESTION, "duree_s": tr.duration_s}
            print(f"{c['id']} {label:17} WER {row[label]['wer']:.2f}  termes {row[label]['termes']}  « {tr.text[:70]} »")
            time.sleep(3)
        rows.append(row)

    agg = {}
    for label in ("avec_vocabulaire", "sans_vocabulaire"):
        done = [r[label] for r in rows if label in r]
        if done:
            agg[label] = {"enregistrements": len(done),
                          "wer_moyen": round(statistics.mean(d["wer"] for d in done), 3),
                          "termes_tous_reconnus": f"{sum(d['termes_ok'] for d in done)}/{len(done)}",
                          "routage_correct": f"{sum(d['routage_ok'] for d in done)}/{len(done)}"}
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    (out / f"speech_{stamp}.json").write_text(json.dumps({"date": stamp, "modele": settings.speech_model,
                                                          "agregats": agg, "cas": rows},
                                                         ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# Question vocale — {settings.speech_model}", "",
             f"Généré le {stamp} par `python -m eval.eval_speech` ({len(rows)} enregistrements, "
             f"routeur : {settings.router_mode}).", "",
             "| Version | WER moyen | Termes tous reconnus | Routage correct |", "| --- | --- | --- | --- |"]
    lines += [f"| {k.replace('_', ' ')} | {v['wer_moyen']} | {v['termes_tous_reconnus']} | {v['routage_correct']} |"
              for k, v in agg.items()]
    lines += ["", "| Id | Phrase lue | Avec vocabulaire | Sans vocabulaire |", "| --- | --- | --- | --- |"]
    for r in rows:
        a = r.get("avec_vocabulaire", {})
        b = r.get("sans_vocabulaire", {})
        lines.append(f"| {r['id']} | {r['texte']} | {a.get('transcription', '—')} (WER {a.get('wer', '—')}) | "
                     f"{b.get('transcription', '—')} (WER {b.get('wer', '—')}) |")
    (HERE / "speech_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n== Résultats")
    for k, v in agg.items():
        print(f"  {k:18} {v}")
    print("\n→ eval/speech_report.md")


if __name__ == "__main__":
    main()
