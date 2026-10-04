# Vérificateur (LLM-juge) contre la relecture humaine — openai/gpt-oss-120b

Généré le 20261004-153357 par `python -m eval.eval_verifier --model large` sur `rag_answers_20261004-015143.json` et `rag_human_labels.jsonl`.

| Mesure | Valeur |
| --- | --- |
| reponses jugees | 48 |
| erreurs detectees | 3/7 |
| fausses alertes | 3/41 |
| dont reponses incompletes | 1 |
| precision du rejet | 0.5 |
| kappa | 0.378 |
| tokens entree | 93177 |
| tokens sortie | 22728 |

| Id | Humain | Juge | Résultat | Problèmes signalés par le juge | Note de la relecture |
| --- | --- | --- | --- | --- | --- |
| q01 | fidèle | ok | juste acceptée | — |  |
| q02 | faux | a_corriger | erreur détectée | hors_portee : [65] Application du paragraphe 65 (réassurance détenue) présentée comme règle générale pour tout groupe de contrats. | §65 (réassurance détenue) présenté comme la règle générale ; §32 non trouvé |
| q03 | faux | ok | erreur manquée | — | B70 (groupes qui influencent d'autres groupes) présenté comme règle générale |
| q04 | fidèle | ok | juste acceptée | — |  |
| q05 | fidèle | ok | juste acceptée | — |  |
| q06 | fidèle | ok | juste acceptée | — |  |
| q07 | fidèle | ok | juste acceptée | — |  |
| q08 | fidèle | ok | juste acceptée | — |  |
| q09 | fidèle | ok | juste acceptée | — |  |
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
| q23 | fidèle | a_corriger | fausse alerte | non_soutenu : [B19] Mention de probabilité faible non contenue dans B19 |  |
| q24 | fidèle | ok | juste acceptée | — |  |
| q25 | faux | a_corriger | erreur détectée | non_soutenu : [44] Affirmation que les mêmes taux que ceux de l'initiale sont appliqués aux flux de trésorerie d'exécution, ce qui n'est pas prévu par le paragraphe 44 | C13 (transition) présenté comme la règle générale des taux |
| q26 | fidèle | a_corriger | fausse alerte | incomplet : [B97] La réponse ne mentionne pas les autres cas pertinents, par ex. les variations des flux d'exécution liées au risque de non‑exécution dans les contrats de réassurance détenus (E2) | B97(b) et (c) oubliés |
| q27 | fidèle | ok | juste acceptée | — |  |
| q28 | faux | ok | erreur manquée | — | contenu de B119 attribué à la définition de la période de couverture et à §44 |
| q29 | fidèle | ok | juste acceptée | — |  |
| q30 | fidèle | ok | juste acceptée | — |  |
| q31 | fidèle | ok | juste acceptée | — |  |
| q32 | fidèle | ok | juste acceptée | — |  |
| q33 | fidèle | ok | juste acceptée | — |  |
| q34 | fidèle | ok | juste acceptée | — |  |
| q35 | fidèle | ok | juste acceptée | — |  |
| q36 | fidèle | a_corriger | fausse alerte | hors_portee : [62A] La phrase ne mentionne pas la condition de couverture proportionnelle prévue par le paragraphe 62A |  |
| q37 | fidèle | ok | juste acceptée | — |  |
| q38 | fidèle | ok | juste acceptée | — |  |
| q39 | fidèle | ok | juste acceptée | — |  |
| q40 | fidèle | ok | juste acceptée | — |  |
| q41 | fidèle | ok | juste acceptée | — |  |
| q43 | fidèle | ok | juste acceptée | — | art-2 non cité |
| q44 | fidèle | ok | juste acceptée | — |  |
| q45 | faux | ok | erreur manquée | — | flux discrétionnaires attribués à B113 |
| q46 | faux | ok | erreur manquée | — | §18 et §19 (classement en groupes) utilisés pour le traitement des contrats onéreux |
| q48 | faux | a_corriger | erreur détectée | non_soutenu : [B113] Affirme que les variations qui ne varient pas en fonction des rendements d’éléments sous‑jacents ne modifient pas la CSM, alors que B113 indique qu’elles entraînent un ajustement de la CSM sauf si B1 | B113 (participation directe) présenté comme règle générale |
| q49 | fidèle | ok | juste acceptée | — |  |
| q50 | fidèle | ok | juste acceptée | — | §22 oublié |
