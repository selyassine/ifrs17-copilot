# Relecture humaine des réponses de l'agent RAG (prompt v1)

Réponses : `eval/results/rag_answers_20261003-231744.md` (gpt-oss-120b sur Groq, routeur LLM, recherche hybride B + glossaire).
Méthode : chaque réponse est comparée au texte des paragraphes cités et attendus (`data/processed/C002_units.jsonl`).
Une réponse est **fidèle** si chaque affirmation est soutenue par le paragraphe qu'elle cite et respecte sa portée ;
**complète** si elle couvre toute la question. Relecteur : une personne (à faire relire par un second membre).

## Résultat

| Mesure | Valeur |
| --- | --- |
| Questions pièges refusées | 6/6 |
| Réponses fidèles | 40/50 (80%) |
| Réponses fidèles et complètes | 39/50 (78%) |
| Réponses avec un problème | 11/50 |
| … dont confusion de portée (réassurance, transition, participation directe, PAA) | 7 (q02, q25, q26, q32, q45, q46, q48) |
| … dont réponse reconstruite faute du bon paragraphe | 2 (q22, q42) |
| … dont mauvaise attribution | 1 (q50) |
| … dont incomplète seulement | 1 (q43) |
| Précision des citations, annotation d'origine | 0,63 |
| Précision des citations, en acceptant les paragraphes légitimes | 0,83 |

## Ce qu'on en tire

1. **La précision 0,63 sous-estimait l'agent.** Beaucoup de citations « en trop » sont légitimes (B87 pour l'ajustement pour risque,
   B119C-F pour §66A, §24 pour q03…). Elles sont maintenant dans un champ `acceptables` de `eval/rag_questions.jsonl` (17 questions),
   et `eval_rag` calcule une précision élargie à côté de la précision stricte (D-023).
2. **L'erreur principale est la portée.** L'agent prend un paragraphe proche dans le texte mais qui vise un cas particulier
   (réassurance détenue, transition, participation directe) et l'applique à une question générale. Cause : l'extrait ne montrait
   que le titre court (« Évaluation »), pas sa place dans la norme. → prompt v2 (D-024).
3. **Quand le bon paragraphe manque, l'agent reconstruit au lieu de le dire** (q22, q42). → règle 4 du prompt v2.
4. **Recherche** : q42 (définition) reste une erreur de recherche connue (F-005). Pour q22, q43, q45, vérifier dans le JSON
   des résultats (champ `provided`) si les paragraphes attendus étaient dans les extraits.
5. **Piste suivante (ingestion)** : les titres n'ont qu'un niveau ; §62 à §70 ont « Comptabilisation » ou « Évaluation » comme titre
   et perdent « Contrats de réassurance détenus ». Garder la hiérarchie des titres améliorerait la recherche et la portée.

## Détail

| Id | Niveau | Attendus | Cités | Fidèle | Complète | Type d'erreur | Cause | Commentaire |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| q01 | factuelle | 25 | 25 | oui | oui | — | — |  |
| q02 | factuelle | 32 | 65 | non | non | portée | génération | Question générale (§32) ; répond avec §65, propre à la réassurance détenue, et décrit en fait la CSM, pas l'évaluation. |
| q03 | factuelle | 33 | 33, 24 | oui | oui | — | — |  |
| q04 | factuelle | 34 | B66, 34, B61 | oui | oui | — | — |  |
| q05 | factuelle | 36 | 36, B74, B79 | oui | oui | — | — |  |
| q06 | factuelle | 37 | B87, B89, B88, B90 | oui | oui | — | — | B87 dit la même chose que §37 : citation légitime. |
| q07 | factuelle | 38 | 38 | oui | oui | — | — |  |
| q08 | factuelle | 43 | def:marge sur services contractuels, 43 | oui | oui | — | — |  |
| q09 | factuelle | 44 | 44 | oui | oui | — | — |  |
| q10 | factuelle | 47 | 47, 50 | oui | oui | — | — |  |
| q11 | factuelle | 48 | 48 | oui | oui | — | — |  |
| q12 | factuelle | 53 | 53, 69 | oui | oui | — | — | Juste ; mentionne §69 en précisant qu'il vise la réassurance détenue. |
| q13 | factuelle | 59 | 59 | oui | oui | — | — |  |
| q14 | factuelle | 16 | 16 | oui | oui | — | — |  |
| q15 | factuelle | 22 | 22 | oui | oui | — | — |  |
| q16 | factuelle | 11 | 11, B31, B32 | oui | oui | — | — |  |
| q17 | factuelle | 28B | 28B, C14C, C14B | oui | oui | — | — | Juste ; ajoute C14B/C14C (transition) en le disant clairement : acceptable. |
| q18 | factuelle | 72 | 72 | oui | oui | — | — |  |
| q19 | factuelle | 74 | 74 | oui | oui | — | — |  |
| q20 | factuelle | 78 | 78 | oui | oui | — | — |  |
| q21 | factuelle | 83 | 83, B121, B123 | oui | oui | — | — |  |
| q22 | factuelle | 88 | 118, 80 | non | non | réponse reconstruite | recherche ou génération | §88 (le choix de méthode) n'est pas cité ; la réponse s'appuie sur §118 (informations à fournir) et §80 (présentation). |
| q23 | factuelle | B18 | B19, B22 | oui | oui | — | — | B19 et B22 répondent aussi à la question. |
| q24 | factuelle | B66 | B66 | oui | oui | — | — |  |
| q25 | factuelle | B72 | C13, B72, 44, 66 | non | partiel | portée | génération | Présente C13 (transition) comme la règle générale ; or B72(a) impose des taux courants pour les flux d'exécution, B72(b) des taux initiaux pour l'intérêt sur la CSM. |
| q26 | factuelle | B97 | B97, 67 | partiel | oui | portée | génération | B97 bien restitué, mais §67 (réassurance détenue) est ajouté comme 4e cas d'une règle générale. |
| q27 | factuelle | B101 | B101 | oui | oui | — | — |  |
| q28 | factuelle | B119 | B119, def:période de couverture | oui | oui | — | — |  |
| q29 | factuelle | B120 | B120 | oui | oui | — | — |  |
| q30 | factuelle | C5 | C5, C6 | oui | oui | — | — |  |
| q31 | factuelle | C6 | C6 | oui | oui | — | — |  |
| q32 | factuelle | C20 | C20, C17 | non | partiel | portée | génération | C20 est juste ; C17 relève de l'approche rétrospective modifiée, pas de l'approche juste valeur. |
| q33 | factuelle | 101 | 101 | oui | oui | — | — |  |
| q34 | factuelle | 128 | 128 | oui | oui | — | — |  |
| q35 | factuelle | 130 | 130 | oui | oui | — | — |  |
| q36 | factuelle | 62 | 62, 62A | oui | oui | — | — |  |
| q37 | factuelle | 65 | 65 | oui | oui | — | — | Fidèle à §65. |
| q38 | factuelle | 66A | B119C, B119E, B119D, B119F | oui | oui | — | — | B119C-F détaillent §66A : citations légitimes. |
| q39 | factuelle | def:période de couverture | def:période de couverture | oui | oui | — | — |  |
| q40 | factuelle | def:flux de trésorerie d'exécution | def:flux de trésorerie d'exécution | oui | oui | — | — |  |
| q41 | factuelle | def:composante investissement | def:composante investissement, B31 | oui | oui | — | — |  |
| q42 | factuelle | def:passif au titre de la couverture restante | 51, 41 | non | non | réponse reconstruite | recherche (F-005) | Définition absente des extraits ; la réponse est déduite de §51 et §41, imprécise. |
| q43 | multi | art-2, cons-12 | cons-12, cons-10 | oui | partiel | incomplète | recherche (art-2 absent ?) | Juste, mais ne dit pas que c'est une option (art-2 §2) ni les conditions précises. |
| q44 | multi | C1, art-2 | C1 | oui | oui | — | — | C1 couvre les deux parties de la question. |
| q45 | multi | 44, 45 | B97, B98, B113 | partiel | partiel | portée / attribution | recherche (44, 45 absents ?) et génération | B97(b) déformé (le passif au titre des sinistres survenus disparaît) ; la règle des flux discrétionnaires vient de B98, citée sous B97. |
| q46 | multi | 47, 48 | 19, 18, 48, 50 | non | partiel | portée | génération | §18 et §19 servent au classement en groupes, pas au traitement des contrats onéreux ; §47 (perte en résultat à l'origine) manque. §48 et §50 sont justes. |
| q47 | multi | 44, B72 | 44 | oui | oui | — | — | §44 renvoie bien à B72(b). |
| q48 | multi | B96, B97 | B113, B97 | partiel | oui | portée | génération | B113 (participation directe) présenté comme règle générale ; la partie B97 est juste. |
| q49 | multi | 55, 56 | 55, 56 | oui | oui | — | — |  |
| q50 | multi | 16, 22, 24 | 23, 24, def:groupe de contrats d'assurance | partiel | partiel | attribution | génération | Le contenu de §16 est attribué à §23 ; §24 (pas de révision de la composition) est juste ; §22 (un an d'intervalle) manque. |
