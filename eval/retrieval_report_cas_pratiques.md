# Évaluation du retrieval

Généré le 20261017-222909 par `python -m eval.eval_retrieval`. 30 questions notées sur 30 (0 questions pièges réservées au test de refus). Chunks : A = 138, B = 380.

## Résultats globaux

A = taille fixe (512 tokens, chevauchement 64) ; B = un chunk par paragraphe avec en-tête de contexte ; B0 = chunks B indexés sans l'en-tête (ablation).

| Configuration | Recall@1 | Recall@5 | Recall@10 | Recall @1000 tokens | Recall @2000 tokens | MRR@10 | nDCG@5 | tokens@5 | p50 (ms) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A · bm25 | 0.183 | 0.450 | 0.617 | 0.250 | 0.417 | 0.308 | 0.318 | 2386 | 0.3 |
| B · bm25 | 0.167 | 0.450 | 0.600 | 0.417 | 0.517 | 0.302 | 0.324 | 1187 | 0.4 |
| B0 · bm25 | 0.183 | 0.450 | 0.667 | 0.417 | 0.550 | 0.342 | 0.342 | 1159 | 0.4 |
| B · bm25+glossaire | 0.133 | 0.450 | 0.600 | 0.383 | 0.517 | 0.275 | 0.303 | 1161 | 0.5 |
| B · bm25+glossaire+rerank | 0.433 | 0.667 | 0.667 | 0.617 | 0.667 | 0.533 | 0.561 | 1286 | 849.2 |
| A · dense · bge-m3 | 0.283 | 0.517 | 0.650 | 0.383 | 0.450 | 0.406 | 0.409 | 2394 | 101.2 |
| A · hybrid · bge-m3 | 0.250 | 0.583 | 0.700 | 0.450 | 0.517 | 0.412 | 0.437 | 2391 | 103.5 |
| B · dense · bge-m3 | 0.333 | 0.550 | 0.583 | 0.517 | 0.550 | 0.420 | 0.448 | 1230 | 62.3 |
| B · hybrid · bge-m3 | 0.233 | 0.583 | 0.767 | 0.450 | 0.650 | 0.386 | 0.416 | 1185 | 56.3 |
| B0 · dense · bge-m3 | 0.400 | 0.617 | 0.717 | 0.617 | 0.683 | 0.494 | 0.510 | 1368 | 60.2 |
| B0 · hybrid · bge-m3 | 0.317 | 0.650 | 0.750 | 0.583 | 0.733 | 0.469 | 0.495 | 1241 | 59.4 |
| B · hybrid+glossaire · bge-m3 | 0.233 | 0.517 | 0.733 | 0.417 | 0.583 | 0.375 | 0.389 | 1192 | 56.6 |
| B · hybrid+glossaire+rerank · bge-m3 | 0.467 | 0.617 | 0.750 | 0.583 | 0.683 | 0.553 | 0.553 | 1347 | 1085.8 |

## Par niveau de question

| Configuration | Niveau | n | Recall@5 | MRR@10 |
| --- | --- | --- | --- | --- |
| A · bm25 | cas_pratique | 30 | 0.450 | 0.308 |
| B · bm25 | cas_pratique | 30 | 0.450 | 0.302 |
| B0 · bm25 | cas_pratique | 30 | 0.450 | 0.342 |
| B · bm25+glossaire | cas_pratique | 30 | 0.450 | 0.275 |
| B · bm25+glossaire+rerank | cas_pratique | 30 | 0.667 | 0.533 |
| A · dense · bge-m3 | cas_pratique | 30 | 0.517 | 0.406 |
| A · hybrid · bge-m3 | cas_pratique | 30 | 0.583 | 0.412 |
| B · dense · bge-m3 | cas_pratique | 30 | 0.550 | 0.420 |
| B · hybrid · bge-m3 | cas_pratique | 30 | 0.583 | 0.386 |
| B0 · dense · bge-m3 | cas_pratique | 30 | 0.617 | 0.494 |
| B0 · hybrid · bge-m3 | cas_pratique | 30 | 0.650 | 0.469 |
| B · hybrid+glossaire · bge-m3 | cas_pratique | 30 | 0.517 | 0.375 |
| B · hybrid+glossaire+rerank · bge-m3 | cas_pratique | 30 | 0.617 | 0.553 |

## Écarts appariés (moyenne et IC bootstrap 95 %)

| Comparaison | Δ Recall@5 | Δ Recall @1000 tokens | Δ MRR@10 |
| --- | --- | --- | --- |
| A · bm25 → B · bm25 | +0.000 [-0.133 ; +0.133] | +0.167 [+0.000 ; +0.333] | -0.005 [-0.119 ; +0.107] |
| B · bm25 → B0 · bm25 | +0.000 [+0.000 ; +0.000] | +0.000 [+0.000 ; +0.000] | +0.040 [-0.018 ; +0.098] |
| A · dense · bge-m3 → B · dense · bge-m3 | +0.033 [-0.167 ; +0.233] | +0.133 [-0.067 ; +0.333] | +0.014 [-0.161 ; +0.196] |
| A · hybrid · bge-m3 → B · hybrid · bge-m3 | +0.000 [-0.200 ; +0.200] | +0.000 [-0.200 ; +0.200] | -0.026 [-0.169 ; +0.116] |
| B · dense · bge-m3 → B0 · dense · bge-m3 | +0.067 [+0.000 ; +0.167] | +0.100 [+0.000 ; +0.233] | +0.073 [-0.045 ; +0.192] |
| B · hybrid · bge-m3 → B0 · hybrid · bge-m3 | +0.067 [-0.067 ; +0.200] | +0.133 [-0.001 ; +0.300] | +0.083 [-0.014 ; +0.190] |
| B · bm25+glossaire → B · bm25+glossaire+rerank | +0.217 [+0.083 ; +0.367] | +0.233 [+0.100 ; +0.400] | +0.258 [+0.144 ; +0.384] |
| B · hybrid+glossaire · bge-m3 → B · hybrid+glossaire+rerank · bge-m3 | +0.100 [-0.033 ; +0.233] | +0.167 [+0.033 ; +0.333] | +0.179 [+0.080 ; +0.295] |
| B · bm25 → B · bm25+glossaire | +0.000 [+0.000 ; +0.000] | -0.033 [-0.100 ; +0.000] | -0.028 [-0.094 ; +0.033] |
| B · hybrid · bge-m3 → B · hybrid+glossaire · bge-m3 | -0.067 [-0.167 ; +0.000] | -0.033 [-0.100 ; +0.000] | -0.012 [-0.037 ; +0.007] |

Un intervalle qui ne contient pas 0 indique une différence robuste sur ce jeu de questions.

## Échecs de la meilleure configuration (B · hybrid+glossaire+rerank · bge-m3)

Questions dont aucun paragraphe attendu n'est dans les 10 premiers résultats :

- **p04** « Un contrat de retraite contient une part d'épargne qu'une banque pourrait vendre seule. Doit-on la sortir du contrat d'assurance ? » — attendu 11 ; obtenu B31, 6/7, B26
- **p05** « Notre police santé inclut un abonnement à une salle de sport sans lien avec le risque assuré. Comment traiter ce service ? » — attendu 12 ; obtenu B14, B21, B11
- **p08** « Les commissions versées aux courtiers pour vendre une gamme de contrats : comment les rattacher aux groupes ? » — attendu 28A ; obtenu 23/24, B93, B35A
- **p19** « En cas de rachat, la somme restituée à l'assuré peut-elle figurer dans le chiffre d'affaires et dans les charges de sinistres ? » — attendu 85 ; obtenu B21, 42, 84
- **p20** « La désactualisation de nos engagements et l'effet des variations de taux : sur quelle ligne du compte de résultat ? » — attendu 87 ; obtenu B97, B75, B72
- **p27** « À la transition, impossible de reconstituer l'historique de contrats souscrits il y a quinze ans. Comment fixer leur marge ? » — attendu C5, C20 ; obtenu C15, C17, C14D
- **p29** « Que publier sur l'effet d'une hausse de la mortalité ou d'une baisse des taux sur le résultat et les capitaux propres ? » — attendu 128 ; obtenu B57, B58, B56

## Limites

- Questions rédigées et annotées par une seule personne (biais lexical possible) : à compléter par des questions écrites par l'équipe sans regarder le texte.
- Un seul document (règlement UE 2021/2036) ; les résultats changeront avec le corpus complet.
- Le nombre de tokens est une approximation (1,4 token par mot).
