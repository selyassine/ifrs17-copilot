# Évaluation du retrieval

Généré le 20261003-202115 par `python -m eval.eval_retrieval`. 50 questions notées sur 56 (6 questions pièges réservées au test de refus). Chunks : A = 137, B = 380.

## Résultats globaux

A = taille fixe (512 tokens, chevauchement 64) ; B = un chunk par paragraphe avec en-tête de contexte ; B0 = chunks B indexés sans l'en-tête (ablation).

| Configuration | Recall@1 | Recall@5 | Recall@10 | Recall @1000 tokens | Recall @2000 tokens | MRR@10 | nDCG@5 | tokens@5 | p50 (ms) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A · bm25 | 0.323 | 0.640 | 0.780 | 0.470 | 0.600 | 0.492 | 0.504 | 2384 | 0.2 |
| B · bm25 | 0.277 | 0.563 | 0.703 | 0.533 | 0.703 | 0.454 | 0.449 | 942 | 0.4 |
| B0 · bm25 | 0.277 | 0.503 | 0.663 | 0.473 | 0.663 | 0.429 | 0.414 | 929 | 0.3 |
| B · bm25+glossaire | 0.377 | 0.653 | 0.793 | 0.623 | 0.793 | 0.546 | 0.540 | 990 | 0.5 |
| A · dense · bge-m3 | 0.273 | 0.760 | 0.820 | 0.423 | 0.673 | 0.478 | 0.531 | 2401 | 212.1 |
| A · hybrid · bge-m3 | 0.353 | 0.620 | 0.840 | 0.500 | 0.610 | 0.517 | 0.511 | 2392 | 116.1 |
| B · dense · bge-m3 | 0.467 | 0.837 | 0.867 | 0.737 | 0.867 | 0.642 | 0.671 | 1054 | 116.5 |
| B · hybrid · bge-m3 | 0.377 | 0.683 | 0.853 | 0.673 | 0.813 | 0.567 | 0.559 | 1016 | 114.1 |
| B0 · dense · bge-m3 | 0.407 | 0.807 | 0.890 | 0.727 | 0.880 | 0.612 | 0.639 | 1128 | 259.5 |
| B0 · hybrid · bge-m3 | 0.407 | 0.703 | 0.783 | 0.693 | 0.763 | 0.569 | 0.575 | 1064 | 114.0 |
| B · hybrid+glossaire · bge-m3 | 0.467 | 0.823 | 0.913 | 0.773 | 0.913 | 0.661 | 0.670 | 1022 | 133.9 |

## Par niveau de question

| Configuration | Niveau | n | Recall@5 | MRR@10 |
| --- | --- | --- | --- | --- |
| A · bm25 | factuelle | 42 | 0.667 | 0.461 |
| A · bm25 | multi | 8 | 0.500 | 0.651 |
| B · bm25 | factuelle | 42 | 0.595 | 0.430 |
| B · bm25 | multi | 8 | 0.396 | 0.583 |
| B0 · bm25 | factuelle | 42 | 0.524 | 0.401 |
| B0 · bm25 | multi | 8 | 0.396 | 0.573 |
| B · bm25+glossaire | factuelle | 42 | 0.690 | 0.537 |
| B · bm25+glossaire | multi | 8 | 0.458 | 0.598 |
| A · dense · bge-m3 | factuelle | 42 | 0.762 | 0.458 |
| A · dense · bge-m3 | multi | 8 | 0.750 | 0.588 |
| A · hybrid · bge-m3 | factuelle | 42 | 0.619 | 0.510 |
| A · hybrid · bge-m3 | multi | 8 | 0.625 | 0.554 |
| B · dense · bge-m3 | factuelle | 42 | 0.905 | 0.670 |
| B · dense · bge-m3 | multi | 8 | 0.479 | 0.494 |
| B · hybrid · bge-m3 | factuelle | 42 | 0.738 | 0.560 |
| B · hybrid · bge-m3 | multi | 8 | 0.396 | 0.604 |
| B0 · dense · bge-m3 | factuelle | 42 | 0.857 | 0.617 |
| B0 · dense · bge-m3 | multi | 8 | 0.542 | 0.588 |
| B0 · hybrid · bge-m3 | factuelle | 42 | 0.738 | 0.546 |
| B0 · hybrid · bge-m3 | multi | 8 | 0.521 | 0.688 |
| B · hybrid+glossaire · bge-m3 | factuelle | 42 | 0.881 | 0.652 |
| B · hybrid+glossaire · bge-m3 | multi | 8 | 0.521 | 0.708 |

## Écarts appariés (moyenne et IC bootstrap 95 %)

| Comparaison | Δ Recall@5 | Δ Recall @1000 tokens | Δ MRR@10 |
| --- | --- | --- | --- |
| A · bm25 → B · bm25 | -0.077 [-0.200 ; +0.043] | +0.063 [-0.090 ; +0.213] | -0.037 [-0.143 ; +0.063] |
| B · bm25 → B0 · bm25 | -0.060 [-0.140 ; +0.000] | -0.060 [-0.140 ; +0.000] | -0.026 [-0.069 ; +0.015] |
| A · dense · bge-m3 → B · dense · bge-m3 | +0.077 [-0.043 ; +0.210] | +0.313 [+0.183 ; +0.460] | +0.163 [+0.050 ; +0.283] |
| A · hybrid · bge-m3 → B · hybrid · bge-m3 | +0.063 [-0.090 ; +0.220] | +0.173 [+0.027 ; +0.320] | +0.050 [-0.060 ; +0.156] |
| B · dense · bge-m3 → B0 · dense · bge-m3 | -0.030 [-0.120 ; +0.050] | -0.010 [-0.100 ; +0.080] | -0.029 [-0.120 ; +0.058] |
| B · hybrid · bge-m3 → B0 · hybrid · bge-m3 | +0.020 [-0.060 ; +0.100] | +0.020 [-0.060 ; +0.100] | +0.002 [-0.053 ; +0.059] |
| B · bm25 → B · bm25+glossaire | +0.090 [+0.020 ; +0.160] | +0.090 [+0.020 ; +0.170] | +0.092 [+0.031 ; +0.165] |
| B · hybrid · bge-m3 → B · hybrid+glossaire · bge-m3 | +0.140 [+0.050 ; +0.240] | +0.100 [+0.000 ; +0.210] | +0.094 [+0.024 ; +0.167] |

Un intervalle qui ne contient pas 0 indique une différence robuste sur ce jeu de questions.

## Échecs de la meilleure configuration (B · hybrid+glossaire · bge-m3)

Questions dont aucun paragraphe attendu n'est dans les 10 premiers résultats :

- **q02** « De quoi se compose l'évaluation d'un groupe de contrats au moment de sa première comptabilisation ? » — attendu 32 ; obtenu 25, 65, 23/24
- **q22** « Peut-on ventiler les produits ou charges financières d'assurance entre résultat net et autres éléments du résultat global ? » — attendu 88 ; obtenu 118, 116, 80
- **q45** « Quelle différence dans l'ajustement de la CSM entre contrats avec et sans participation directe ? » — attendu 44, 45 ; obtenu B97, B99, B113

## Limites

- Questions rédigées et annotées par une seule personne (biais lexical possible) : à compléter par des questions écrites par l'équipe sans regarder le texte.
- Un seul document (règlement UE 2021/2036) ; les résultats changeront avec le corpus complet.
- Le nombre de tokens est une approximation (1,4 token par mot).
