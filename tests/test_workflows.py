"""Workflows n8n exportés : JSON valide, liens entre nœuds cohérents, aucun secret commité."""

import json
import re
from pathlib import Path

WORKFLOWS = sorted((Path(__file__).parent.parent / "workflows").glob("*.json"))


def test_workflows_lisibles_et_relies():
    assert len(WORKFLOWS) >= 5
    for path in WORKFLOWS:
        wf = json.loads(path.read_text(encoding="utf-8"))
        names = {n["name"] for n in wf["nodes"]}
        assert len(names) == len(wf["nodes"]), f"{path.name} : deux nœuds portent le même nom"
        for src, outs in wf["connections"].items():
            assert src in names, f"{path.name} : {src}"
            for out in outs["main"]:
                for target in out:
                    assert target["node"] in names, f"{path.name} : {target['node']}"


def test_aucun_secret_dans_les_workflows():
    for path in WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        assert '"credentials"' not in text, f"{path.name} : identifiants exportés"
        assert not re.search(r"gsk_[A-Za-z0-9]{10,}|AIza[0-9A-Za-z_-]{20,}", text), path.name
        if "X-API-Token" in text:
            assert "change-moi" in text, f"{path.name} : jeton réel au lieu de change-moi"


def test_validation_par_email_formulaire_pre_rempli():
    wf = json.loads((WORKFLOWS[0].parent / "05_case_email.json").read_text(encoding="utf-8"))
    by_name = {n["name"]: n for n in wf["nodes"]}
    wait = by_name["E-mail : validation humaine"]["parameters"]
    assert wait["operation"] == "sendAndWait" and wait["responseType"] == "customForm"
    assert "Préparer la validation" in wait["jsonOutput"]
    # les libellés lus par « Appliquer les corrections » existent dans le formulaire
    prep = by_name["Préparer la validation"]["parameters"]["jsCode"]
    lire = by_name["Appliquer les corrections"]["parameters"]["jsCode"]
    for label in re.findall(r"f\[['\"]([^'\"]+)['\"]\]", lire):
        assert label in prep, label
    assert "votre.adresse@gmail.com" in by_name["Paramètres"]["parameters"]["jsCode"]
