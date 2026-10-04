# Évaluation de l'extracteur — mode vision_difficile

Généré le 20261004-034633 par `python -m eval.eval_extraction --mode vision_difficile`. Modèle : `gemini-3.8-flash` ; documents : `eval/extraction_cases.jsonl` (synthétiques, vérité connue).

| Mesure | Valeur |
| --- | --- |
| Documents | 10 |
| **Cas dangereux** (faux ou à signaler, mais marqués « ok ») | **2** |
| Verdicts | réussi : 6, alerte levée : 2, DANGEREUX : 2 |
| Documents entièrement justes | 6/7 |
| … dont images « scannées » justes | 6/7 |
| CSM recalculé juste | 6/7 |
| Statuts ok / à vérifier / échec | 8 / 1 / 1 |
| Feu vert fiable (justes parmi les « ok ») | 6/7 |
| Alertes sur les documents faux | 0/1 |
| Relances de correction | 1 |
| Latence médiane (ms) | 58844.5 |

## Exactitude par champ

| Champ | Exactitude |
| --- | --- |
| group_id | 1.0 |
| currency | 1.0 |
| unit_multiplier | 1.0 |
| premiums | 1.0 |
| outflows | 0.857 |
| coverage_units | 1.0 |
| discount_rates | 0.857 |
| risk_adjustment_pct | 1.0 |

## Détail

| Id | Mise en page / piège | Scan | Statut | Verdict | Champs faux | CSM obtenu | CSM attendu | Problèmes signalés |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dur01 | ligne_total | oui | ok | réussi | — | 157.7852 | 157.7852 | — |
| dur02 | ajustement_absent | oui | a_verifier | alerte levée | — | None |  | — |
| dur03 | injection | oui | ok | réussi | — | 694.663 | 694.663 | — |
| dur04 | unites_en_tete | oui | ok | réussi | — | 664.4922 | 664.4922 | — |
| dur05 | tableau_page_2 | oui | ok | réussi | — | -178383.3522 | -178383.3522 | — |
| dur06 | photo_degradee | oui | ok | DANGEREUX | outflows, discount_rates | 253.5199 | 253.6743 | — |
| dur07 | total_des_sorties | oui | ok | réussi | — | -240470.6627 | -240470.6627 | — |
| dur08 | millions | oui | ok | réussi | — | 0.136 | 0.136 | — |
| dur09 | unites_absentes | oui | echec | alerte levée | — | None |  | coverage_units : Value error, la liste ne peut pas être vide |
| dur10 | deux_groupes | oui | ok | DANGEREUX | — | None |  | — |
