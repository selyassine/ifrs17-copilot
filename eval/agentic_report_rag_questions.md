# Agent de recherche LangGraph : rag_questions.jsonl

Généré le 20261017-230425 par `python -m eval.eval_agentic`. 50 questions. Moteur : hybrid BAAI/bge-m3, options {'rerank_model': 'BAAI/bge-reranker-v2-m3', 'questions': True, 'graph': True, 'store': 'qdrant', 'qdrant_url': ''}.

| Méthode | Recall@5 | MRR@5 |
| --- | --- | --- |
| Recherche en un coup | 0.893 | 0.786 |
| Agent LangGraph (planifier, chercher, évaluer) | 0.953 | 0.893 |

Écart Recall@5 : +0.060 [+0.010 ; +0.130] ; écart MRR : +0.108 [+0.035 ; +0.187] (IC bootstrap 95 %).
Coût : 2.06 appels LLM par question, latence médiane 7.9 s, 3 nouvelles recherches décidées par l'agent.

## Questions qui changent

- **q22** 0.00 → 1.00 · attendu 88 · mécanismes : présentation des produits et charges d'assurance dans le compte de résultat et les autres éléments du résultat global; distinction entre résultat net et OCI selon IFRS 17; classification des flux financiers liés aux contrats d'assurance
- **q23** 0.00 → 1.00 · attendu B18 · mécanismes : critère de transfert de risque d'assurance selon IFRS 17; définition du contrat d'assurance et du risque d'assurance transféré
- **q45** 0.00 → 0.50 · attendu 44, 45 · mécanismes : participation aux bénéfices directe et son impact sur la CSM; traitement de la marge sur services contractuels pour contrats avec participation versus sans participation
- **q46** 0.50 → 1.00 · attendu 47, 48 · mécanismes : groupe de contrats déficitaire; composante de perte (loss component); ajustement de la marge sur services contractuels (CSM) lors de l'évaluation ultérieure
