# IFRS 17 Copilot

Copilote multi-agent pour l'analyse de contrats d'assurance sous IFRS 17 : il lit un document (PDF, image, question vocale), retrouve les paragraphes de la norme applicables, calcule la marge sur services contractuels (CSM) et livre une note justifiée et citée. Le tout est déclenché de bout en bout par n8n.

> Projet pédagogique. Le moteur de calcul couvre un périmètre simplifié (modèle général) et n'a aucune valeur de conseil comptable.

## Livrables du projet final (Advanced DL, ESPRIT 5DS)

| Livrable | Fichier | Remarque |
| --- | --- | --- |
| Workflow n8n (tout le processus, un seul fichier) | [`workflows/ifrs17_copilot.json`](workflows/ifrs17_copilot.json) | installation et essais : [`workflows/README.md`](workflows/README.md) |
| Dépôt et instructions | ce README (installation ci-dessous) | Windows (PowerShell) ou Linux/macOS, sans Docker |
| Rapport technique (8 pages au plus, vérifié à la génération) | [`docs/rapport/IFRS17_Copilot_rapport.pdf`](docs/rapport/IFRS17_Copilot_rapport.pdf) | outils, LLM, prompt engineering, RAG, multimodalité, agents, évaluation, sécurité |
| Annexes du rapport (fichier séparé) | [`docs/rapport/IFRS17_Copilot_annexes.pdf`](docs/rapport/IFRS17_Copilot_annexes.pdf) | A : bibliothèque de prompts ; B : commandes pour reproduire chaque mesure |
| Bibliothèque de prompts (fichier séparé) | [`prompt_library.md`](prompt_library.md) et [`docs/rapport/prompt_library.pdf`](docs/rapport/prompt_library.pdf) | générée à partir des 29 fiches versionnées de `prompts/` |
| Évaluation de la recherche | [`docs/rapport/evaluation_recherche.pdf`](docs/rapport/evaluation_recherche.pdf) | requêtes de test, résultats, commentaires ; rapports détaillés dans `eval/` |
| Dossier complet du projet (chronologie, composants, techniques, tests, rejets) | [`docs/rapport/IFRS17_Copilot_dossier_complet.pdf`](docs/rapport/IFRS17_Copilot_dossier_complet.pdf) | document interne de préparation de l'oral ; `python docs/rapport/build_dossier.py` |
| Campagne de tests « prêt pour la production ? » (4 niveaux) | [`docs/campagne_tests.md`](docs/campagne_tests.md) | volume, photos, données réelles CAS, documents de camarades, robustesse ; critères fixés d'avance |
| Registre des décisions, journal des échecs | [`docs/decisions.md`](docs/decisions.md), [`docs/failures.md`](docs/failures.md) | 99 décisions motivées et mesurées, 36 échecs documentés |

Les PDF du rapport se régénèrent avec `python docs/rapport/build.py` et `python docs/rapport/build_annexes.py` (Edge, Chrome ou Chromium).

## État (fin de projet, octobre 2026)

| Composant | Statut |
| --- | --- |
| Schémas Pydantic des 6 agents | fait, testé |
| Moteur CSM v0 (§38, §44, §47, B119) | fait, 10 tests contre calculs manuels |
| Client LLM (tout fournisseur compatible, repli, réessais, traces) | fait, testé avec un fournisseur factice |
| Routeur (heuristique + LLM) | fait ; heuristique 95 % sur 20 cas |
| API FastAPI : `/health`, `/v1/route`, `/v1/csm/compute` | fait |
| Workflows n8n 01 à 11 (construits étape par étape) | remplacés par le workflow unique ; conservés dans `workflows/par_etape/` |
| Notebooks Colab (test T4, fine-tuning de BGE-M3) | exécutés ; fine-tuning mesuré et non retenu (D-046) |
| RAG : ingestion du règlement 2021/2036 (397 paragraphes), découpages A/B, BM25, dense, hybride, `/v1/search` | fait ; dense à mesurer avec BGE-M3 |
| Évaluation du retrieval (56 questions, IC bootstrap) | BM25 fait : `eval/retrieval_report.md` |
| Routeur LLM (Groq gpt-oss-20b) | 100 % sur 20 cas |
| Agent RAG : réponse citée et vérifiée, refus, `POST /v1/ask` | 56 questions : 6/6 pièges refusés, 0 faux refus, 0 citation inventée ; relecture humaine (prompt v2, titres hiérarchiques) : 43/50 sans erreur, 37/50 complètes ; optimisation arrêtée (D-026) |
| Extracteur multimodal : PDF texte (Groq), image ou scan (Gemini), hybride ; contrôle d'ancrage ; `POST /v1/extract`, `POST /v1/case/document` | 15/15 documents justes dans les 3 modes ; jeu de 10 pièges : 0 cas dangereux (double lecture des scans) |
| Vérificateur (LLM-juge : soutien et portée de chaque phrase) + boucle de correction bornée → validation humaine ; `verdict` dans `/v1/ask` | juge ancré (v2) : 5/7 erreurs détectées, 6/41 fausses alertes, kappa 0,46 (v1 : 3/7, 3/41, 0,38) |
| Question vocale : Whisper (Groq) avec vocabulaire IFRS 17 → même chaîne que `/v1/ask` ; `POST /v1/ask/audio` | 8 enregistrements : WER 0,9 % avec vocabulaire IFRS 17 (4,8 % sans), termes reconnus 8/8 (6/8 sans) |
| **Rédacteur** (note HTML/Markdown, graphique, synthèse dont chaque nombre et chaque paragraphe sont vérifiés) et **orchestrateur** : `POST /v1/case` (document → note), `POST /v1/case/validated` (après validation humaine) ; appelés par le workflow n8n | 10 dossiers piégés de bout en bout : 0 cas dangereux, CSM juste 7/7, synthèses acceptées 9/9 ; démo n8n → note validée ; réponses de référence (`python -m agents.reference`) ; note et validation humaine par e-mail, formulaire pré-rempli (`workflows/README.md`) |
| **Interface web** (`/app/`) : dossier suivi en direct (flux SSE), données extraites corrigeables puis validées, questions écrites ou vocales à la norme, résultats mesurés | servie par l'API, sans dépendance externe ; 2 tests |
| **Moteur complet du cours** : modèle général pluriannuel (`POST /v1/csm/rollforward` : BEL au taux courant, OCI, RA, écarts d'expérience, perte, compte de résultat) et PAA (`POST /v1/paa/position`) | exemples chiffrés d'un cours IFRS 17 retrouvés à l'euro près (tests/test_engine_cours.py) ; quiz du cours = jeu d'évaluation hors échantillon |
| **Adaptation du modèle d'embedding** (mesurée, non retenue) : paires question → passage générées par le LLM, filtre de fuite contre les jeux de test, négatifs difficiles BM25, entraînement contrastif de BGE-M3 sur Colab T4 (`python -m rag.finetune`, notebooks/01) | critères fixés avant l'entraînement ; quiz Recall@5 0,200 → 0,200, jeu principal sans écart significatif : non retenu (D-046, F-013) |
| **RAG avancé et agentique** : agent de recherche **LangGraph** (planifier → chercher → évaluer les passages → nouvelle recherche bornée), Graph RAG sur les renvois de la norme, reranker cross-encoder, query indexing | protocole pré-enregistré (30 cas pratiques gelés avant le développement) ; cas pratiques Recall@5 0,517 → **0,750** avec l'agent (retenu), 0,683 avec index des questions + graphe sans LLM ; les deux ne s'additionnent pas (D-048 à D-051) |
| **Base vectorielle Qdrant** : embarquée ou serveur (Docker), métadonnées et filtre par zone, collection liée à l'empreinte des textes | mêmes résultats que la recherche exacte NumPy (tests/test_qdrant.py, `python -m rag.qdrant_sync`) (D-052) |
| **Registre, comptes et piste d'audit** : chaque dossier inscrit (canal, déposant, empreinte du document, statut, chiffres, note, coût) ; événements chaînés par SHA-256 ; rôles analyste, valideur, admin ; tableau de bord, registre et administration dans le site | tests/test_registry.py, tests/test_api.py ; altération de la piste détectée (D-058) |
| **Périmètre actuariel élargi** (D-071 à D-078) : recouvrements (B65 k), frais d'acquisition (B65 e), PAA dans la note (§53 à §59), RA calibré par branche (§119), première clôture (`POST /v1/case/cloture`), plusieurs groupes par document, registre des hypothèses versionné, grille de relecture | double calcul avec le script R de l'équipe : 50/50 dossiers identiques au centime ; back-testing de 50 dossiers réels et 25 premières clôtures (rapprochement exact) ; 297 tests |
| **Classeurs Excel (.xlsx) et CSV** (D-079) : chaque feuille devient un tableau lu comme un PDF, provenance à la cellule, formules sans valeur et feuilles cachées signalées | 1er lot : 17/19 CSM justes, 1 cas dangereux (montant au format %, F-021), corrigé par un contrôle de vraisemblance (D-080) ; jeu corrigé de 22 classeurs (dont 7 pièges) : CSM 19/19, 3/3 alertes, 0 dangereux |
| **Unité ancrée et hypothèses du RA annoncées** (D-081, D-082) : l'unité des montants doit être écrite dans le document ; volatilité et niveau de confiance du document lus et rapprochés du registre dans la note | 0 fausse alerte d'unité sur 187 documents connus et sur 75 documents lus par le LLM, 338/338 erreurs simulées détectées ; dossier A : RA au quantile 75 % avec son CV, 65 % avec le registre |
| **Passif pour sinistres survenus (LIC)** (D-083) : triangle reconnu, lu par le LLM et relu par le code ; Chain Ladder, erreur de Mack, actualisation, RA ; note écrite par le code ; site et n8n | Mack (1993) reproduit au franc près ; 8 triangles CAS lus par le LLM : triangle juste 7/7, LIC au centime 7/7, 0 dangereux ; dossier C : LIC 17 634,74 |
| **Copilot et note d'un dossier LIC** (D-087) : outils propres (scénario taux, queue, niveau de confiance ; détail par survenance ; paiements futurs), points d'attention et contrôle Bornhuetter-Ferguson dans la note | jeu gelé de 6 questions : chiffre 6/6, piège 1/1, relecture humaine 3/6 (F-026) |
| **Copilot v4** (D-084) et **mesures d'équipe** (D-085, [`docs/protocole_mesures_equipe.md`](docs/protocole_mesures_equipe.md)) | v4 sur 10 questions gelées : 8/10, **piège d'injection obéi** (F-023) → garde-fous par le code (D-086) : 5/5 pièges neufs refusés ; routeur externe, photos, n8n |
| **Processus n8n complet en un seul workflow** (`workflows/ifrs17_copilot.json`, D-064) : dépôt par e-mail (IMAP), formulaire ou webhook, analyse, validation humaine par formulaire pré-rempli, accusés de réception, traces dans le registre, alertes d'erreur, supervision de l'API et rapport hebdomadaire | paramètres vérifiés dans le code source de n8n 2.42.3, 14 tests ; essai réel le 19/10/2026 (Windows, Gmail) : note prête avec PDF, validation humaine complète jusqu'à la note validée |

## Installation (sans Docker)

Prérequis : **Python 3.11 ou 3.12**, **Node.js 24 ou plus** (n8n 2.42, version fixée dans `make.ps1` et `Makefile`, refuse Node 22), Git.

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

Puis importer **un seul fichier**, `workflows/ifrs17_copilot.json` (tout le processus n8n), et suivre `workflows/README.md`.

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

### Dossier complet : document → note IFRS 17

```powershell
curl.exe -X POST http://127.0.0.1:8000/v1/case -H "X-API-Token: change-moi" -F "file=@data/synth/ext01.pdf" -o dossier.json
```

`status` : `note_prete`, `validation_humaine` ou `document_illisible` ; `steps` : le journal des 6 agents ; `note_html` : la note à envoyer.

La note est une **note actuarielle complète** (D-055), de 9 à 10 pages A4 :
- page de garde et sommaire ;
- 10 sections : résumé exécutif, objet et méthode, données, hypothèses avec références à la norme, évaluation initiale, évolution de la CSM, projection du compte de résultat et du passif, sensibilités avec seuils de bascule, fondements cités, contrôles et bloc de validation ;
- annexes : traçabilité et glossaire.

Tous les chiffres viennent du moteur (`engine/analysis.py`). Le LLM n'écrit que le résumé et le commentaire des sensibilités, et le code vérifie chaque nombre. Dans le site, le bouton « Imprimer ou enregistrer en PDF » ouvre la boîte d'impression ; la note a sa propre mise en page A4.

### Copilot : un agent qui choisit ses outils

```powershell
python -m eval.eval_copilot          # 16 questions (dont 3 questions de suite), chiffres attendus calculés par le moteur
```

Dans le site, après l'analyse d'un dossier, l'onglet **Copilot** accepte des questions comme « le groupe reste-t-il bénéficiaire si les sinistres augmentent de 15 % ? ». L'agent (LangGraph) choisit seul ses outils, qui sont tous en lecture seule : données, scénario, sensibilités, niveau de confiance de l'ajustement pour risque, projection, recherche dans la norme. Le code vérifie que chaque nombre de sa réponse vient d'un outil (D-057). API : `POST /v1/copilot` avec `{question, portfolio}`.

**Mémoire et état (D-061).** Le Copilot se souvient du dossier : les trois derniers échanges contrôlés et les décisions du valideur sont placés dans son contexte, les plus anciens se retrouvent avec l'outil `memoire_du_dossier` ; une question de suite (« et à 25 % ? ») est donc comprise. Avec LangGraph, l'état du graphe est sauvegardé après chaque étape (`data/copilot_checkpoints.db`, paquet `langgraph-checkpoint-sqlite`) : l'onglet Copilot montre la trajectoire de chaque réponse (décider, agir, vérifier) et un valideur peut la rejouer depuis n'importe quel point de reprise. API : `GET /v1/copilot/{dossier}` (mémoire et points de reprise), `POST /v1/copilot/{dossier}/rejouer`, `DELETE /v1/copilot/{dossier}/memoire`.

### Serveur MCP : les outils du Copilot pour n'importe quel agent

```powershell
python -m api.mcp_server     # transport stdio, lancé par le client MCP
```

Un client MCP (Claude Desktop, un IDE, un autre agent) obtient 9 outils en lecture seule (lister et lire les dossiers, scénario, sensibilités, niveau de confiance, projection, calcul de la marge, recherche dans le règlement, vérification de la piste d'audit), les notes des dossiers et les paragraphes du règlement comme ressources (`ifrs17://dossiers/{id}/note`, `ifrs17://norme/paragraphes/{id}`), et deux prompts. Aucun outil n'écrit. Exemple de configuration (Claude Desktop, `claude_desktop_config.json`) :

```json
{"mcpServers": {"ifrs17": {"command": "C:\\chemin\\ifrs17-copilot\\.venv\\Scripts\\python.exe",
  "args": ["-m", "api.mcp_server"], "cwd": "C:\\chemin\\ifrs17-copilot"}}}
```

Inspection manuelle : `npx @modelcontextprotocol/inspector .venv\Scripts\python.exe -m api.mcp_server` (D-062).

### Côté actuariel : données réelles, calibration, clôture (D-072 à D-078)

Données publiques de la CAS (Schedule P) : `clrd.csv` (1988-1997) et `clrd2025.csv` (1998-2007), dans
`data/cas/` (dossier `chainladder/utils/data` du dépôt github.com/casact/chainladder-python).

```powershell
python -m actuariat.prospectif data\cas\clrd.csv data\cas\clrd2025.csv                 # 50 dossiers prospectifs (Chain Ladder)
python -m actuariat.prospectif data\cas\clrd.csv data\cas\clrd2025.csv --camarade chemin\dossiers_reels   # double calcul + attendus.csv
python -m actuariat.calibration data\cas\clrd2025.csv                                     # volatilité du RA par branche → hypotheses\registre.json
python -m actuariat.backtest data\cas\clrd.csv data\cas\clrd2025.csv --reference eval\reference_script_R_50.csv
python -m eval.eval_production --jeu prospectif                                            # lecture des dossiers par le LLM
```

Première clôture d'un dossier déjà calculé : `POST /v1/case/cloture` avec `{"case_id": "...", "cloture":
{"actual_outflow": 27723, "revised_outflows": [...], "as_of": "31/12/2007"}}` ; la note de clôture est écrite par le
code seul. Relecture : `docs/grille_relecture_actuarielle.md`.

### Brancher un vrai LLM

Dans `.env` : `LLM_PROVIDER=openai_compatible`, puis `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_SMALL`, `LLM_MODEL_LARGE`. Tout service exposant `POST /chat/completions` fonctionne, y compris un modèle servi sur Colab derrière le tunnel. Ensuite : `ROUTER_MODE=llm` et `python -m eval.eval_router --llm` pour comparer au routeur heuristique.

## Interface web

```powershell
.\make.ps1 serve          # puis ouvrir http://127.0.0.1:8000
```

Deux parties, servies par l'API elle-même (HTML, CSS et JavaScript sans dépendance ni étape de construction ; polices auto-hébergées, fonctionne hors ligne) :

- **`/`, présentation du produit** : parcours d'un dossier, agents, contrôles, captures de l'espace de travail, gouvernance, intégration n8n, résultats mesurés.
- **`/app/`, espace de travail** (connexion obligatoire dès qu'un compte existe) :
  - **Vue d'ensemble** : dossiers à valider, activité sur 30 jours, qualité, coût des modèles, état du service ;
  - **Dossiers** : registre filtrable (statut, canal, recherche) ; chaque **fiche dossier** réunit le cycle de vie, la synthèse chiffrée (cascade de la valeur actuelle des flux à la marge, écoulement de la marge), la note (impression PDF A4), les données extraites (corrigées puis approuvées ou rejetées par un valideur), le Copilot et la piste d'audit ;
  - **Nouveau dossier** : dépôt d'un PDF, d'un scan ou d'un exemple, agents suivis en direct (`POST /v1/case/stream`), puis ouverture de la fiche ;
  - **Assistant normatif** : question écrite ou dictée (`/v1/ask`, `/v1/ask/audio`), paragraphe cité affiché à côté de la réponse ;
  - **Simulateur** : modèle général sur plusieurs années et PAA, avec graphiques ;
  - **Administration** (administrateur) : comptes et rôles, piste d'audit et vérification d'intégrité, configuration du service.

Recherche globale `Ctrl K`, raccourcis clavier (`?`), thème clair ou sombre, utilisable sur téléphone.

Pour une démonstration avec un registre déjà rempli (19 dossiers fictifs, trois comptes) : `python -m core.demo_data data/demo.db`, puis `REGISTRY_PATH=data/demo.db` dans `.env` et relancer l'API. Comptes : `admin` / `admin-demo-1`, `claire` / `valideur-demo`, `karim` / `analyste-demo`.

Si un dossier part en validation humaine, le valideur reçoit automatiquement un e-mail avec la note provisoire et un formulaire pré-rempli (branche « validation » du workflow n8n, ligne `N8N_VALIDATION_URL` dans `.env`, voir `workflows/README.md`).

### Comptes et rôles

Dès qu'un compte existe, le site demande une connexion. Trois rôles, chacun avec les droits du précédent :

| Rôle | Peut |
| --- | --- |
| analyste | déposer et analyser des dossiers, interroger la norme et le Copilot, consulter le registre et le tableau de bord |
| valideur | approuver (après correction) ou rejeter un dossier en validation humaine |
| admin | créer et désactiver des comptes, changer un rôle ou un mot de passe, consulter et vérifier la piste d'audit |

Premier compte administrateur, au choix :

```powershell
python -m core.registry add-user admin --role admin      # le mot de passe est demandé
# ou, dans .env : ADMIN_USERNAME=admin et ADMIN_PASSWORD=<mot de passe> (créé au premier démarrage s'il n'existe aucun compte)
python -m core.registry users                            # liste des comptes
python -m core.registry verify                           # la piste d'audit est-elle intacte ?
```

Les autres comptes se créent dans la page **Administration**. n8n continue d'utiliser le jeton `X-API-Token` (acteur « systeme ») : il n'a pas besoin de compte. Le registre est le fichier `data/registry.db` (`REGISTRY_PATH`), hors Git ; une copie du fichier suffit comme sauvegarde.

Pages ajoutées : **Tableau de bord** (dossiers, taux de note directe et de validation humaine, délais, coût des modèles, dossiers en attente), **Dossiers** (registre filtrable par statut, canal et texte ; détail avec la note, les contrôles, les décisions et la piste d'audit), **Administration**.

Sans aucun compte (développement), le site reste ouvert comme avant et le jeton d'API (`API_TOKEN`, `change-moi` par défaut) se règle dans le bouton **Réglages** ; il reste dans le navigateur. Documents fictifs uniquement : les niveaux gratuits de Groq et Gemini peuvent utiliser les données envoyées.

## Architecture

```
n8n (déclencheurs) ──► FastAPI ──► Orchestrateur + Routeur
                                    ├── Extracteur multimodal  → PortfolioData
                                    ├── Chercheur RAG          → GroundedAnswer (citations §)
                                    ├── Calculateur            → CsmResult (engine/csm.py)
                                    ├── Vérificateur           → Verdict (ok / une correction / humain)
                                    └── Rédacteur              → note HTML et PDF
                                   Copilot (agent à outils, LangGraph) · serveur MCP (lecture seule)
n8n (sortie) ◄── e-mail (note HTML + PDF), formulaire de validation humaine, piste d'audit
```

Le LLM ne fait jamais de calcul (D-005) ; toutes les sorties d'agent sont validées par Pydantic (D-007).

## Structure

| Dossier | Contenu |
| --- | --- |
| `api/` | Endpoints FastAPI appelés par n8n |
| `agents/` | Les agents : routeur, chercheur RAG et agent de recherche LangGraph, vérificateur, rédacteur, orchestrateur, Copilot et sa mémoire |
| `core/` | Configuration, client LLM, traces JSONL, chargement des prompts |
| `engine/` | Moteur IFRS 17 (Python pur) : modèle général, PAA, première clôture, sensibilités |
| `actuariat/` | Méthodes actuarielles hors moteur : Chain Ladder, dossiers prospectifs à montants réels, calibration du RA, back-testing, registre des hypothèses |
| `hypotheses/` | Registre des hypothèses actuarielles versionné (`registre.json`), cité dans chaque note |
| `prompts/` | Bibliothèque de prompts versionnée (YAML) |
| `rag/` | Ingestion, découpage, recherche (voir `rag/README.md`) |
| `multimodal/` | Lecture des PDF (couche texte), des images (vision, double lecture), de la voix ; documents synthétiques de test |
| `workflows/` | Le workflow n8n unique (`ifrs17_copilot.json`), son script de génération et l'historique `par_etape/` |
| `eval/` | Jeux de test et scripts d'évaluation |
| `notebooks/` | Expériences Colab (test T4, benchmarks, QLoRA) |
| `data/` | Hors Git, sauf le manifeste du corpus |
| `docs/` | Registre des décisions, journal des échecs, calculs manuels, rapport technique (`docs/rapport/`) |

## Règles d'équipe

- Une branche par tâche, pull request relue par une autre personne, CI verte avant fusion.
- Aucun document du corpus, aucune clé API, aucune sortie de notebook dans Git (`nbstripout` s'en charge).
- Chaque choix technique va dans `docs/decisions.md`, chaque échec dans `docs/failures.md`.
- Un composant est « fini » quand il est appelable par l'API, testé, mesuré et expliqué par une deuxième personne.
