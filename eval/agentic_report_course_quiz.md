# Agent de recherche LangGraph : course_quiz.jsonl

Généré le 20261017-232755 par `python -m eval.eval_agentic`. 15 questions. Moteur : hybrid BAAI/bge-m3, options {'rerank_model': 'BAAI/bge-reranker-v2-m3', 'questions': False, 'graph': False, 'store': 'qdrant', 'qdrant_url': ''}.

| Méthode | Recall@5 | MRR@5 |
| --- | --- | --- |
| Recherche en un coup | 0.333 | 0.194 |
| Agent LangGraph (planifier, chercher, évaluer) | 0.467 | 0.272 |

Écart Recall@5 : +0.133 [-0.133 ; +0.400] ; écart MRR : +0.078 [-0.011 ; +0.172] (IC bootstrap 95 %).
Coût : 2.6 appels LLM par question, latence médiane 11.7 s, 9 nouvelles recherches décidées par l'agent.

## Questions qui changent

- **c02** 0.00 → 1.00 · attendu 16 · mécanismes : niveau d'agrégation des obligations d'assurance; détermination du périmètre du contrat
- **c03** 1.00 → 0.00 · attendu 47 · mécanismes : contrat onéreux; coût d'acquisition supérieur au bénéfice économique attendu; reconnaissance de la marge sur services contractuels au titre des services futurs
- **c04** 0.00 → 1.00 · attendu 50 · mécanismes : groupe de contrats déficitaire; composante de perte non réversible; reconnaissance du profit futur via la marge sur services contractuels
- **c14** 0.00 → 1.00 · attendu 44 · mécanismes : mise à jour des estimations des flux de trésorerie futurs; variation de la marge sur services contractuels (CSM) suite à révision du best estimate
