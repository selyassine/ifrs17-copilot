# Évaluation des réponses de l'agent RAG

Généré le 20261025-172503 par `python -m eval.eval_rag`. Prompt : `rag_answer` v3 ; modèle : `openai/gpt-oss-120b` ; routeur : `llm` ; recherche : `hybrid` (découpage B, glossaire oui).

| Mesure | Valeur |
| --- | --- |
| Questions évaluées | 56 |
| Questions pièges correctement refusées | 6/6 |
| Faux refus (la norme répondait) | 0/50 |
| Réponses avec citation inventée, avant vérification | 0/50 |
| Relances de correction déclenchées | 0 |
| Citations hors extraits après vérification | 0 |
| Précision des citations (cités ∈ attendus) | 0.665 |
| Précision élargie (cités ∈ attendus ou acceptables) | 0.803 |
| Couverture (attendus effectivement cités) | 0.823 |
| Réponses citant au moins un paragraphe attendu | 0.86 |
| Plafond fixé par la recherche (attendus présents dans les extraits) | 0.863 |
| Verdicts du vérificateur (après au plus une correction) | {'ok': 50, 'validation_humaine': 0} |
| Latence médiane d'une réponse (ms) | 1749.35 |

## Détail par question

| Id | Niveau | Refus | Cités | Attendus | Dans les extraits | Correction |
| --- | --- | --- | --- | --- | --- | --- |
| q01 | factuelle | non | 25 | 25 | 25 | 0 |
| q02 | factuelle | non | 32 | 32 | 32 | 0 |
| q03 | factuelle | non | 33 | 33 | 33 | 0 |
| q04 | factuelle | non | B65, B66, B61 | 34 | — | 0 |
| q05 | factuelle | non | 36, B78 | 36 | 36 | 0 |
| q06 | factuelle | non | B86, B87, B88, B90 | 37 | — | 0 |
| q07 | factuelle | non | 38 | 38 | 38 | 0 |
| q08 | factuelle | non | 43, def:marge sur services contractuels | 43 | 43 | 0 |
| q09 | factuelle | non | 44, B96 | 44 | 44 | 0 |
| q10 | factuelle | non | 47 | 47 | 47 | 0 |
| q11 | factuelle | non | 48 | 48 | 48 | 0 |
| q12 | factuelle | non | 53 | 53 | 53 | 0 |
| q13 | factuelle | non | 59 | 59 | 59 | 0 |
| q14 | factuelle | non | 16 | 16 | 16 | 0 |
| q15 | factuelle | non | 22 | 22 | 22 | 0 |
| q16 | factuelle | non | 11, B31 | 11 | 11 | 0 |
| q17 | factuelle | non | 28B, C14C | 28B | 28B | 0 |
| q18 | factuelle | non | 72 | 72 | 72 | 0 |
| q19 | factuelle | non | 74 | 74 | 74 | 0 |
| q20 | factuelle | non | 78 | 78 | 78 | 0 |
| q21 | factuelle | non | B121, B123 | 83 | 83 | 0 |
| q22 | factuelle | non | 118, 80, 90 | 88 | — | 0 |
| q23 | factuelle | non | B18, B22 | B18 | B18 | 0 |
| q24 | factuelle | non | B66 | B66 | B66 | 0 |
| q25 | factuelle | non | B72, 36, B80 | B72 | B72 | 0 |
| q26 | factuelle | non | B97 | B97 | B97 | 0 |
| q27 | factuelle | non | def:contrat d'assurance avec éléments de participation directe, B102 | B101 | B101 | 0 |
| q28 | factuelle | non | B119 | B119 | B119 | 0 |
| q29 | factuelle | non | B120 | B120 | B120 | 0 |
| q30 | factuelle | non | C5, C8, C6 | C5 | C5 | 0 |
| q31 | factuelle | non | C6 | C6 | C6 | 0 |
| q32 | factuelle | non | C20 | C20 | C20 | 0 |
| q33 | factuelle | non | 101, 99 | 101 | 101 | 0 |
| q34 | factuelle | non | 128, 129 | 128 | 128 | 0 |
| q35 | factuelle | non | 130, C28 | 130 | 130 | 0 |
| q36 | factuelle | non | 62, 62A | 62 | 62 | 0 |
| q37 | factuelle | non | 65, B95 | 65 | 65 | 0 |
| q38 | factuelle | non | 66A, B119D, B119C | 66A | 66A | 0 |
| q39 | factuelle | non | def:période de couverture | def:période de couverture | def:période de couverture | 0 |
| q40 | factuelle | non | def:flux de trésorerie d'exécution, 31 | def:flux de trésorerie d'exécution | def:flux de trésorerie d'exécution | 0 |
| q41 | factuelle | non | def:composante investissement, B31 | def:composante investissement | def:composante investissement | 0 |
| q42 | factuelle | non | def:passif au titre de la couverture restante | def:passif au titre de la couverture restante | def:passif au titre de la couverture restante | 0 |
| q43 | multi | non | cons-12, cons-10, cons-13, cons-14 | art-2, cons-12 | cons-12 | 0 |
| q44 | multi | non | C1 | C1, art-2 | C1 | 0 |
| q45 | multi | non | B97, B110, B112, B113 | 44, 45 | — | 0 |
| q46 | multi | non | 18, 17, 41 | 47, 48 | — | 0 |
| q47 | multi | non | B72, C15 | 44, B72 | B72 | 0 |
| q48 | multi | non | B96, B97 | B96, B97 | B96, B97 | 0 |
| q49 | multi | non | 55, 56 | 55, 56 | 55, 56 | 0 |
| q50 | multi | non | 24, 16 | 16, 22, 24 | 16, 24 | 0 |
| q51 | piege | oui | — | (refus attendu) | — | 0 |
| q52 | piege | oui | — | (refus attendu) | — | 0 |
| q53 | piege | oui | — | (refus attendu) | — | 0 |
| q54 | piege | oui | — | (refus attendu) | — | 0 |
| q55 | piege | oui | — | (refus attendu) | — | 0 |
| q56 | piege | oui | — | (refus attendu) | — | 0 |

## Lecture

- Une citation attendue absente des extraits est une erreur de **recherche** ; présente dans les extraits mais non citée, c'est une erreur de **génération**.
- Les réponses complètes sont dans `eval/results/rag_answers_<date>.md` pour la relecture humaine (fidélité, clarté) de 20 réponses.
