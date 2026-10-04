# Évaluation de l'extracteur — mode texte

Généré le 20261004-152427 par `python -m eval.eval_extraction --mode texte`. Modèle : `openai/gpt-oss-120b` ; documents : `eval/extraction_cases.jsonl` (synthétiques, vérité connue).

| Mesure | Valeur |
| --- | --- |
| Documents | 15 |
| **Cas dangereux** (faux ou à signaler, mais marqués « ok ») | **0** |
| Verdicts | réussi : 15 |
| Documents entièrement justes | 15/15 |
| … dont images « scannées » justes | 7/7 |
| CSM recalculé juste | 15/15 |
| Statuts ok / à vérifier / échec | 15 / 0 / 0 |
| Feu vert fiable (justes parmi les « ok ») | 15/15 |
| Alertes sur les documents faux | — |
| Relances de correction | 1 |
| Latence médiane (ms) | 1255.3 |

## Exactitude par champ

| Champ | Exactitude |
| --- | --- |
| group_id | 1.0 |
| currency | 1.0 |
| unit_multiplier | 1.0 |
| premiums | 1.0 |
| outflows | 1.0 |
| coverage_units | 1.0 |
| discount_rates | 1.0 |
| risk_adjustment_pct | 1.0 |

## Détail

| Id | Mise en page / piège | Scan | Statut | Verdict | Champs faux | CSM obtenu | CSM attendu | Problèmes signalés |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ext01 | lignes | non | ok | réussi | — | 397.8927 | 397.8927 | — |
| ext02 | colonnes | oui | ok | réussi | — | -87.762 | -87.762 | — |
| ext03 | recit | non | ok | réussi | — | 524425.2934 | 524425.2934 | — |
| ext04 | lignes | oui | ok | réussi | — | 194.9731 | 194.9731 | — |
| ext05 | colonnes | non | ok | réussi | — | -101.3134 | -101.3134 | — |
| ext06 | recit | oui | ok | réussi | — | 293231.528 | 293231.528 | — |
| ext07 | lignes | non | ok | réussi | — | 487.1279 | 487.1279 | — |
| ext08 | colonnes | oui | ok | réussi | — | -301.9358 | -301.9358 | — |
| ext09 | recit | non | ok | réussi | — | 1646.098 | 1646.108 | — |
| ext10 | lignes | oui | ok | réussi | — | 273594.904 | 273594.904 | — |
| ext11 | colonnes | non | ok | réussi | — | 1006.3176 | 1006.3176 | — |
| ext12 | recit | oui | ok | réussi | — | -660448.3027 | -660448.3027 | — |
| ext13 | lignes | non | ok | réussi | — | 969.6144 | 969.6144 | — |
| ext14 | colonnes | oui | ok | réussi | — | 462.4883 | 462.4883 | — |
| ext15 | recit | non | ok | réussi | — | 1299.8584 | 1299.8584 | — |
