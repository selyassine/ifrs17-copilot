# Workflows n8n séparés (historique)

> Le livrable est désormais **un seul fichier**, `../ifrs17_copilot.json` (voir `../README.md`, D-064).
> Ces workflows, construits étape par étape, restent pour l'historique. Ne pas les activer en même temps que le
> workflow unique : les mêmes chemins de webhook (`ifrs17/validation`) et le même formulaire seraient en conflit.

| Fichier | Déclencheur | Appelle | Rôle |
| --- | --- | --- | --- |
| `01_route.json` | `POST /webhook/ifrs17/route` | `POST /v1/route` | Test du socle S1 : n8n → API → réponse |
| `02_csm_compute.json` | `POST /webhook/ifrs17/csm` | `POST /v1/csm/compute` | Calcul du CSM à partir de données JSON |
| `03_case_document.json` | `POST /webhook/ifrs17/case` (fichier PDF, PNG ou JPEG) | `POST /v1/case` | Dossier complet : extracteur → calculateur → RAG + vérificateur → rédacteur. Note prête → la note HTML (200) ; sinon → réponse « validation humaine » (202) avec les contrôles, les données extraites et la note provisoire |
| `04_case_validated.json` | `POST /webhook/ifrs17/case/validated` (données JSON corrigées) | `POST /v1/case/validated` | Suite de la validation humaine : données corrigées → calcul → norme → note HTML |
| `05_case_email.json` | `POST /webhook/ifrs17/case-email` (fichier PDF, PNG ou JPEG) | `POST /v1/case`, puis `POST /v1/case/validated` | Dossier complet **par e-mail**. Note prête → envoyée par e-mail. Sinon → e-mail de la note provisoire, puis e-mail de validation avec un **formulaire pré-rempli** (n8n attend la réponse) ; Approuver → note recalculée et envoyée ; Rejeter → e-mail de rejet |
| `06_validation_email.json` | `POST /webhook/ifrs17/validation` (dossier déjà analysé, envoyé par l'API) | `POST /v1/case/validated` | Appelé **automatiquement par l'API** quand un dossier analysé sur le site web part en validation humaine : même e-mail et même formulaire que le 05, sans relancer l'analyse |
| `07_intake_email.json` | Boîte mail (IMAP), e-mails non lus dont l'objet contient « IFRS17 » | sous-workflow 09 | Un dossier par pièce jointe PDF, PNG ou JPEG ; réponse à l'expéditeur si aucun document n'est joint |
| `08_intake_form.json` | Formulaire n8n `/form/ifrs17-depot` | sous-workflow 09 | Dépôt par une page web : adresse e-mail, nom, document, commentaire |
| `09_case_processing.json` | Appelé par 07 et 08 | `POST /v1/case`, `POST /v1/cases/{id}/events`, workflow 06 | Traitement commun : note prête → envoyée au déposant ; validation humaine → transmise au 06 et accusé de réception au déposant ; document inexploitable → explication ; échec → e-mail au déposant et alerte à l'équipe. Chaque envoi est inscrit dans la piste d'audit |
| `10_error_alerts.json` | Erreur dans un autre workflow | — | Workflow d'erreur : e-mail d'alerte (workflow, nœud, message, lien vers l'exécution) |
| `11_monitoring.json` | Toutes les 15 min ; lundi à 8 h | `GET /health`, `GET /v1/dashboard` | Alerte quand l'API tombe et quand elle revient (pas toutes les 15 min) ; rapport hebdomadaire par e-mail |

Chaque workflow a une branche d'erreur : si l'API ne répond pas ou refuse la requête, n8n renvoie un message clair avec le code 502 au lieu de rester bloqué.

## Importer

1. Lancer l'API (`make serve`) puis n8n (`make n8n`) et ouvrir http://localhost:5678.
2. Menu **Workflows → Import from file**, choisir le fichier JSON.
3. Dans le nœud « Appel API », remplacer `change-moi` par la valeur d'`API_TOKEN` du `.env`. Si l'API tourne sur Colab, remplacer `http://127.0.0.1:8000` par l'URL du tunnel.
   L'adresse est `127.0.0.1` et non `localhost` : Node.js résout `localhost` en IPv6 (`::1`) alors qu'uvicorn écoute en IPv4, ce qui donne `ECONNREFUSED ::1:8000` (voir docs/failures.md, F-002).
4. Cliquer sur **Execute workflow** (mode test), puis dans un terminal :

```bash
curl -X POST http://localhost:5678/webhook-test/ifrs17/route \
  -H "Content-Type: application/json" \
  -d '{"request": "Comment le CSM est-il ajusté ?"}'

curl -X POST http://localhost:5678/webhook-test/ifrs17/csm \
  -H "Content-Type: application/json" \
  -d '{"group_id": "G1", "premiums": [100, 0, 0], "outflows": [20, 20, 20], "coverage_units": [1, 1, 1]}'
```

Dossier complet (PowerShell : `curl.exe`, livré avec Windows 10 et 11) :

```powershell
curl.exe -X POST http://localhost:5678/webhook-test/ifrs17/case -F "file=@data/synth/ext01.pdf" -o note.html
start note.html
```

Une réponse en 1 à 3 minutes (6 agents, 8 à 12 appels LLM). Avec `data/synth_hard/dur10.pdf` (deux groupes), la
réponse est un JSON « validation humaine » : corriger `donnees_extraites` puis l'envoyer au workflow 04.

## Workflow 05 : validation humaine par e-mail et formulaire

Le workflow 05 envoie les résultats par e-mail et fait valider les dossiers douteux par un humain, sans quitter sa boîte mail :

1. le dossier passe par `/v1/case` ;
2. **note prête** → la note HTML part par e-mail ;
3. **validation humaine** → deux e-mails : la note provisoire (HTML), puis un e-mail « à valider » qui liste les contrôles non passés, avec un bouton **Vérifier les données** ; n8n met l'exécution en attente ;
4. le bouton ouvre un **formulaire n8n pré-rempli** avec les données extraites (groupe, devise, unité, primes, sorties, unités de couverture, taux, ajustement pour risque) ; l'humain corrige et choisit **Approuver** ou **Rejeter** ;
5. Approuver → `/v1/case/validated` recalcule tout (calcul, norme, note) et la note validée part par e-mail ; Rejeter → e-mail de rejet avec le commentaire ; donnée illisible ou API en panne → e-mail d'erreur.

Il utilise le nœud **Send Email** (SMTP), opération *Send and Wait for Response*, réponse *Custom Form* définie en JSON : c'est ce qui permet de pré-remplir le formulaire. Il faut une version récente de n8n : `.\make.ps1 n8n` lance n8n 2.42.3, qui demande Node.js 24 ou plus.

### Mettre en place l'e-mail (Gmail, 10 minutes, une seule fois)

1. Sur le compte Google : **Sécurité → Validation en deux étapes** (à activer si ce n'est pas fait), puis **Mots de passe des applications** → créer un mot de passe nommé « n8n ». Google affiche 16 caractères : les copier. C'est ce mot de passe, pas celui du compte, que n8n utilise.
2. Dans n8n : **Credentials → Add credential → SMTP** : User = votre adresse Gmail ; Password = les 16 caractères ; Host = `smtp.gmail.com` ; Port = `465` ; SSL/TLS = activé. **Save** (n8n teste la connexion).
3. Importer `05_case_email.json`. Ouvrir chacun des 6 nœuds « E-mail : … » et choisir ce credential SMTP.
4. Ouvrir le nœud **Paramètres** et remplacer `votre.adresse@gmail.com` (deux fois) par votre adresse, et `change-moi` par la valeur d'`API_TOKEN`.
5. **Ne jamais réexporter le workflow avec votre vraie adresse ou votre jeton** : remettre les valeurs d'exemple avant de committer. Les identifiants SMTP restent dans n8n, ils ne sont pas dans le fichier exporté.

### Depuis le site web : e-mail automatique (workflow 06)

Quand un dossier analysé sur le site (`http://127.0.0.1:8000`, page « Analyser un dossier ») part en validation humaine, l'API envoie aussitôt le dossier au workflow 06 : le valideur reçoit la note provisoire et l'e-mail avec le formulaire, sans aucun bouton à cliquer sur le site. La page affiche « E-mail envoyé au valideur » (ou la raison de l'échec). L'analyse n'est pas relancée : n8n reçoit le résultat déjà calculé.

1. Importer `06_validation_email.json`, choisir le credential SMTP dans ses 6 nœuds « E-mail : … », remplir le nœud **Paramètres** comme pour le 05, puis activer le workflow.
2. Ajouter dans `.env` la ligne suivante, puis relancer l'API (`.\make.ps1 serve`) :

```
N8N_VALIDATION_URL=http://127.0.0.1:5678/webhook/ifrs17/validation
```

Sans cette ligne, le site fonctionne comme avant et indique « E-mail non envoyé ». Un dossier dont la note est prête n'envoie pas d'e-mail depuis le site : la note s'affiche directement.

### Lancer un dossier (workflow 05)

Activer le workflow (bouton **Active** ou **Publish** selon la version), puis, dans PowerShell :

```powershell
curl.exe -X POST http://localhost:5678/webhook/ifrs17/case-email -F "file=@data/synth_hard/dur10.pdf"
```

La réponse arrive en 1 à 3 minutes (`statut`, `case_id`). Avec `dur10` (deux groupes de contrats), vous recevez la note provisoire et l'e-mail « à valider ». Cliquez sur **Vérifier les données**, vérifiez le groupe retenu (corrigez-le si besoin), puis **Approuver** : la note validée arrive quelques instants plus tard. Avec `data/synth/ext01.pdf`, la note arrive directement.

Le lien du formulaire pointe vers `http://localhost:5678` : il faut cliquer depuis l'ordinateur où tourne n8n. Documents fictifs uniquement.

En mode test l'URL contient `webhook-test` ; une fois le workflow activé, c'est `webhook`.

## Chaîne complète : du dépôt à la note (workflows 06 à 11)

```
e-mail « IFRS17 » + PDF ──► 07 ┐
                               ├─► 09 ──► /v1/case ──► note prête ───────► e-mail au déposant
formulaire n8n ───────────► 08 ┘                  ├──► validation humaine ─► 06 (valideur : formulaire pré-rempli)
                                                  │                          └─► accusé de réception au déposant
                                                  └──► échec ───────────────► e-mail au déposant + alerte équipe
10 : toute erreur de workflow → alerte          11 : santé de l'API (15 min) + rapport du lundi
```

Chaque dossier est inscrit dans le registre de l'API avec son canal (`n8n-email`, `n8n-formulaire`) et son déposant ; il apparaît aussitôt dans la page **Dossiers** du site. Les e-mails envoyés, les transmissions au valideur, les approbations (avec l'adresse du valideur) et les rejets sont ajoutés à sa piste d'audit.

### Mise en place (une fois, environ 20 minutes)

1. **Identifiants.** Le credential SMTP du workflow 05 sert à tous les nœuds « E-mail : … ». Pour le 07, créer en plus **Credentials → Add credential → IMAP** : User = votre adresse Gmail ; Password = le même mot de passe d'application de 16 caractères ; Host = `imap.gmail.com` ; Port = `993` ; SSL/TLS = activé. Dans Gmail, IMAP est activé par défaut sur les comptes récents (sinon : Paramètres → Transfert et POP/IMAP).
2. **Importer** 06, 09, 10, 11, puis 07 et 08 (dans cet ordre : 07 et 08 appellent 09).
3. **Paramètres.** Dans chaque nœud « Paramètres… », remplacer `votre.adresse@gmail.com` et `change-moi` (valeur d'`API_TOKEN`). Choisir le credential SMTP dans chaque nœud « E-mail : … ».
4. **Sous-workflow.** Dans 07 et 08, ouvrir le nœud « Traiter le dossier (09) » et choisir « 09 — Traitement d'un dossier » dans la liste *From list*.
5. **Workflow d'erreur.** Dans chaque workflow 05 à 11 : **⋯ → Settings → Error workflow** = « 10 — Alertes en cas d'erreur ».
6. **Activer** 06, 07, 08 et 11 (10 et 09 n'ont pas besoin d'être activés : ils sont appelés).

### Essayer

- **Par e-mail** : envoyer à votre propre adresse un e-mail dont l'objet contient `IFRS17`, avec `data/synth/ext01.pdf` en pièce jointe. n8n relève la boîte toutes les minutes environ ; la note arrive en 1 à 3 minutes. Avec `data/synth_hard/dur10.pdf`, vous recevez l'accusé de réception puis, comme valideur, la note provisoire et le formulaire.
- **Par formulaire** : ouvrir l'URL de production affichée dans le nœud « Formulaire de dépôt » (`http://localhost:5678/form/ifrs17-depot`), remplir, envoyer.
- **Supervision** : arrêter l'API ; l'alerte « API injoignable » arrive au contrôle suivant (15 min au plus), puis « API rétablie » après le redémarrage. Le rapport hebdomadaire se teste avec **Execute workflow** sur le déclencheur du lundi.
- **Dans le site** : page **Dossiers**, le dossier apparaît avec son canal et sa piste d'audit (dépôt, analyse, e-mail envoyé, validation).

L'état « API en panne » du workflow 11 est gardé dans les données statiques du workflow, qui ne sont conservées qu'en exécution de production (workflow activé), pas pendant un essai manuel.

Ces fichiers ont été écrits à la main et doivent être importés une première fois pour vérifier qu'ils correspondent à votre version de n8n. Après toute modification dans l'interface, **réexporter** le workflow ici (Download) et committer : c'est le livrable demandé par le sujet. Penser à remettre `change-moi` à la place du vrai jeton avant de committer.
