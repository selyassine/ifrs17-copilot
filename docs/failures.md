# Journal des échecs

Le sujet récompense explicitement ce qui n'a pas marché, à condition que ce soit analysé.
Une entrée par échec : ce qu'on attendait, ce qui s'est passé, la cause, ce qu'on a fait, et la mesure après correction.

## F-001 — Le routeur heuristique classe une question IFRS 16 dans IFRS 17

- **Date / auteur :** 2026-10-03, R4
- **Attendu :** « Comment comptabiliser un leasing selon IFRS 16 ? » → `hors_perimetre`.
- **Obtenu :** `question_norme` (cas r18 de `eval/router_cases.jsonl`).
- **Cause :** la règle par mots-clés détecte « ifrs » sans distinguer le numéro de la norme.
- **Décision :** on ne corrige pas la règle à la main pour l'instant. Ce cas sert de point de comparaison pour le routeur LLM (D-009), qui devrait le classer correctement.
- **Mesure :** heuristique 95 % (19/20). Routeur LLM : à mesurer en S2.
- **Limite connue :** les 20 cas ont été écrits par la même personne que les règles. Ajouter en S2 au moins 20 cas rédigés par un autre membre, sans voir les règles.

## Gabarit

```
## F-0xx — <titre court>
- Date / auteur :
- Attendu :
- Obtenu :
- Cause :
- Décision :
- Mesure avant / après :
```
