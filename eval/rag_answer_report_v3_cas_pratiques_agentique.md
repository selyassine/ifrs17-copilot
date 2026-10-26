# Évaluation des réponses de l'agent RAG

Généré le 20261026-002518 par `python -m eval.eval_rag`. Prompt : `rag_answer` v3 ; modèle : `openai/gpt-oss-120b` ; routeur : `llm` ; recherche : `hybrid` (découpage B, glossaire oui).

| Mesure | Valeur |
| --- | --- |
| Questions évaluées | 30 |
| Questions pièges correctement refusées | 0/0 |
| Faux refus (la norme répondait) | 2/30 |
| Réponses avec citation inventée, avant vérification | 0/28 |
| Relances de correction déclenchées | 0 |
| Citations hors extraits après vérification | 0 |
| Précision des citations (cités ∈ attendus) | 0.549 |
| Précision élargie (cités ∈ attendus ou acceptables) | 0.698 |
| Couverture (attendus effectivement cités) | 0.732 |
| Réponses citant au moins un paragraphe attendu | 0.75 |
| Plafond fixé par la recherche (attendus présents dans les extraits) | 0.717 |
| Verdicts du vérificateur (après au plus une correction) | {'ok': 22, 'validation_humaine': 8} |
| Latence médiane d'une réponse (ms) | 10630.7 |

## Détail par question

| Id | Niveau | Refus | Cités | Attendus | Dans les extraits | Correction |
| --- | --- | --- | --- | --- | --- | --- |
| p01 | cas_pratique | non | 7 | 7 | 7 | 0 |
| p02 | cas_pratique | non | 8 | 8 | 8 | 0 |
| p03 | cas_pratique | non | 13 | 9 | — | 0 |
| p04 | cas_pratique | non | B31, B32, 11 | 11 | 11 | 0 |
| p05 | cas_pratique | non | B34, 12, B33 | 12 | 12 | 0 |
| p06 | cas_pratique | non | 14, 17 | 16 | — | 0 |
| p07 | cas_pratique | non | 25 | 25 | 25 | 0 |
| p08 | cas_pratique | non | B35A, 28A | 28A | 28A | 0 |
| p09 | cas_pratique | non | 30 | 30 | 30 | 0 |
| p10 | cas_pratique | non | 67 | 67 | 67 | 0 |
| p11 | cas_pratique | non | B61, B64 | 34 | — | 0 |
| p12 | cas_pratique | non | B80, B81 | 36, B80 | B80 | 0 |
| p13 | cas_pratique | non | B112, 45 | 45 | 45 | 0 |
| p14 | cas_pratique | non | 42, B119 | 57 | — | 0 |
| p15 | cas_pratique | non | 59 | 59 | 59 | 0 |
| p16 | cas_pratique | non | 71, cons-5 | 71 | 71 | 0 |
| p17 | cas_pratique | non | B119, 43 | B119 | B119 | 0 |
| p18 | cas_pratique | non | 78 | 78 | 78 | 0 |
| p19 | cas_pratique | oui | — | 85 | 85 | 0 |
| p20 | cas_pratique | oui | — | 87 | — | 0 |
| p21 | cas_pratique | non | B65 | B65 | B65 | 0 |
| p22 | cas_pratique | non | B66 | B66 | B66 | 0 |
| p23 | cas_pratique | non | B96 | B96 | B96 | 0 |
| p24 | cas_pratique | non | B115, B116 | B115 | B115 | 0 |
| p25 | cas_pratique | non | 53, 59 | B126 | — | 0 |
| p26 | cas_pratique | non | B54, B137 | B137 | B137 | 0 |
| p27 | cas_pratique | non | C14D | C5, C20 | — | 0 |
| p28 | cas_pratique | non | 100, 101, 105A, 114, 44 | 100 | 100 | 0 |
| p29 | cas_pratique | non | B57, B58, B99, B56 | 128 | — | 0 |
| p30 | cas_pratique | non | B5 | B5 | B5 | 0 |

## Lecture

- Une citation attendue absente des extraits est une erreur de **recherche** ; présente dans les extraits mais non citée, c'est une erreur de **génération**.
- Les réponses complètes sont dans `eval/results/rag_answers_<date>.md` pour la relecture humaine (fidélité, clarté) de 20 réponses.
