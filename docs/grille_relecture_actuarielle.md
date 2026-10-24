# Grille de relecture actuarielle d'une note IFRS 17 Copilot (D-077)

Une note produite par le système n'est jamais diffusée sans la relecture d'un actuaire, même quand tous les
contrôles automatiques sont passés (F-017). Cette grille rend la relecture homogène et traçable : une ligne par
point, réponse **oui / non / sans objet**, et un commentaire si la réponse est non. La grille remplie est jointe
au dossier (registre, événement `validation_approuvee`, champ commentaire).

## 1. Données

| # | Point à vérifier | Où le voir dans la note |
| --- | --- | --- |
| D1 | Le groupe de contrats, la devise et l'unité des montants correspondent au document source | Page de garde, section 3 |
| D2 | Chaque donnée a été retrouvée dans le document (tableau « Où chaque donnée a été lue ») | Section 3 |
| D3 | Les primes, sinistres, recouvrements et frais d'acquisition sont dans la bonne colonne (pas de produits financiers dans les sorties, B66) | Section 3, flux par période |
| D4 | La durée de couverture et la branche sont celles du contrat | Page de garde |
| D5 | Les corrections du valideur, s'il y en a, sont justifiées | Section 3, « Modifications du valideur » |

## 2. Hypothèses

| # | Point à vérifier | Où le voir dans la note |
| --- | --- | --- |
| H1 | La courbe des taux est celle de la date d'évaluation et de la devise du groupe (§36, B72) | Section 4 |
| H2 | L'ajustement pour risque atteint le niveau de confiance cible du registre ; sinon, l'écart est accepté par écrit | Section 8, encadré « niveau de confiance cible » |
| H3 | La volatilité utilisée est calibrée pour la branche ; si elle est « prudente » ou « supposée », la limite est acceptée | Section 4, ligne « Ajustement au titre du risque » |
| H4 | Le profil des unités de couverture reflète le service rendu (B119) | Section 6 |
| H5 | La version du registre des hypothèses citée est la version en vigueur | Section 4, annexe A |

## 3. Calculs

| # | Point à vérifier | Où le voir dans la note |
| --- | --- | --- |
| C1 | CSM ou perte initiale cohérente avec un ordre de grandeur calculé à la main (primes − sorties actualisées − RA − frais d'acquisition) | Section 5 |
| C2 | Le passif se rapproche période par période et s'éteint en fin de couverture | Section 7 |
| C3 | Couverture d'un an au plus : la mesure PAA est cohérente avec le modèle général (même résultat total) | Section 7, PAA |
| C4 | Les sensibilités vont dans le sens attendu ; le seuil de bascule est plausible | Section 8 |
| C5 | Note de clôture : écart de rapprochement nul ; écarts d'expérience en résultat, révisions affectées au bon service | Note de clôture, sections 2, 3 et 6 |

## 4. Norme et rédaction

| # | Point à vérifier | Où le voir dans la note |
| --- | --- | --- |
| N1 | Les paragraphes cités répondent à la question posée | Section 9 |
| N2 | Le résumé ne contient aucun chiffre absent des tableaux | Section 1 |
| N3 | Les limites de la section 10 sont acceptables pour l'usage prévu de la note | Section 10 |

## 5. Décision

| Décision | Signification |
| --- | --- |
| Approuvée | Diffusion possible ; visa dans le tableau de validation de la note |
| Approuvée avec réserves | Diffusion possible ; réserves écrites dans le commentaire de validation |
| Rejetée | Données ou hypothèses à reprendre ; motif écrit, le dossier reste au registre |

Le back-testing (`eval/backtest_report.md`) montre pourquoi cette relecture reste nécessaire : une projection
mécanique peut se tromper d'un facteur 2 à 4 pour certaines compagnies (responsabilité médicale), et seule la
connaissance du portefeuille permet de le voir avant que le réalisé ne le révèle.
