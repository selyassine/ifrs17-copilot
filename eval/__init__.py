"""Évaluations. Chaque mesure tourne en « mode mesure » (D-096) : un seul modèle, attente du quota sans limite.

Les réglages de production (secours sans attente D-092, budget d'attente D-093) servent la latence du site ; dans une
mesure ils faussent la comparaison : une question échoue sur le budget, ou elle est répondue par le modèle de secours
au lieu du modèle mesuré (mesure du 25/10 : v2 sur les jeux de test, 8 questions perdues, réponses de secours mêlées).
"""

from __future__ import annotations

import os

MESURE = {"LLM_FALLBACK_MODEL": "", "LLM_FALLBACK_BASE_URL": "", "LLM_FALLBACK_API_KEY": "",
          "LLM_MAX_WAIT_S": "-1", "LLM_QUOTA_MAX_WAIT_S": "-1"}


def mode_mesure() -> None:
    """À appeler en tête de chaque ``main()`` d'évaluation, avant tout ``get_settings()``. Les variables d'environnement
    l'emportent sur le .env (python-dotenv ne les écrase pas). ``IFRS17_MESURE_PROD=1`` garde les réglages de
    production (pour mesurer la latence du site, comme le fait eval.diagnostic)."""
    if os.environ.get("IFRS17_MESURE_PROD") == "1":
        return
    os.environ.update(MESURE)
    from core.config import get_settings

    get_settings.cache_clear()
    print("Mode mesure : un seul modèle (pas de secours), attente du quota sans limite (D-096).")
