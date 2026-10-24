# Dossiers de bout en bout — jeu facile

Généré le 20261019-025924 par `python -m eval.eval_case`.

| Mesure | Valeur |
| --- | --- |
| dossiers | 3 |
| statuts | {'note_prete': 3, 'validation_humaine': 0, 'document_illisible': 0} |
| csm de la note juste | 3/3 |
| syntheses verifiees du llm | 3/3 |
| reponses norme validees | 7/7 |
| duree mediane s | 168.2 |
| appels llm par dossier | 12.0 |
| tokens entree par dossier | 21343 |

| Dossier | Statut | CSM juste | Synthèse | Norme validée | Durée (s) | Étapes |
| --- | --- | --- | --- | --- | --- | --- |
| ext01 | note_prete | True | llm | 2/2 | 89.8 | extracteur:ok → calculateur:ok → chercheur_rag+verificateur:ok → chercheur_rag+verificateur:ok → redacteur:ok |
| ext02 | note_prete | True | llm | 3/3 | 168.2 | extracteur:ok → calculateur:ok → chercheur_rag+verificateur:ok → chercheur_rag+verificateur:ok → chercheur_rag+verificateur:ok → redacteur:ok |
| ext03 | note_prete | True | llm | 2/2 | 428.1 | extracteur:ok → calculateur:ok → chercheur_rag+verificateur:ok → chercheur_rag+verificateur:ok → redacteur:ok |
