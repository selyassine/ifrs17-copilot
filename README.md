# IFRS 17 Copilot

Copilote multi-agent pour l'analyse de contrats d'assurance sous IFRS 17 : il lit un document (PDF, image, question vocale), retrouve les paragraphes de la norme applicables, calcule la marge sur services contractuels (CSM) et livre une note justifiée et citée. Le tout est déclenché de bout en bout par n8n.

> Projet pédagogique. Le moteur de calcul couvre un périmètre simplifié (modèle général) et n'a aucune valeur de conseil comptable.

## État (sprint 2 en cours)

| Composant | Statut |
| --- | --- |
| Schémas Pydantic des 6 agents | fait, testé |
| Moteur CSM v0 (§38, §44, §47, B119) | fait, 10 tests contre calculs manuels |
| Client LLM (tout fournisseur compatible, repli, réessais, traces) | fait, testé avec un fournisseur factice |
| Routeur (heuristique + LLM) | fait ; heuristique 95 % sur 20 cas |
| API FastAPI : `/health`, `/v1/route`, `/v1/csm/compute` | fait |
| Workflows n8n 01 et 02 | validés de bout en bout (n8n → API) |
| Notebook 00 (test T4 + tunnel) | à exécuter sur Colab |
| RAG : ingestion du règlement 2021/2036 (397 paragraphes), découpages A/B, BM25, dense, hybride, `/v1/search` | fait ; dense à mesurer avec BGE-M3 |
| Évaluation du retrieval (56 questions, IC bootstrap) | BM25 fait : `eval/retrieval_report.md` |
| Routeur LLM (Groq gpt-oss-20b) | 100 % sur 20 cas |
| Agent RAG : réponse citée et vérifiée, refus, `POST /v1/ask` | 56 questions : 6/6 pièges refusés, 0 faux refus, 0 citation inventée ; relecture humaine (prompt v2, titres hiérarchiques) : 43/50 sans erreur, 37/50 complètes ; optimisation arrêtée (D-026) |
| Extracteur (PDF texte → données → contrôle d'ancrage → CSM), `POST /v1/extract`, `POST /v1/case/document` | fait, testé avec un LLM factice ; à mesurer sur 15 documents synthétiques |
| Mode image, voix, vérificateur, rédacteur | S3-S4 |

## Installation (sans Docker)

Prérequis : **Python 3.11 ou 3.12**, **Node.js 20 ou 22 LTS** (pour n8n ; vérifier les versions supportées dans la documentation n8n), Git.

**Linux / macOS**

```bash
git clone <url-du-depot> && cd ifrs17-copilot
make setup                 # crée .venv, installe, copie .env.example en .env
source .venv/bin/activate
make test                  # tous les tests doivent passer
make serve                 # API sur http://localhost:8000/docs
make n8n                   # (autre terminal) n8n sur http://localhost:5678
```

**Windows (PowerShell)**

```powershell
git clone <url-du-depot>; cd ifrs17-copilot
.\make.ps1 setup
.\.venv\Scripts\Activate.ps1
.\make.ps1 test
.\make.ps1 serve
.\make.ps1 n8n             # (autre terminal)
```

Puis importer `workflows/01_route.json` dans n8n et suivre `workflows/README.md`.

### Premier test sans n8n

```bash
curl -X POST http://localhost:8000/v1/csm/compute \
  -H "Content-Type: application/json" -H "X-API-Token: change-moi" \
  -d '{"group_id":"G1","premiums":[100,0,0],"outflows":[30,30,30],"coverage_units":[1,1,1],"discount_rates":0.05,"risk_adjustment_pct":0.05}'
```

Résultat attendu : `initial_csm` ≈ 14,22 (détail dans `docs/engine_hand_calcs.md`).

### Construire l'index et chercher dans la norme

```powershell
# placer le PDF du règlement dans data\corpus\C002_reg_2021_2036_fr.pdf
.\make.ps1 index           # unités + chunks A et B
.\make.ps1 eval            # rapport eval\retrieval_report.md
```

Puis `POST /v1/search` avec `{"query": "Comment la CSM est-elle libérée ?"}` : renvoie les paragraphes (B119, 44…) avec leur texte. Recherche dense : `.\make.ps1 index-dense` puis `RAG_MODE=hybrid` et `RAG_EMBED_MODEL=BAAI/bge-m3` dans `.env`.

### Tester l'API depuis PowerShell (accents)

Windows PowerShell n'envoie pas l'UTF-8 par défaut : convertir le corps avant l'envoi (F-007).

```powershell
$body = @{query = "Comment la CSM est-elle libérée ?"; k = 3} | ConvertTo-Json
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/search -Headers @{"X-API-Token"="change-moi"} `
  -ContentType "application/json; charset=utf-8" -Body $bytes | ConvertTo-Json -Depth 5
```

### Poser une question sur la norme

```powershell
$body = @{question = "Comment la CSM est-elle libérée en résultat ?"} | ConvertTo-Json
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/ask -Headers @{"X-API-Token"="change-moi"} `
  -ContentType "application/json; charset=utf-8" -Body $bytes | ConvertTo-Json -Depth 6
```

Réponse : `plan` (décision du routeur), `answer` (texte avec [§…], citations vérifiées ou refus motivé), `sources` (extraits fournis au LLM), `warnings`, `corrections`.

### Lire un document client et calculer le CSM

```powershell
python -m multimodal.synth                     # 15 documents de test dans data\synth\
curl.exe -X POST http://127.0.0.1:8000/v1/case/document -H "X-API-Token: change-moi" -F "file=@data/synth/ext01.pdf"
```

Réponse : `status` (ok / a_verifier / echec), `portfolio` (données extraites), `issues` (chiffres introuvables dans le document), `next_step` et `csm` si le calcul a pu partir.

### Brancher un vrai LLM

Dans `.env` : `LLM_PROVIDER=openai_compatible`, puis `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_SMALL`, `LLM_MODEL_LARGE`. Tout service exposant `POST /chat/completions` fonctionne, y compris un modèle servi sur Colab derrière le tunnel. Ensuite : `ROUTER_MODE=llm` et `python -m eval.eval_router --llm` pour comparer au routeur heuristique.

## Architecture

```
n8n (déclencheurs) ──► FastAPI ──► Orchestrateur + Routeur
                                    ├── Extracteur multimodal  → PortfolioData
                                    ├── Chercheur RAG          → GroundedAnswer (citations §)
                                    ├── Calculateur            → CsmResult (engine/csm.py)
                                    ├── Vérificateur           → Verdict (ok / à corriger ≤ 2 / humain)
                                    └── Rédacteur              → note PDF
n8n (sortie) ◄── e-mail, approbation humaine, traces JSONL
```

Le LLM ne fait jamais de calcul (D-005) ; toutes les sorties d'agent sont validées par Pydantic (D-007).

## Structure

| Dossier | Contenu |
| --- | --- |
| `api/` | Endpoints FastAPI appelés par n8n |
| `agents/` | Schémas de sortie, routeur ; les autres agents arrivent en S2-S3 |
| `core/` | Configuration, client LLM, traces JSONL, chargement des prompts |
| `engine/` | Moteur IFRS 17 (Python pur) |
| `prompts/` | Bibliothèque de prompts versionnée (YAML) |
| `rag/` | Ingestion, découpage, recherche (voir `rag/README.md`) |
| `multimodal/` | S3 |
| `workflows/` | Exports JSON n8n |
| `eval/` | Jeux de test et scripts d'évaluation |
| `notebooks/` | Expériences Colab (test T4, benchmarks, QLoRA) |
| `data/` | Hors Git, sauf le manifeste du corpus |
| `docs/` | Registre des décisions, journal des échecs, calculs manuels |

## Règles d'équipe

- Une branche par tâche, pull request relue par une autre personne, CI verte avant fusion.
- Aucun document du corpus, aucune clé API, aucune sortie de notebook dans Git (`nbstripout` s'en charge).
- Chaque choix technique va dans `docs/decisions.md`, chaque échec dans `docs/failures.md`.
- Un composant est « fini » quand il est appelable par l'API, testé, mesuré et expliqué par une deuxième personne.
