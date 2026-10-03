# Registre des décisions

Une ligne par choix technique. Règle des 3 preuves : **une source**, **une mesure ou un test**, **une décision écrite**.
Statut : `proposée` → `validée` (mesure faite) ou `remplacée par D-xxx`.

| ID | Date | Décision | Options comparées | Critères | Preuve (source / mesure) | Statut | Auteur |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D-001 | 2026-10-03 | Pas de Docker : Python en venv + Node.js pour n8n | Docker Compose ; installation native | Simplicité pour 6 machines hétérogènes, consigne de l'équipe | README testé sur machine vierge (à faire en S1) | proposée | équipe |
| D-002 | 2026-10-03 | n8n auto-hébergé lancé par `npx n8n` | n8n Cloud ; npm global | Gratuit, workflows exportables en JSON | Doc d'installation npm de n8n ; webhook → API testé | proposée | R2 |
| D-003 | 2026-10-03 | Qdrant en mode embarqué (fichier local) | Qdrant serveur ; Chroma | Filtres de métadonnées, aucun serveur à lancer | Benchmark S2 | proposée | R1 |
| D-004 | 2026-10-03 | Entraînement sur T4 en FP16, sans FlashAttention-2 ni BF16 | BF16 ; FP32 | T4 = capacité 7.5 (pas de BF16 natif, FA2 exige ≥ 8.0) | Notebook 00, cellule 1 | proposée | R5 |
| D-005 | 2026-10-03 | Le LLM ne calcule jamais : le Calculateur appelle `engine/csm.py` | Calcul par le LLM ; code généré à la volée | Exactitude, testabilité | 10 tests contre calculs manuels (docs/engine_hand_calcs.md) | validée | R3 |
| D-006 | 2026-10-03 | Moteur v0 : modèle général, primes en début de période, sorties en fin, RA en % des sorties actualisées | Périmètre complet (VFA, PAA) | Le sujet n'est pas noté : outil simple et juste | Tests ; relecture actuarielle prévue en S3 | proposée | R3 |
| D-007 | 2026-10-03 | Sorties d'agents typées par Pydantic, champs inconnus refusés | Texte libre ; JSON non validé | Détecter les hallucinations de structure à chaque frontière | tests/test_schemas.py | validée | R4 |
| D-008 | 2026-10-03 | Client LLM « compatible chat completions » + fournisseur factice | SDK propre à un fournisseur | Changer de fournisseur via .env ; CI sans réseau ni coût | tests/test_router_llm_prompts.py | validée | R4 |
| D-009 | 2026-10-03 | Le routeur LLM choisit l'intention, le code fixe les étapes | Le LLM choisit aussi les agents | Plan toujours valide (vérificateur obligatoire), moins d'erreurs | Comparaison heuristique vs LLM sur eval/router_cases.jsonl (S2) | proposée | R4 |
| D-010 | 2026-10-03 | Corpus hors Git ; seul `data/corpus_manifest.csv` est versionné | Corpus dans le dépôt | Droits d'auteur de l'IFRS Foundation | Conditions d'usage de l'IFRS Foundation ; question posée à l'encadrant en S1 | proposée | R1 |

## Gabarit d'une nouvelle ligne

```
| D-0xx | AAAA-MM-JJ | <décision en une phrase> | <option A> ; <option B> | <2-3 critères> | <lien source> ; <fichier de mesure> | proposée | <rôle> |
```
