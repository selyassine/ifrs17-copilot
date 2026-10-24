# Campagne « prêt pour la production ? » : jeu reel (mode texte)

Généré le 20261021-064427 par `python -m eval.eval_production --jeu reel`. Critères fixés avant la mesure (D-070).

| Critère | Seuil | Atteint |
| --- | --- | --- |
| cas dangereux | 0, et borne supérieure à 95 % sous 5 % | **OUI** |
| feu vert fiable | 100 % des documents acceptés sans humain ont la bonne CSM | **OUI** |
| fausses alertes | au plus 15 % des documents justes envoyés à un humain | **OUI** |
| erreurs techniques | aucune exception ni réponse illisible | **OUI** |
| latence | lecture d'un document en moins de 60 s (95e centile) | **OUI** |

| Mesure | Valeur |
| --- | --- |
| documents | 60 |
| dont pieges ou alertes | 0 |
| cas dangereux | 0 |
| borne dangereux 95 | 0.0487 |
| csm juste | 60/60 |
| feu vert fiable | 60/60 |
| feu vert fiable pct | 1.0 |
| fausses alertes | 0/60 |
| fausses alertes pct | 0.0 |
| alertes levees | 0/0 |
| erreurs rattrapees | 0 |
| erreurs techniques | 0 |
| latence mediane s | 5.0 |
| latence p95 s | 11.8 |
| tokens par document | 2043 |
| appels llm par document | 1.03 |

## Documents à regarder (dangereux, rattrapés, fausses alertes, erreurs)

| Document | Mise en page | Statut | Verdict | CSM juste | CSM lue / attendue | Champs faux | Problèmes |
| --- | --- | --- | --- | --- | --- | --- | --- |
