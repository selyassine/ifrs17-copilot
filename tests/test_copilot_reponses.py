"""Réponses du Copilot lisibles et rapides (D-090) : texte du code sans JSON, raccourci pour une question sur la
règle seule, effet sur la marge calculé par l'outil, calcul de la CSM et du LIC, graphes gardés en mémoire."""

import json
import re

from agents.copilot import Copilot, DossierTools, csm_formula, pure_norm_question
from agents.copilot_text import describe, fallback_text
from agents.schemas import PortfolioData
from agents.writer import fr
from core.registry import Registry
from engine.csm import compute_csm
from tests.test_copilot import P, scripted

TECH = re.compile(r"[{}\"]|\w_\w")
NORM_OK = {"reponse": "La CSM représente le profit non acquis [§38].", "verdict": "ok",
           "citations": [{"paragraphe": "§38", "extrait": "profit non acquis"}]}
NORM_REFUS = {"reponse": None, "refus": "Les extraits ne contiennent pas les étapes de calcul."}


def tools(norm):
    return DossierTools(P, norm_search=lambda q: dict(norm))


def test_reponse_du_code_sans_json_ni_nom_de_champ():
    d = DossierTools(P)
    for name, run in [("niveau_de_confiance", lambda: d.confidence(90)), ("evaluer_scenario", lambda: d.scenario(15)),
                      ("sensibilites", d.sensitivities), ("projection_resultat", d.projection),
                      ("donnees_du_dossier", d.dossier)]:
        text = describe({"outil": name, "arguments": {}, "resultat": run()})
        assert text and not TECH.search(text), (name, text)
    text = fallback_text([{"outil": "rechercher_norme", "resultat": NORM_REFUS}])
    assert "Je n'ai pas trouvé" in text and not TECH.search(text)


def test_effet_sur_la_marge_calcule_par_l_outil():
    """Exemple du 25/10 (PREV-2023-A, 90 %) : le modèle soustrayait lui-même → réponse rejetée. L'outil donne l'écart."""
    r, c = compute_csm(P), DossierTools(P).confidence(90)
    def f(x):
        return float(c[x].replace(" ", "").replace(",", "."))
    assert c["csm_centrale"] == fr(r.initial_csm)
    expected = (f("csm_initiale") - f("perte_initiale")) - (r.initial_csm - r.initial_loss_component)
    assert c["variation_du_resultat_a_l_origine"].lstrip("+") == fr(expected)


def test_calcul_de_la_csm_juste():
    for p in (P, PortfolioData(group_id="G2", premiums=[100, 0, 0], outflows=[40, 40, 40], coverage_units=[1, 1, 1],
                               discount_rates=[0.02, 0.02, 0.02], risk_adjustment_pct=0.05)):
        r = compute_csm(p)
        f = csm_formula(r)
        nums = [float(x.replace(" ", "").replace(",", ".")) for x in re.findall(r"-?\d[\d ]*,\d\d", f)]
        primes, sorties, ra = nums[0], nums[1], nums[2]
        assert abs(primes - sorties - ra - (r.initial_csm - r.initial_loss_component)) < 0.02, f
        assert ("CSM " + fr(r.initial_csm)) in f if not r.onerous else "déficitaire" in f


def test_question_sur_la_regle_seule():
    assert pure_norm_question("c quoi CSM") and pure_norm_question("comment calculer le CSM")
    assert not pure_norm_question("Quel ajustement pour risque à 90 % de confiance ?")
    assert not pure_norm_question("Que dit la norme si le groupe devient déficitaire ?")


def test_raccourci_norme_un_seul_appel(tmp_path):
    turn = {"action": "outil", "outil": "rechercher_norme", "arguments": {"question": "c quoi la CSM"}}
    res = Copilot(tools(NORM_OK), scripted(tmp_path, [turn])).ask("c quoi la CSM ?")
    assert res.llm_calls == 1 and res.source == "llm" and res.answer == NORM_OK["reponse"]


def test_refus_de_la_norme_et_calcul_du_dossier(tmp_path):
    turn = {"action": "outil", "outil": "rechercher_norme", "arguments": {"question": "comment calculer la CSM"}}
    res = Copilot(tools(NORM_REFUS), scripted(tmp_path, [turn])).ask("comment calculer le CSM")
    assert res.llm_calls == 1 and res.source == "code"
    assert "Calcul de la CSM" in res.answer and fr(compute_csm(P).initial_csm) in res.answer
    assert [o["outil"] for o in res.observations] == ["donnees_du_dossier", "rechercher_norme"]
    assert not TECH.search(res.answer)


def test_question_chiffree_pas_de_raccourci(tmp_path):
    """Une question qui demande aussi un chiffre du dossier repasse par le modèle après la norme."""
    turns = [{"action": "outil", "outil": "rechercher_norme", "arguments": {"question": "groupe déficitaire"}},
             {"action": "outil", "outil": "donnees_du_dossier", "arguments": {}},
             lambda m: {"action": "repondre", "reponse": f"La CSM est de {fr(compute_csm(P).initial_csm)} [§38]."}]
    res = Copilot(tools(NORM_OK), scripted(tmp_path, turns)).ask("Que dit la norme si le groupe devient déficitaire ?")
    assert res.llm_calls == 3 and res.source == "llm"


def test_repli_garde_les_resultats_pour_le_graphe(tmp_path):
    bad = {"action": "repondre", "reponse": "La marge disparaît avec 7,77 points."}
    res = Copilot(DossierTools(P), scripted(tmp_path, [bad, bad])).ask("Quelle translation des taux annule la marge ?")
    assert res.source == "code" and res.observations and res.observations[0]["resultat"]["chocs"]


def test_memoire_garde_les_resultats_d_outils(tmp_path):
    db = tmp_path / "r.sqlite"
    reg = Registry(db)
    obs = [{"outil": "sensibilites", "arguments": {}, "resultat": DossierTools(P).sensitivities()}]
    reg.add_memory("c1", "ines", "Quelle hypothèse pèse le plus ?", "Les sinistres.", "llm", [], [], obs)
    assert Registry(db).memories("c1")[0]["observations"] == json.loads(json.dumps(obs))


def test_ancienne_base_migree(tmp_path):
    """Une base créée avant D-090 (sans colonne observations) s'ouvre et garde ses échanges."""
    import sqlite3

    db = tmp_path / "old.sqlite"
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL, at TEXT NOT "
                      "NULL, actor TEXT NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL, source TEXT NOT NULL, "
                      "tools TEXT NOT NULL DEFAULT '[]', refs TEXT NOT NULL DEFAULT '[]');"
                      "INSERT INTO memories (case_id, at, actor, question, answer, source) "
                      "VALUES ('c1', '2026-10-24', 'ines', 'q', 'r', 'llm');")
    con.close()
    m = Registry(db).memories("c1")
    assert m[0]["answer"] == "r" and m[0]["observations"] == []


def test_questions_sur_notre_calcul_acceptees_f030():
    """Essai du 25/10 : deux questions sur le calcul du dossier refusées comme hors sujet."""
    from agents.copilot import off_topic

    for q in ["es ce que notre calcul est corrrect ??", "quelle est le demarche de notre calcul",
              "Quelle méthode a été utilisée ?", "Explique les étapes"]:
        assert not off_topic(q), q
    for q in ["definir lionel messi", "quelle est la capitale de la France", "donne moi une recette de crêpes"]:
        assert off_topic(q), q


def test_calcul_sans_outil_rejete_puis_calcul_du_dossier_f030(tmp_path):
    """« comment calculer le CSM » répondu sans outil, sans chiffre (donc sans contrôle) : rejeté ; au deuxième échec,
    le repli donne le calcul du dossier."""
    vague = {"action": "repondre", "reponse": "La CSM se calcule à partir des flux futurs et de la CSM déjà libérée."}
    res = Copilot(DossierTools(P), scripted(tmp_path, [vague, vague])).ask("comment calculer le CSM")
    assert res.source == "code" and "Calcul de la CSM" in res.answer and fr(compute_csm(P).initial_csm) in res.answer
    good = [{"action": "outil", "outil": "donnees_du_dossier", "arguments": {}},
            {"action": "repondre", "reponse": f"La CSM initiale vaut {fr(compute_csm(P).initial_csm)}."}]
    res = Copilot(DossierTools(P), scripted(tmp_path, good)).ask("est-ce que notre calcul est correct ?")
    assert res.source == "llm" and res.llm_calls == 2


def test_demandes_de_graphe_f036(tmp_path):
    """Essai du 26/10 (WC-1997-388) : « changer le graphe », « donner sous forme d'un graphe » refusées comme hors sujet,
    et toujours le même graphe. Le code choisit la vue, sans appel au modèle."""
    from agents.copilot import graph_request, off_topic

    for q in ["changer le graphe qui vous avez toujours fournie", "changer cette graphe il est toujours le meme",
              "donner sous forme d'un graphe", "donner un graphe simple qui aide moi a comprendre les calcul"]:
        assert not off_topic(q, True) and graph_request(q), q
    assert not graph_request("Que dit la norme sur le paragraphe 32 ?")
    cp = Copilot(DossierTools(P), scripted(tmp_path, []))          # aucun appel au modèle permis
    first = cp.ask("donner un graphe simple qui aide moi a comprendre les calcul")
    assert first.llm_calls == 0 and first.observations[0]["outil"] == "donnees_du_dossier"
    assert "Calcul de la CSM" in first.answer and not TECH.search(first.answer)
    cp.memory = "Résultats d'outils : donnees_du_dossier() → csm_initiale 9,16"
    other = cp.ask("changer le graphe, il est toujours le même")
    assert other.llm_calls == 0 and other.observations[0]["outil"] == "projection_resultat"
    assert cp.ask("un graphe des sensibilités").observations[0]["outil"] == "sensibilites"


def test_nature_du_dossier_et_desactualisation_f036():
    """« ce dossier est LIC ? » → réponse qui confondait LIC et PAA : la nature du passif est donnée par l'outil ;
    la libération de la première période peut dépasser la CSM initiale, la désactualisation l'explique."""
    d = DossierTools(P).dossier()
    assert "LRC" in d["nature_du_dossier"] and "LIC" in d["nature_du_dossier"]
    r = compute_csm(P)
    assert d["desactualisation_csm_premiere_periode"] == fr(r.rollforward[0].interest_accretion)
    rows = DossierTools(P).projection()["par_periode"]
    assert rows[-1]["csm_fin_de_periode"] == fr(r.rollforward[-1].closing)
