# Évaluation

| Fichier | Mesure | Commande | Statut |
| --- | --- | --- | --- |
| `router_cases.jsonl` (20 cas) | Exactitude du routeur, heuristique vs LLM | `python -m eval.eval_router [--llm]` | Heuristique : 95 % ; LLM : 100 % |
| `rag_questions.jsonl` (56 questions : 42 factuelles, 8 multi-paragraphes, 6 pièges) | Recall@k, rappel à budget de tokens, MRR, nDCG@5, IC bootstrap | `python -m eval.eval_retrieval [--model BAAI/bge-m3]` | Fait : BM25, dense BGE-M3, hybride (meilleur : B hybride + glossaire, MRR 0,661) |
| `rag_questions.jsonl` (mêmes 56 questions) | Réponses de l'agent RAG : refus des pièges, faux refus, citations inventées, précision et couverture des citations, plafond de la recherche | `python -m eval.eval_rag [--limit 10] [--pause 15] [--resume]` | v1 : pièges 6/6, faux refus 0/50, citations inventées 0, couverture 0,80, précision 0,63 (élargie 0,83) ; relecture humaine `results/rag_human_review_v1.md` : 39/50 fidèles et complètes. v2 : à mesurer |
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

Champ facultatif `acceptables` : autres paragraphes qui répondent aussi à la question (ex. B87 pour l'ajustement pour risque). Ils comptent dans la précision élargie, pas dans la couverture ni dans le rappel de la recherche (D-023).
