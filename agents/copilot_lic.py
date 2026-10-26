"""Outils du Copilot pour un dossier de sinistres survenus (LIC, D-087).

Même agent, même graphe, mêmes contrôles que pour un état de portefeuille (``agents/copilot.py``) : seuls les outils
et le prompt changent (``copilot_lic``). Chaque outil appelle le moteur ``engine/lic.py`` ; aucun n'écrit.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import Field

from agents.copilot import LevelArgs, NoArgs, NormArgs, SujetArgs, Tool, _Args
from agents.schemas import TriangleData
from agents.writer import fr, pct, signed
from engine.lic import bornhuetter_ferguson, compute_lic, confidence_level, ra_at_level

UNIT = {1: "", 1_000: "milliers de ", 1_000_000: "millions de "}


class LicScenarioArgs(_Args):
    taux_pb: float = Field(0.0, ge=-500, le=500, description="translation des taux, en points de base, ex. 100")
    niveau: float = Field(0.0, ge=0, lt=100, description="niveau de confiance du RA en %, ex. 90 (0 = celui du dossier)")
    facteur_queue: float = Field(1.0, ge=1.0, le=3.0, description="facteur de queue, ex. 1,02 (1 = aucun)")
    volatilite_pct: float = Field(0.0, ge=0, le=300, description="coefficient de variation imposé en %, ex. 20 (0 = Mack)")


class SurvenanceArgs(_Args):
    survenance: str = Field("", max_length=10, description="année de survenance, ex. 1995 (vide = toutes)")


class LicTools:
    """Outils du Copilot pour un triangle de sinistres survenus."""

    def __init__(self, triangle: TriangleData, default_level: float = 0.75,
                 norm_search: Callable[[str], dict] | None = None, recall: Callable[[str], dict] | None = None):
        self.t = triangle
        self.level = triangle.confidence_level or default_level
        self.norm_search = norm_search
        self.recall = recall
        self.r = self._lic()
        self.cv = self.r.cv
        self.n_periods = triangle.n_years
        self.unit = f"{UNIT[triangle.unit_multiplier]}{triangle.currency}"
        self.currency = triangle.currency

    def _lic(self, shift: float = 0.0, level: float | None = None, tail: float | None = None, cv: float | None = None):
        t = self.t
        rates = t.discount_rates if isinstance(t.discount_rates, list) else [t.discount_rates]
        return compute_lic(t.cumulative_triangle(), [r + shift for r in rates], level or self.level,
                           cv=cv if cv is not None else t.declared_cv, tail=tail or t.tail_factor,
                           labels=t.origin_years, premiums=t.premiums)

    def tools(self) -> dict[str, Tool]:
        out = [
            Tool("donnees_du_dossier", "Résumé du dossier de sinistres survenus : provision non actualisée, meilleure "
                 "estimation actualisée (BEL), erreur de Mack, ajustement pour risque, LIC, niveau de confiance, et le "
                 "détail du calcul du LIC.",
                 NoArgs, self.dossier),
            Tool("evaluer_scenario", "Recalcule le LIC avec des hypothèses modifiées : translation des taux, niveau "
                 "de confiance, facteur de queue, volatilité imposée ; compare au scénario central.",
                 LicScenarioArgs, self.scenario),
            Tool("sensibilites", "Effet sur le LIC de chocs standard : taux ±1 point, facteur de queue 1,01 et 1,02, "
                 "niveaux de confiance usuels.", NoArgs, self.sensitivities),
            Tool("niveau_de_confiance", "Ajustement pour risque et LIC à un niveau de confiance donné ; niveau du RA "
                 "retenu.", LevelArgs, self.confidence),
            Tool("par_survenance", "Détail par année de survenance : dernier cumul, ultime, provision, erreur de "
                 "Mack, S/P ultime.", SurvenanceArgs, self.by_year),
            Tool("paiements_futurs", "Paiements futurs attendus par année calendaire, taux, valeur actuelle, "
                 "duration.", NoArgs, self.cash_flows),
        ]
        if self.norm_search is not None:
            out.append(Tool("rechercher_norme", "Cherche dans le texte officiel d'IFRS 17 et renvoie une réponse "
                            "vérifiée avec les paragraphes cités.", NormArgs, self.norm))
        if self.recall is not None:
            out.append(Tool("memoire_du_dossier", "Retrouve les questions déjà posées sur ce dossier et leurs réponses "
                            "vérifiées.", SujetArgs, self.memory))
        return {t.name: t for t in out}

    # -------------------------------------------------------------- outils
    def dossier(self) -> dict:
        r, t = self.r, self.t
        return {"portefeuille": t.portfolio_id, "unite": self.unit, "annees_de_survenance": t.n_years,
                "nature_du_dossier": "passif au titre des sinistres survenus (LIC) : provision pour les sinistres déjà "
                                     "survenus (Chain Ladder, Mack), sans CSM",
                "date_de_cloture": t.valuation_date or "non indiquée",
                "provision_non_actualisee": fr(r.reserve), "meilleure_estimation_bel": fr(r.bel),
                "effet_actualisation": fr(r.discount_effect), "erreur_de_mack": fr(r.mack_se),
                "coefficient_de_variation": pct(r.cv, 1), "niveau_de_confiance": pct(r.level, 0),
                "ajustement_risque": fr(r.risk_adjustment), "lic": fr(r.lic), "duration_annees": fr(r.duration),
                "calcul_du_lic": (f"provision non actualisée {fr(r.reserve)} {'−' if r.discount_effect >= 0 else '+'} "
                                  f"effet de l'actualisation {fr(abs(r.discount_effect))} = BEL {fr(r.bel)} ; "
                                  f"BEL {fr(r.bel)} + ajustement pour risque {fr(r.risk_adjustment)} = LIC {fr(r.lic)}"),
                **({"provision_bornhuetter_ferguson_controle": fr(bf.total),
                    "s_p_a_priori_bf": pct(bf.prior_loss_ratio, 1)} if (bf := bornhuetter_ferguson(r)) else {})}

    def scenario(self, taux_pb: float = 0.0, niveau: float = 0.0, facteur_queue: float = 1.0,
                 volatilite_pct: float = 0.0) -> dict:
        if niveau and not 50 < niveau < 100:
            return {"erreur": "niveau de confiance entre 50 et 100 %"}
        s = self._lic(taux_pb / 10_000, niveau / 100 if niveau else None,
                      facteur_queue if facteur_queue > 1 else None, volatilite_pct / 100 if volatilite_pct else None)
        return {"hypotheses": {"taux": f"{signed(taux_pb, 0)} pb",
                               "niveau_de_confiance": pct(s.level, 0), "facteur_de_queue": fr(s.tail, 4),
                               "volatilite": pct(s.cv, 1)},
                "provision_non_actualisee": fr(s.reserve), "meilleure_estimation_bel": fr(s.bel),
                "ajustement_risque": fr(s.risk_adjustment), "lic": fr(s.lic),
                "variation_du_lic": signed(s.lic - self.r.lic), "lic_central": fr(self.r.lic)}

    def sensitivities(self) -> dict:
        r = self.r
        rows = [{"choc": f"Taux {'+' if sh > 0 else '−'}{fr(abs(sh), 0)} point", "bel": fr(b), "lic": fr(lic),
                 "variation_du_lic": signed(lic - r.lic)} for sh, b, lic in r.rate_shocks]
        for q in (1.01, 1.02):
            s = self._lic(tail=q)
            rows.append({"choc": f"Facteur de queue {fr(q, 2)}", "bel": fr(s.bel), "lic": fr(s.lic),
                         "variation_du_lic": signed(s.lic - r.lic)})
        return {"chocs": rows,
                "niveaux_de_confiance": [{"niveau": pct(lv, 1), "ajustement_risque": fr(ra), "lic": fr(lic)}
                                         for lv, ra, lic in r.levels]}

    def confidence(self, niveau: float) -> dict:
        r = self.r
        ra = ra_at_level(r.bel, r.cv, niveau / 100)
        return {"niveau_demande": f"{fr(niveau, 1)} %", "ajustement_risque_exige": fr(ra),
                "ajustement_risque_exige_en_pourcentage_du_bel": pct(ra / r.bel) if r.bel else "0,00 %",
                "lic": fr(r.bel + ra), "lic_central": fr(r.lic), "variation_du_lic": signed(r.bel + ra - r.lic),
                "ajustement_risque_retenu": fr(r.risk_adjustment),
                "niveau_de_confiance_retenu": pct(confidence_level(r.bel, r.cv, r.risk_adjustment), 1),
                "hypothese": f"loi lognormale, coefficient de variation {pct(r.cv, 1)} ({r.cv_source})"}

    def by_year(self, survenance: str = "") -> dict:
        rows = [x for x in self.r.rows if not survenance or x.label == survenance.strip()]
        if not rows:
            return {"erreur": f"année de survenance inconnue : {survenance} ; années : "
                              f"{', '.join(x.label for x in self.r.rows)}"}
        out = [{"survenance": x.label, "dernier_cumul": fr(x.latest), "facteur_restant": fr(x.development, 4),
                "deja_paye_en_pourcentage_de_l_ultime": pct(x.latest / x.ultimate, 1) if x.ultimate else "—",
                "ultime": fr(x.ultimate),
                "provision": fr(x.reserve), "erreur_de_mack": fr(x.mack_se),
                "part_de_la_provision": pct(x.reserve / self.r.reserve, 1) if self.r.reserve else "0,00 %",
                **({"s_p_ultime": pct(x.loss_ratio, 1)} if x.loss_ratio is not None else {})} for x in rows]
        res = {"par_survenance": out, "provision_totale": fr(self.r.reserve)}
        if len(out) == 1:
            res |= {"provision": out[0]["provision"], "part_de_la_provision": out[0]["part_de_la_provision"]}
        else:
            top = max(rows, key=lambda x: x.reserve)
            res["survenance_la_plus_lourde"] = f"{top.label} ({fr(top.reserve)}, {pct(top.reserve / self.r.reserve, 1)})"
        return res

    def cash_flows(self) -> dict:
        r = self.r
        return {"par_annee": [{"annee": k + 1, "paiements": fr(c), "taux_spot": pct(r.rates[k], 3),
                               "valeur_actuelle": fr(c * r.discount[k])} for k, c in enumerate(r.cash_flows)],
                "total_paiements": fr(sum(r.cash_flows)), "total_valeur_actuelle": fr(r.bel),
                "duration_annees": fr(r.duration)}

    def memory(self, sujet: str) -> dict:
        return self.recall(sujet) if self.recall else {"echanges": []}

    def norm(self, question: str) -> dict:
        return self.norm_search(question) if self.norm_search else {"erreur": "norme non indexée"}
