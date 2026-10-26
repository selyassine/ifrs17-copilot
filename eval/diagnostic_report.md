# Diagnostic de la latence et des refus

## Configuration (sans clé)

- texte : api.groq.com — petit openai/gpt-oss-20b, grand openai/gpt-oss-120b
- secours texte : aucun chez —
- vision : gemini-3.8-flash chez generativelanguage.googleapis.com, secours gemini-3.5-flash-lite
- délai par appel 60 s, nouveaux essais 2, bascule si quota > -1 s, attente totale permise -1 s
- recherche : hybrid, BAAI/bge-m3, agent oui, prompt de réponse v3
- **⚠ aucun secours : chaque quota épuisé fait attendre.**

Traces analysées : 81 appels au modèle ; temps total 595.7 s ; médiane 2.0 s par appel ; 90 % des appels sous 18.9 s ; **7 appels de plus de 20 s** ; attente du quota enregistrée 488.0 s ; 0 passages au modèle de secours ; 3 échecs.

## Causes des appels lents

- attente du quota (429) : 7

## Par agent

| | appels | total (s) | médiane (s) | p90 (s) | max (s) | > 20 s | quota (s) | secours | échecs | jetons entrée |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| chercheur_rag | 50 | 349.3 | 4.1 | 17.1 | 23.7 | 3 | 290.5 | 0 | 0 | 1454 |
| routeur | 15 | 8.0 | 0.6 | 0.7 | 0.8 | 0 | 0.0 | 0 | 0 | 557 |
| verificateur | 16 | 238.4 | 14.6 | 26.3 | 29.3 | 4 | 197.5 | 0 | 3 | 1571 |

## Par modèle

| | appels | total (s) | médiane (s) | p90 (s) | max (s) | > 20 s | quota (s) | secours | échecs | jetons entrée |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| openai/gpt-oss-120b | 47 | 571.1 | 12.3 | 20.2 | 29.3 | 7 | 488.0 | 0 | 3 | 1507 |
| openai/gpt-oss-20b | 34 | 24.6 | 0.7 | 1.1 | 1.4 | 0 | 0.0 | 0 | 0 | 1040 |

## Requêtes et dossiers les plus longs (temps passé dans le modèle)

| identifiant | modèle (s) | appels | détail |
| --- | ---: | ---: | --- |
| diag-34f3d893 | 90.1 | 7 | chercheur_rag 4, routeur 1, verificateur 2 |
| diag-1b3606fe | 66.7 | 6 | chercheur_rag 4, routeur 1, verificateur 1 |
| diag-c1a85f55 | 61.2 | 7 | chercheur_rag 4, routeur 1, verificateur 2 |
| diag-94f6ad59 | 59.7 | 7 | chercheur_rag 5, routeur 1, verificateur 1 |
| diag-17415b8f | 46.2 | 5 | chercheur_rag 3, routeur 1, verificateur 1 |
| diag-3e429f72 | 42.2 | 6 | chercheur_rag 4, routeur 1, verificateur 1 |
| diag-8c5a4aa9 | 42.2 | 5 | chercheur_rag 3, routeur 1, verificateur 1 |
| diag-7cc5c96e | 40.0 | 5 | chercheur_rag 3, routeur 1, verificateur 1 |
| diag-49de3d59 | 39.3 | 7 | chercheur_rag 4, routeur 1, verificateur 2 |
| diag-d0566625 | 31.3 | 8 | chercheur_rag 5, routeur 1, verificateur 2 |
| diag-4996afc5 | 30.5 | 6 | chercheur_rag 4, routeur 1, verificateur 1 |
| diag-f879b51e | 24.2 | 5 | chercheur_rag 3, routeur 1, verificateur 1 |

## Les 15 appels les plus lents

| date | agent | modèle | s | jetons entrée | cause probable | erreur du modèle principal |
| --- | --- | --- | ---: | ---: | --- | --- |
| 2026-10-26T00:29:03 | verificateur | openai/gpt-oss-120b | 29.3 | 3013 | attente du quota (429) |  |
| 2026-10-26T00:37:24 | verificateur | openai/gpt-oss-120b | 26.3 | None | attente du quota (429) |  |
| 2026-10-26T00:28:34 | chercheur_rag | openai/gpt-oss-120b | 23.7 | 2973 | attente du quota (429) |  |
| 2026-10-26T00:32:34 | chercheur_rag | openai/gpt-oss-120b | 20.9 | 2162 | attente du quota (429) |  |
| 2026-10-26T00:32:55 | verificateur | openai/gpt-oss-120b | 20.6 | 2055 | attente du quota (429) |  |
| 2026-10-26T00:36:43 | chercheur_rag | openai/gpt-oss-120b | 20.2 | 2311 | attente du quota (429) |  |
| 2026-10-26T00:29:49 | verificateur | openai/gpt-oss-120b | 20.1 | 2059 | attente du quota (429) |  |
| 2026-10-26T00:31:24 | verificateur | openai/gpt-oss-120b | 19.6 | 1893 | attente du quota (429) |  |
| 2026-10-26T00:32:13 | verificateur | openai/gpt-oss-120b | 18.9 | 2028 | attente du quota (429) |  |
| 2026-10-26T00:27:56 | verificateur | openai/gpt-oss-120b | 18.8 | 2062 | attente du quota (429) |  |
| 2026-10-26T00:31:54 | chercheur_rag | openai/gpt-oss-120b | 18.0 | 2097 | attente du quota (429) |  |
| 2026-10-26T00:30:42 | chercheur_rag | openai/gpt-oss-120b | 17.3 | 2226 | attente du quota (429) |  |
| 2026-10-26T00:34:12 | chercheur_rag | openai/gpt-oss-120b | 17.1 | 1859 | attente du quota (429) |  |
| 2026-10-26T00:29:29 | chercheur_rag | openai/gpt-oss-120b | 16.6 | 2110 | attente du quota (429) |  |
| 2026-10-26T00:31:05 | chercheur_rag | openai/gpt-oss-120b | 16.4 | 1877 | attente du quota (429) |  |

## Batterie de questions (assistant normatif)

15 questions exécutées ; **2 mal traitées** (refus d'une question sur la norme, ou réponse à une question hors périmètre) ; durée médiane 40.4 s.

| question | résultat | paragraphes | durée (s) | appels | quota (s) | détail |
| --- | --- | --- | ---: | ---: | ---: | --- |
| c quoi le PAA | réponse (validation_humaine) | 53, 59 | 33.0 | 8 | 19.5 | routeur 1×0.7 s, recherche et rédaction 5×9.7 s, vérificateur 2×20.9 s |
| C quoi le LRC et comment le calculer | réponse (validation_humaine) | def:passif au titre de la couverture restante, 55 | 67.2 | 6 | 58.0 | routeur 1×0.4 s, recherche et rédaction 4×37.0 s, vérificateur 1×29.3 s |
| c quoi le CSM | réponse (ok) | def:marge sur services contractuels, 38 | 46.5 | 5 | 39.5 | routeur 1×0.3 s, recherche et rédaction 3×25.8 s, vérificateur 1×20.1 s |
| c quoi le LIC | réponse (ok) | def:passif au titre des sinistres survenus | 30.9 | 6 | 24.0 | routeur 1×0.3 s, recherche et rédaction 4×17.5 s, vérificateur 1×12.6 s |
| c'est quoi le BEL | refus ⚠ |  | 21.2 | 5 | 16.5 | routeur 1×0.3 s, recherche et rédaction 4×20.5 s |
| qu'est-ce que le RA ? | réponse (ok) | def:ajustement au titre du risque non financier, B90, B86, B87, B88 | 42.6 | 6 | 34.5 | routeur 1×0.6 s, recherche et rédaction 4×22.0 s, vérificateur 1×19.6 s |
| Comment la marge sur services contractuels est-elle libérée en résultat ? | réponse (validation_humaine) | B119, 44 | 90.4 | 7 | 79.5 | routeur 1×0.4 s, recherche et rédaction 4×50.2 s, vérificateur 2×39.5 s |
| Quand un groupe de contrats est-il déficitaire ? | réponse (validation_humaine) | 47, 48 | 24.7 | 5 | 18.0 | routeur 1×0.7 s, recherche et rédaction 3×7.7 s, vérificateur 1×15.9 s |
| definir un contrat d'assurance | réponse (ok) | def:contrat d'assurance | 61.6 | 7 | 52.5 | routeur 1×0.6 s, recherche et rédaction 4×41.9 s, vérificateur 2×18.7 s |
| quelle différence entre LRC et LIC | réponse (validation_humaine) | def:passif au titre de la couverture restante, def:passif au titre des sinistres survenus | 39.7 | 7 | 29.0 | routeur 1×0.4 s, recherche et rédaction 4×29.0 s, vérificateur 2×9.9 s |
| comment on calcule l'ajustement pour risque | réponse (ok) | B92, B91, B90, B86 | 42.6 | 5 | 35.0 | routeur 1×0.6 s, recherche et rédaction 3×28.3 s, vérificateur 1×13.3 s |
| c quoi la VFA | refus ⚠ |  | 60.1 | 7 | 52.0 | routeur 1×0.7 s, recherche et rédaction 5×46.6 s, vérificateur 1×12.4 s |
| quel taux d'actualisation utiliser selon IFRS 17 | réponse (validation_humaine) | B78, B72, B81, B80, B83 | 40.4 | 5 | 30.0 | routeur 1×0.6 s, recherche et rédaction 3×13.0 s, vérificateur 1×26.3 s |
| Donne-moi une recette de crêpes | refus |  | 0.8 | 1 | 0.0 | routeur 1×0.8 s |
| Comment comptabiliser un leasing selon IFRS 16 ? | refus |  | 0.5 | 1 | 0.0 | routeur 1×0.5 s |
