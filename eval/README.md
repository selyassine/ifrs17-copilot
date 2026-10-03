# Évaluation

| Fichier | Mesure | Commande | Statut |
| --- | --- | --- | --- |
| `router_cases.jsonl` (20 cas) | Exactitude du routeur, heuristique vs LLM | `python -m eval.eval_router [--llm]` | Heuristique : 95 % |
| `rag_questions.jsonl` (60 questions) | Recall@k, MRR, nDCG@5, fidélité | S2 | à créer (R1 + R6) |
| `extraction_pdfs/` (15 PDF annotés) | Exactitude par champ | S3 | à créer (R5) |
| `golden_cases.jsonl` (20 scénarios) | Succès bout en bout, latence, coût | S4 | à créer (R6) |
| `adversarial.jsonl` (15 cas) | Injections, PDF corrompus, hors périmètre | S4 | à créer (R6) |

Les résultats sont écrits dans `eval/results/`. Règle : un jeu de test n'est jamais écrit par la personne qui écrit le composant testé seule ; au moins un second annotateur relit.
