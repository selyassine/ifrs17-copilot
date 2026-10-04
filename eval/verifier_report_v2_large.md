# Vérificateur (LLM-juge, prompt v2) contre la relecture humaine — openai/gpt-oss-120b

Généré le 20261004-160038 par `python -m eval.eval_verifier --model large` sur `rag_answers_20261004-015143.json` et `rag_human_labels.jsonl`.

| Mesure | Valeur |
| --- | --- |
| reponses jugees | 48 |
| erreurs detectees | 5/7 |
| fausses alertes | 6/41 |
| dont reponses incompletes | 2 |
| precision du rejet | 0.455 |
| kappa | 0.459 |
| tokens entree | 98781 |
| tokens sortie | 29051 |

| Id | Humain | Juge | Résultat | Problèmes signalés par le juge | Note de la relecture |
| --- | --- | --- | --- | --- | --- |
| q01 | fidèle | ok | juste acceptée | — |  |
| q02 | faux | a_corriger | erreur détectée | hors_portee : [65] La réponse utilise un extrait qui ne s'applique qu'aux contrats de réassurance détenus, alors que la question porte sur l'évaluation d'un groupe de contrats d'assurance général. | §65 (réassurance détenue) présenté comme la règle générale ; §32 non trouvé |
| q03 | faux | ok | erreur manquée | — | B70 (groupes qui influencent d'autres groupes) présenté comme règle générale |
| q04 | fidèle | ok | juste acceptée | — |  |
| q05 | fidèle | ok | juste acceptée | — |  |
| q06 | fidèle | a_corriger | fausse alerte | autre : le juge rejette la réponse sans détailler |  |
| q07 | fidèle | ok | juste acceptée | — |  |
| q08 | fidèle | a_corriger | fausse alerte | non_soutenu : [def:marge sur services contractuels, 43] preuve introuvable dans le paragraphe cité pour « La CSM (marge sur services contractuels) à la fin de la période représente la co… » |  |
| q09 | fidèle | a_corriger | fausse alerte | non_soutenu : Phrase d’introduction sans citation |  |
| q10 | fidèle | ok | juste acceptée | — |  |
| q11 | fidèle | ok | juste acceptée | — |  |
| q12 | fidèle | ok | juste acceptée | — |  |
| q13 | fidèle | ok | juste acceptée | — |  |
| q14 | fidèle | ok | juste acceptée | — |  |
| q15 | fidèle | ok | juste acceptée | — |  |
| q16 | fidèle | ok | juste acceptée | — |  |
| q17 | fidèle | ok | juste acceptée | — |  |
| q18 | fidèle | ok | juste acceptée | — |  |
| q19 | fidèle | ok | juste acceptée | — |  |
| q20 | fidèle | ok | juste acceptée | — |  |
| q21 | fidèle | ok | juste acceptée | — |  |
| q22 | fidèle | ok | juste acceptée | — | §88 non cité |
| q23 | fidèle | a_corriger | fausse alerte | non_soutenu : [B19] La phrase attribue au paragraphe B19 l'idée que le risque peut être important même si la probabilité est faible au niveau du portefeuille, alors que cette nuance se trouve au paragraphe B22. Le B19 ne |  |
| q24 | fidèle | ok | juste acceptée | — |  |
| q25 | faux | a_corriger | erreur détectée | non_soutenu : [44] Affirmation que le paragraphe 44 indique que les mêmes taux sont appliqués aux flux d'exécution et aux variations de la CSM; hors_portee : [B72] Utilisation de B72(b) pour les variations de la CSM, alo | C13 (transition) présenté comme la règle générale des taux |
| q26 | fidèle | a_corriger | fausse alerte | non_soutenu : [B97] L'affirmation selon laquelle les variations de l'ajustement au titre du risque non financier (non liées aux services futurs) n'affectent pas la CSM n'est pas soutenue par le paragraphe B97, qui ne lis | B97(b) et (c) oubliés |
| q27 | fidèle | ok | juste acceptée | — |  |
| q28 | faux | a_corriger | erreur détectée | non_soutenu : [def:période de couverture] première phrase, les unités de couverture ne sont pas définies dans la définition de période de couverture; hors_portee : [44] troisième phrase cite le mauvais paragraphe, le con | contenu de B119 attribué à la définition de la période de couverture et à §44 |
| q29 | fidèle | ok | juste acceptée | — |  |
| q30 | fidèle | ok | juste acceptée | — |  |
| q31 | fidèle | ok | juste acceptée | — |  |
| q32 | fidèle | ok | juste acceptée | — |  |
| q33 | fidèle | ok | juste acceptée | — |  |
| q34 | fidèle | ok | juste acceptée | — |  |
| q35 | fidèle | ok | juste acceptée | — |  |
| q36 | fidèle | ok | juste acceptée | — |  |
| q37 | fidèle | ok | juste acceptée | — |  |
| q38 | fidèle | ok | juste acceptée | — |  |
| q39 | fidèle | ok | juste acceptée | — |  |
| q40 | fidèle | ok | juste acceptée | — |  |
| q41 | fidèle | ok | juste acceptée | — |  |
| q43 | fidèle | ok | juste acceptée | — | art-2 non cité |
| q44 | fidèle | ok | juste acceptée | — |  |
| q45 | faux | a_corriger | erreur détectée | non_soutenu : [B113] la mention des variations discrétionnaires des flux de trésorerie n'est pas supportée par le paragraphe cité | flux discrétionnaires attribués à B113 |
| q46 | faux | ok | erreur manquée | — | §18 et §19 (classement en groupes) utilisés pour le traitement des contrats onéreux |
| q48 | faux | a_corriger | erreur détectée | non_soutenu : [B113] les variations de l’effet de la valeur temps de l'argent et des risques financiers qui ne résultent pas d’éléments sous‑jacents sont présentées comme n'ajustant pas la CSM alors que B113 indique le c | B113 (participation directe) présenté comme règle générale |
| q49 | fidèle | ok | juste acceptée | — |  |
| q50 | fidèle | a_corriger | fausse alerte | non_soutenu : [E3] Phrase sur la détermination du nombre de groupes à partir des paragraphes 14 à 23 | §22 oublié |
