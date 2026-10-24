# Agent de recherche LangGraph : cas_pratiques.jsonl

Généré le 20261017-043908 par `python -m eval.eval_agentic`. 30 questions. Moteur : hybrid BAAI/bge-m3, options {'rerank_model': '', 'questions': True, 'graph': True}.

| Méthode | Recall@5 | MRR@5 |
| --- | --- | --- |
| Recherche en un coup | 0.683 | 0.514 |
| Agent LangGraph (planifier, chercher, évaluer) | 0.717 | 0.583 |

Écart Recall@5 : +0.033 [-0.100 ; +0.167] ; écart MRR : +0.069 [+0.001 ; +0.141] (IC bootstrap 95 %).
Coût : 2.3 appels LLM par question, latence médiane 11.5 s, 9 nouvelles recherches décidées par l'agent.

## Questions qui changent

- **p05** 0.00 → 1.00 · attendu 12 · mécanismes : exclusion du service du périmètre du contrat d'assurance; séparation des services non liés au risque assuré; traitement du service selon IFRS 15
- **p08** 0.00 → 1.00 · attendu 28A · mécanismes : coût d'acquisition et son affectation aux groupes de contrats; méthode d'affectation des primes et des coûts d'acquisition; groupes de contrats selon le périmètre du contrat
- **p11** 1.00 → 0.00 · attendu 34 · mécanismes : estimation des flux de trésorerie futurs incluant les primes futures attendues; méthode d'affectation des primes pour les contrats à renouvellement; détermination de la période de couverture et de la durée du contrat
- **p13** 1.00 → 0.00 · attendu 45 · mécanismes : ajustement de la marge sur services contractuels au titre des services futurs; participation directe aux résultats financiers du contrat; méthode d'affectation des primes aux obligations de service
- **p25** 0.00 → 1.00 · attendu B126 · mécanismes : méthode d'allocation de la prime en méthode simplifiée; répartition de la prime selon le pattern de sinistres; détermination du revenu de service contractuel saisonnier
