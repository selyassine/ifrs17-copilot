# Évaluation des réponses de l'agent RAG

Généré le 20261010-044634 par `python -m eval.eval_rag`. Prompt : `rag_answer` v2 ; modèle : `openai/gpt-oss-120b` ; routeur : `llm` ; recherche : `hybrid` (découpage B, glossaire oui).

| Mesure | Valeur |
| --- | --- |
| Questions évaluées | 15 |
| Questions pièges correctement refusées | 0/0 |
| Faux refus (la norme répondait) | 5/15 |
| Réponses avec citation inventée, avant vérification | 1/10 |
| Relances de correction déclenchées | 1 |
| Citations hors extraits après vérification | 0 |
| Précision des citations (cités ∈ attendus) | 0.15 |
| Précision élargie (cités ∈ attendus ou acceptables) | 0.2 |
| Couverture (attendus effectivement cités) | 0.3 |
| Réponses citant au moins un paragraphe attendu | 0.3 |
| Plafond fixé par la recherche (attendus présents dans les extraits) | 0.267 |
| Verdicts du vérificateur (après au plus une correction) | {'ok': 12, 'validation_humaine': 3} |
| Latence médiane d'une réponse (ms) | 4257.75 |

## Détail par question

| Id | Niveau | Refus | Cités | Attendus | Dans les extraits | Correction |
| --- | --- | --- | --- | --- | --- | --- |
| c01 | cours | non | def:passif au titre des sinistres survenus, def:passif au titre de la couverture restante | 40 | — | 0 |
| c02 | cours | non | 40 | 16 | — | 0 |
| c03 | cours | oui | — | 47 | 47 | 0 |
| c04 | cours | oui | — | 50 | — | 0 |
| c05 | cours | non | B91, B92 | B92 | B92 | 0 |
| c06 | cours | non | 42, 57 | B97 | — | 0 |
| c07 | cours | non | 55, 106 | 83 | — | 0 |
| c08 | cours | non | def:période de couverture, 46, B96, 44 | 34 | — | 1 |
| c09 | cours | non | 42, 130 | 44 | — | 0 |
| c10 | cours | oui | — | 32 | — | 0 |
| c11 | cours | non | 53, 69 | 53 | 53 | 0 |
| c12 | cours | non | B101, B104 | B101 | B101 | 0 |
| c13 | cours | oui | — | 88 | — | 0 |
| c14 | cours | non | 104 | 44 | — | 0 |
| c15 | cours | oui | — | 57 | — | 0 |

## Lecture

- Une citation attendue absente des extraits est une erreur de **recherche** ; présente dans les extraits mais non citée, c'est une erreur de **génération**.
- Les réponses complètes sont dans `eval/results/rag_answers_<date>.md` pour la relecture humaine (fidélité, clarté) de 20 réponses.
