"""Workflows n8n exportés : JSON valide, liens entre nœuds cohérents, aucun secret commité."""

import json
import re
from pathlib import Path

WF_DIR = Path(__file__).parent.parent / "workflows"
UNIQUE = WF_DIR / "ifrs17_copilot.json"           # le livrable : tout le processus (D-064)
ETAPES = WF_DIR / "par_etape"                       # les workflows séparés d'origine (historique)
WORKFLOWS = sorted(WF_DIR.rglob("*.json"))


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
    wf = json.loads((ETAPES / "05_case_email.json").read_text(encoding="utf-8"))
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


def test_validation_depuis_le_site_workflow_06():
    wf = json.loads((ETAPES / "06_validation_email.json").read_text(encoding="utf-8"))
    by_name = {n["name"]: n for n in wf["nodes"]}
    hook = by_name["Webhook (depuis l'API)"]["parameters"]
    # l'API ne doit pas attendre la réponse du valideur : n8n répond dès réception
    assert hook["path"] == "ifrs17/validation" and hook["responseMode"] == "onReceived"
    assert by_name["E-mail : validation humaine"]["parameters"]["operation"] == "sendAndWait"
    assert "json.body" in by_name["Paramètres"]["parameters"]["jsCode"]


def _wf(name: str) -> dict:
    wf = json.loads((ETAPES / name).read_text(encoding="utf-8"))
    return {n["name"]: n for n in wf["nodes"]} | {"__wf__": wf}


def test_chaine_complete_reception_traitement():
    """07 (e-mail) et 08 (formulaire) confient chaque document au sous-workflow 09 (D-059)."""
    for fichier, declencheur in (("07_intake_email.json", "n8n-nodes-base.emailReadImap"),
                                 ("08_intake_form.json", "n8n-nodes-base.formTrigger")):
        nodes = _wf(fichier)
        types = {n["type"] for k, n in nodes.items() if k != "__wf__"}
        assert declencheur in types and "n8n-nodes-base.executeWorkflow" in types, fichier
        sub = nodes["Traiter le dossier (09)"]["parameters"]
        assert sub["source"] == "database" and sub["workflowId"]["value"] == "", fichier  # choisi à l'import
        assert "binary: { document" in json.dumps(nodes["__wf__"], ensure_ascii=False), fichier
    form = _wf("08_intake_form.json")["Formulaire de dépôt"]["parameters"]
    labels = {f["fieldLabel"]: f for f in form["formFields"]["values"]}
    assert labels["Document"]["fieldType"] == "file" and labels["Adresse e-mail"]["requiredField"]
    assert "i.binary.Document" in _wf("08_intake_form.json")["Préparer le dossier"]["parameters"]["jsCode"]
    imap = _wf("07_intake_email.json")["E-mail reçu (IMAP)"]["parameters"]
    assert imap["downloadAttachments"] and "IFRS17" in imap["options"]["customEmailConfig"]


def test_sous_workflow_09_trace_au_registre():
    nodes = _wf("09_case_processing.json")
    assert nodes["Appelé par 07 ou 08"]["parameters"]["inputSource"] == "passthrough"
    corps = {p["name"]: p for p in nodes["Appel API /v1/case"]["parameters"]["bodyParameters"]["parameters"]}
    assert corps["file"]["inputDataFieldName"] == "document" and {"source", "submitter"} <= set(corps)
    assert nodes["Appel API /v1/case"]["onError"] == "continueErrorOutput"
    texte = json.dumps(nodes["__wf__"], ensure_ascii=False)
    for action in ("email_note_envoyee", "transmis_validation"):
        assert action in texte
    assert "/v1/cases/" in texte and "webhook/ifrs17/validation" in texte
    # une trace qui échoue ne doit jamais bloquer l'envoi de la note
    assert nodes["Registre : note envoyée"]["onError"] == "continueRegularOutput"


def test_validation_inscrit_valideur_et_rejet():
    for fichier in ("05_case_email.json", "06_validation_email.json"):
        nodes = _wf(fichier)
        assert "validated_by" in nodes["Appel API /v1/case/validated"]["parameters"]["jsonBody"], fichier
        assert nodes["Registre : rejet"]["parameters"]["url"].endswith("/reject"), fichier
        suite = nodes["__wf__"]["connections"]["Registre : rejet"]["main"][0][0]["node"]
        assert suite == "E-mail : dossier rejeté", fichier


def test_alertes_et_supervision():
    err = _wf("10_error_alerts.json")
    assert err["Erreur d'un workflow"]["type"] == "n8n-nodes-base.errorTrigger"
    sup = _wf("11_monitoring.json")
    regles = [n["parameters"]["rule"]["interval"][0] for k, n in sup.items()
              if k != "__wf__" and n["type"] == "n8n-nodes-base.scheduleTrigger"]
    assert {"field": "minutes", "minutesInterval": 15} in regles
    assert any(r.get("expression") == "0 8 * * 1" for r in regles)
    # une alerte au changement d'état, pas une toutes les 15 minutes
    assert "$getWorkflowStaticData" in sup["État changé ? (API muette)"]["parameters"]["jsCode"]
    assert "/v1/dashboard" in sup["Tableau de bord"]["parameters"]["url"]


def test_parametres_d_exemple_conserves():
    for path in WORKFLOWS:
        wf = json.loads(path.read_text(encoding="utf-8"))
        for n in wf["nodes"]:
            if n["name"].startswith("Paramètres"):
                code = n["parameters"]["jsCode"]
                assert "votre.adresse@gmail.com" in code and "change-moi" in code, f"{path.name} : {n['name']}"
        assert not re.search(r"[\w.+-]+@gmail\.com", path.read_text(encoding="utf-8").replace("votre.adresse@gmail.com", "")), path.name


# ============================================================================ workflow unique (D-064)
def _unique() -> tuple[dict, dict]:
    wf = json.loads(UNIQUE.read_text(encoding="utf-8"))
    return wf, {n["name"]: n for n in wf["nodes"]}


def _cibles(wf: dict, src: str, out: int) -> list[str]:
    outs = wf["connections"].get(src, {"main": []})["main"]
    return [t["node"] for t in outs[out]] if out < len(outs) else []


def test_unique_tous_les_declencheurs_mènent_aux_parametres():
    wf, nodes = _unique()
    declencheurs = {k: n for k, n in nodes.items() if k in wf["connections"]
                    and n["type"].split(".")[-1] in {"emailReadImap", "formTrigger", "webhook", "scheduleTrigger", "errorTrigger"}}
    types = sorted(n["type"].split(".")[-1] for n in declencheurs.values())
    assert types == ["emailReadImap", "errorTrigger", "formTrigger", "scheduleTrigger", "scheduleTrigger", "webhook", "webhook"]
    for nom in declencheurs:
        (prep,) = _cibles(wf, nom, 0)
        assert _cibles(wf, prep, 0) == ["Paramètres"], nom
        assert "flux" in nodes[prep]["parameters"]["jsCode"], prep
    assert _cibles(wf, "Paramètres", 0) == ["Aiguillage"]
    chemins = {n["parameters"]["path"] for n in declencheurs.values() if "path" in n["parameters"]}
    assert chemins == {"ifrs17/depot", "ifrs17/validation", "ifrs17-depot"}


def test_unique_aiguillage_couvre_chaque_flux():
    wf, nodes = _unique()
    sw = nodes["Aiguillage"]
    regles = [r["outputKey"] for r in sw["parameters"]["rules"]["values"]]
    assert regles == ["dossier", "validation", "sans_document", "sante", "rapport", "erreur"]
    attendu = ["Appel API /v1/case", "Préparer la validation", "E-mail : aucun document", "Santé de l'API",
               "Tableau de bord (7 jours)", "E-mail : alerte d'erreur"]
    assert [_cibles(wf, "Aiguillage", i) for i in range(len(regles))] == [[a] for a in attendu]
    # chaque flux annoncé par un nœud « Préparer » a sa sortie dans l'aiguillage
    produits = set()
    for n in nodes.values():
        if n["type"].endswith(".code"):
            produits |= set(re.findall(r"flux: '(\w+)'", n["parameters"]["jsCode"]))
    assert produits == set(regles)


def test_unique_chaine_dossier_et_validation():
    wf, nodes = _unique()
    corps = {p["name"]: p for p in nodes["Appel API /v1/case"]["parameters"]["bodyParameters"]["parameters"]}
    assert corps["file"]["inputDataFieldName"] == "document" and {"source", "submitter"} <= set(corps)
    assert _cibles(wf, "Appel API /v1/case", 1) == ["E-mail : incident (déposant)"]
    assert _cibles(wf, "À valider ?", 0) == ["Transmettre à la validation"]
    # la validation passe par le webhook de CE workflow : une exécution (un formulaire en attente) par dossier
    code = nodes["Paramètres"]["parameters"]["jsCode"]
    assert "webhook/ifrs17/validation" in code and "parametres.validation" in nodes["Transmettre à la validation"]["parameters"]["url"]
    wait = nodes["E-mail : validation humaine"]["parameters"]
    assert wait["operation"] == "sendAndWait" and wait["responseType"] == "customForm"
    prep = nodes["Préparer la validation"]["parameters"]["jsCode"]
    for label in re.findall(r"f\[['\"]([^'\"]+)['\"]\]", nodes["Appliquer les corrections"]["parameters"]["jsCode"]):
        assert label in prep, label
    assert "validated_by" in nodes["Appel API /v1/case/validated"]["parameters"]["jsonBody"]
    assert _cibles(wf, "Approuvé ?", 1) == ["Registre : rejet"] and _cibles(wf, "Registre : rejet", 0) == ["E-mail : dossier rejeté"]
    assert "ccEmail" in nodes["E-mail : note validée"]["parameters"]["options"]
    for n in nodes.values():                  # une trace au registre ne bloque jamais l'envoi
        if n["name"].startswith("Registre"):
            assert n["onError"] == "continueRegularOutput", n["name"]


def test_unique_supervision_et_reglages():
    wf, nodes = _unique()
    regles = [n["parameters"]["rule"]["interval"][0] for n in nodes.values() if n["type"].endswith("scheduleTrigger")]
    assert {"field": "minutes", "minutesInterval": 15} in regles and any(r.get("expression") == "0 8 * * 1" for r in regles)
    assert "$getWorkflowStaticData" in nodes["État changé ?"]["parameters"]["jsCode"]
    assert sorted(_cibles(wf, "Santé de l'API", 0) + _cibles(wf, "Santé de l'API", 1)) == ["État changé ?"] * 2
    # un seul nœud de réglages pour tout le processus
    assert [k for k in nodes if k.startswith("Paramètres")] == ["Paramètres"]
    assert wf["settings"].get("errorWorkflow") is None   # Error Trigger interne : aucun réglage à faire


def test_unique_note_en_pdf_jointe():
    """La note part en HTML dans le corps et en PDF en pièce jointe (D-065) ; sans PDF, l'e-mail part quand même."""
    wf, nodes = _unique()
    for pdf, mail, amont in (("Note en PDF", "E-mail : note au déposant", "Note prête ?"),
                             ("Note validée en PDF", "E-mail : note validée", "Appel API /v1/case/validated")):
        n = nodes[pdf]
        assert n["parameters"]["url"].endswith("/note.pdf") and n["onError"] == "continueRegularOutput"
        assert n["parameters"]["options"]["response"]["response"] == {"responseFormat": "file", "outputPropertyName": "note_pdf"}
        assert _cibles(wf, amont, 0) == [pdf] and _cibles(wf, pdf, 0) == [mail]
        corps = nodes[mail]["parameters"]
        assert corps["options"]["fileAttachments"] == "note_pdf"
        assert "$json.note_html" not in corps["html"]       # le $json est le PDF : la note est relue à sa source
