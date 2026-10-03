# Évaluation

| Fichier | Mesure | Commande | Statut |
| --- | --- | --- | --- |
| `router_cases.jsonl` (20 cas) | Exactitude du routeur, heuristique vs LLM | `python -m eval.eval_router [--llm]` | Heuristique : 95 % |
| `rag_questions.jsonl` (56 questions : 42 factuelles, 8 multi-paragraphes, 6 pièges) | Recall@k, rappel à budget de tokens, MRR, nDCG@5, IC bootstrap | `python -m eval.eval_retrieval [--model BAAI/bge-m3]` | Fait : BM25, dense BGE-M3, hybride (meilleur : B hybride + glossaire, MRR 0,661) |
| `extraction_pdfs/` (15 PDF annotés) | Exactitude par champ | S3 | à créer (R5) |
| `golden_cases.jsonl` (20 scénarios) | Succès bout en bout, latence, coût | S4 | à créer (R6) |
| `adversarial.jsonl` (15 cas) | Injections, PDF corrompus, hors périmètre | S4 | à créer (R6) |

Les résultats sont écrits dans `eval/results/`. Règle : un jeu de test n'est jamais écrit par la personne qui écrit le composant testé seule ; au moins un second annotateur relit.

## Ajouter des questions (à faire par l'équipe en S2)

Les 56 questions actuelles ont été rédigées par une seule personne qui connaissait le texte. Chaque membre ajoute 5 questions **sans relire la norme**, comme un utilisateur les poserait, puis une autre personne retrouve les paragraphes attendus :

```json
{"id": "q57", "niveau": "factuelle", "question": "…", "gold": ["44"], "doc": "C002", "annotateur": "R3", "relu_par": "R1"}
```

`gold` contient des identifiants de `data/processed/C002_units.jsonl` : `44`, `B119`, `C5`, `art-2`, `cons-12`, `def:période de couverture`. Un jeu de questions pièges (`gold: []`) sert au test de refus de l'agent RAG (S3).
