# Robustesse de l'API (niveau 4)

Généré le 20261022-024138 par `python -m eval.eval_robustesse`.

| Test | Résultat | Détail |
| --- | --- | --- |
| santé | OK | 200 ok |
| sans jeton | OK | 401 (attendu 401) |
| fichier texte | OK | 415 format non pris en charge : PDF, PNG, JPEG, Excel (.xlsx) ou |
| fichier vide | OK | 415 format non pris en charge : PDF, PNG, JPEG, Excel (.xlsx) ou |
| fichier de plus de 10 Mo | OK | 413 fichier trop volumineux (10 Mo maximum) |
| PDF corrompu | OK | 422 PDF illisible : No /Root object! - Is this really a PDF? |
| note d'un dossier inconnu | OK | 404 |
| piste d'audit intacte | OK | 200 {'intacte': True, 'evenements': 117, 'derniere_empreinte': '7737be6dbb194a1891f7b30a2d |
| dossier 1 à la suite (ext01.pdf) | OK | 200 note_prete, 3 s |
| dossier 2 à la suite (ext02.pdf) | OK | 200 note_prete, 3 s |
| dossier 3 à la suite (ext03.pdf) | OK | 200 note_prete, 35 s |
| dossier 4 à la suite (ext04.pdf) | OK | 200 note_prete, 46 s |
| dossier 5 à la suite (ext05.pdf) | OK | 200 note_prete, 24 s |
| 3 dossiers en même temps | OK | codes [200, 200, 200], durée totale 114 s |

Durée d'un dossier complet : médiane 24 s, maximum 46 s (critère : moins de 180 s).

## Tests à faire à la main (noter le résultat)

| Situation | Comportement attendu | Constaté |
| --- | --- | --- |
| API arrêtée pendant qu'un e-mail arrive | n8n envoie « votre dossier n'a pas pu être traité » au déposant et l'alerte à l'équipe ; le contrôle de santé envoie « API injoignable » dans les 15 minutes, puis « API rétablie » | à remplir |
| Clé Groq invalide ou quota épuisé (LLM_API_KEY faux dans .env, API relancée) | réponse 502 « LLM indisponible : … » ; dossier inscrit en « erreur » au registre ; e-mail d'incident | à remplir |
| E-mail « IFRS17 » sans pièce jointe | réponse « aucun document joint » au déposant | à remplir |
| E-mail avec 3 PDF | 3 dossiers distincts au registre ; 3 notes ou 3 formulaires de validation indépendants | à remplir |
| Formulaire n8n avec une image .png | dossier traité en mode vision | à remplir |
| Valideur qui saisit « abc » dans une liste du formulaire | e-mail « échec du dossier … n'est pas un nombre », aucune note fausse | à remplir |
| n8n arrêté pendant qu'un dossier est analysé sur le site | le site affiche « e-mail non envoyé » ; le dossier reste au registre | à remplir |
