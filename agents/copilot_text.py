"""Réponse du Copilot écrite par le code, en français lisible (D-090).

Utilisée quand le texte du modèle n'a pas passé le contrôle (ou qu'aucun modèle ne répond) : chaque phrase reprend
les montants des outils tels quels, sans JSON, sans nom de champ ni caractère technique. Aucune interprétation
n'est ajoutée : seulement ce que l'outil a calculé, dit avec des mots.
"""

from __future__ import annotations

import re
from typing import Any

LABEL = {
    "niveau_demande": "niveau demandé", "ajustement_risque_exige": "ajustement pour risque exigé",
    "ajustement_risque_retenu": "ajustement pour risque retenu", "csm_initiale": "CSM initiale",
    "perte_initiale": "perte à l'origine", "csm_centrale": "CSM centrale", "perte_centrale": "perte centrale",
    "flux_execution": "flux de trésorerie d'exécution", "valeur_actuelle_primes": "valeur actuelle des primes",
    "valeur_actuelle_sorties": "valeur actuelle des sorties", "ajustement_risque": "ajustement pour risque",
    "meilleure_estimation_bel": "meilleure estimation (BEL)", "provision_non_actualisee": "provision non actualisée",
    "erreur_de_mack": "erreur de prédiction de Mack", "lic": "LIC", "lic_central": "LIC central",
}


def human(key: str) -> str:
    """Nom de champ → mots (« ajustement_risque_exige » → « ajustement pour risque exigé »)."""
    return LABEL.get(key, key.replace("_", " ").replace(" pourcentage ", " en % ").strip())


def _v(r: dict, k: str, default: str = "—") -> str:
    v = r.get(k)
    return default if v in (None, "") else str(v)


def _plain(value: Any) -> str:
    if isinstance(value, bool):
        return "oui" if value else "non"
    if isinstance(value, dict):
        return " ; ".join(f"{human(k)} {_plain(v)}" for k, v in value.items())
    if isinstance(value, list):
        return ", ".join(_plain(v) for v in value[:8])
    return str(value)


def _generic(name: str, r: dict) -> str:
    parts = [f"{human(k)} : {_plain(v)}" for k, v in r.items() if not isinstance(v, list)]
    return f"Résultats ({human(name)}) — " + " ; ".join(parts) + "."


def _portfolio(name: str, r: dict, args: dict) -> str | None:
    if name == "niveau_de_confiance":
        share = (f"{r['ajustement_risque_exige_en_pourcentage_du_bel']} du BEL" if "ajustement_risque_exige_en_pourcentage_du_bel" in r
                 else f"{_v(r, 'ajustement_risque_exige_en_pourcentage_des_sorties')} des sorties actualisées")
        out = (f"À {_v(r, 'niveau_demande')} de confiance, l'ajustement pour risque exigé est de "
               f"{_v(r, 'ajustement_risque_exige')} ({share}), contre {_v(r, 'ajustement_risque_retenu')} retenu dans "
               f"le dossier, ce qui correspond à un niveau de confiance de {_v(r, 'niveau_de_confiance_retenu')}.")
        if "lic" in r:      # dossier LIC
            return out + (f" Le LIC passerait de {_v(r, 'lic_central')} à {_v(r, 'lic')} ({_v(r, 'variation_du_lic')})."
                          if "lic_central" in r else f" Le LIC serait de {_v(r, 'lic')}.")
        effect = (f" Effet sur la marge : la CSM initiale passerait de {_v(r, 'csm_centrale')} à {_v(r, 'csm_initiale')} "
                  f"(variation du résultat à l'origine {_v(r, 'variation_du_resultat_a_l_origine')})"
                  if "csm_centrale" in r else f" La CSM initiale serait de {_v(r, 'csm_initiale')}")
        return out + effect + f" ; le groupe serait {_v(r, 'statut')}. Hypothèse : {_v(r, 'hypothese')}."
    if name == "evaluer_scenario" and "csm_initiale" in r:
        h = r.get("hypotheses") or {}
        hyp = ", ".join(f"{human(k)} {v}" for k, v in h.items() if not re.match(r"^[+-]?0(,0+)? ", str(v)))
        return (f"Dans ce scénario ({hyp or 'hypothèses centrales'}), la CSM initiale est de {_v(r, 'csm_initiale')} "
                f"et la perte à l'origine de {_v(r, 'perte_initiale')} ; le groupe est {_v(r, 'statut')}. Dans le "
                f"scénario central, la CSM est de {_v(r, 'csm_centrale')} (variation du résultat à l'origine "
                f"{_v(r, 'variation_du_resultat_a_l_origine')}).")
    if name == "sensibilites" and "chocs" in r and "lic" not in str(r.get("chocs", [{}])[0].keys()):
        lines = [f"{c['choc']} : variation du résultat à l'origine {c['variation_du_resultat_a_l_origine']}, groupe "
                 f"{c['statut']}{' (bascule)' if c.get('bascule') else ''}" for c in r["chocs"]]
        tail = []
        if r.get("variation_des_sorties_qui_annule_la_marge"):
            tail.append(f"la marge s'annule si les sorties varient de {r['variation_des_sorties_qui_annule_la_marge']}")
        if r.get("translation_des_taux_qui_annule_la_marge"):
            tail.append(f"translation des taux qui annule la marge : {r['translation_des_taux_qui_annule_la_marge']}")
        return "Effet des chocs standard :\n" + "\n".join(f"• {x}" for x in lines) + (
            "\n" + " ; ".join(tail).capitalize() + "." if tail else "")
    if name == "projection_resultat" and "par_periode" in r:
        csm = [x.get("csm_fin_de_periode") for x in r["par_periode"] if x.get("csm_fin_de_periode")]
        return (f"Sur toute la durée, les produits des activités d'assurance totalisent {_v(r, 'total_produits')}, "
                f"le résultat des services {_v(r, 'total_resultat_des_services')} et les charges financières "
                f"{_v(r, 'total_charges_financieres')} ({len(r['par_periode'])} périodes, détail dans le graphe)."
                + (f" La CSM restante passe de {csm[0]} en fin de première période à {csm[-1]} à la fin." if len(csm) > 1 else ""))
    if name == "donnees_du_dossier" and "csm_initiale" in r:
        return (f"Groupe {_v(r, 'groupe')} ({_v(r, 'unite')}, {_v(r, 'periodes')} périodes), {_v(r, 'statut')}. "
                f"Calcul de la CSM : {_v(r, 'calcul_de_la_csm')}. Flux de trésorerie d'exécution "
                f"{_v(r, 'flux_execution')} ; CSM libérée la première période {_v(r, 'liberation_csm_premiere_periode')}"
                + (f", après une désactualisation de {r['desactualisation_csm_premiere_periode']} (la CSM porte intérêt "
                   f"avant d'être libérée)" if r.get("desactualisation_csm_premiere_periode") not in (None, "0,00") else "")
                + ".")
    return None


def _lic(name: str, r: dict, args: dict) -> str | None:
    if name == "donnees_du_dossier" and "lic" in r:
        return (f"Portefeuille {_v(r, 'portefeuille')} ({_v(r, 'unite')}, {_v(r, 'annees_de_survenance')} années de "
                f"survenance, clôture {_v(r, 'date_de_cloture')}). Calcul : {_v(r, 'calcul_du_lic')}. Erreur de "
                f"prédiction de Mack {_v(r, 'erreur_de_mack')} (coefficient de variation "
                f"{_v(r, 'coefficient_de_variation')}), niveau de confiance {_v(r, 'niveau_de_confiance')}, duration "
                f"{_v(r, 'duration_annees')} ans.")
    if name == "evaluer_scenario" and "lic" in r:
        h = r.get("hypotheses") or {}
        return (f"Avec ces hypothèses (taux {_v(h, 'taux')}, niveau de confiance {_v(h, 'niveau_de_confiance')}, facteur "
                f"de queue {_v(h, 'facteur_de_queue')}, volatilité {_v(h, 'volatilite')}), le LIC passe de "
                f"{_v(r, 'lic_central')} à {_v(r, 'lic')} ({_v(r, 'variation_du_lic')}) : BEL "
                f"{_v(r, 'meilleure_estimation_bel')} et ajustement pour risque {_v(r, 'ajustement_risque')}.")
    if name == "sensibilites" and r.get("chocs") and "lic" in r["chocs"][0]:
        lines = [f"{c['choc']} : LIC {c['lic']} ({c['variation_du_lic']})" for c in r["chocs"]]
        lv = [f"{x['niveau']} : {x['ajustement_risque']}" for x in r.get("niveaux_de_confiance", [])]
        return ("Effet des chocs sur le LIC :\n" + "\n".join(f"• {x}" for x in lines)
                + (f"\nAjustement pour risque selon le niveau de confiance : {' ; '.join(lv)}." if lv else ""))
    if name == "par_survenance" and "par_survenance" in r:
        rows = r["par_survenance"]
        if len(rows) == 1:
            x = rows[0]
            return (f"Survenance {x['survenance']} : dernier cumul {x['dernier_cumul']}, ultime {x['ultime']}, "
                    f"provision {x['provision']} ({x['part_de_la_provision']} de la provision totale "
                    f"{_v(r, 'provision_totale')}), déjà payé {x['deja_paye_en_pourcentage_de_l_ultime']} de l'ultime.")
        return (f"La survenance la plus lourde est {_v(r, 'survenance_la_plus_lourde')} sur une provision totale de "
                f"{_v(r, 'provision_totale')} ; le détail par année est dans le graphe et le tableau.")
    if name == "paiements_futurs" and "par_annee" in r:
        first = r["par_annee"][0] if r["par_annee"] else {}
        return (f"Les paiements futurs attendus totalisent {_v(r, 'total_paiements')}, soit une valeur actuelle de "
                f"{_v(r, 'total_valeur_actuelle')} (duration {_v(r, 'duration_annees')} ans) ; la première année, "
                f"{_v(first, 'paiements')} sont attendus. Le calendrier complet est dans le graphe.")
    return None


def _norm(r: dict) -> str:
    if r.get("reponse"):
        return str(r["reponse"])
    why = str(r.get("refus") or "").strip().rstrip(".")
    return ("Je n'ai pas trouvé dans le texte d'IFRS 17 de passage qui réponde précisément à cette question"
            + (f" ({why[0].lower() + why[1:]})" if why else "") + ". Reformulez-la plus précisément, ou posez-la "
            "dans l'Assistant normatif.")


def describe(o: dict) -> str:
    """Une observation d'outil {outil, arguments, resultat} → phrase(s) en français."""
    name, r, args = o.get("outil", ""), o.get("resultat"), o.get("arguments") or {}
    if not isinstance(r, dict):
        return f"{human(name)} : {_plain(r)}"
    if r.get("erreur"):
        return f"L'outil « {human(name)} » n'a pas pu répondre : {r['erreur']}."
    if name == "rechercher_norme":
        return _norm(r)
    if name == "memoire_du_dossier":
        ex = r.get("echanges") or []
        return ("Échanges retrouvés dans la mémoire du dossier :\n" + "\n".join(
            f"• « {e.get('question', '')} » : {e.get('reponse', '')}" for e in ex[:3])) if ex else \
            "Aucun échange antérieur ne correspond dans la mémoire du dossier."
    return _lic(name, r, args) or _portfolio(name, r, args) or _generic(name, r)


def fallback_text(observations: list[dict]) -> str:
    if not observations:
        return "Je n'ai pas pu obtenir de résultat fiable pour cette question."
    return "\n\n".join(describe(o) for o in observations)
