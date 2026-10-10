# Évaluation des réponses de l'agent RAG

Généré le 20261010-043251 par `python -m eval.eval_rag`. Prompt : `rag_answer` v2 ; modèle : `openai/gpt-oss-120b` ; routeur : `llm` ; recherche : `hybrid` (découpage B, glossaire oui).

| Mesure | Valeur |
| --- | --- |
| Questions évaluées | 15 |
| Questions pièges correctement refusées | 0/0 |
| Faux refus (la norme répondait) | 4/15 |
| Réponses avec citation inventée, avant vérification | 0/11 |
| Relances de correction déclenchées | 0 |
| Citations hors extraits après vérification | 0 |
| Précision des citations (cités ∈ attendus) | 0.136 |
| Précision élargie (cités ∈ attendus ou acceptables) | 0.182 |
| Couverture (attendus effectivement cités) | 0.273 |
| Réponses citant au moins un paragraphe attendu | 0.273 |
| Plafond fixé par la recherche (attendus présents dans les extraits) | 0.267 |
| Verdicts du vérificateur (après au plus une correction) | {'ok': 14, 'validation_humaine': 1} |
| Latence médiane d'une réponse (ms) | 1908.2 |

## Détail par question

| Id | Niveau | Refus | Cités | Attendus | Dans les extraits | Correction |
| --- | --- | --- | --- | --- | --- | --- |
| c01 | cours | non | 78 | 40 | — | 0 |
| c02 | cours | non | 40, 55 | 16 | — | 0 |
| c03 | cours | oui | — | 47 | 47 | 0 |
| c04 | cours | oui | — | 50 | — | 0 |
| c05 | cours | non | B92, B91 | B92 | B92 | 0 |
| c06 | cours | non | def:ajustements liés à l'expérience, 42 | B97 | — | 0 |
| c07 | cours | non | 55, 59 | 83 | — | 0 |
| c08 | cours | oui | — | 34 | — | 0 |
| c09 | cours | non | 130 | 44 | — | 0 |
| c10 | cours | oui | — | 32 | — | 0 |
| c11 | cours | non | 53, 69 | 53 | 53 | 0 |
| c12 | cours | non | B101, B104 | B101 | B101 | 0 |
| c13 | cours | non | C24, 116, C18 | 88 | — | 0 |
| c14 | cours | non | B57 | 44 | — | 0 |
| c15 | cours | non | B26, 130 | 57 | — | 0 |

## Lecture

- Une citation attendue absente des extraits est une erreur de **recherche** ; présente dans les extraits mais non citée, c'est une erreur de **génération**.
- Les réponses complètes sont dans `eval/results/rag_answers_<date>.md` pour la relecture humaine (fidélité, clarté) de 20 réponses.
