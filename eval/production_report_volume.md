# Campagne « prêt pour la production ? » : jeu volume (mode texte)

Généré le 20261021-025244 par `python -m eval.eval_production --jeu volume`. Critères fixés avant la mesure (D-070).

| Critère | Seuil | Atteint |
| --- | --- | --- |
| cas dangereux | 0, et borne supérieure à 95 % sous 5 % | **OUI** |
| feu vert fiable | 100 % des documents acceptés sans humain ont la bonne CSM | **OUI** |
| fausses alertes | au plus 15 % des documents justes envoyés à un humain | **OUI** |
| erreurs techniques | aucune exception ni réponse illisible | **OUI** |
| latence | lecture d'un document en moins de 60 s (95e centile) | **OUI** |

| Mesure | Valeur |
| --- | --- |
| documents | 150 |
| dont pieges ou alertes | 15 |
| cas dangereux | 0 |
| borne dangereux 95 | 0.0198 |
| csm juste | 135/135 |
| feu vert fiable | 135/135 |
| feu vert fiable pct | 1.0 |
| fausses alertes | 0/135 |
| fausses alertes pct | 0.0 |
| alertes levees | 15/15 |
| erreurs rattrapees | 0 |
| erreurs techniques | 0 |
| latence mediane s | 1.3 |
| latence p95 s | 8.2 |
| tokens par document | 1570 |
| appels llm par document | 1.04 |

## Dossiers de bout en bout

| Dossier | Statut | Durée (s) | Appels LLM | Tokens |
| --- | --- | --- | --- | --- |
| v001 | note_prete | 3.5 | 2 | 4000 |
| v002 | note_prete | 3.6 | 2 | 4322 |
| v003 | note_prete | 29.9 | 3 | 7122 |
| v004 | note_prete | 43.9 | 3 | 6755 |
| v005 | note_prete | 26.0 | 2 | 4373 |

## Documents à regarder (dangereux, rattrapés, fausses alertes, erreurs)

| Document | Mise en page | Statut | Verdict | Problèmes |
| --- | --- | --- | --- | --- |
