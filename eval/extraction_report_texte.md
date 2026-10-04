# Évaluation de l'extracteur — mode texte

Généré le 20261004-024450 par `python -m eval.eval_extraction --mode texte`. Modèle : `openai/gpt-oss-120b` ; documents : `eval/extraction_cases.jsonl` (synthétiques, vérité connue).

| Mesure | Valeur |
| --- | --- |
| Documents | 15 |
| Documents entièrement justes | 15/15 |
| CSM recalculé juste | 15/15 |
| Statuts ok / à vérifier / échec | 15 / 0 / 0 |
| Feu vert fiable (justes parmi les « ok ») | 15/15 |
| Alertes sur les documents faux | — |
| Relances de correction | 1 |
| Latence médiane (ms) | 1012.8 |

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

| Id | Mise en page | Statut | Champs faux | CSM obtenu | CSM attendu | Problèmes signalés |
| --- | --- | --- | --- | --- | --- | --- |
| ext01 | lignes | ok | — | 397.8927 | 397.8927 | — |
| ext02 | colonnes | ok | — | -87.762 | -87.762 | — |
| ext03 | recit | ok | — | 524425.2934 | 524425.2934 | — |
| ext04 | lignes | ok | — | 194.9731 | 194.9731 | — |
| ext05 | colonnes | ok | — | -101.3134 | -101.3134 | — |
| ext06 | recit | ok | — | 293231.528 | 293231.528 | — |
| ext07 | lignes | ok | — | 487.1279 | 487.1279 | — |
| ext08 | colonnes | ok | — | -301.9358 | -301.9358 | — |
| ext09 | recit | ok | — | 1646.108 | 1646.108 | — |
| ext10 | lignes | ok | — | 273594.904 | 273594.904 | — |
| ext11 | colonnes | ok | — | 1006.3176 | 1006.3176 | — |
| ext12 | recit | ok | — | -660448.3027 | -660448.3027 | — |
| ext13 | lignes | ok | — | 969.6144 | 969.6144 | — |
| ext14 | colonnes | ok | — | 462.4883 | 462.4883 | — |
| ext15 | recit | ok | — | 1299.8584 | 1299.8584 | — |
