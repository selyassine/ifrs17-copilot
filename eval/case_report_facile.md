# Dossiers de bout en bout — jeu facile

Généré le 20261004-165935 par `python -m eval.eval_case`.

| Mesure | Valeur |
| --- | --- |
| dossiers | 1 |
| statuts | {'note_prete': 1, 'validation_humaine': 0, 'document_illisible': 0} |
| csm de la note juste | 1/1 |
| syntheses verifiees du llm | 1/1 |
| reponses norme validees | 2/2 |
| duree mediane s | 73.7 |
| appels llm par dossier | 8.0 |
| tokens entree par dossier | 14507 |

| Dossier | Statut | CSM juste | Synthèse | Norme validée | Durée (s) | Étapes |
| --- | --- | --- | --- | --- | --- | --- |
| ext01 | note_prete | True | llm | 2/2 | 73.7 | extracteur:ok → calculateur:ok → chercheur_rag+verificateur:ok → chercheur_rag+verificateur:ok → redacteur:ok |
