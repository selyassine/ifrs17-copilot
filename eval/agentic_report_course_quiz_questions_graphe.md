# Agent de recherche LangGraph : course_quiz.jsonl

Généré le 20261017-043531 par `python -m eval.eval_agentic`. 15 questions. Moteur : hybrid BAAI/bge-m3, options {'rerank_model': '', 'questions': True, 'graph': True}.

| Méthode | Recall@5 | MRR@5 |
| --- | --- | --- |
| Recherche en un coup | 0.267 | 0.180 |
| Agent LangGraph (planifier, chercher, évaluer) | 0.400 | 0.300 |

Écart Recall@5 : +0.133 [+0.000 ; +0.333] ; écart MRR : +0.120 [-0.033 ; +0.287] (IC bootstrap 95 %).
Coût : 2.53 appels LLM par question, latence médiane 22.5 s, 8 nouvelles recherches décidées par l'agent.

## Questions qui changent

- **c02** 0.00 → 1.00 · attendu 16 · mécanismes : niveau d'agrégation des obligations d'assurance; détermination du périmètre du contrat
- **c06** 0.00 → 1.00 · attendu B97 · mécanismes : ajustement de la marge sur services contractuels au titre des services futurs; mise à jour des estimations des flux de trésorerie futurs et réévaluation du CSM
