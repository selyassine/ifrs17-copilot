# Évaluation du retrieval

Généré le 20261010-043226 par `python -m eval.eval_retrieval`. 15 questions notées sur 15 (0 questions pièges réservées au test de refus). Chunks : A = 138, B = 380.

## Résultats globaux

A = taille fixe (512 tokens, chevauchement 64) ; B = un chunk par paragraphe avec en-tête de contexte ; B0 = chunks B indexés sans l'en-tête (ablation).

| Configuration | Recall@1 | Recall@5 | Recall@10 | Recall @1000 tokens | Recall @2000 tokens | MRR@10 | nDCG@5 | tokens@5 | p50 (ms) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A · bm25 | 0.067 | 0.133 | 0.267 | 0.133 | 0.133 | 0.119 | 0.109 | 2389 | 0.3 |
| B · bm25 | 0.067 | 0.133 | 0.133 | 0.133 | 0.133 | 0.083 | 0.095 | 1140 | 0.5 |
| B0 · bm25 | 0.067 | 0.067 | 0.200 | 0.067 | 0.133 | 0.084 | 0.067 | 998 | 0.4 |
| B · bm25+glossaire | 0.133 | 0.200 | 0.200 | 0.200 | 0.200 | 0.150 | 0.162 | 1075 | 0.7 |
| A · dense · bge-m3 | 0.000 | 0.200 | 0.400 | 0.067 | 0.200 | 0.095 | 0.104 | 2411 | 137.1 |
| A · hybrid · bge-m3 | 0.000 | 0.267 | 0.400 | 0.200 | 0.267 | 0.135 | 0.155 | 2401 | 110.7 |
| B · dense · bge-m3 | 0.067 | 0.200 | 0.200 | 0.200 | 0.200 | 0.133 | 0.151 | 1031 | 109.0 |
| B · hybrid · bge-m3 | 0.133 | 0.200 | 0.333 | 0.200 | 0.267 | 0.168 | 0.162 | 1087 | 107.5 |
| B0 · dense · bge-m3 | 0.067 | 0.133 | 0.200 | 0.133 | 0.200 | 0.100 | 0.100 | 1133 | 100.9 |
| B0 · hybrid · bge-m3 | 0.000 | 0.133 | 0.267 | 0.133 | 0.200 | 0.072 | 0.075 | 1076 | 102.4 |
| B · hybrid+glossaire · bge-m3 | 0.200 | 0.267 | 0.333 | 0.267 | 0.267 | 0.223 | 0.229 | 1119 | 110.6 |

## Par niveau de question

| Configuration | Niveau | n | Recall@5 | MRR@10 |
| --- | --- | --- | --- | --- |
| A · bm25 | cours | 15 | 0.133 | 0.119 |
| B · bm25 | cours | 15 | 0.133 | 0.083 |
| B0 · bm25 | cours | 15 | 0.067 | 0.084 |
| B · bm25+glossaire | cours | 15 | 0.200 | 0.150 |
| A · dense · bge-m3 | cours | 15 | 0.200 | 0.095 |
| A · hybrid · bge-m3 | cours | 15 | 0.267 | 0.135 |
| B · dense · bge-m3 | cours | 15 | 0.200 | 0.133 |
| B · hybrid · bge-m3 | cours | 15 | 0.200 | 0.168 |
| B0 · dense · bge-m3 | cours | 15 | 0.133 | 0.100 |
| B0 · hybrid · bge-m3 | cours | 15 | 0.133 | 0.072 |
| B · hybrid+glossaire · bge-m3 | cours | 15 | 0.267 | 0.223 |

## Écarts appariés (moyenne et IC bootstrap 95 %)

| Comparaison | Δ Recall@5 | Δ Recall @1000 tokens | Δ MRR@10 |
| --- | --- | --- | --- |
| A · bm25 → B · bm25 | +0.000 [-0.200 ; +0.200] | +0.000 [-0.200 ; +0.200] | -0.035 [-0.107 ; +0.011] |
| B · bm25 → B0 · bm25 | -0.067 [-0.200 ; +0.000] | -0.067 [-0.200 ; +0.000] | +0.001 [-0.017 ; +0.020] |
| A · dense · bge-m3 → B · dense · bge-m3 | +0.000 [-0.200 ; +0.200] | +0.133 [+0.000 ; +0.333] | +0.039 [-0.073 ; +0.192] |
| A · hybrid · bge-m3 → B · hybrid · bge-m3 | -0.067 [-0.267 ; +0.133] | +0.000 [-0.200 ; +0.200] | +0.033 [-0.086 ; +0.153] |
| B · dense · bge-m3 → B0 · dense · bge-m3 | -0.067 [-0.200 ; +0.000] | -0.067 [-0.200 ; +0.000] | -0.033 [-0.089 ; +0.000] |
| B · hybrid · bge-m3 → B0 · hybrid · bge-m3 | -0.067 [-0.200 ; +0.000] | -0.067 [-0.200 ; +0.000] | -0.095 [-0.207 ; -0.010] |
| B · bm25 → B · bm25+glossaire | +0.067 [+0.000 ; +0.200] | +0.067 [+0.000 ; +0.200] | +0.067 [+0.000 ; +0.200] |
| B · hybrid · bge-m3 → B · hybrid+glossaire · bge-m3 | +0.067 [+0.000 ; +0.200] | +0.067 [+0.000 ; +0.200] | +0.056 [-0.022 ; +0.200] |

Un intervalle qui ne contient pas 0 indique une différence robuste sur ce jeu de questions.

## Échecs de la meilleure configuration (B · hybrid+glossaire · bge-m3)

Questions dont aucun paragraphe attendu n'est dans les 10 premiers résultats :

- **c02** « À quelle maille doit-on comptabiliser et évaluer les passifs d'assurance ? » — attendu 16 ; obtenu 35, 41, B95
- **c04** « Un groupe de contrats initialement onéreux devient profitable : que faut-il faire ? » — attendu 50 ; obtenu 48, 47, 65
- **c06** « Comment comptabiliser un écart d'expérience sur les sinistres de la période ? » — attendu B97 ; obtenu 130, 57, B41
- **c07** « Où comptabiliser les primes sous IFRS 17 ? » — attendu 83 ; obtenu 55, 106, 35
- **c08** « J'ai vendu un contrat annuel à tacite reconduction et j'anticipe son renouvellement pendant 3 ans. Que dois-je comptabiliser ? » — attendu 34 ; obtenu B95E, C28, 27/28
- **c09** « Les sinistres augmentent depuis deux ans par rapport aux estimations initiales. Qu'impose IFRS 17 ? » — attendu 44 ; obtenu 130, def:passif au titre des sinistres survenus, B41
- **c10** « Quels sont les trois modèles comptables d'IFRS 17 ? » — attendu 32 ; obtenu B137, C3, C32
- **c13** « À quoi sert l'option OCI sous IFRS 17 ? » — attendu 88 ; obtenu C24, 116, 118
- **c14** « J'anticipe une hausse du best estimate au titre des services futurs : le coût moyen des sinistres passe de 10 à 20. Quel est l'impact sur mon résultat ? » — attendu 44 ; obtenu B5, 130, B57
- **c15** « Des contrats auto à garantie annuelle, vendus par un partenaire, affichent un ratio sinistres sur primes de 120 %. Que dois-je faire ? » — attendu 57 ; obtenu 130, 86, B6

## Limites

- Questions rédigées et annotées par une seule personne (biais lexical possible) : à compléter par des questions écrites par l'équipe sans regarder le texte.
- Un seul document (règlement UE 2021/2036) ; les résultats changeront avec le corpus complet.
- Le nombre de tokens est une approximation (1,4 token par mot).
