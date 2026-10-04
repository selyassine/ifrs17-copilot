# Évaluation du retrieval

Généré le 20261004-190934 par `python -m eval.eval_retrieval`. 50 questions notées sur 56 (6 questions pièges réservées au test de refus). Chunks : A = 138, B = 380.

## Résultats globaux

A = taille fixe (512 tokens, chevauchement 64) ; B = un chunk par paragraphe avec en-tête de contexte ; B0 = chunks B indexés sans l'en-tête (ablation).

| Configuration | Recall@1 | Recall@5 | Recall@10 | Recall @1000 tokens | Recall @2000 tokens | MRR@10 | nDCG@5 | tokens@5 | p50 (ms) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A · bm25 | 0.323 | 0.650 | 0.770 | 0.470 | 0.620 | 0.492 | 0.510 | 2384 | 0.2 |
| B · bm25 | 0.297 | 0.563 | 0.723 | 0.533 | 0.723 | 0.469 | 0.459 | 972 | 0.4 |
| B0 · bm25 | 0.277 | 0.503 | 0.663 | 0.453 | 0.663 | 0.429 | 0.414 | 947 | 0.4 |
| B · bm25+glossaire | 0.397 | 0.663 | 0.793 | 0.623 | 0.793 | 0.557 | 0.553 | 1024 | 0.6 |

## Par niveau de question

| Configuration | Niveau | n | Recall@5 | MRR@10 |
| --- | --- | --- | --- | --- |
| A · bm25 | factuelle | 42 | 0.667 | 0.464 |
| A · bm25 | multi | 8 | 0.562 | 0.639 |
| B · bm25 | factuelle | 42 | 0.595 | 0.447 |
| B · bm25 | multi | 8 | 0.396 | 0.583 |
| B0 · bm25 | factuelle | 42 | 0.524 | 0.401 |
| B0 · bm25 | multi | 8 | 0.396 | 0.573 |
| B · bm25+glossaire | factuelle | 42 | 0.690 | 0.547 |
| B · bm25+glossaire | multi | 8 | 0.521 | 0.608 |

## Écarts appariés (moyenne et IC bootstrap 95 %)

| Comparaison | Δ Recall@5 | Δ Recall @1000 tokens | Δ MRR@10 |
| --- | --- | --- | --- |
| A · bm25 → B · bm25 | -0.087 [-0.210 ; +0.033] | +0.063 [-0.090 ; +0.220] | -0.023 [-0.126 ; +0.076] |
| B · bm25 → B0 · bm25 | -0.060 [-0.140 ; +0.000] | -0.080 [-0.160 ; -0.020] | -0.040 [-0.089 ; +0.006] |
| B · bm25 → B · bm25+glossaire | +0.100 [+0.030 ; +0.180] | +0.090 [+0.020 ; +0.170] | +0.088 [+0.031 ; +0.156] |

Un intervalle qui ne contient pas 0 indique une différence robuste sur ce jeu de questions.

## Échecs de la meilleure configuration (B · bm25+glossaire)

Questions dont aucun paragraphe attendu n'est dans les 10 premiers résultats :

- **q01** « À partir de quelle date un assureur doit-il reconnaître un groupe de contrats qu'il a émis ? » — attendu 25 ; obtenu C23, cons-4, B73
- **q02** « De quoi se compose l'évaluation d'un groupe de contrats au moment de sa première comptabilisation ? » — attendu 32 ; obtenu 60/61, 62, 25
- **q07** « À l'origine, comment détermine-t-on le montant de la CSM d'un groupe de contrats ? » — attendu 38 ; obtenu C7, B119, C15
- **q11** « Que se passe-t-il lorsque, après l'origine, des variations défavorables des flux dépassent la CSM restante ? » — attendu 48 ; obtenu 46, 50, 44
- **q15** « Peut-on regrouper des contrats émis à deux ans d'écart dans un même groupe ? » — attendu 22 ; obtenu B93, 5, 92
- **q19** « Dans quels cas un contrat d'assurance doit-il être retiré du bilan ? » — attendu 74 ; obtenu 78, B119B, 93
- **q42** « Qu'est-ce que le passif au titre de la couverture restante ? » — attendu def:passif au titre de la couverture restante ; obtenu 46, 51, 50
- **q45** « Quelle différence dans l'ajustement de la CSM entre contrats avec et sans participation directe ? » — attendu 44, 45 ; obtenu B99, B97, B113

## Limites

- Questions rédigées et annotées par une seule personne (biais lexical possible) : à compléter par des questions écrites par l'équipe sans regarder le texte.
- Un seul document (règlement UE 2021/2036) ; les résultats changeront avec le corpus complet.
- Le nombre de tokens est une approximation (1,4 token par mot).
