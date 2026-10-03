# Registre des décisions

Une ligne par choix technique. Règle des 3 preuves : **une source**, **une mesure ou un test**, **une décision écrite**.
Statut : `proposée` → `validée` (mesure faite) ou `remplacée par D-xxx`.

| ID | Date | Décision | Options comparées | Critères | Preuve (source / mesure) | Statut | Auteur |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D-001 | 2026-10-03 | Pas de Docker : Python en venv + Node.js pour n8n | Docker Compose ; installation native | Simplicité pour 6 machines hétérogènes, consigne de l'équipe | README testé sur machine vierge (à faire en S1) | proposée | équipe |
| D-002 | 2026-10-03 | n8n auto-hébergé lancé par `npx n8n` | n8n Cloud ; npm global | Gratuit, workflows exportables en JSON | Doc d'installation npm de n8n ; webhook → API testé | proposée | R2 |
| D-003 | 2026-10-03 | Vecteurs en mémoire (NumPy) par défaut ; Qdrant embarqué en option (`--store qdrant`) | Qdrant seul ; Chroma | ~400 chunks : recherche exacte en < 5 ms sans service ; Qdrant utile si le corpus dépasse ~50 000 chunks ou pour les filtres avancés | rag/retrieve.py ; latence dans eval/retrieval_report.md | validée (remplace la version « Qdrant seul ») | R1 |
| D-004 | 2026-10-03 | Entraînement sur T4 en FP16, sans FlashAttention-2 ni BF16 | BF16 ; FP32 | T4 = capacité 7.5 (pas de BF16 natif, FA2 exige ≥ 8.0) | Notebook 00, cellule 1 | proposée | R5 |
| D-005 | 2026-10-03 | Le LLM ne calcule jamais : le Calculateur appelle `engine/csm.py` | Calcul par le LLM ; code généré à la volée | Exactitude, testabilité | 10 tests contre calculs manuels (docs/engine_hand_calcs.md) | validée | R3 |
| D-006 | 2026-10-03 | Moteur v0 : modèle général, primes en début de période, sorties en fin, RA en % des sorties actualisées | Périmètre complet (VFA, PAA) | Le sujet n'est pas noté : outil simple et juste | Tests ; relecture actuarielle prévue en S3 | proposée | R3 |
| D-007 | 2026-10-03 | Sorties d'agents typées par Pydantic, champs inconnus refusés | Texte libre ; JSON non validé | Détecter les hallucinations de structure à chaque frontière | tests/test_schemas.py | validée | R4 |
| D-008 | 2026-10-03 | Client LLM « compatible chat completions » + fournisseur factice | SDK propre à un fournisseur | Changer de fournisseur via .env ; CI sans réseau ni coût | tests/test_router_llm_prompts.py | validée | R4 |
| D-009 | 2026-10-03 | Le routeur LLM choisit l'intention, le code fixe les étapes | Le LLM choisit aussi les agents | Plan toujours valide (vérificateur obligatoire), moins d'erreurs | Routeur LLM (gpt-oss-20b, prompt route v1) : 100 % sur 20 cas, 0 repli, contre 95 % pour l'heuristique (il classe correctement IFRS 16 hors périmètre, F-001). Jeu de test petit : à élargir | validée | R4 |
| D-010 | 2026-10-03 | Corpus hors Git ; seul `data/corpus_manifest.csv` est versionné | Corpus dans le dépôt | Droits d'auteur de l'IFRS Foundation | Conditions d'usage de l'IFRS Foundation ; question posée à l'encadrant en S1 | proposée | R1 |
| D-011 | 2026-10-03 | Extraction PDF avec pdfplumber, analyse de la mise en page (marge gauche, polices, colonnes) | pypdf ; pdftotext ; PyMuPDF | Mots intacts, numéros de paragraphe fiables, installation pure Python sous Windows | pypdf : 55 % des termes clés intacts, pdfplumber : 100 % (F-003) ; 148 + 156 + 51 paragraphes retrouvés sans trou | validée | R1 |
| D-012 | 2026-10-03 | Annexe D du règlement (modifications d'autres normes) exclue de l'index | L'indexer | Ses numéros (B1, B13, 7…) sont ceux d'IFRS 1, IAS 32… et créeraient de fausses citations | rag/ingest.py | validée | R1 |
| D-013 | 2026-10-03 | Découpage B (un chunk par paragraphe + en-tête de contexte) retenu | A : 512 tokens, chevauchement 64 | Rappel à budget de contexte égal, citation exacte du paragraphe, coût LLM | BGE-M3 dense, 50 questions : rappel à 1 000 tokens B 0,737 contre A 0,423 ; Recall@5 B 0,837 contre A 0,760 ; MRR 0,642 contre 0,478. En BM25 l'écart n'était pas significatif. L'en-tête de contexte aide aussi en dense (B 0,837 contre B0 0,807) | validée | R1 |
| D-014 | 2026-10-03 | Métrique principale = rappel à budget de tokens égal, en plus de Recall@k | Recall@k seul | À k égal, A envoie 2,5 fois plus de texte au LLM et gagne mécaniquement | eval/eval_retrieval.py | validée | R1, R6 |
| D-015 | 2026-10-03 | Glossaire de sigles avant la recherche (CSM, PAA, VFA, onéreux, bilan…) | Aucun ; réécriture par LLM (S3) | Gratuit, déterministe, explicable ; baseline pour la réécriture LLM | B · BM25 : Recall@5 0,563 → 0,653 (+0,09, IC 95 % [+0,02 ; +0,16]) ; MRR 0,454 → 0,546 | validée | R1, R4 |
| D-016 | 2026-10-03 | BM25 et analyseur français écrits à la main (racinisation légère) | rank-bm25 ; spaCy | Aucune dépendance, contrôle total, testé | tests/test_rag.py | validée | R1 |
| D-017 | 2026-10-03 | Recherche par défaut : hybride BGE-M3 + BM25 avec glossaire (RRF), sur le découpage B | Dense seul ; BM25 seul ; hybride sans glossaire | Meilleur rappel à budget égal et meilleur MRR ; robustesse aux sigles | B hybride + glossaire : rappel à 1 000 tokens 0,773, MRR 0,661, Recall@5 0,823 ; B dense seul : 0,737, 0,642, 0,837 (écart faible, à confirmer par IC) ; BM25 seul : 0,533, 0,454, 0,563 | validée | R1 |
| D-018 | 2026-10-03 | Modèle d'embedding BGE-M3 (1 024 dimensions, multilingue) | Qwen3-Embedding-0.6B (à mesurer) | Français, contexte long, licence MIT | Encodage CPU : 380 chunks en ~4 min ; voir eval/retrieval_report.md | proposée (comparaison Qwen3 à faire) | R5 |
| D-019 | 2026-10-03 | LLM gratuit Groq : gpt-oss-20b (petit), gpt-oss-120b (grand), qwen3.8-27b (secours) | Claude API (payante, non incluse dans Claude Pro) ; Gemini ; OpenRouter | Gratuit sans carte, compatible OpenAI, rapide ; limites 8 000 tokens/min et 200 000/jour par modèle | Docs Groq (modèles, limites) consultées le 03/10/2026 ; F-009 | validée | R4 |

## Gabarit d'une nouvelle ligne

```
| D-0xx | AAAA-MM-JJ | <décision en une phrase> | <option A> ; <option B> | <2-3 critères> | <lien source> ; <fichier de mesure> | proposée | <rôle> |
```
