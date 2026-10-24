"""Génère workflows/ifrs17_copilot.json (lancer : python workflows/generer.py) : TOUT le processus n8n dans un seul workflow (D-064).

Sept déclencheurs → un nœud « Paramètres » commun → un Switch « Aiguillage » sur le champ ``flux`` :

    dossier        IMAP, formulaire, webhook de dépôt → /v1/case → note / validation / illisible / incident
    validation     webhook ifrs17/validation (appelé par l'API et par la branche dossier) → formulaire → note validée
    sans_document  e-mail reçu sans pièce jointe exploitable → réponse à l'expéditeur
    sante          toutes les 15 min → /health → alerte au changement d'état
    rapport        lundi 8 h → /v1/dashboard → rapport HTML
    erreur         Error Trigger : n8n le lance pour toute erreur de CE workflow (workflow d'erreur interne,
                   execute-error-workflow.ts : « Start internal error workflow »), sans réglage

La branche dossier transmet la validation humaine en appelant le webhook de validation du même workflow :
chaque validation devient une exécution séparée (un formulaire en attente par dossier), même quand un
e-mail porte plusieurs pièces jointes.

Paramètres des nœuds vérifiés dans le code source de n8n 2.42.3 (packages/nodes-base) : emailReadImap 2.2,
formTrigger 2.2, webhook 2, errorTrigger 1, scheduleTrigger 1.2, httpRequest 4.2, emailSend 2.1, code 2,
if 2, switch 3.2, stickyNote 1.
"""

import json
import uuid
from pathlib import Path

OUT = Path(__file__).with_name("ifrs17_copilot.json")
NS = uuid.UUID("6f1d0c3e-1f7a-4b52-9a51-0b6c1ee17064")
W = "unique"
NODES: list[dict] = []
CONNS: dict = {}


def uid(name: str) -> str:
    return str(uuid.uuid5(NS, name))


def add(name: str, typ: str, ver, params: dict, pos, **extra) -> str:
    n = {"parameters": params, "id": uid(f"{W}/{name}"), "name": name, "type": f"n8n-nodes-base.{typ}",
         "typeVersion": ver, "position": list(pos)}
    if typ in ("emailSend", "formTrigger", "webhook"):
        n["webhookId"] = uid(f"{W}/{name}/webhook")
    n.update(extra)
    assert all(x["name"] != name for x in NODES), name
    NODES.append(n)
    return name


def link(src: str, dst: str, out: int = 0) -> None:
    outs = CONNS.setdefault(src, {"main": []})["main"]
    while len(outs) <= out:
        outs.append([])
    outs[out].append({"node": dst, "type": "main", "index": 0})


def chain(*names: str) -> None:
    for a, b in zip(names, names[1:], strict=False):
        link(a, b)


def sticky(name: str, text: str, pos, w: int, h: int, color: int) -> None:
    NODES.append({"parameters": {"content": text, "height": h, "width": w, "color": color},
                  "id": uid(f"{W}/note/{name}"), "name": name, "type": "n8n-nodes-base.stickyNote",
                  "typeVersion": 1, "position": list(pos)})


def cond(cid: str, left: str, op: dict, right="", validation="strict") -> dict:
    return {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": validation},
                           "conditions": [{"id": uid(cid), "leftValue": left, "rightValue": right, "operator": op}],
                           "combinator": "and"}, "options": {}}


EQ = {"type": "string", "operation": "equals"}
TRUE = {"type": "boolean", "operation": "true", "singleValue": True}
MAIL = {"appendAttribution": False}
PI = "$('Paramètres').item.json"            # élément courant (branche dossier : plusieurs éléments possibles)
P1 = "$('Paramètres').first().json"         # branches à un seul élément (validation, supervision, erreur)


def head(p: str) -> dict:
    return {"sendHeaders": True, "headerParameters": {"parameters": [
        {"name": "X-API-Token", "value": f"={{{{ {p}.parametres.jeton }}}}"}]}}


def mail(name, pos, to, subject, body, p=PI, html=False, **opts):
    params = {"fromEmail": f"={{{{ {p}.parametres.expediteur }}}}", "toEmail": to, "subject": subject,
              "emailFormat": "html" if html else "text", ("html" if html else "text"): body,
              "options": {**MAIL, **opts}}
    return add(name, "emailSend", 2.1, params, pos)


def event(name, action, detail, pos, case_expr="$json.case_id ?? $('Appel API /v1/case').item.json.case_id", p=PI):
    """Inscrit une action n8n dans la piste d'audit du dossier (ne bloque jamais le workflow)."""
    return add(name, "httpRequest", 4.2, {
        "method": "POST", "url": f"={{{{ {p}.parametres.api }}}}/v1/cases/{{{{ {case_expr} }}}}/events", **head(p),
        "sendBody": True, "specifyBody": "json",
        "jsonBody": f"={{{{ JSON.stringify({{ action: '{action}', detail: {detail} }}) }}}}",
        "options": {"timeout": 15000}}, pos, onError="continueRegularOutput")


def note_pdf(name, pos, case_expr, p):
    """Télécharge la note en PDF (GET /v1/cases/{id}/note.pdf, D-065) dans la pièce binaire « note_pdf ».
    En cas d'échec (aucun navigateur côté API), l'e-mail part quand même, sans pièce jointe."""
    return add(name, "httpRequest", 4.2, {
        "method": "GET", "url": f"={{{{ {p}.parametres.api }}}}/v1/cases/{{{{ {case_expr} }}}}/note.pdf", **head(p),
        "options": {"timeout": 120000, "response": {"response": {"responseFormat": "file", "outputPropertyName": "note_pdf"}}}},
        pos, onError="continueRegularOutput")


PDF_OPTS = {"fileAttachments": "note_pdf"}
CASE = "$('Appel API /v1/case').item.json"
VALID = "$('Appel API /v1/case/validated').first().json"

# ============================================================================ déclencheurs
X0, X1, XP, XS = 0, 260, 560, 800
Y = {"imap": -900, "form": -700, "depot": -500, "valid": 40, "sante": 620, "rapport": 900, "erreur": 1180}

add("E-mail reçu (IMAP)", "emailReadImap", 2.2, {
    "mailbox": "INBOX", "postProcessAction": "read", "format": "simple", "downloadAttachments": True,
    "dataPropertyAttachmentsPrefixName": "attachment_",
    "options": {"customEmailConfig": '["UNSEEN", ["SUBJECT", "IFRS17"]]'}}, (X0, Y["imap"]))
add("Extraire les documents", "code", 2, {"jsCode":
    "// Un élément par pièce jointe exploitable (PDF, PNG, JPEG, Excel, CSV) ; un e-mail sans document est signalé.\n"
    "const ACCEPTE = ['application/pdf', 'image/png', 'image/jpeg',\n"
    "  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'text/csv'];\n"
    "const EXTENSIONS = /\\.(pdf|png|jpe?g|xlsx|csv)$/i;   // un CSV arrive souvent avec un type générique\n"
    "const adresse = de => (String(de || '').match(/[\\w.+-]+@[\\w-]+(\\.[\\w-]+)+/) || [''])[0].toLowerCase();\n"
    "const sortie = [];\n"
    "for (const mail of $input.all()) {\n"
    "  const deposant = adresse(mail.json.from);\n"
    "  const sujet = mail.json.subject || '';\n"
    "  const pieces = Object.values(mail.binary || {}).filter(b => ACCEPTE.includes(b.mimeType) || EXTENSIONS.test(b.fileName || ''));\n"
    "  if (!pieces.length) { sortie.push({ json: { flux: 'sans_document', deposant, sujet } }); continue; }\n"
    "  for (const b of pieces) {\n"
    "    sortie.push({ json: { flux: 'dossier', source: 'n8n-email', deposant, sujet, nom_fichier: b.fileName || 'document' },\n"
    "                  binary: { document: b } });\n"
    "  }\n"
    "}\n"
    "return sortie;\n"}, (X1, Y["imap"]))

add("Formulaire de dépôt", "formTrigger", 2.2, {
    "path": "ifrs17-depot", "formTitle": "Déposer un dossier IFRS 17",
    "formDescription": "Déposez l'état du portefeuille (PDF, scan ou photo). Vous recevrez la note par e-mail, "
                       "ou un accusé de réception si un valideur doit d'abord l'approuver. Données fictives uniquement.",
    "formFields": {"values": [
        {"fieldLabel": "Adresse e-mail", "fieldType": "email", "requiredField": True, "placeholder": "nom@assureur.fr"},
        {"fieldLabel": "Nom", "fieldType": "text", "requiredField": False},
        {"fieldLabel": "Document", "fieldType": "file", "multipleFiles": False, "acceptFileTypes": ".pdf, .png, .jpg, .jpeg, .xlsx, .csv",
         "requiredField": True},
        {"fieldLabel": "Commentaire", "fieldType": "textarea", "requiredField": False}]},
    "responseMode": "onReceived",
    "options": {"appendAttribution": False, "buttonLabel": "Envoyer le dossier",
                "respondWithOptions": {"values": {"respondWith": "text", "formSubmittedText":
                    "Dossier reçu. L'analyse prend 1 à 3 minutes : la note, ou un accusé de réception, arrive par e-mail."}}}},
    (X0, Y["form"]))
add("Préparer : formulaire", "code", 2, {"jsCode":
    "// Le fichier du champ « Document » devient la pièce « document » attendue par l'appel à l'API.\n"
    "return $input.all().map(i => ({\n"
    "  json: { flux: 'dossier', source: 'n8n-formulaire', deposant: String(i.json['Adresse e-mail'] || '').trim().toLowerCase(),\n"
    "          nom: i.json['Nom'] || '', commentaire: i.json['Commentaire'] || '',\n"
    "          nom_fichier: i.binary?.Document?.fileName || 'document' },\n"
    "  binary: { document: i.binary.Document },\n"
    "}));\n"}, (X1, Y["form"]))

add("Webhook de dépôt", "webhook", 2, {"httpMethod": "POST", "path": "ifrs17/depot", "responseMode": "onReceived",
                                       "options": {}}, (X0, Y["depot"]))
add("Préparer : webhook", "code", 2, {"jsCode":
    "// Dépôt par requête HTTP (démo, scripts) : curl.exe -F \"file=@doc.pdf\" -F \"email=nom@exemple.fr\" ...\n"
    "// Sans champ email, la note part au valideur (Paramètres).\n"
    "return $input.all().map(i => {\n"
    "  const fichiers = Object.values(i.binary || {});\n"
    "  const deposant = String(i.json.body?.email || '').trim().toLowerCase();\n"
    "  if (!fichiers.length) return { json: { flux: 'sans_document', deposant, sujet: 'dépôt par webhook' } };\n"
    "  return { json: { flux: 'dossier', source: 'n8n-webhook', deposant, nom_fichier: fichiers[0].fileName || 'document' },\n"
    "           binary: { document: fichiers[0] } };\n"
    "});\n"}, (X1, Y["depot"]))

add("Webhook de validation", "webhook", 2, {"httpMethod": "POST", "path": "ifrs17/validation", "responseMode": "onReceived",
                                            "options": {}}, (X0, Y["valid"]))
add("Préparer : validation", "code", 2, {"jsCode":
    "// Dossier déjà analysé (réponse de /v1/case), envoyé par l'API (site web, N8N_VALIDATION_URL)\n"
    "// ou par la branche « dossier » de ce workflow (dépôt par e-mail, formulaire, webhook).\n"
    "const corps = $input.first().json.body || {};\n"
    "return [{ json: { ...corps, flux: 'validation' } }];\n"}, (X1, Y["valid"]))

add("Toutes les 15 minutes", "scheduleTrigger", 1.2, {"rule": {"interval": [{"field": "minutes", "minutesInterval": 15}]}},
    (X0, Y["sante"]))
add("Préparer : santé", "code", 2, {"jsCode": "return [{ json: { flux: 'sante' } }];\n"}, (X1, Y["sante"]))
add("Chaque lundi à 8 h", "scheduleTrigger", 1.2,
    {"rule": {"interval": [{"field": "cronExpression", "expression": "0 8 * * 1"}]}}, (X0, Y["rapport"]))
add("Préparer : rapport", "code", 2, {"jsCode": "return [{ json: { flux: 'rapport' } }];\n"}, (X1, Y["rapport"]))
add("Erreur du workflow", "errorTrigger", 1, {}, (X0, Y["erreur"]))
add("Préparer : erreur", "code", 2, {"jsCode":
    "// n8n lance ce déclencheur quand une exécution de CE workflow échoue (hors exécution manuelle).\n"
    "const e = $input.first().json;\n"
    "return [{ json: { flux: 'erreur', workflow: e.workflow?.name ?? '?', noeud: e.execution?.lastNodeExecuted ?? '?',\n"
    "  message: e.execution?.error?.message ?? e.trigger?.error?.message ?? '?',\n"
    "  url: e.execution?.url ?? '(pas d\\'URL)', mode: e.execution?.mode ?? '?' } }];\n"}, (X1, Y["erreur"]))

for a, b in [("E-mail reçu (IMAP)", "Extraire les documents"), ("Formulaire de dépôt", "Préparer : formulaire"),
             ("Webhook de dépôt", "Préparer : webhook"), ("Webhook de validation", "Préparer : validation"),
             ("Toutes les 15 minutes", "Préparer : santé"), ("Chaque lundi à 8 h", "Préparer : rapport"),
             ("Erreur du workflow", "Préparer : erreur")]:
    link(a, b)
    link(b, "Paramètres")

# ============================================================================ paramètres + aiguillage
add("Paramètres", "code", 2, {"mode": "runOnceForEachItem", "jsCode":
    "// À ADAPTER : les SEULS réglages de tout le processus. Le jeton reste « change-moi » et l'adresse\n"
    "// « votre.adresse@gmail.com » dans le fichier commité ; mettez vos valeurs dans n8n, jamais dans Git.\n"
    "const parametres = {\n"
    "  valideur: 'votre.adresse@gmail.com',             // reçoit les dossiers à valider et les alertes\n"
    "  expediteur: 'Copilote IFRS 17 <votre.adresse@gmail.com>',  // l'adresse du compte SMTP\n"
    "  api: 'http://127.0.0.1:8000',                   // 127.0.0.1 et non localhost (F-002)\n"
    "  jeton: 'change-moi',                            // valeur d'API_TOKEN du .env\n"
    "  validation: 'http://127.0.0.1:5678/webhook/ifrs17/validation',  // webhook de validation de CE workflow\n"
    "};\n"
    "const j = $input.item.json;\n"
    "// sans adresse de déposant (site web, webhook sans champ email), la note part au valideur\n"
    "return { json: { ...j, deposant: j.deposant || parametres.valideur, parametres }, binary: $input.item.binary };\n"},
    (XP, 140))

LANES = ["dossier", "validation", "sans_document", "sante", "rapport", "erreur"]
add("Aiguillage", "switch", 3.2, {"mode": "rules", "rules": {"values": [
    {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                    "conditions": [{"id": uid(f"switch/{k}"), "leftValue": "={{ $json.flux }}", "rightValue": k, "operator": EQ}],
                    "combinator": "and"}, "renameOutput": True, "outputKey": k} for k in LANES]},
    "options": {}}, (XS, 140))
link("Paramètres", "Aiguillage")

# ============================================================================ 1. dossier
XD = 1100
YD = Y["imap"] + 120
add("Appel API /v1/case", "httpRequest", 4.2, {
    "method": "POST", "url": f"={{{{ {PI}.parametres.api }}}}/v1/case", **head(PI), "sendBody": True,
    "contentType": "multipart-form-data",
    "bodyParameters": {"parameters": [
        {"parameterType": "formBinaryData", "name": "file", "inputDataFieldName": "document"},
        {"parameterType": "formData", "name": "source", "value": "={{ $json.source }}"},
        {"parameterType": "formData", "name": "submitter", "value": "={{ $json.deposant }}"}]},
    "options": {"timeout": 300000}}, (XD, YD), onError="continueErrorOutput")
link("Aiguillage", "Appel API /v1/case", 0)
add("Note prête ?", "if", 2, cond("if/note", "={{ $json.status }}", EQ, "note_prete"), (XD + 240, YD - 100))
note_pdf("Note en PDF", (XD + 480, YD - 220), f"{CASE}.case_id", PI)
mail("E-mail : note au déposant", (XD + 720, YD - 220), f"={{{{ {PI}.deposant }}}}",
     f"=IFRS 17 · note prête · {{{{ {CASE}.portfolio?.group_id ?? {CASE}.triangle?.portfolio_id ?? '' }}}} (dossier {{{{ {CASE}.case_id }}}})",
     f"={{{{ {CASE}.note_html }}}}", html=True, **PDF_OPTS)
event("Registre : note envoyée", "email_note_envoyee",
      f"{{ a: {PI}.deposant, canal: {PI}.source, pdf: Boolean($('Note en PDF').item.binary?.note_pdf) }}", (XD + 960, YD - 220))
add("À valider ?", "if", 2, cond("if/valider", "={{ $json.status }}", EQ, "validation_humaine"), (XD + 480, YD))
add("Transmettre à la validation", "httpRequest", 4.2, {
    "method": "POST", "url": f"={{{{ {PI}.parametres.validation }}}}", "sendBody": True, "specifyBody": "json",
    "jsonBody": f"={{{{ JSON.stringify({{ ...$json, deposant: {PI}.deposant }}) }}}}",
    "options": {"timeout": 30000}}, (XD + 720, YD - 40), onError="continueRegularOutput")
mail("E-mail : accusé de réception", (XD + 960, YD - 40), f"={{{{ {PI}.deposant }}}}",
     "=IFRS 17 · dossier {{ $('Appel API /v1/case').item.json.case_id }} reçu, en cours de validation",
     "=Bonjour,\n\nVotre dossier {{ $('Appel API /v1/case').item.json.case_id }} ({{ $('Paramètres').item.json.nom_fichier }}) "
     "a bien été analysé. Un contrôle automatique demande l'avis d'un valideur avant diffusion de la note : vous la "
     "recevrez dès sa décision.\n\nContrôles en cours de revue :\n"
     "{{ ($('Appel API /v1/case').item.json.controls || []).map(c => '- ' + c).join('\\n') }}\n\n"
     "Référence à rappeler : {{ $('Appel API /v1/case').item.json.case_id }}")
event("Registre : transmis au valideur", "transmis_validation", f"{{ valideur: {PI}.parametres.valideur }}",
      (XD + 1200, YD - 40), case_expr="$('Appel API /v1/case').item.json.case_id")
mail("E-mail : document inexploitable", (XD + 720, YD + 140), f"={{{{ {PI}.deposant }}}}",
     "=IFRS 17 · dossier {{ $json.case_id }} : document inexploitable",
     "=Bonjour,\n\nLe document {{ $('Paramètres').item.json.nom_fichier }} n'a pas pu être exploité :\n"
     "{{ ($json.controls || []).map(c => '- ' + c).join('\\n') }}\n\nMerci d'envoyer un PDF ou une image lisible de l'état "
     "du portefeuille (primes, sinistres et frais, unités de couverture, taux).")
mail("E-mail : incident (déposant)", (XD + 240, YD + 260), f"={{{{ {PI}.deposant }}}}",
     "=IFRS 17 · votre dossier n'a pas pu être traité",
     "=Bonjour,\n\nLe document {{ $('Paramètres').item.json.nom_fichier }} n'a pas pu être traité "
     "({{ String($json.error?.message ?? $json.error ?? 'erreur inconnue').slice(0, 300) }}).\n\n"
     "S'il s'agit d'un scan, vérifiez qu'il est lisible ; sinon l'équipe a été prévenue et reviendra vers vous.")
mail("E-mail : alerte équipe", (XD + 480, YD + 260), f"={{{{ {PI}.parametres.valideur }}}}",
     "=IFRS 17 · échec d'un dossier reçu par {{ $('Paramètres').item.json.source }}",
     "=Déposant : {{ $('Paramètres').item.json.deposant }}\nDocument : {{ $('Paramètres').item.json.nom_fichier }}\n"
     "Erreur : {{ String($('Appel API /v1/case').item.json.error?.message ?? JSON.stringify($('Appel API /v1/case').item.json.error ?? '')).slice(0, 1500) }}\n"
     "Détail : {{ JSON.stringify($('Appel API /v1/case').item.json.error?.description ?? '').slice(0, 1500) }}\n\n"
     "Le dossier est visible dans le registre (site, page Dossiers) avec son statut d'échec.")
link("Appel API /v1/case", "Note prête ?", 0)
link("Appel API /v1/case", "E-mail : incident (déposant)", 1)
link("E-mail : incident (déposant)", "E-mail : alerte équipe")
link("Note prête ?", "Note en PDF", 0)
link("Note en PDF", "E-mail : note au déposant")
link("Note prête ?", "À valider ?", 1)
link("E-mail : note au déposant", "Registre : note envoyée")
link("À valider ?", "Transmettre à la validation", 0)
link("À valider ?", "E-mail : document inexploitable", 1)
chain("Transmettre à la validation", "E-mail : accusé de réception", "Registre : transmis au valideur")

# ============================================================================ 2. validation humaine
XV, YV = 1100, Y["valid"]
add("Préparer la validation", "code", 2, {"jsCode":
    "// Prépare l'e-mail de validation et le formulaire pré-rempli avec les données extraites.\n"
    "const r = $input.first().json;\n"
    "const p = r.portfolio || {};\n"
    "const lic = r.kind === 'lic';   // triangle de sinistres survenus (D-083) : approbation de la note, sans formulaire de cellules\n"
    "const liste = v => Array.isArray(v) ? v.join(' ; ') : (v ?? '');\n"
    "const unite = { 1: 'unités', 1000: 'milliers', 1000000: 'millions' }[p.unit_multiplier] || '';\n"
    "const controles = (r.controls || []).map(c => '- ' + c).join('\\n') || '- aucun contrôle détaillé';\n"
    "const autres = (r.groups || []).slice(1).map(g => g.portfolio);   // autres groupes du document (D-078)\n"
    "const csm = lic && r.lic\n"
    "  ? `passif pour sinistres survenus (LIC) provisoire : ${r.lic.lic.toFixed(2)} ${r.triangle?.currency || ''}`\n"
    "  : r.csm\n"
    "  ? `${r.csm.onerous ? 'composante de perte' : 'CSM initiale'} provisoire : ${(r.csm.onerous ? r.csm.initial_loss_component : r.csm.initial_csm).toFixed(2)} ${p.currency || ''} (${unite})`\n"
    "  : 'CSM non calculée : aucune donnée exploitable';\n"
    "const message = [\n"
    "  `Dossier ${r.case_id} : un contrôle n'est pas passé, la note ne peut pas partir sans vous.`,\n"
    "  r.deposant ? `Déposé par : ${r.deposant}` : 'Déposé depuis le site web.',\n"
    "  '', 'Contrôles non passés :', controles, '', csm, '',\n"
    "  'La note provisoire vous a été envoyée dans un e-mail séparé.',\n"
    "  'Cliquez sur « Vérifier les données » : le formulaire est pré-rempli avec les données extraites.',\n"
    "  'Corrigez ce qui est faux, puis choisissez Approuver (la note définitive est recalculée et envoyée) ou Rejeter.',\n"
    "  'Listes : une valeur par période, séparées par des points-virgules ; la virgule sert de séparateur décimal.',\n"
    "  ...(autres.length ? ['', `Le document contient ${autres.length + 1} groupes : le formulaire corrige le groupe `\n"
    "    + `${p.group_id} ; les autres (${autres.map(g => g.group_id).join(', ')}) sont repris tels quels dans la note.`] : []),\n"
    "].join('\\n');\n"
    "const champ = (fieldLabel, defaultValue, extra = {}) =>\n"
    "  ({ fieldLabel, fieldType: 'text', defaultValue: String(defaultValue ?? ''), requiredField: true, ...extra });\n"
    "const formulaireLic = [\n"
    "  { fieldLabel: 'Décision', fieldType: 'dropdown', defaultValue: 'Approuver',\n"
    "    fieldOptions: { values: [{ option: 'Approuver' }, { option: 'Rejeter' }] }, requiredField: true },\n"
    "  { fieldLabel: 'Commentaire', fieldType: 'textarea', requiredField: false },\n"
    "];\n"
    "const formulaire = [\n"
    "  { fieldLabel: 'Décision', fieldType: 'dropdown', defaultValue: 'Approuver',\n"
    "    fieldOptions: { values: [{ option: 'Approuver' }, { option: 'Rejeter' }] }, requiredField: true },\n"
    "  champ('Groupe de contrats', p.group_id),\n"
    "  champ('Devise', p.currency || 'EUR'),\n"
    "  champ('Unité (1, 1000 ou 1000000)', p.unit_multiplier ?? 1),\n"
    "  champ('Primes par période', liste(p.premiums), { fieldType: 'textarea' }),\n"
    "  champ('Sorties par période', liste(p.outflows), { fieldType: 'textarea' }),\n"
    "  champ('Recouvrements par période (facultatif)', p.recoveries ? liste(p.recoveries) : '',\n"
    "        { fieldType: 'textarea', requiredField: false }),\n"
    "  champ(\"Frais d'acquisition par période (facultatif)\", p.acquisition_costs ? liste(p.acquisition_costs) : '',\n"
    "        { fieldType: 'textarea', requiredField: false }),\n"
    "  champ('Durée de couverture en mois (facultatif)', p.coverage_months ?? '', { requiredField: false }),\n"
    "  champ('Branche (facultatif)', p.line_of_business ?? '', { requiredField: false }),\n"
    "  champ('Unités de couverture par période', liste(p.coverage_units), { fieldType: 'textarea' }),\n"
    "  champ(\"Taux d'actualisation\", liste(p.discount_rates ?? 0)),\n"
    "  champ('Ajustement pour risque (0 à 1)', p.risk_adjustment_pct ?? 0),\n"
    "  { fieldLabel: 'Commentaire', fieldType: 'textarea', requiredField: false },\n"
    "];\n"
    "return [{ json: {\n"
    "  case_id: r.case_id, statut: r.status,\n"
    "  sujet: `IFRS 17 · dossier ${r.case_id} à valider (${(r.controls || []).length} contrôle(s) non passé(s))`,\n"
    "  message: lic ? message.replace('le formulaire est pré-rempli avec les données extraites', 'dossier de sinistres survenus : '\n"
    "    + 'comparez le triangle de la note au document ; une cellule fausse se corrige sur le site (ou rejetez)') : message,\n"
    "  formulaire: lic ? formulaireLic : formulaire, portfolio_extrait: p, autres_groupes: autres,\n"
    "  kind: r.kind || 'lrc', triangle_extrait: r.triangle || null,\n"
    "  note_provisoire_html: r.note_html || '<p>Aucune note provisoire : le document est illisible.</p>',\n"
    "} }];\n"}, (XV, YV))
link("Aiguillage", "Préparer la validation", 1)
mail("E-mail : note provisoire", (XV + 240, YV), f"={{{{ {P1}.parametres.valideur }}}}",
     "=IFRS 17 · note provisoire · dossier {{ $json.case_id }} (à valider)", "={{ $json.note_provisoire_html }}",
     p=P1, html=True)
add("E-mail : validation humaine", "emailSend", 2.1, {
    "operation": "sendAndWait", "fromEmail": f"={{{{ {P1}.parametres.expediteur }}}}",
    "toEmail": f"={{{{ {P1}.parametres.valideur }}}}",
    "subject": "={{ $('Préparer la validation').first().json.sujet }}",
    "message": "={{ $('Préparer la validation').first().json.message }}",
    "responseType": "customForm", "defineForm": "json",
    "jsonOutput": "={{ $('Préparer la validation').first().json.formulaire }}",
    "options": {"messageButtonLabel": "Vérifier les données", "responseFormTitle": "Validation du dossier IFRS 17",
                "responseFormDescription": "Le formulaire est pré-rempli avec les données extraites du document. "
                                           "Corrigez ce qui est faux, puis choisissez une décision.",
                "responseFormButtonLabel": "Envoyer ma décision", "appendAttribution": False}}, (XV + 480, YV))
add("Appliquer les corrections", "code", 2, {"jsCode":
    "// Lit la réponse du formulaire et reconstruit les données du portefeuille (PortfolioData).\n"
    "const f = $input.first().json.data;\n"
    "const prep = $('Préparer la validation').first().json;\n"
    "const nombre = (s, nom) => {\n"
    "  const t = String(s ?? '').replace(/\\s/g, '').replace(',', '.');\n"
    "  const x = Number(t);\n"
    "  if (t === '' || !Number.isFinite(x)) throw new Error(`${nom} : « ${s} » n'est pas un nombre`);\n"
    "  return x;\n"
    "};\n"
    "const liste = (s, nom) => String(s ?? '').split(';').map(t => t.trim()).filter(t => t !== '')\n"
    "  .map(t => nombre(t, nom));\n"
    "const decision = f['Décision'];\n"
    "const commentaire = f['Commentaire'] || '';\n"
    "if (decision !== 'Approuver') {\n"
    "  return [{ json: { case_id: prep.case_id, decision, commentaire } }];\n"
    "}\n"
    "if (prep.kind === 'lic') {   // dossier LIC (D-083) : le triangle lu est approuvé tel quel\n"
    "  return [{ json: { case_id: prep.case_id, decision, commentaire, triangle: prep.triangle_extrait } }];\n"
    "}\n"
    "const taux = liste(f[\"Taux d'actualisation\"], \"Taux d'actualisation\");\n"
    "const portfolio = {\n"
    "  group_id: String(f['Groupe de contrats']).trim(),\n"
    "  currency: String(f['Devise']).trim().toUpperCase(),\n"
    "  unit_multiplier: nombre(f['Unité (1, 1000 ou 1000000)'], 'Unité'),\n"
    "  premiums: liste(f['Primes par période'], 'Primes'),\n"
    "  outflows: liste(f['Sorties par période'], 'Sorties'),\n"
    "  coverage_units: liste(f['Unités de couverture par période'], 'Unités de couverture'),\n"
    "  discount_rates: taux.length === 1 ? taux[0] : (taux.length ? taux : 0),\n"
    "  risk_adjustment_pct: nombre(f['Ajustement pour risque (0 à 1)'], 'Ajustement pour risque'),\n"
    "};\n"
    "// recouvrements (B65 k, D-071) : facultatifs ; vide ou que des zéros = aucun\n"
    "const rec = liste(f['Recouvrements par période (facultatif)'], 'Recouvrements');\n"
    "if (rec.some(x => x !== 0)) portfolio.recoveries = rec;\n"
    "// frais d'acquisition (B65 e, D-075), durée de couverture (PAA, D-073) et branche (RA, D-074) : facultatifs\n"
    "const acq = liste(f[\"Frais d'acquisition par période (facultatif)\"], \"Frais d'acquisition\");\n"
    "if (acq.some(x => x !== 0)) portfolio.acquisition_costs = acq;\n"
    "const duree = String(f['Durée de couverture en mois (facultatif)'] ?? '').trim();\n"
    "if (duree) portfolio.coverage_months = Math.round(nombre(duree, 'Durée de couverture'));\n"
    "const branche = String(f['Branche (facultatif)'] ?? '').trim();\n"
    "if (branche) portfolio.line_of_business = branche;\n"
    "// ajustements de service futur : repris tels quels s'ils ont toujours le bon nombre de périodes\n"
    "for (const k of ['declared_cv', 'declared_confidence']) {   // D-082 : repris tels quels\n"
    "  const v = (prep.portfolio_extrait || {})[k];\n"
    "  if (typeof v === 'number') portfolio[k] = v;\n"
    "}\n"
    "const fsa = (prep.portfolio_extrait || {}).future_service_adjustments;\n"
    "if (Array.isArray(fsa) && fsa.length === portfolio.premiums.length) {\n"
    "  portfolio.future_service_adjustments = fsa;\n"
    "}\n"
    "return [{ json: { case_id: prep.case_id, decision, commentaire, portfolio, other_groups: prep.autres_groupes || [] } }];\n"},
    (XV + 720, YV), onError="continueErrorOutput")
add("Approuvé ?", "if", 2, cond("if/approuve", "={{ $json.decision }}", EQ, "Approuver"), (XV + 960, YV - 20))
add("Appel API /v1/case/validated", "httpRequest", 4.2, {
    "method": "POST", "url": f"={{{{ {P1}.parametres.api }}}}/v1/case/validated", **head(P1),
    "sendBody": True, "specifyBody": "json",
    "jsonBody": f"={{{{ JSON.stringify({{ portfolio: $json.portfolio || null, triangle: $json.triangle || null, other_groups: $json.other_groups || [], case_id: $json.case_id, "
                f"validated_by: {P1}.parametres.valideur, comment: $json.commentaire || null }}) }}}}",
    "options": {"timeout": 300000}}, (XV + 1200, YV - 120), onError="continueErrorOutput")
note_pdf("Note validée en PDF", (XV + 1440, YV - 120), f"{VALID}.case_id", P1)
mail("E-mail : note validée", (XV + 1680, YV - 120), f"={{{{ {P1}.parametres.valideur }}}}",
     f"=IFRS 17 · note validée{{{{ {VALID}.status === 'note_prete' ? '' : ' (contrôles de la norme à revoir)' }}}} · "
     f"{{{{ {VALID}.portfolio?.group_id ?? {VALID}.triangle?.portfolio_id ?? '' }}}} (dossier {{{{ {VALID}.case_id }}}})", f"={{{{ {VALID}.note_html }}}}", p=P1, html=True,
     **PDF_OPTS,
     ccEmail=f"={{{{ {P1}.deposant && {P1}.deposant !== {P1}.parametres.valideur ? {P1}.deposant : '' }}}}")
event("Registre : note validée envoyée", "email_note_envoyee",
      f"{{ a: {P1}.parametres.valideur, copie: {P1}.deposant, apres: 'validation' }}", (XV + 1920, YV - 120),
      case_expr="$('Appel API /v1/case/validated').first().json.case_id", p=P1)
add("Registre : rejet", "httpRequest", 4.2, {
    "method": "POST", "url": f"={{{{ {P1}.parametres.api }}}}/v1/cases/{{{{ $json.case_id }}}}/reject", **head(P1),
    "sendBody": True, "specifyBody": "json",
    "jsonBody": f"={{{{ JSON.stringify({{ comment: $json.commentaire || 'rejeté sans commentaire', "
                f"rejected_by: {P1}.parametres.valideur }}) }}}}",
    "options": {"timeout": 15000}}, (XV + 1200, YV + 60), onError="continueRegularOutput")
mail("E-mail : dossier rejeté", (XV + 1440, YV + 60), f"={{{{ {P1}.parametres.valideur }}}}",
     "=IFRS 17 · dossier {{ $('Appliquer les corrections').first().json.case_id }} rejeté",
     "=Le dossier {{ $('Appliquer les corrections').first().json.case_id }} a été rejeté lors de la validation humaine."
     "\n\nCommentaire : {{ $('Appliquer les corrections').first().json.commentaire || '(aucun)' }}\n\n"
     "Aucune note n'a été diffusée. Le rejet est inscrit dans la piste d'audit du registre.", p=P1,
     ccEmail=f"={{{{ {P1}.deposant && {P1}.deposant !== {P1}.parametres.valideur ? {P1}.deposant : '' }}}}")
mail("E-mail : erreur de validation", (XV + 1200, YV + 220), f"={{{{ {P1}.parametres.valideur }}}}",
     "=IFRS 17 · échec du dossier {{ $('Préparer la validation').first().json.case_id }}",
     "=Le dossier {{ $('Préparer la validation').first().json.case_id }} n'a pas pu être terminé.\n\n"
     "Cause : {{ $json.error?.message ?? $json.error ?? JSON.stringify($json) }}\n\n"
     "Vérifiez les données saisies (nombres, points-virgules entre les périodes) ou l'API, puis relancez le dossier.", p=P1)
chain("Préparer la validation", "E-mail : note provisoire", "E-mail : validation humaine", "Appliquer les corrections")
link("Appliquer les corrections", "Approuvé ?", 0)
link("Appliquer les corrections", "E-mail : erreur de validation", 1)
link("Approuvé ?", "Appel API /v1/case/validated", 0)
link("Approuvé ?", "Registre : rejet", 1)
link("Appel API /v1/case/validated", "Note validée en PDF", 0)
link("Note validée en PDF", "E-mail : note validée")
link("Appel API /v1/case/validated", "E-mail : erreur de validation", 1)
chain("E-mail : note validée", "Registre : note validée envoyée")
chain("Registre : rejet", "E-mail : dossier rejeté")

# ============================================================================ 3. e-mail sans document
mail("E-mail : aucun document", (XD, 400), f"={{{{ {PI}.deposant }}}}",
     "=Re: {{ $json.sujet }} · aucun document joint",
     "=Bonjour,\n\nVotre envoi ne contient pas de document exploitable. Joignez l'état du portefeuille en PDF, PNG ou "
     "JPEG (et gardez « IFRS17 » dans l'objet d'un e-mail).")
link("Aiguillage", "E-mail : aucun document", 2)

# ============================================================================ 4. santé de l'API
YS = Y["sante"]
add("Santé de l'API", "httpRequest", 4.2, {"method": "GET", "url": f"={{{{ {P1}.parametres.api }}}}/health",
                                           "options": {"timeout": 10000}}, (XD, YS), onError="continueErrorOutput")
add("État changé ?", "code", 2, {"jsCode":
    "// Compare à l'état précédent (gardé dans le workflow) : une alerte à la panne, une au retour,\n"
    "// jamais une toutes les 15 minutes. Les données statiques ne persistent qu'en production (workflow activé).\n"
    "const memo = $getWorkflowStaticData('global');\n"
    "const r = $input.first().json;\n"
    "const ok = r.status === 'ok';\n"
    "const avant = memo.etat ?? 'ok';\n"
    "memo.etat = ok ? 'ok' : 'panne';\n"
    "const detail = ok ? '' : String(r.error?.message ?? JSON.stringify(r)).slice(0, 500);\n"
    "return [{ json: { changement: memo.etat !== avant, etat: memo.etat, detail, version: r.version ?? '' } }];\n"},
    (XD + 260, YS))
add("Alerter ?", "if", 2, cond("if/alerte", "={{ $json.changement }}", TRUE, validation="loose"), (XD + 500, YS))
mail("E-mail : état de l'API", (XD + 740, YS - 20), f"={{{{ {P1}.parametres.valideur }}}}",
     "=IFRS 17 · API {{ $json.etat === 'ok' ? 'rétablie' : 'injoignable' }}",
     "={{ $json.etat === 'ok' ? 'L\\'API répond de nouveau (version ' + $json.version + ').' : "
     "'L\\'API ne répond pas au contrôle de santé : ' + $json.detail + '\\nLes dossiers reçus par e-mail ou formulaire "
     "échoueront tant qu\\'elle est arrêtée. Relancer : .\\\\make.ps1 serve' }}", p=P1)
link("Aiguillage", "Santé de l'API", 3)
link("Santé de l'API", "État changé ?", 0)
link("Santé de l'API", "État changé ?", 1)       # API muette : même contrôle, la réponse contient l'erreur
chain("État changé ?", "Alerter ?", "E-mail : état de l'API")

# ============================================================================ 5. rapport hebdomadaire
YR = Y["rapport"]
add("Tableau de bord (7 jours)", "httpRequest", 4.2, {
    "method": "GET", "url": f"={{{{ {P1}.parametres.api }}}}/v1/dashboard?days=7", **head(P1),
    "options": {"timeout": 20000}}, (XD, YR), onError="continueErrorOutput")
add("Mettre en forme le rapport", "code", 2, {"jsCode":
    "const d = $input.first().json;\n"
    "const pct = x => `${Math.round((x || 0) * 100)} %`;\n"
    "const s = d.par_statut || {};\n"
    "const semaine = (d.par_jour || []).reduce((a, j) => a + j.dossiers, 0);\n"
    "const ligne = (k, v) => `<tr><td style=\"padding:6px 12px;border-bottom:1px solid #ddd\">${k}</td>"
    "<td style=\"padding:6px 12px;border-bottom:1px solid #ddd;text-align:right\"><b>${v}</b></td></tr>`;\n"
    "const attente = (d.en_attente || []).map(w => `<li>${w.case_id} (depuis ${w.depuis.slice(0, 10)})</li>`).join('') || '<li>aucun</li>';\n"
    "const html = `<div style=\"font-family:Segoe UI,Arial,sans-serif;color:#1B2A41;max-width:620px\">\n"
    "<h2 style=\"font-family:Georgia,serif\">IFRS 17 Copilot · rapport de la semaine</h2>\n"
    "<table style=\"border-collapse:collapse;width:100%\">${[\n"
    "  ligne('Dossiers déposés sur 7 jours', semaine), ligne('Dossiers au registre (total)', d.dossiers),\n"
    "  ligne('Note produite sans intervention', pct(d.taux_note_directe)), ligne('Validation humaine demandée', pct(d.taux_validation_humaine)),\n"
    "  ligne('Validés / rejetés', `${s.validee || 0} / ${s.rejetee || 0}`), ligne('En attente d\\'un valideur', s.validation_humaine || 0),\n"
    "  ligne('Durée médiane d\\'analyse', d.duree_mediane_s == null ? '—' : `${Math.round(d.duree_mediane_s)} s`),\n"
    "  ligne('Appels LLM par dossier', d.appels_llm_moyens), ligne('Coût des modèles', `${d.cout_total_usd} $`),\n"
    "].join('')}</table>\n<h3 style=\"font-family:Georgia,serif\">En attente de validation</h3><ul>${attente}</ul>\n"
    "<p style=\"color:#6B7A8F;font-size:13px\">Détail et piste d'audit : site, pages Tableau de bord et Dossiers.</p></div>`;\n"
    "return [{ json: { html } }];\n"}, (XD + 260, YR - 60))
mail("E-mail : rapport hebdomadaire", (XD + 500, YR - 60), f"={{{{ {P1}.parametres.valideur }}}}",
     "=IFRS 17 · rapport de la semaine du {{ $now.minus({ days: 7 }).toFormat('dd/MM') }} au {{ $now.toFormat('dd/MM/yyyy') }}",
     "={{ $json.html }}", p=P1, html=True)
mail("E-mail : rapport impossible", (XD + 260, YR + 100), f"={{{{ {P1}.parametres.valideur }}}}",
     "=IFRS 17 · rapport hebdomadaire impossible",
     "=Le tableau de bord n'a pas pu être lu : {{ String($json.error?.message ?? $json.error ?? '').slice(0, 500) }}", p=P1)
link("Aiguillage", "Tableau de bord (7 jours)", 4)
link("Tableau de bord (7 jours)", "Mettre en forme le rapport", 0)
link("Tableau de bord (7 jours)", "E-mail : rapport impossible", 1)
chain("Mettre en forme le rapport", "E-mail : rapport hebdomadaire")

# ============================================================================ 6. alerte d'erreur
mail("E-mail : alerte d'erreur", (XD, Y["erreur"]), f"={{{{ {P1}.parametres.valideur }}}}",
     "=IFRS 17 · alerte n8n · nœud « {{ $json.noeud }} » en échec",
     "=Workflow : {{ $json.workflow }}\nNœud en échec : {{ $json.noeud }}\nErreur : {{ $json.message }}\n"
     "Exécution : {{ $json.url }}\nMode : {{ $json.mode }}\n\n"
     "Vérifier l'API (page /health) et les identifiants SMTP/IMAP, puis relancer l'exécution depuis n8n.", p=P1)
link("Aiguillage", "E-mail : alerte d'erreur", 5)

# ============================================================================ notes (lecture du workflow)
sticky("Note : entrées", "## Entrées\nSept déclencheurs. Chacun prépare ses données et indique son **flux** "
       "(dossier, validation, sans_document, sante, rapport, erreur).\n\nIMAP : objet contenant **IFRS17**, "
       "pièce jointe PDF/PNG/JPEG.\nFormulaire : `/form/ifrs17-depot`.\nWebhook : `POST /webhook/ifrs17/depot`.",
       (X0 - 40, Y["imap"] - 260), 520, 200, 7)
sticky("Note : paramètres", "## Réglages\nTout se règle dans **Paramètres** : adresse du valideur, expéditeur, "
       "URL de l'API, jeton.\n\nNe jamais exporter avec vos vraies valeurs.", (XP - 40, -120), 440, 220, 3)
sticky("Note : dossier", "## 1. Dossier\n`/v1/case` : extracteur → calculateur → RAG + vérificateur → rédacteur.\n"
       "Note prête → déposant. Contrôle non passé → validation humaine (webhook ci-dessous) + accusé de réception. "
       "Document illisible ou API en panne → e-mails.", (XD - 40, YD - 480), 700, 220, 4)
sticky("Note : validation", "## 2. Validation humaine (human-in-the-loop)\nn8n envoie la note provisoire puis un "
       "e-mail **Vérifier les données** et attend. Le formulaire est pré-rempli ; Approuver → `/v1/case/validated` "
       "recalcule et la note part (déposant en copie) ; Rejeter → registre + e-mail.", (XV - 40, YV - 330), 700, 200, 6)
sticky("Note : supervision", "## 4-6. Supervision\nSanté de l'API toutes les 15 min (alerte au changement d'état), "
       "rapport le lundi à 8 h, alerte pour toute erreur de ce workflow (Error Trigger interne).",
       (XD - 40, YS - 220), 700, 160, 5)

wf = {"name": "IFRS 17 Copilot — processus complet", "nodes": NODES, "connections": CONNS, "active": False,
      "settings": {"executionOrder": "v1"}, "pinData": {}, "tags": []}
OUT.write_text(json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("écrit", OUT, len([n for n in NODES if n["type"] != "n8n-nodes-base.stickyNote"]), "nœuds")
