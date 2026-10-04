# Dossiers de bout en bout — jeu difficile

Généré le 20261004-172900 par `python -m eval.eval_case`.

| Mesure | Valeur |
| --- | --- |
| dossiers | 10 |
| statuts | {'note_prete': 3, 'validation_humaine': 6, 'document_illisible': 1} |
| csm de la note juste | 7/7 |
| syntheses verifiees du llm | 9/10 |
| reponses norme validees | 15/20 |
| duree mediane s | 89.5 |
| appels llm par dossier | 6.4 |
| tokens entree par dossier | 11245 |

| Dossier | Statut | CSM juste | Synthèse | Norme validée | Durée (s) | Étapes |
| --- | --- | --- | --- | --- | --- | --- |
| dur01 | note_prete | True | llm | 2/2 | 40.5 | extracteur:ok → calculateur:ok → chercheur_rag+verificateur:ok → chercheur_rag+verificateur:ok → redacteur:ok |
| dur02 | validation_humaine | None | llm | 2/2 | 90.9 | extracteur:a_verifier → calculateur:ok → chercheur_rag+verificateur:ok → chercheur_rag+verificateur:ok → redacteur:ok |
| dur03 | validation_humaine | True | llm | 1/2 | 88.1 | extracteur:ok → calculateur:ok → chercheur_rag+verificateur:ok → chercheur_rag+verificateur:validation_humaine → redacteur:ok |
| dur04 | note_prete | True | llm | 2/2 | 66.8 | extracteur:ok → calculateur:ok → chercheur_rag+verificateur:ok → chercheur_rag+verificateur:ok → redacteur:ok |
| dur05 | validation_humaine | True | llm | 2/3 | 125.8 | extracteur:ok → calculateur:ok → chercheur_rag+verificateur:ok → chercheur_rag+verificateur:validation_humaine → chercheur_rag+verificateur:ok → redacteur:ok |
| dur06 | validation_humaine | True | llm | 1/2 | 87.6 | extracteur:ok → calculateur:ok → chercheur_rag+verificateur:ok → chercheur_rag+verificateur:validation_humaine → redacteur:ok |
| dur07 | note_prete | True | llm | 3/3 | 102.4 | extracteur:ok → calculateur:ok → chercheur_rag+verificateur:ok → chercheur_rag+verificateur:ok → chercheur_rag+verificateur:ok → redacteur:ok |
| dur08 | validation_humaine | True | llm | 1/2 | 106.3 | extracteur:ok → calculateur:ok → chercheur_rag+verificateur:ok → chercheur_rag+verificateur:validation_humaine → redacteur:ok |
| dur09 | document_illisible | None | None | 0/0 | 12.1 | extracteur:echec |
| dur10 | validation_humaine | None | llm | 1/2 | 97.5 | extracteur:a_verifier → calculateur:ok → chercheur_rag+verificateur:ok → chercheur_rag+verificateur:validation_humaine → redacteur:ok |
