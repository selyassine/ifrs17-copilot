# Workflows n8n

| Fichier | Déclencheur | Appelle | Rôle |
| --- | --- | --- | --- |
| `01_route.json` | `POST /webhook/ifrs17/route` | `POST /v1/route` | Test du socle S1 : n8n → API → réponse |
| `02_csm_compute.json` | `POST /webhook/ifrs17/csm` | `POST /v1/csm/compute` | Calcul du CSM à partir de données JSON |
| `03_case_document.json` | `POST /webhook/ifrs17/case` (fichier PDF, PNG ou JPEG) | `POST /v1/case` | Dossier complet : extracteur → calculateur → RAG + vérificateur → rédacteur. Note prête → la note HTML (200) ; sinon → réponse « validation humaine » (202) avec les contrôles, les données extraites et la note provisoire |
| `04_case_validated.json` | `POST /webhook/ifrs17/case/validated` (données JSON corrigées) | `POST /v1/case/validated` | Suite de la validation humaine : données corrigées → calcul → norme → note HTML |

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

**Validation humaine par e-mail (à ajouter dans l'interface)** : sur la branche « validation humaine » du workflow 03,
ajouter un nœud Gmail ou Outlook « Send and Wait for Response » (approbation) avec les contrôles et la note provisoire ;
si l'humain approuve, appeler le workflow 04 avec les données. Ce nœud dépend de vos identifiants : il n'est pas livré.

En mode test l'URL contient `webhook-test` ; une fois le workflow activé, c'est `webhook`.

Ces fichiers ont été écrits à la main et doivent être importés une première fois pour vérifier qu'ils correspondent à votre version de n8n. Après toute modification dans l'interface, **réexporter** le workflow ici (Download) et committer : c'est le livrable demandé par le sujet. Penser à remettre `change-moi` à la place du vrai jeton avant de committer.
