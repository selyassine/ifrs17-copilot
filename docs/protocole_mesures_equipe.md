# Protocole des mesures qui restent à faire (avant la soutenance)

Ces mesures demandent la clé Groq, un téléphone ou un membre de l'équipe qui n'a pas écrit le code : elles ne
peuvent pas être faites par le générateur de tests. Chaque mesure se lance **une seule fois** sur un jeu figé
d'avance ; le résultat, bon ou mauvais, est reporté tel quel (décisions, échecs, rapport).

## 1. Routeur : 20 questions écrites par un autre membre (F-001, D-085)

Pourquoi : les 20 cas actuels ont été écrits par la personne qui a écrit les règles du routeur (limite notée
dans F-001). Un jeu écrit par quelqu'un d'autre mesure la vraie généralisation (comme le quiz de l'enseignant
pour le RAG, F-012).

Qui : **un membre qui n'a pas lu `agents/router.py` ni `prompts/router/`** (proposition : Maha).

Consigne à lui donner, sans autre aide :

1. Écrire 20 demandes qu'un utilisateur pourrait taper, avec ses propres mots :
   8 questions sur la norme IFRS 17, 4 demandes de traitement d'un document (pièce jointe), 3 calculs à partir
   de chiffres donnés dans le texte, 5 demandes hors périmètre (dont 2 proches : une autre norme IFRS,
   Solvabilité II…).
2. Une ligne par demande dans `eval/router_cases_externes.jsonl`, au format :

   ```json
   {"id": "x01", "request": "…", "has_attachment": false, "intent": "question_norme"}
   ```

   `intent` : `question_norme`, `traitement_document`, `calcul` ou `hors_perimetre` ; `has_attachment` : true
   seulement pour les demandes qui joignent un fichier.
3. Committer le fichier **avant** toute mesure, puis noter son empreinte (affichée par la commande ci-dessous)
   dans `docs/decisions.md` (D-085).

Mesure (une seule fois) :

```powershell
python -m eval.eval_router --llm --jeu externe
```

À reporter : exactitude heuristique et LLM, nombre de replis (doit être 0, F-008), erreurs. Si le score baisse
par rapport à 20/20, c'est un résultat : on l'écrit dans `docs/failures.md` sans corriger les règles sur ce jeu.

## 2. Photos prises au téléphone (D-035, D-070 niveau 2)

1. Imprimer 6 documents : `data/synth/ext04.pdf`, `ext07.pdf`, `ext11.pdf`, `ext14.pdf`,
   `data/synth_hard/dur04.pdf`, `dur08.pdf`.
2. Photographier chacun deux fois : une photo correcte (à plat, lumière du jour), une photo difficile
   (de biais, ombre, ou papier froissé). Soit 12 photos.
3. Les copier dans `data/photos/` en gardant l'identifiant au début du nom : `ext04_plat.jpg`,
   `ext04_biais.jpg`, `dur08_ombre.jpg`… (les photos restent hors de Git, comme `data/`).
4. Mesure :

   ```powershell
   python -m eval.eval_production --jeu photos
   ```

À reporter : CSM justes, alertes, **cas dangereux** (doit rester 0), et ce que montrent les photos ratées. Le
contrôle d'unité D-081 s'applique aussi en mode image (sur la transcription du modèle) : une alerte « unité »
sur une photo dont l'unité est lisible est une fausse alerte à noter.

## 3. Tests manuels n8n (D-059, D-064)

Lancer l'API et n8n, importer `workflows/ifrs17_copilot.json`, régler le nœud « Paramètres » (adresse,
jeton) **dans n8n seulement**. Cocher chaque ligne :

| # | Scénario | Résultat attendu |
| --- | --- | --- |
| 1 | E-mail avec `IFRS17` dans l'objet et `ext01.pdf` en pièce jointe | note en PDF reçue par le déposant |
| 2 | E-mail avec `dur10.pdf` (deux groupes) | une note par groupe, ou validation si un contrôle échoue |
| 3 | E-mail avec un document piégé (`dur02.pdf`, RA absent) | accusé de réception au déposant ; e-mail au valideur avec formulaire pré-rempli |
| 4 | Dans le formulaire : corriger une valeur puis « Approuver » | note validée reçue ; « Modifications du valideur » dans la note et la piste d'audit |
| 5 | Dans le formulaire : « Rejeter » avec un motif | e-mail de rejet au déposant ; statut « rejetée » au registre |
| 6 | Formulaire n8n de dépôt (sans e-mail) | même chaîne que 1 |
| 7 | **Dossier LIC** : e-mail avec le dossier C du camarade | note LIC (Chain Ladder, Mack) ; si un contrôle échoue, formulaire « Approuver / Rejeter » sans cellules |
| 8 | Arrêter l'API 2 minutes | e-mail « API injoignable », puis « API rétablie » au redémarrage |
| 9 | E-mail sans `IFRS17` dans l'objet | rien ne se passe |

À reporter : les lignes cochées et, pour chaque échec, ce qui s'est passé (capture d'écran de l'exécution n8n).

## 4. Mesures avec la clé Groq des nouveautés du 24/10/2026

Toutes en une fois, dans cet ordre (environ 30 minutes avec les pauses du quota gratuit) :

```powershell
python -m pytest -q                                   # d'abord : tous les tests (fastapi et langgraph installés)
python -m multimodal.lic_cases                         # jeu LIC : 8 triangles CAS (6 propres, 2 pièges)
python -m eval.eval_lic --fichier "chemin\vers\dossier_C_farmbureau_cloture_1997.pdf"
python -m eval.eval_extraction --mode texte            # prompt v5 : aucune régression attendue (15/15)
python -m eval.eval_extraction --mode texte --jeu difficile
python -m eval.eval_production --jeu independants      # les 50 PDF du script R : 50/50 attendu, 0 dangereux
python -m eval.eval_copilot --jeu test2                # Copilot v4 : nouveau jeu gelé, UNE seule exécution
```

| Mesure | Ce qui compte | Attendu |
| --- | --- | --- |
| LIC (D-083) | triangles justes, LIC au centime, alertes sur les 2 pièges, cas dangereux | 0 dangereux ; dossier C : LIC 17 634,74 |
| Extraction v5 (D-082) | pas de régression ; dossiers A et B : CV et niveau de confiance lus | 15/15 ; A : CV 12,41 %, 75 % |
| Unité (D-081) | fausses alertes d'unité sur les jeux connus | 0 |
| Copilot v4 (D-084) | outil juste, chiffre juste, unité, relecture humaine | **fait le 24/10 : 8/10, piège obéi (F-023)** |

Après F-023 (garde-fous D-086), une seule mesure de plus, sur 5 pièges neufs :

```powershell
python -m eval.eval_copilot --jeu injections
```

Fait le 24/10 : 5/5 pièges refusés.

Copilot d'un dossier LIC (D-087), une seule fois :

```powershell
python -m eval.eval_copilot --jeu lic
```

Reporter les chiffres dans les fiches de prompts (`eval.scores`), `docs/decisions.md` (D-081 à D-085) et, si
une mesure échoue, `docs/failures.md`.
