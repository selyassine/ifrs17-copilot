"""Génère le livrable prompt_library.md à partir des fiches YAML de prompts/ (une seule source).

    python -m core.prompt_library          # → prompt_library.md à la racine du dépôt
"""

from __future__ import annotations

from collections import defaultdict

from core.config import ROOT
from core.prompts import PromptSpec, all_prompt_files, load_prompt_file

OUT = ROOT / "prompt_library.md"
AGENT_ORDER = ["router", "extracteur", "chercheur_rag", "verificateur", "redacteur", "copilote"]
AGENT_LABEL = {"router": "Routeur", "extracteur": "Extracteur multimodal", "chercheur_rag": "Chercheur RAG",
               "verificateur": "Vérificateur (LLM-juge)", "redacteur": "Rédacteur",
               "copilote": "Copilot (agent à outils)"}


def _scores(spec: PromptSpec) -> str:
    if not spec.eval or not spec.eval.scores:
        return "—"
    return ", ".join(f"{k} : {v}" for k, v in spec.eval.scores.items())


def render(specs: list[PromptSpec]) -> str:
    by_agent: dict[str, list[PromptSpec]] = defaultdict(list)
    for s in specs:
        by_agent[s.agent].append(s)
    agents = [a for a in AGENT_ORDER if a in by_agent] + sorted(set(by_agent) - set(AGENT_ORDER))
    techniques = sorted({t for s in specs for t in s.techniques})
    lines = [
        "# Bibliothèque de prompts — IFRS 17 Copilot", "",
        "Fichier généré par `python -m core.prompt_library` à partir des fiches `prompts/<agent>/<id>.vN.yaml` "
        "(ne pas modifier à la main). Méthode : une version n'est jamais modifiée ; chaque nouvelle version change "
        "une seule chose, motivée par des échecs observés, et elle est mesurée sur le même jeu de test que la précédente.", "",
        f"{len(specs)} fiches, {len(agents)} agents, {len(techniques)} techniques : {', '.join(techniques)}.", "",
        "## Vue d'ensemble", "",
        "| Agent | Prompt | Version | Techniques | Modèle | Scores mesurés |", "| --- | --- | --- | --- | --- | --- |",
    ]
    for a in agents:
        for s in sorted(by_agent[a], key=lambda x: (x.id, x.version)):
            lines.append(f"| {AGENT_LABEL.get(a, a)} | `{s.id}` | v{s.version} | {', '.join(s.techniques)} | "
                         f"{s.params.model}, t={s.params.temperature} | {_scores(s)} |")
    for a in agents:
        lines += ["", f"## {AGENT_LABEL.get(a, a)}"]
        for s in sorted(by_agent[a], key=lambda x: (x.id, x.version)):
            lines += ["", f"### `{s.id}` v{s.version}", "", f"**Rôle.** {s.role}", "",
                      f"**Techniques.** {', '.join(s.techniques)} · **Paramètres.** modèle {s.params.model}, "
                      f"température {s.params.temperature}, {s.params.max_tokens} tokens max · "
                      f"**Sortie.** {s.output_schema or 'texte libre vérifié par le code'}", "",
                      f"**Ce qui a changé.** {s.changes or '—'}", ""]
            if s.failures_observed:
                lines += ["**Échecs observés (motivation de la version suivante ou de celle-ci).**", ""]
                lines += [f"- {f}" for f in s.failures_observed] + [""]
            if s.eval:
                lines += [f"**Évaluation.** jeu `{s.eval.test_set}` · mesure : {s.eval.metric} · scores : {_scores(s)}"]
                if s.eval.notes:
                    lines += ["", f"> {s.eval.notes}"]
                lines += [""]
            lines += ["<details><summary>Prompt système et gabarit</summary>", "", "```text", s.system.rstrip(),
                      "```", "", "```text", s.template.rstrip(), "```", "", "</details>"]
    return "\n".join(lines) + "\n"


def main() -> None:
    specs = [load_prompt_file(p) for p in all_prompt_files()]
    OUT.write_text(render(specs), encoding="utf-8")
    print(f"{len(specs)} fiches → {OUT}")


if __name__ == "__main__":
    main()
