# IFRS 17 Copilot

Copilote multi-agent pour l'analyse de contrats d'assurance sous IFRS 17 : il lit un document (PDF, image, question vocale), retrouve les paragraphes de la norme applicables, calcule la marge sur services contractuels (CSM) et livre une note justifiée et citée. Le tout est déclenché de bout en bout par n8n.

> Projet pédagogique. Le moteur de calcul couvre un périmètre simplifié (modèle général) et n'a aucune valeur de conseil comptable.

## État (sprint 1)

| Composant | Statut |
| --- | --- |
| Schémas Pydantic des 6 agents | fait, testé |
| Moteur CSM v0 (§38, §44, §47, B119) | fait, 10 tests contre calculs manuels |
| Client LLM (tout fournisseur compatible, repli, réessais, traces) | fait, testé avec un fournisseur factice |
| Routeur (heuristique + LLM) | fait ; heuristique 95 % sur 20 cas |
| API FastAPI : `/health`, `/v1/route`, `/v1/csm/compute` | fait |
| Workflows n8n 01 et 02 | à importer et vérifier |
| Notebook 00 (test T4 + tunnel) | à exécuter sur Colab |
| RAG, extraction multimodale, vérificateur, rédacteur | S2-S3 |

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
| `rag/`, `multimodal/` | S2-S3 |
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
