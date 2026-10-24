# Workflow n8n : IFRS 17 Copilot, processus complet

**Un seul fichier à importer : `ifrs17_copilot.json`.** Il contient tout le processus, du dépôt du document
à l'envoi de la note validée, plus la supervision et les alertes (D-064).

```
 ENTRÉES (7 déclencheurs)                         AIGUILLAGE                 TRAITEMENT
 ─────────────────────────                         ──────────                 ──────────
 E-mail « IFRS17 » + PDF (IMAP) ──┐                             ┌─ dossier ──► /v1/case ─┬─ note prête ──► e-mail au déposant
 Formulaire /form/ifrs17-depot ───┤                             │                        ├─ à valider ──► webhook de validation
 POST /webhook/ifrs17/depot ──────┤                             │                        │                + accusé de réception
                                  │                             │                        ├─ illisible ──► e-mail d'explication
 POST /webhook/ifrs17/validation ─┤   ┌────────────┐  ┌───────┐  │                        └─ API en panne ► e-mail + alerte équipe
   (API / site web, ou la         ├──►│ Paramètres │─►│Switch │──┼─ validation ─► note provisoire ► e-mail « Vérifier les données »
    branche dossier ci-contre)    │   └────────────┘  └───────┘  │                (n8n attend) ► formulaire pré-rempli
 Toutes les 15 min ───────────────┤                             │                ├─ Approuver ► /v1/case/validated ► note validée
 Chaque lundi à 8 h ──────────────┤                             │                └─ Rejeter ──► registre + e-mail de rejet
 Erreur du workflow ──────────────┘                             ├─ sans_document ► « aucun document joint »
                                                                ├─ sante ──► /health ► alerte à la panne et au retour
                                                                ├─ rapport ► /v1/dashboard ► rapport HTML par e-mail
                                                                └─ erreur ─► e-mail d'alerte (nœud, message, lien)
```

- **Un seul nœud de réglages**, « Paramètres » : adresse du valideur, expéditeur, URL de l'API, jeton.
- **Human-in-the-loop** : tout dossier dont un contrôle échoue attend la décision d'un valideur (Send and Wait).
  Chaque validation est une exécution séparée : un e-mail portant trois PDF ouvre trois formulaires indépendants.
- **Note en PDF** : la note arrive dans le corps de l'e-mail (HTML) **et en pièce jointe PDF**, imprimée par
  l'API avec Edge ou Chrome (`GET /v1/cases/{id}/note.pdf`, D-065). Si l'API ne trouve pas de navigateur,
  l'e-mail part quand même, sans pièce jointe.
- **Traçabilité** : chaque e-mail envoyé, chaque transmission, approbation et rejet est inscrit dans la piste
  d'audit du registre de l'API (visible sur le site, page Dossiers).
- **Alertes sans réglage** : le workflow contient un Error Trigger ; n8n le lance automatiquement pour toute
  erreur de ce workflow en production (workflow d'erreur interne).

## Installation (une fois, environ 15 minutes)

Prérequis : l'API tourne (`.\make.ps1 serve`), n8n 2.42.3 tourne (`.\make.ps1 n8n`, Node.js 24+), http://localhost:5678.

1. **Mot de passe d'application Gmail** : compte Google → Sécurité → Validation en deux étapes (activée) →
   **Mots de passe des applications** → créer « n8n », copier les 16 caractères.
2. **Credentials dans n8n** (Credentials → Add credential) :
   - **SMTP** : User = votre adresse Gmail ; Password = les 16 caractères ; Host `smtp.gmail.com` ; Port `465` ; SSL/TLS activé.
   - **IMAP** : même User et Password ; Host `imap.gmail.com` ; Port `993` ; SSL/TLS activé.
3. **Importer** : Workflows → **Import from file** → `workflows/ifrs17_copilot.json`.
4. **Credentials des nœuds** : ouvrir le nœud « E-mail reçu (IMAP) » et choisir le credential IMAP ; ouvrir chacun
   des 15 nœuds « E-mail : … » et choisir le credential SMTP (n8n le propose d'office quand il n'y en a qu'un ;
   vérifier qu'aucun nœud ne reste marqué en rouge).
5. **Paramètres** : ouvrir le nœud « Paramètres », remplacer `votre.adresse@gmail.com` (deux fois) par votre
   adresse et `change-moi` par la valeur d'`API_TOKEN` du `.env`. Si l'API tourne sur Colab, remplacer
   `http://127.0.0.1:8000` par l'URL du tunnel (garder `127.0.0.1`, pas `localhost` : F-002).
6. **Activer** le workflow (bouton *Active* / *Publish*). L'IMAP, les horaires, le formulaire et la validation
   n'utilisent que les URL de production (`/webhook/…`, `/form/…`), qui n'existent qu'une fois le workflow activé.
7. **Site web → n8n** : dans `.env`, la ligne suivante (inchangée), puis relancer l'API :

   ```
   N8N_VALIDATION_URL=http://127.0.0.1:5678/webhook/ifrs17/validation
   ```

Si les anciens workflows séparés (`par_etape/`) sont encore importés, les **désactiver** : ils déclarent les
mêmes chemins de webhook et n8n refuserait d'activer le workflow unique.

**Ne jamais réexporter avec vos vraies valeurs** : remettre `votre.adresse@gmail.com` et `change-moi` avant de
committer. Les identifiants SMTP/IMAP restent dans n8n ; ils ne sont pas dans le fichier exporté.

## Essayer chaque flux

| Flux | Comment le déclencher | Résultat attendu |
| --- | --- | --- |
| Dossier, note directe | e-mail à vous-même, objet `IFRS17 test`, pièce jointe `data/synth/ext01.pdf` | la note en 1 à 3 min, dans l'e-mail et en PDF joint |
| Dossier à valider | même chose avec `data/synth_hard/dur10.pdf` (deux groupes) | accusé de réception, puis (valideur) note provisoire et e-mail « Vérifier les données » |
| Validation | cliquer **Vérifier les données**, corriger si besoin, **Approuver** | note validée (déposant en copie) ; **Rejeter** → e-mail de rejet |
| Formulaire | ouvrir http://localhost:5678/form/ifrs17-depot | mêmes e-mails que par l'IMAP |
| Webhook (démo sans boîte mail) | voir ci-dessous | mêmes e-mails |
| Site web | page « Analyser un dossier » avec `dur10.pdf` | « E-mail envoyé au valideur », puis le formulaire par e-mail |
| E-mail sans document | e-mail `IFRS17` sans pièce jointe | réponse « aucun document joint » |
| Santé de l'API | arrêter l'API | « API injoignable » au contrôle suivant (15 min au plus), « API rétablie » au redémarrage |
| Rapport | ouvrir le déclencheur « Chaque lundi à 8 h » → **Execute step** | le rapport de la semaine par e-mail |
| Alerte d'erreur | provoquer une erreur en production (ex. jeton faux dans Paramètres puis dépôt) | e-mail « alerte n8n » |

```powershell
curl.exe -X POST http://localhost:5678/webhook/ifrs17/depot -F "file=@data/synth_hard/dur10.pdf" -F "email=votre.adresse@gmail.com"
```

n8n répond aussitôt « Workflow was started » ; la suite arrive par e-mail. Sans champ `email`, la note part au valideur.

Le lien du formulaire de validation pointe vers `http://localhost:5678` : cliquer depuis l'ordinateur où tourne
n8n. L'état « API en panne » est gardé dans les données statiques du workflow, conservées seulement en production.
Documents fictifs uniquement.

## Pour la démonstration

1. Montrer le workflow dans l'éditeur : les notes jaunes, vertes et violettes délimitent les six branches.
2. Envoyer `dur10.pdf` par le formulaire, ouvrir l'onglet **Executions** pendant l'analyse.
3. Montrer l'accusé de réception, puis l'e-mail du valideur ; corriger, **Approuver**.
4. Ouvrir la note validée, puis le dossier sur le site (page Dossiers) : sa piste d'audit montre le dépôt,
   l'analyse, la transmission, l'approbation (avec l'adresse du valideur) et l'envoi.

Prévoir un enregistrement vidéo de ce parcours au cas où le réseau ou Gmail ferait défaut le jour J.

## Fichiers

- `ifrs17_copilot.json` : le workflow à importer (le livrable).
- `generer.py` : le script qui l'écrit (`python workflows/generer.py`). Après une modification faite dans
  l'interface de n8n, réexporter plutôt le workflow (Download) par-dessus `ifrs17_copilot.json`.
- `par_etape/` : les onze workflows séparés construits pendant le projet (historique, D-041, D-059).

Ce fichier a été généré à partir des paramètres des nœuds lus dans le code source de n8n 2.42.3 et ses nœuds
Code ont été exécutés hors de n8n ; il **doit être importé et essayé une fois dans n8n** avant la soutenance.
