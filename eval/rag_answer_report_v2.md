# Évaluation des réponses de l'agent RAG

Généré le 20261004-003445 par `python -m eval.eval_rag`. Prompt : `rag_answer` v2 ; modèle : `openai/gpt-oss-120b` ; routeur : `llm` ; recherche : `hybrid` (découpage B, glossaire oui).

| Mesure | Valeur |
| --- | --- |
| Questions évaluées | 56 |
| Questions pièges correctement refusées | 6/6 |
| Faux refus (la norme répondait) | 0/50 |
| Réponses avec citation inventée, avant vérification | 1/50 |
| Relances de correction déclenchées | 1 |
| Citations hors extraits après vérification | 0 |
| Précision des citations (cités ∈ attendus) | 0.605 |
| Précision élargie (cités ∈ attendus ou acceptables) | 0.76 |
| Couverture (attendus effectivement cités) | 0.823 |
| Réponses citant au moins un paragraphe attendu | 0.88 |
| Plafond fixé par la recherche (attendus présents dans les extraits) | 0.823 |
| Latence médiane d'une réponse (ms) | 1501.1 |

## Détail par question

| Id | Niveau | Refus | Cités | Attendus | Dans les extraits | Correction |
| --- | --- | --- | --- | --- | --- | --- |
| q01 | factuelle | non | 25 | 25 | 25 | 1 |
| q02 | factuelle | non | 65 | 32 | — | 0 |
| q03 | factuelle | non | 33, 24 | 33 | 33 | 0 |
| q04 | factuelle | non | 34, B61, B66 | 34 | 34 | 0 |
| q05 | factuelle | non | 36, B74 | 36 | 36 | 0 |
| q06 | factuelle | non | B87, B89, B90, B88 | 37 | — | 0 |
| q07 | factuelle | non | 38 | 38 | 38 | 0 |
| q08 | factuelle | non | def:marge sur services contractuels, 43 | 43 | 43 | 0 |
| q09 | factuelle | non | 44 | 44 | 44 | 0 |
| q10 | factuelle | non | 47, 50 | 47 | 47 | 0 |
| q11 | factuelle | non | 48, 44 | 48 | 48 | 0 |
| q12 | factuelle | non | 53, 69 | 53 | 53 | 0 |
| q13 | factuelle | non | 59 | 59 | 59 | 0 |
| q14 | factuelle | non | 16 | 16 | 16 | 0 |
| q15 | factuelle | non | 22 | 22 | 22 | 0 |
| q16 | factuelle | non | 11, 13, B31 | 11 | 11 | 0 |
| q17 | factuelle | non | 28B | 28B | 28B | 0 |
| q18 | factuelle | non | 72 | 72 | 72 | 0 |
| q19 | factuelle | non | 74 | 74 | 74 | 0 |
| q20 | factuelle | non | 78, 79 | 78 | 78 | 0 |
| q21 | factuelle | non | B121, 83 | 83 | 83 | 0 |
| q22 | factuelle | non | 80, 118 | 88 | — | 0 |
| q23 | factuelle | non | B19, B21, B22, B17 | B18 | — | 0 |
| q24 | factuelle | non | B66 | B66 | B66 | 0 |
| q25 | factuelle | non | C13, B72, 44 | B72 | B72 | 0 |
| q26 | factuelle | non | B97, 67 | B97 | B97 | 0 |
| q27 | factuelle | non | B101 | B101 | B101 | 0 |
| q28 | factuelle | non | def:période de couverture, 44, B119 | B119 | B119 | 0 |
| q29 | factuelle | non | B120 | B120 | B120 | 0 |
| q30 | factuelle | non | C5, C6 | C5 | C5 | 0 |
| q31 | factuelle | non | C6 | C6 | C6 | 0 |
| q32 | factuelle | non | C20, C22, C24 | C20 | C20 | 0 |
| q33 | factuelle | non | 101, 100 | 101 | 101 | 0 |
| q34 | factuelle | non | 128, 129 | 128 | 128 | 0 |
| q35 | factuelle | non | 130, C28 | 130 | 130 | 0 |
| q36 | factuelle | non | 62, 62A | 62 | 62 | 0 |
| q37 | factuelle | non | 65 | 65 | 65 | 0 |
| q38 | factuelle | non | 66A, B119D | 66A | 66A | 0 |
| q39 | factuelle | non | def:période de couverture | def:période de couverture | def:période de couverture | 0 |
| q40 | factuelle | non | def:flux de trésorerie d'exécution | def:flux de trésorerie d'exécution | def:flux de trésorerie d'exécution | 0 |
| q41 | factuelle | non | def:composante investissement, B31, B32 | def:composante investissement | def:composante investissement | 0 |
| q42 | factuelle | non | 41 | def:passif au titre de la couverture restante | — | 0 |
| q43 | multi | non | cons-12, cons-10 | art-2, cons-12 | cons-12 | 0 |
| q44 | multi | non | C1 | C1, art-2 | C1 | 0 |
| q45 | multi | non | B97, B113 | 44, 45 | — | 0 |
| q46 | multi | non | 18, 19, 48, 50 | 47, 48 | 48 | 0 |
| q47 | multi | non | 44 | 44, B72 | 44 | 0 |
| q48 | multi | non | B113, B97, 67 | B96, B97 | B97 | 0 |
| q49 | multi | non | 55, 56 | 55, 56 | 55, 56 | 0 |
| q50 | multi | non | 16, 23, 24 | 16, 22, 24 | 16, 24 | 0 |
| q51 | piege | oui | — | (refus attendu) | — | 0 |
| q52 | piege | oui | — | (refus attendu) | — | 0 |
| q53 | piege | oui | — | (refus attendu) | — | 0 |
| q54 | piege | oui | — | (refus attendu) | — | 0 |
| q55 | piege | oui | — | (refus attendu) | — | 0 |
| q56 | piege | oui | — | (refus attendu) | — | 0 |

## Lecture

- Une citation attendue absente des extraits est une erreur de **recherche** ; présente dans les extraits mais non citée, c'est une erreur de **génération**.
- Les réponses complètes sont dans `eval/results/rag_answers_<date>.md` pour la relecture humaine (fidélité, clarté) de 20 réponses.
