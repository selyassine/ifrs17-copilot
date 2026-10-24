"""Mémoire du Copilot (D-061), selon les quatre types du cours « AI Agents & Agentic AI » :

- **de travail** (contexte) : la question en cours, les résultats d'outils de ce tour — l'état du graphe ;
- **épisodique** : les échanges déjà contrôlés sur ce dossier (table ``memories`` du registre) ; les
  derniers sont placés dans le contexte, les plus anciens sont retrouvés à la demande (outil
  ``memoire_du_dossier``) ;
- **sémantique** : les faits établis sur le dossier par les humains et le registre (statut, décision
  du valideur, commentaire, canal) ;
- **procédurale** : les règles et prompts versionnés (prompts/), inchangés ici.

La mémoire n'est pas le RAG : le RAG cherche dans un texte qui existe sans l'agent (le règlement) ;
la mémoire garde ce que l'agent et l'équipe ont produit sur ce dossier.

Seuls les échanges dont la réponse a passé le contrôle du code (ou a été écrite par le code) sont
mémorisés : un chiffre relu de la mémoire est donc un chiffre déjà vérifié.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

RECENT = 3          # échanges placés dans le contexte à chaque question
RECALL_K = 3        # échanges renvoyés par l'outil de rappel

_STOP = {"avec", "ces", "dans", "des", "elle", "est", "les", "leur", "lui", "mais", "même", "mes", "moi", "mon",
         "nos", "notre", "nous", "par", "pas", "pour", "que", "qui", "ses", "son", "sur", "tes", "toi", "ton", "une",
         "vos", "votre", "vous", "quel", "quelle", "quels", "quelles", "comment", "combien", "quoi", "groupe", "dossier"}


def _tokens(text: str) -> set[str]:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return {w for w in re.findall(r"[a-z0-9§]+", t) if len(w) > 2 and w not in _STOP}


def tool_digest(observations: list[dict], per_tool: int = 8) -> list[dict]:
    """Résultats d'outils à garder en mémoire : nom, arguments, valeurs simples (calculées par le moteur)."""
    out = []
    for o in observations:
        res = o.get("resultat")
        if not isinstance(res, dict) or "erreur" in res or o.get("outil") in ("memoire_du_dossier", "rechercher_norme"):
            continue
        flat = {k: v for k, v in res.items() if isinstance(v, str | int | float) and not isinstance(v, bool)}
        if flat:
            out.append({"outil": o.get("outil"), "arguments": o.get("arguments") or {},
                        "resultats": dict(list(flat.items())[:per_tool])})
    return out


def _digest_text(tools: list) -> str:
    parts = []
    for t in tools or []:
        if isinstance(t, dict) and t.get("resultats"):
            args = ", ".join(f"{k}={v}" for k, v in (t.get("arguments") or {}).items())
            vals = ", ".join(f"{k} {v}" for k, v in t["resultats"].items())
            parts.append(f"{t['outil']}({args}) → {vals}")
    return " ; ".join(parts)


def context_block(recent: list[dict], facts: dict) -> str:
    """Texte placé avant la question : faits du dossier, puis derniers échanges (déjà vérifiés), avec les
    résultats d'outils qui les fondent (chiffres du moteur : réutilisables sans recalcul)."""
    lines = []
    if facts:
        lines.append("Faits établis sur le dossier (registre) :")
        lines += [f"- {k} : {v}" for k, v in facts.items() if v not in (None, "", [])]
    if recent:
        lines.append("Échanges précédents sur ce dossier, déjà contrôlés (du plus ancien au plus récent) :")
        for m in recent:
            lines.append(f"- Q : {m['question']}\n  R : {m['answer']}")
            digest = _digest_text(m.get("tools"))
            if digest:
                lines.append(f"  Résultats d'outils : {digest}")
    return "\n".join(lines)


def case_facts(case: dict | None) -> dict:
    """Mémoire sémantique : ce que le registre sait du dossier (décisions humaines comprises)."""
    if not case:
        return {}
    status = {"note_prete": "note prête", "validation_humaine": "en attente de validation humaine",
              "validee": "validé par un valideur", "rejetee": "rejeté"}.get(case.get("status"), case.get("status"))
    return {"statut": status, "decision_par": case.get("validated_by") or None,
            "commentaire_du_valideur": case.get("decision_comment") or None,
            "controles_non_passes": case.get("controls") if case.get("status") == "validation_humaine" else None}


def recall_with(memories: list[dict], k: int = RECALL_K) -> Callable[[str], dict]:
    """Outil de rappel : les échanges anciens les plus proches du sujet (recouvrement de mots)."""
    def recall(sujet: str) -> dict:
        q = _tokens(sujet)
        scored = sorted(((len(q & _tokens(m["question"] + " " + m["answer"])), i, m) for i, m in enumerate(memories)),
                        key=lambda x: (-x[0], -x[1]))
        hits = [m for s, _, m in scored if s > 0][:k]
        if not hits:
            return {"echanges": [], "remarque": "aucun échange antérieur sur ce sujet"}
        return {"echanges": [{"date": m["at"][:16].replace("T", " "), "question": m["question"], "reponse": m["answer"],
                              **({"resultats_outils": _digest_text(m.get("tools"))} if _digest_text(m.get("tools")) else {})}
                             for m in hits]}
    return recall
