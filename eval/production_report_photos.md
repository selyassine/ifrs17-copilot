# Campagne « prêt pour la production ? » : jeu photos (mode vision)

Généré le 20261022-022648 par `python -m eval.eval_production --jeu photos`. Critères fixés avant la mesure (D-070).

| Critère | Seuil | Atteint |
| --- | --- | --- |
| cas dangereux | 0, et borne supérieure à 95 % sous 5 % | **NON** |
| feu vert fiable | 100 % des documents acceptés sans humain ont la bonne CSM | **OUI** |
| fausses alertes | au plus 15 % des documents justes envoyés à un humain | **OUI** |
| erreurs techniques | aucune exception ni réponse illisible | **OUI** |
| latence | lecture d'un document en moins de 60 s (95e centile) | **NON** |

| Mesure | Valeur |
| --- | --- |
| documents | 5 |
| dont pieges ou alertes | 1 |
| cas dangereux | 0 |
| borne dangereux 95 | 0.4507 |
| csm juste | 4/4 |
| feu vert fiable | 4/4 |
| feu vert fiable pct | 1.0 |
| fausses alertes | 0/4 |
| fausses alertes pct | 0.0 |
| alertes levees | 1/1 |
| erreurs rattrapees | 0 |
| erreurs techniques | 0 |
| latence mediane s | 75.5 |
| latence p95 s | 208.0 |
| tokens par document | 6651 |
| appels llm par document | 2.0 |

## Documents à regarder (dangereux, rattrapés, fausses alertes, erreurs)

| Document | Mise en page | Statut | Verdict | CSM juste | CSM lue / attendue | Champs faux | Problèmes |
| --- | --- | --- | --- | --- | --- | --- | --- |
