# Campagne « prêt pour la production ? » : jeu excel (mode texte)

Généré le 20261021-215540 par `python -m eval.eval_production --jeu excel`. Critères fixés avant la mesure (D-070).

| Critère | Seuil | Atteint |
| --- | --- | --- |
| cas dangereux | 0, et borne supérieure à 95 % sous 5 % | **NON** |
| feu vert fiable | 100 % des documents acceptés sans humain ont la bonne CSM | **OUI** |
| fausses alertes | au plus 15 % des documents justes envoyés à un humain | **OUI** |
| erreurs techniques | aucune exception ni réponse illisible | **OUI** |
| latence | lecture d'un document en moins de 60 s (95e centile) | **OUI** |

| Mesure | Valeur |
| --- | --- |
| documents | 22 |
| dont pieges ou alertes | 3 |
| cas dangereux | 0 |
| borne dangereux 95 | 0.1273 |
| csm juste | 19/19 |
| feu vert fiable | 19/19 |
| feu vert fiable pct | 1.0 |
| fausses alertes | 0/19 |
| fausses alertes pct | 0.0 |
| alertes levees | 3/3 |
| erreurs rattrapees | 0 |
| erreurs techniques | 0 |
| latence mediane s | 1.3 |
| latence p95 s | 18.6 |
| tokens par document | 2005 |
| appels llm par document | 1.09 |

## Documents à regarder (dangereux, rattrapés, fausses alertes, erreurs)

| Document | Mise en page | Statut | Verdict | CSM juste | CSM lue / attendue | Champs faux | Problèmes |
| --- | --- | --- | --- | --- | --- | --- | --- |
