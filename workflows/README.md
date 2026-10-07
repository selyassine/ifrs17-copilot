# Workflows n8n

| Fichier | Déclencheur | Appelle | Rôle |
| --- | --- | --- | --- |
| `01_route.json` | `POST /webhook/ifrs17/route` | `POST /v1/route` | Test du socle S1 : n8n → API → réponse |
| `02_csm_compute.json` | `POST /webhook/ifrs17/csm` | `POST /v1/csm/compute` | Calcul du CSM à partir de données JSON |
| `03_case_document.json` | `POST /webhook/ifrs17/case` (fichier PDF, PNG ou JPEG) | `POST /v1/case` | Dossier complet : extracteur → calculateur → RAG + vérificateur → rédacteur. Note prête → la note HTML (200) ; sinon → réponse « validation humaine » (202) avec les contrôles, les données extraites et la note provisoire |
| `04_case_validated.json` | `POST /webhook/ifrs17/case/validated` (données JSON corrigées) | `POST /v1/case/validated` | Suite de la validation humaine : données corrigées → calcul → norme → note HTML |
| `05_case_email.json` | `POST /webhook/ifrs17/case-email` (fichier PDF, PNG ou JPEG) | `POST /v1/case`, puis `POST /v1/case/validated` | Dossier complet **par e-mail**. Note prête → envoyée par e-mail. Sinon → e-mail de la note provisoire, puis e-mail de validation avec un **formulaire pré-rempli** (n8n attend la réponse) ; Approuver → note recalculée et envoyée ; Rejeter → e-mail de rejet |

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

### Lancer un dossier

Activer le workflow (bouton **Active** ou **Publish** selon la version), puis, dans PowerShell :

```powershell
curl.exe -X POST http://localhost:5678/webhook/ifrs17/case-email -F "file=@data/synth_hard/dur10.pdf"
```

La réponse arrive en 1 à 3 minutes (`statut`, `case_id`). Avec `dur10` (deux groupes de contrats), vous recevez la note provisoire et l'e-mail « à valider ». Cliquez sur **Vérifier les données**, vérifiez le groupe retenu (corrigez-le si besoin), puis **Approuver** : la note validée arrive quelques instants plus tard. Avec `data/synth/ext01.pdf`, la note arrive directement.

Le lien du formulaire pointe vers `http://localhost:5678` : il faut cliquer depuis l'ordinateur où tourne n8n. Documents fictifs uniquement.

En mode test l'URL contient `webhook-test` ; une fois le workflow activé, c'est `webhook`.

Ces fichiers ont été écrits à la main et doivent être importés une première fois pour vérifier qu'ils correspondent à votre version de n8n. Après toute modification dans l'interface, **réexporter** le workflow ici (Download) et committer : c'est le livrable demandé par le sujet. Penser à remettre `change-moi` à la place du vrai jeton avant de committer.
