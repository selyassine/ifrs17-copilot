# Agent de recherche LangGraph : cas_pratiques.jsonl

Généré le 20261017-232143 par `python -m eval.eval_agentic`. 30 questions. Moteur : hybrid BAAI/bge-m3, options {'rerank_model': 'BAAI/bge-reranker-v2-m3', 'questions': False, 'graph': False, 'store': 'qdrant', 'qdrant_url': ''}.

| Méthode | Recall@5 | MRR@5 |
| --- | --- | --- |
| Recherche en un coup | 0.617 | 0.536 |
| Agent LangGraph (planifier, chercher, évaluer) | 0.650 | 0.592 |

Écart Recall@5 : +0.033 [-0.100 ; +0.167] ; écart MRR : +0.056 [-0.075 ; +0.183] (IC bootstrap 95 %).
Coût : 2.27 appels LLM par question, latence médiane 9.9 s, 8 nouvelles recherches décidées par l'agent.

## Questions qui changent

- **p04** 0.00 → 1.00 · attendu 11 · mécanismes : détermination du périmètre du contrat d'assurance; séparation des composantes d'assurance et de services financiers; exigence de comptabiliser séparément les services d'épargne
- **p05** 0.00 → 1.00 · attendu 12 · mécanismes : exclusion du service non-assuré du périmètre du contrat d'assurance; séparation du service accessoire et comptabilisation en tant que prestation distincte
- **p08** 0.00 → 1.00 · attendu 28A · mécanismes : allocation des coûts d'acquisition aux groupes de contrats; méthode d'affectation des primes et des coûts d'acquisition selon IFRS 17
- **p11** 1.00 → 0.00 · attendu 34 · mécanismes : méthode d'affectation des primes (premium allocation approach); projection des flux de trésorerie futurs sur la période de couverture; contrats renouvelables et durée de projection des primes
- **p21** 1.00 → 0.00 · attendu B65 · mécanismes : détermination des flux de trésorerie futurs du contrat; exclusion des frais généraux non directement attribuables aux services du contrat
