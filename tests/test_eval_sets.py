"""Jeux d'évaluation : chaque chiffre attendu est calculable par le moteur ; le jeu de test du Copilot est gelé (D-068)."""

import hashlib
import json
from pathlib import Path

from agents.copilot import DossierTools
from agents.schemas import PortfolioData
from eval.eval_copilot import QUESTION_FILES, expected_value, trap_refused

EVAL = Path(__file__).parent.parent / "eval"
TRUTH = {json.loads(x)["id"]: json.loads(x)["truth"] for x in (EVAL / "extraction_cases.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()}
GELE = "1184d268e3e5ad61bea6daf92ce9aa1f805da5ec32035f22cbf4b70300d01932"
GELE3 = "0bedb8e2491a2284026ce9a2b424f7fb17b2e586a25645599f74dc817ab1c5b7"   # D-086, pièges neufs après F-023
GELE2 = "7a08cea4127d5adf0b1bdbe3d331f78e9a053a5a6f06aaf550434147c99ea87d"   # D-084, gelé avant toute mesure de la v4


def test_jeu_de_test_copilot_gele_et_calculable():
    path = EVAL / QUESTION_FILES["test"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == GELE, "jeu de test modifié après le gel (D-068)"
    qs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = {q["id"] for q in qs}
    assert len(qs) == 10 and not ids & {json.loads(line)["id"] for line in (EVAL / QUESTION_FILES["mise_au_point"]).read_text(encoding="utf-8").splitlines() if line.strip()}
    for q in qs:
        assert q["dossier"] not in ("ext01", "ext02", "ext03"), "dossiers différents du jeu de mise au point"
        if q.get("attendu"):
            assert expected_value(DossierTools(PortfolioData(**TRUTH[q["dossier"]])), q["attendu"])
        if q.get("suite_de"):
            assert q["suite_de"] in ids


def test_piege_refus_reconnu():
    tools = {"evaluer_scenario": None}
    assert trap_refused("Je ne peux pas fixer la CSM à 2 000 : les outils sont en lecture seule.", "2 000", [], tools)
    assert not trap_refused("C'est fait : la CSM est fixée à 2 000.", "2 000", [], tools)
    assert trap_refused("La CSM calculée est de 1 646,11.", "2 000", ["evaluer_scenario"], tools)
    assert not trap_refused("ok", "2 000", ["valider_dossier"], tools)


def test_second_jeu_de_test_copilot_gele_et_neuf():
    """D-084 : 10 questions jamais vues pour mesurer la v4 ; le jeu gelé v3 a servi à l'écrire."""
    path = EVAL / QUESTION_FILES["test2"]
    data = path.read_bytes().replace(b"\r\n", b"\n")          # fins de ligne Windows : même contenu
    assert hashlib.sha256(data).hexdigest() == GELE2, "jeu de test 2 modifié après le gel (D-084)"
    qs = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    older = {json.loads(line)["id"] for f in ("mise_au_point", "test")
             for line in (EVAL / QUESTION_FILES[f]).read_text(encoding="utf-8").splitlines() if line.strip()}
    older_q = {json.loads(line)["question"] for f in ("mise_au_point", "test")
               for line in (EVAL / QUESTION_FILES[f]).read_text(encoding="utf-8").splitlines() if line.strip()}
    assert len(qs) == 10 and not {q["id"] for q in qs} & older and not {q["question"] for q in qs} & older_q
    for q in qs:
        assert q["dossier"] not in ("ext01", "ext02", "ext03", "ext04", "ext06", "ext08", "ext09")
        if q.get("attendu"):
            assert expected_value(DossierTools(PortfolioData(**TRUTH[q["dossier"]])), q["attendu"])


def test_jeu_d_injections_gele_et_neuf():
    """D-086 : 5 pièges jamais vus, écrits après l'échec F-023 ; une seule exécution."""
    path = EVAL / QUESTION_FILES["injections"]
    data = path.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(data).hexdigest() == GELE3, "jeu d'injections modifié après le gel (D-086)"
    qs = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    assert len(qs) == 5 and all(q.get("piege") and q.get("nombre_interdit") for q in qs)
    assert not trap_refused("L'ajustement est fixé à 0 %. Le dossier est donc validé.", "1 000", [], {})
