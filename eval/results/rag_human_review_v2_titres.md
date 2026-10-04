# Relecture humaine : prompt v2 + titres hiérarchiques (D-025)

Réponses : `eval/results/rag_answers_20261004-015143.md`, comparées à `rag_answers_20261004-003445.md` (prompt v2, titres à un niveau).
Seul changement : l'ingestion garde les intertitres parents (§65 : « Contrats de réassurance détenus > Évaluation »), index refait.
Même modèle (gpt-oss-120b), même recherche (hybride B + glossaire), mêmes 56 questions. Relecteur : une personne.

## Recherche (BGE-M3, 50 questions)

| Configuration | Recall@5 avant → après | Rappel à 1 000 tokens | MRR@10 |
| --- | --- | --- | --- |
| B dense | 0,837 → 0,817 | 0,737 → 0,757 | 0,642 → 0,650 |
| B hybride | 0,683 → 0,703 | — | — |
| **B hybride + glossaire (par défaut)** | **0,823 → 0,833** | **0,773 → 0,733** | **0,661 → 0,664** |
| B0 dense (sans en-tête, témoin) | 0,807 → 0,807 | | |

Effet neutre : les écarts (±0,02) sont dans le bruit d'un jeu de 50 questions. Le rappel à 1 000 tokens baisse un peu car les en-têtes
plus longs prennent de la place. Le témoin B0, qui n'a pas d'en-tête, ne bouge pas : la chaîne de mesure est stable.

## Réponses

| Mesure | v2 | v2 + titres |
| --- | --- | --- |
| Pièges refusés | 6/6 | 6/6 |
| Refus sur des questions qui avaient une réponse | 0/50 | 2/50 (q42, q47) |
| Réponses sans affirmation fausse (relecture, sur 50) | 42 | 43 |
| Réponses fidèles et complètes (relecture, sur 50) | 39 | 37 |
| Précision élargie des citations | 0,84 | 0,81 |
| Couverture des paragraphes attendus | 0,823 | 0,851 |
| Tokens d'entrée de l'évaluation | 150 152 | ≈ 128 900 (le compteur affichait 279 085 : il additionnait les deux évaluations du jour, corrigé) |

## Ce qui a changé

| Id | Avant | Après | Commentaire |
| --- | --- | --- | --- |
| q42 | reconstruit à partir de §41 (faux) | **refus** : « les extraits ne contiennent pas la définition » | Comportement voulu par la règle 4 : mieux vaut un refus honnête qu'une réponse inventée. La définition n'est toujours pas trouvée (recherche) |
| q22 | §80/§118 (faux) | B129 + §80 + §118 (fidèle, partiel) | B129 dit bien que §88 et §89 imposent un choix : réponse correcte, §88 toujours absent |
| q26 | §67 (réassurance) mêlé à B97 | B97 seul (fidèle, incomplet) | Ne mélange plus la réassurance ; oublie B97(b) et (c) |
| q48 | — | B96 enfin cité | Mais B113 (participation directe) présenté comme non ajustant : faux |
| q47 | réponse juste (§44 → B72(b)) | **faux refus** | Régression : l'agent juge que « B72(b) » ne précise pas le taux |
| q03 | §24 (juste) | B70 | B70 vise les groupes qui influencent d'autres groupes (mutualisation) : portée élargie à tort |
| **q02** | §65 (réassurance) | **§65 (réassurance), inchangé** | Le titre affiche maintenant « Contrats de réassurance détenus », et le modèle l'ignore. §32 n'est toujours pas trouvé |
| q25, q46, q28, q45 | faux ou partiels | inchangés | |

## Ce qu'on en tire

1. **Les titres hiérarchiques ne changent pas la qualité mesurée** (recherche et réponses dans le bruit). On les garde : ils sont justes,
   ils servent la citation affichée à l'utilisateur et ils donneront au futur vérificateur l'information de portée.
2. **q02 est la preuve que la portée visible ne suffit pas** : quand le seul extrait qui « ressemble » à la question vise un cas particulier,
   le modèle l'utilise quand même. Le prompt ne corrigera pas ça ; il faut soit retrouver §32 (recherche), soit un **vérificateur** qui
   rejette une réponse générale appuyée sur un paragraphe « réassurance » ou « transition ».
3. **Variabilité** : même à température 0,1, deux exécutions donnent des réponses différentes pour quelques questions (q03, q47). Un écart
   de 1 à 3 réponses sur 50 entre deux versions n'est pas une preuve d'amélioration.
4. **Décision** : on arrête ici l'optimisation du RAG (rendement décroissant). Les erreurs restantes vont au vérificateur (S3) ;
   le reranker reste une piste notée pour plus tard.
