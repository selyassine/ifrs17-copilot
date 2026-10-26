# Évaluation des réponses de l'agent RAG

Généré le 20261025-235947 par `python -m eval.eval_rag`. Prompt : `rag_answer` v3 ; modèle : `openai/gpt-oss-120b` ; routeur : `llm` ; recherche : `hybrid` (découpage B, glossaire oui).

| Mesure | Valeur |
| --- | --- |
| Questions évaluées | 15 |
| Questions pièges correctement refusées | 0/0 |
| Faux refus (la norme répondait) | 2/15 |
| Réponses avec citation inventée, avant vérification | 0/13 |
| Relances de correction déclenchées | 0 |
| Citations hors extraits après vérification | 0 |
| Précision des citations (cités ∈ attendus) | 0.154 |
| Précision élargie (cités ∈ attendus ou acceptables) | 0.269 |
| Couverture (attendus effectivement cités) | 0.231 |
| Réponses citant au moins un paragraphe attendu | 0.231 |
| Plafond fixé par la recherche (attendus présents dans les extraits) | 0.333 |
| Verdicts du vérificateur (après au plus une correction) | {'ok': 11, 'validation_humaine': 4} |
| Latence médiane d'une réponse (ms) | 5265.6 |

## Détail par question

| Id | Niveau | Refus | Cités | Attendus | Dans les extraits | Correction |
| --- | --- | --- | --- | --- | --- | --- |
| c01 | cours | non | def:passif au titre des sinistres survenus, def:passif au titre de la couverture restante | 40 | — | 0 |
| c02 | cours | non | 16, 40 | 16 | 16 | 0 |
| c03 | cours | oui | — | 47 | 47 | 0 |
| c04 | cours | non | C15 | 50 | — | 0 |
| c05 | cours | non | B92, B91 | B92 | B92 | 0 |
| c06 | cours | non | B57 | B97 | — | 0 |
| c07 | cours | non | B65, 55 | 83 | — | 0 |
| c08 | cours | non | def:période de couverture, 2 | 34 | — | 0 |
| c09 | cours | non | B54, B41, B59, 130 | 44 | — | 0 |
| c10 | cours | oui | — | 32 | — | 0 |
| c11 | cours | non | 53 | 53 | 53 | 0 |
| c12 | cours | non | def:contrat d'assurance avec éléments de participation directe | B101 | B101 | 0 |
| c13 | cours | non | 80, C24, 116 | 88 | — | 0 |
| c14 | cours | non | 104, B96 | 44 | — | 0 |
| c15 | cours | non | 47, 49 | 57 | — | 0 |

## Lecture

- Une citation attendue absente des extraits est une erreur de **recherche** ; présente dans les extraits mais non citée, c'est une erreur de **génération**.
- Les réponses complètes sont dans `eval/results/rag_answers_<date>.md` pour la relecture humaine (fidélité, clarté) de 20 réponses.
