# Workflows n8n

| Fichier | Déclencheur | Appelle | Rôle |
| --- | --- | --- | --- |
| `01_route.json` | `POST /webhook/ifrs17/route` | `POST /v1/route` | Test du socle S1 : n8n → API → réponse |
| `02_csm_compute.json` | `POST /webhook/ifrs17/csm` | `POST /v1/csm/compute` | Calcul du CSM à partir de données JSON |

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

En mode test l'URL contient `webhook-test` ; une fois le workflow activé, c'est `webhook`.

Ces fichiers ont été écrits à la main et doivent être importés une première fois pour vérifier qu'ils correspondent à votre version de n8n. Après toute modification dans l'interface, **réexporter** le workflow ici (Download) et committer : c'est le livrable demandé par le sujet. Penser à remettre `change-moi` à la place du vrai jeton avant de committer.
