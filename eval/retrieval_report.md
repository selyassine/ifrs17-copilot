# Évaluation du retrieval

Généré le 20261004-015052 par `python -m eval.eval_retrieval`. 50 questions notées sur 56 (6 questions pièges réservées au test de refus). Chunks : A = 138, B = 380.

## Résultats globaux

A = taille fixe (512 tokens, chevauchement 64) ; B = un chunk par paragraphe avec en-tête de contexte ; B0 = chunks B indexés sans l'en-tête (ablation).

| Configuration | Recall@1 | Recall@5 | Recall@10 | Recall @1000 tokens | Recall @2000 tokens | MRR@10 | nDCG@5 | tokens@5 | p50 (ms) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A · bm25 | 0.323 | 0.650 | 0.770 | 0.470 | 0.620 | 0.492 | 0.510 | 2384 | 0.2 |
| B · bm25 | 0.297 | 0.563 | 0.723 | 0.533 | 0.723 | 0.469 | 0.459 | 972 | 0.4 |
| B0 · bm25 | 0.277 | 0.503 | 0.663 | 0.453 | 0.663 | 0.429 | 0.414 | 947 | 0.4 |
| B · bm25+glossaire | 0.397 | 0.663 | 0.793 | 0.623 | 0.793 | 0.557 | 0.553 | 1024 | 0.5 |
| A · dense · bge-m3 | 0.313 | 0.750 | 0.800 | 0.493 | 0.693 | 0.509 | 0.556 | 2401 | 104.7 |
| A · hybrid · bge-m3 | 0.333 | 0.640 | 0.820 | 0.480 | 0.610 | 0.500 | 0.509 | 2395 | 104.4 |
| B · dense · bge-m3 | 0.487 | 0.817 | 0.867 | 0.757 | 0.827 | 0.650 | 0.670 | 1071 | 101.5 |
| B · hybrid · bge-m3 | 0.377 | 0.703 | 0.843 | 0.693 | 0.813 | 0.569 | 0.568 | 1040 | 103.5 |
| B0 · dense · bge-m3 | 0.407 | 0.807 | 0.890 | 0.727 | 0.880 | 0.612 | 0.639 | 1145 | 354.8 |
| B0 · hybrid · bge-m3 | 0.407 | 0.703 | 0.783 | 0.693 | 0.763 | 0.569 | 0.575 | 1082 | 354.8 |
| B · hybrid+glossaire · bge-m3 | 0.467 | 0.833 | 0.913 | 0.733 | 0.913 | 0.664 | 0.676 | 1054 | 311.9 |

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
| A · dense · bge-m3 | factuelle | 42 | 0.762 | 0.499 |
| A · dense · bge-m3 | multi | 8 | 0.688 | 0.557 |
| A · hybrid · bge-m3 | factuelle | 42 | 0.643 | 0.492 |
| A · hybrid · bge-m3 | multi | 8 | 0.625 | 0.542 |
| B · dense · bge-m3 | factuelle | 42 | 0.881 | 0.679 |
| B · dense · bge-m3 | multi | 8 | 0.479 | 0.494 |
| B · hybrid · bge-m3 | factuelle | 42 | 0.762 | 0.567 |
| B · hybrid · bge-m3 | multi | 8 | 0.396 | 0.583 |
| B0 · dense · bge-m3 | factuelle | 42 | 0.857 | 0.617 |
| B0 · dense · bge-m3 | multi | 8 | 0.542 | 0.588 |
| B0 · hybrid · bge-m3 | factuelle | 42 | 0.738 | 0.546 |
| B0 · hybrid · bge-m3 | multi | 8 | 0.521 | 0.688 |
| B · hybrid+glossaire · bge-m3 | factuelle | 42 | 0.881 | 0.655 |
| B · hybrid+glossaire · bge-m3 | multi | 8 | 0.583 | 0.708 |

## Écarts appariés (moyenne et IC bootstrap 95 %)

| Comparaison | Δ Recall@5 | Δ Recall @1000 tokens | Δ MRR@10 |
| --- | --- | --- | --- |
| A · bm25 → B · bm25 | -0.087 [-0.210 ; +0.033] | +0.063 [-0.090 ; +0.220] | -0.023 [-0.126 ; +0.076] |
| B · bm25 → B0 · bm25 | -0.060 [-0.140 ; +0.000] | -0.080 [-0.160 ; -0.020] | -0.040 [-0.089 ; +0.006] |
| A · dense · bge-m3 → B · dense · bge-m3 | +0.067 [-0.067 ; +0.210] | +0.263 [+0.127 ; +0.410] | +0.141 [+0.033 ; +0.254] |
| A · hybrid · bge-m3 → B · hybrid · bge-m3 | +0.063 [-0.077 ; +0.210] | +0.213 [+0.077 ; +0.360] | +0.069 [-0.034 ; +0.171] |
| B · dense · bge-m3 → B0 · dense · bge-m3 | -0.010 [-0.100 ; +0.090] | -0.030 [-0.130 ; +0.060] | -0.037 [-0.126 ; +0.045] |
| B · hybrid · bge-m3 → B0 · hybrid · bge-m3 | +0.000 [-0.070 ; +0.080] | +0.000 [-0.080 ; +0.080] | -0.000 [-0.057 ; +0.057] |
| B · bm25 → B · bm25+glossaire | +0.100 [+0.030 ; +0.180] | +0.090 [+0.020 ; +0.170] | +0.088 [+0.031 ; +0.156] |
| B · hybrid · bge-m3 → B · hybrid+glossaire · bge-m3 | +0.130 [+0.050 ; +0.230] | +0.040 [-0.040 ; +0.130] | +0.094 [+0.029 ; +0.162] |

Un intervalle qui ne contient pas 0 indique une différence robuste sur ce jeu de questions.

## Échecs de la meilleure configuration (B · hybrid+glossaire · bge-m3)

Questions dont aucun paragraphe attendu n'est dans les 10 premiers résultats :

- **q02** « De quoi se compose l'évaluation d'un groupe de contrats au moment de sa première comptabilisation ? » — attendu 32 ; obtenu 25, 23/24, 65
- **q22** « Peut-on ventiler les produits ou charges financières d'assurance entre résultat net et autres éléments du résultat global ? » — attendu 88 ; obtenu 118, 116, 80
- **q45** « Quelle différence dans l'ajustement de la CSM entre contrats avec et sans participation directe ? » — attendu 44, 45 ; obtenu B97, B99, B113

## Limites

- Questions rédigées et annotées par une seule personne (biais lexical possible) : à compléter par des questions écrites par l'équipe sans regarder le texte.
- Un seul document (règlement UE 2021/2036) ; les résultats changeront avec le corpus complet.
- Le nombre de tokens est une approximation (1,4 token par mot).
