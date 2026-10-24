# Campagne « prêt pour la production ? » (D-070)

Quatre niveaux de tests, du plus nombreux au plus réaliste. Les **critères d'acceptation sont fixés avant la
mesure** (tableau ci-dessous) ; les résultats sont publiés tels quels, y compris quand un critère n'est pas atteint.

| Critère | Seuil |
| --- | --- |
| Cas dangereux (chiffre faux, ou cas à signaler, annoncé sûr) | 0, et borne supérieure à 95 % sous 5 % |
| Documents acceptés sans humain qui ont la bonne CSM | 100 % |
| Fausses alertes (document juste envoyé à un humain) | au plus 15 % |
| Erreurs techniques (exception, réponse illisible) | aucune |
| Lecture d'un document | moins de 60 s (95ᵉ centile) |
| Dossier complet (norme et note comprises) | moins de 180 s |
| Panne (API, quota, fichier invalide) | toujours un message clair, jamais un silence |

**Pourquoi le volume compte.** 0 cas dangereux sur 25 documents laisse un vrai taux possible jusqu'à 11,3 % ;
sur 150 documents, jusqu'à 2 % (borne de Clopper-Pearson à 95 %, « règle de trois » : 3/n).

## Niveau 1 : volume, documents jamais vus (≈ 45 min, Groq)

```powershell
python -m multimodal.volume                       # 100 propres + 5 séries des 10 pièges = 150 documents
python -m eval.eval_production --jeu volume --chaine-complete 5
```

Nouvelle graine, nouveaux identifiants : aucun de ces documents n'a servi à régler un prompt. Environ
1 600 tokens par document en lecture (≈ 240 000 tokens pour 150) : changer de compte Groq au besoin, ou
couper en deux avec `--limit`. `--chaine-complete 5` fait passer 5 dossiers par toute la chaîne pour la durée et
le coût réels. Lecture des images (quota Gemini) : `--mode vision --limit 30`.

## Niveau 2 : photos réelles au téléphone (≈ 20 min)

1. Imprimer `data/synth/ext01.pdf`, `ext05.pdf`, `ext09.pdf`, `data/synth_hard/dur07.pdf`, `dur10.pdf`.
2. Pour chacun, trois photos : bien droite ; de biais (environ 20°) ; avec une ombre ou sous une lampe jaune.
3. Nommer chaque photo par l'identifiant du document : `ext01_droite.jpg`, `ext01_biais.jpg`, `dur10_ombre.jpg`…
4. Les copier dans `data/photos/`, puis :

```powershell
python -m eval.eval_production --jeu photos
```

La vérité est celle de l'original. `dur10` (deux groupes) doit déclencher une alerte, même photographié.

## Niveau 3 : données réelles et documents indépendants

**3a, montants réels (CAS Loss Reserving Database)** : primes et sinistres déclarés au régulateur américain par
de vraies compagnies, courbe des taux du Trésor américain (FRED). Données publiques : on peut les envoyer aux LLM.

```powershell
python -m multimodal.real_cas                     # télécharge 6 branches, 60 documents (3 mises en page)
python -m multimodal.real_cas --taux-plat 0.04    # si FRED est inaccessible
python -m eval.eval_production --jeu reel
```

Si le téléchargement échoue : récupérer `wkcomp_pos.csv` sur casact.org (Loss Reserving Data Pulled From NAIC
Schedule P) et lancer `python -m multimodal.real_cas --fichier wkcomp_pos.csv --lignes wkcomp`.

**3b, documents de camarades** : voir `docs/consigne_documents_independants.md`. Fichiers et `attendus.csv` dans
`data/independants/`, puis `python -m eval.eval_production --jeu independants`.

**3c, dossiers prospectifs à montants réels (D-072)** : flux ATTENDUS par Chain Ladder au 1er janvier (rien du futur),
branche et durée de couverture écrites (PAA, RA calibré). Les 50 PDF du script R de l'équipe servent de documents
indépendants (mise en page R) ; notre générateur produit les mêmes dossiers dans notre mise en page.

```powershell
python -m actuariat.prospectif data\cas\clrd.csv data\cas\clrd2025.csv --camarade chemin\dossiers_reels
python -m eval.eval_production --jeu independants      # les 50 PDF du script R
python -m actuariat.prospectif data\cas\clrd.csv data\cas\clrd2025.csv
python -m eval.eval_production --jeu prospectif        # les mêmes dossiers, notre mise en page
```

**3d, classeurs Excel et CSV (D-079)** : les 15 documents de référence en tableur (lignes, colonnes, deux
feuilles, CSV à la française) et 7 pièges propres aux tableurs (taux en décimal, nombres en texte, feuille cachée,
injection, formule sans valeur → alerte, deux groupes → alerte, montant au format pourcentage → alerte).

```powershell
python -m multimodal.excel_cases
python -m eval.eval_production --jeu excel
```

## Niveau 4 : robustesse de l'API en marche (≈ 20 min)

```powershell
python -m eval.eval_robustesse                    # sans LLM : jeton, fichier texte, vide, > 10 Mo, PDF corrompu, audit
python -m eval.eval_robustesse --dossiers 5 --paralleles 3
```

Puis les tests à la main listés en fin de `eval/robustesse_report.md` (API arrêtée, quota épuisé, e-mail sans pièce
jointe, e-mail à trois PDF…) : noter ce qui s'est passé dans la colonne « Constaté ».

## Résultats mesurés (21/10/2026, gpt-oss-120b, mode texte)

| Niveau | Documents | CSM juste | Cas dangereux (borne 95 %) | Fausses alertes | Latence médiane | Critères |
| --- | --- | --- | --- | --- | --- | --- |
| 1, volume | 150 jamais vus (100 propres, 50 pièges) | 100/100 propres, 35/35 pièges lisibles | 0 (2,0 %) | 0 | — | 5/5 |
| 3a, montants réels, 1er lot | 60 (graine 1988) | 58/60 | « 54 », artefact de mesure (F-019) | 5 | 64 s | 2/5, lot invalidé |
| 3a, après corrections | 60 jamais vus (graine 2024) | 60/60 | 0 (4,9 %) | 0 | 1,2 s | 5/5 |
| 3a, avec recouvrements (D-071) | 60 jamais vus (graine 2025, 22 avec recouvrements) | 60/60 | 0 (4,9 %) | 0 | 5,0 s | 5/5 |
| 3b, 50 PDF du script R de l'équipe (D-072) | 50 jamais vus, mise en page R | 50/50 | 0 (5,8 %) | 0 | 6,1 s | 3/5 * |
| 3d, tableurs, 1er lot (D-079) | 21 (19 exacts, 2 alertes) | 17/19 | **1** (20,7 %) | 0 | 2,3 s | 3/5, lot à remesurer (F-021) |
| 3d, tableurs, jeu corrigé (D-079, D-080) | 22 (19 exacts, 3 alertes) | 19/19 | 0 (12,7 %) | 0 | 1,3 s | 4/5 (borne : trop peu de documents) |
| 2, images de pages (mode vision, Gemini, double lecture) | 5 (4 exacts, dur10 en alerte) | 4/4 | 0 (45 %) | 0 | 75,5 s | 3/5 (borne ; latence) |
| Plusieurs groupes de bout en bout (D-078) | dur10 sur le site | 2/2 groupes, CSM justes au centime | 0 | 0 | — | note combinée, contrôles passés |
| 4, robustesse sans LLM | 8 vérifications | — | — | — | — | 8/8 |
| 4, charge | 5 dossiers complets à la suite, puis 3 en même temps | 5/5 notes prêtes | — | — | 24 s par dossier (max 46 s) ; 3 simultanés : 114 s | critère 180 s atteint |

Réserve sur le niveau 2 : les 5 images (`…_page-0001`) sont des rendus de pages, pas encore des photos prises au
téléphone sous plusieurs angles ; elles valident la chaîne vision, pas les conditions réelles (biais, ombre, flou).
| **Total des documents jamais vus (lots valides)** | 320 (150 + 60 + 60 + 50) | toutes les CSM lisibles justes | **0 (borne 0,9 %)** | 0 | | |

\* Critères non atteints sur ce lot : la borne (0 sur 50 laisse jusqu'à 5,8 % ; il faut 59 documents pour descendre sous
5 %) et le 95ᵉ centile de latence (303 s : attentes de quota de l'offre gratuite de Groq sur quelques documents, pas de
lecture ; médiane 6,1 s). Aucun document n'a été mal lu.

Le premier lot réel n'est pas effacé : il a révélé deux défauts (règle de comparaison des taux, tableaux sans grille),
corrigés puis remesurés **sur un nouveau tirage**, jamais sur les documents qui ont servi à corriger. Restent à
mesurer : niveau 2 (photos), 3b (documents de camarades), 4 sous charge (`--dossiers 5 --paralleles 3`), et le mode
vision sur les jeux réels.

## Ce qu'on peut dire, et ce qu'on ne peut pas dire

On peut dire : « sur N documents jamais vus, dont des montants réels et des photos, 0 cas dangereux, borne à 95 %
de X % ; les pannes produisent toujours un message clair ». On ne peut pas dire « prêt pour la production chez un
assureur » : il faudrait de vrais dossiers (confidentiels), un hébergement des modèles compatible avec des données
confidentielles, HTTPS et une revue actuarielle des traitements.
