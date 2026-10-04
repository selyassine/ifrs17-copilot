# Relecture humaine : prompt rag_answer v2 contre v1

Réponses v2 : `eval/results/rag_answers_20261004-003445.md` ; v1 : `rag_answers_20261003-231744.md` (même modèle gpt-oss-120b,
même recherche hybride B + glossaire, mêmes 56 questions). Même méthode que `rag_human_review_v1.md`. Relecteur : une personne.

## Résultat

| Mesure | v1 | v2 |
| --- | --- | --- |
| Pièges refusés | 6/6 | 6/6 |
| Faux refus | 0/50 | 0/50 |
| Réponses fidèles (relecture) | 40/50 | **42/50** |
| Réponses fidèles et complètes (relecture) | 39/50 | 39/50 |
| Précision des citations (stricte) | 0,63 | 0,605 |
| Précision élargie (acceptables révisés sur les deux versions) | 0,83 | 0,84 |
| Couverture des paragraphes attendus | 0,797 | 0,823 |
| Au moins un paragraphe attendu cité | 0,86 | 0,88 |
| Plafond de la recherche | 0,823 | 0,823 |
| Tokens d'entrée (56 questions) | 131 291 | 150 152 (+14 %) |

Les acceptables ont été complétés après lecture de v2 (C22, C24, 100, 129, C28, 79, 13, B17, B21, 44), avec le même critère que pour v1,
et les deux versions ont été recalculées avec la même liste : sinon la comparaison aurait favorisé v1.

## Ce qu'on en tire

1. **Gain réel mais faible** : 2 réponses fausses de moins (q32, q45, q50 corrigées ; q28 se dégrade), aucune réponse complète en plus.
   Sur 50 questions, cet écart n'est pas significatif.
2. **La règle de portée marche quand l'information est visible** : q32 (annexe C, « Approche fondée sur la juste valeur »), q35
   et q17 respectent la portée affichée dans le chemin.
3. **Elle ne peut rien quand l'information manque** : pour q02, le chemin de §65 ne dit pas « réassurance » (titres à un seul niveau) ;
   pour q22, q42 (et probablement q46), le bon paragraphe n'est pas dans les extraits. Les 5 réponses encore fausses sont toutes dans ce cas,
   sauf q25. → la suite se joue dans la **donnée** (titres hiérarchiques) et la **recherche** (reranker), pas dans le prompt.
4. La règle 4 (« dire ce qui manque ») n'est pas suivie : q42 reconstruit encore. C'est le rôle du futur vérificateur.

## Décision

v2 devient la version par défaut (`RAG_PROMPT_VERSION=2`) : moins de réponses fausses, même taux de refus, coût +14 % de tokens
d'entrée, acceptable dans le quota. D-024 validée avec cette réserve.

## Questions qui ont changé ou restent fausses

| Id | v1 fidèle/complète | v2 fidèle/complète | Évolution | Commentaire |
| --- | --- | --- | --- | --- |
| q02 | non/non | non/non | = | Toujours §65 (réassurance) présenté comme règle générale ; §32 absent des extraits. Le chemin affiché pour §65 (« Évaluation > Évaluation ») ne contient pas « réassurance » |
| q22 | non/non | non/non | = | Toujours §80/§118 ; affirme même que §80 « prévoit » la ventilation (faux) ; §88 absent |
| q25 | non/partiel | non/partiel | = | C13 (transition) toujours présentée en premier ; §44 cité à tort pour la « répartition » |
| q42 | non/non | non/non | = | Définition absente des extraits ; réponse reconstruite à partir de §41, sans dire que la définition manque |
| q46 | non/partiel | non/partiel | = | Toujours §18/§19 ; §47 manque |
| q32 | non/partiel | oui/oui | + | C17 (rétrospective modifiée) disparu ; C22 et C24 appartiennent bien à l'approche juste valeur |
| q45 | partiel/partiel | oui/partiel | + | B97 restitué correctement, plus d'attribution B98 → B97 ; §44/§45 toujours absents |
| q50 | partiel/partiel | oui/partiel | + | §16 enfin cité pour son contenu ; §22 manque |
| q26 | partiel/oui | partiel/oui | = | §67 toujours ajouté à la liste, mais désormais nommé « réassureur détenu » |
| q48 | partiel/oui | partiel/oui | = | §67 nommé ; B113 (participation directe) toujours présenté sans sa portée |
| q43 | oui/partiel | oui/partiel | = | Inchangé : art-2 non cité |
| q28 | oui/oui | partiel/oui | − | Régression : contenu de B119 attribué à la définition de la période de couverture et à §44 |
| q05 | oui/oui | oui/oui | · | Aucune citation [§…] dans le texte (règle 2 non respectée), citations seulement dans la liste |
| q35 | oui/oui | oui/oui | + | C28 (transition) ajouté en le nommant (« premières applications ») : la règle 3 fonctionne |
| q17 | oui/oui | oui/oui | + | Ne mélange plus C14B/C14C (transition) |

Toutes les autres réponses sont fidèles et complètes dans les deux versions.
