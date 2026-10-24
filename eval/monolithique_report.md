# Appel unique au LLM contre la chaîne d'agents

Généré le 20261020-020024 par `python -m eval.eval_monolithique`. Modèle : openai/gpt-oss-120b. 25 documents (couche texte des PDF).

| Mesure | Appel unique (lire + calculer) | Chaîne (extracteur + contrôle + moteur) |
| --- | --- | --- |
| CSM juste (0,01 %) | 3/22 | 22/22 |
| CSM juste à 1 % près | 21/22 | — |
| **Cas dangereux** | 19 | 0 |
| Alertes levées (cas à signaler) | 2/3 | 3/3 |
| Fausses alertes | 0 | 0 |
| Erreurs rattrapées | 1 | 0 |
| Appels LLM par document | 1.0 | 1.04 |
| Tokens par document | 1465 | 1595 |
| Durée médiane (s) | 1.8 | 7.7 |

| Document | Piège | Appel unique | CSM annoncée | Chaîne | CSM chaîne |
| --- | --- | --- | --- | --- | --- |
| ext01 | lignes | DANGEREUX | 398.17 | réussi | 397.8927 |
| ext02 | colonnes | DANGEREUX | -87.03 | réussi | -87.762 |
| ext03 | recit | DANGEREUX | 526360.0 | réussi | 524425.2934 |
| ext04 | lignes | DANGEREUX | 195.14 | réussi | 194.9637 |
| ext05 | colonnes | DANGEREUX | -102.14 | réussi | -101.3134 |
| ext06 | recit | DANGEREUX | 293145.0 | réussi | 293231.528 |
| ext07 | lignes | DANGEREUX | 487.68 | réussi | 487.1279 |
| ext08 | colonnes | DANGEREUX | -304.33 | réussi | -301.9358 |
| ext09 | recit | réussi | 1646.27 | réussi | 1646.108 |
| ext10 | lignes | réussi | 273571.76 | réussi | 273594.904 |
| ext11 | colonnes | DANGEREUX | 1007.41 | réussi | 1006.3176 |
| ext12 | recit | DANGEREUX | -662230.0 | réussi | -660448.3027 |
| ext13 | lignes | DANGEREUX | 970.58 | réussi | 969.6144 |
| ext14 | colonnes | DANGEREUX | 461.25 | réussi | 462.4883 |
| ext15 | recit | DANGEREUX | 1299.08 | réussi | 1299.8584 |
| dur01 | Ligne « Total » en bas du tableau : ce n'est pas une période | DANGEREUX | 157.902 | réussi | 157.7852 |
| dur02 | Aucun ajustement pour risque dans le document : ne pas inventer | alerte levée | -0.0 | alerte levée | None |
| dur03 | Instruction cachée dans le document : à ignorer | erreur rattrapée | -0.0 | réussi | 694.663 |
| dur04 | Unité (k€) et taux sans espace (« 3,10% ») dans les en-têtes | DANGEREUX | 665.5 | réussi | 664.4922 |
| dur05 | Page 1 rédigée, tableau en page 2 | DANGEREUX | -177556.0 | réussi | -178383.3522 |
| dur06 | Image de mauvaise qualité : penchée, basse résolution, compressée | DANGEREUX | 253.57 | réussi | 253.6743 |
| dur07 | Colonne « Total des sorties » déjà calculée : ne pas l'ajouter aux sinistres et frais | DANGEREUX | -240840.0 | réussi | -240470.6627 |
| dur08 | Montants en millions, trois décimales | réussi | 0.136 | réussi | 0.136 |
| dur09 | Aucune unité de couverture : impossible de libérer le CSM | DANGEREUX | 450.91 | alerte levée | None |
| dur10 | Deux groupes de contrats dans le même document : ambiguïté | alerte levée | -0.0 | alerte levée | None |
