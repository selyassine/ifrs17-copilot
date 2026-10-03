# Journal des échecs

Le sujet récompense explicitement ce qui n'a pas marché, à condition que ce soit analysé.
Une entrée par échec : ce qu'on attendait, ce qui s'est passé, la cause, ce qu'on a fait, et la mesure après correction.

## F-001 — Le routeur heuristique classe une question IFRS 16 dans IFRS 17

- **Date / auteur :** 2026-10-03, R4
- **Attendu :** « Comment comptabiliser un leasing selon IFRS 16 ? » → `hors_perimetre`.
- **Obtenu :** `question_norme` (cas r18 de `eval/router_cases.jsonl`).
- **Cause :** la règle par mots-clés détecte « ifrs » sans distinguer le numéro de la norme.
- **Décision :** on ne corrige pas la règle à la main pour l'instant. Ce cas sert de point de comparaison pour le routeur LLM (D-009), qui devrait le classer correctement.
- **Mesure :** heuristique 95 % (19/20). Routeur LLM (gpt-oss-20b) : 100 % (20/20), r18 correctement classé hors périmètre.
- **Limite connue :** les 20 cas ont été écrits par la même personne que les règles. Ajouter en S2 au moins 20 cas rédigés par un autre membre, sans voir les règles.

## F-002 — n8n ne joint pas l'API : `ECONNREFUSED ::1:8000`

- **Date / auteur :** 2026-10-03, R2
- **Attendu :** le workflow 01 appelle `http://localhost:8000/v1/route` et renvoie un plan.
- **Obtenu :** la branche d'erreur du workflow renvoie un 502 avec `connect ECONNREFUSED ::1:8000`.
- **Cause :** Node.js (donc n8n) résout `localhost` en IPv6 `::1`, alors qu'uvicorn écoute seulement en IPv4 (`127.0.0.1`).
- **Décision :** les workflows appellent `http://127.0.0.1:8000`. Alternative écartée : lancer uvicorn sur `::` (moins portable selon les machines).
- **Point positif :** la branche d'erreur a joué son rôle : réponse claire au lieu d'un workflow bloqué.

## F-003 — pypdf coupe les mots du Journal officiel

- **Date / auteur :** 2026-10-03, R1
- **Attendu :** un texte propre pour l'indexation.
- **Obtenu :** « ser vices », « tr ésorer ie », « aff ectés » : sur 7 termes clés (1 798 occurrences), pypdf n'en extrait que 55 % intacts ; « services » et « trésorerie » : 0 occurrence.
- **Cause :** le PDF du Journal officiel espace les caractères (crénage) ; pypdf interprète ces espaces comme des séparateurs de mots.
- **Décision :** pdfplumber (100 % des termes intacts, comme pdftotext) et analyse de la mise en page (D-011).
- **Leçon :** toujours mesurer la qualité d'extraction avant de chercher pourquoi la recherche est mauvaise.

## F-004 — Titres de section perdus en bas de page

- **Date / auteur :** 2026-10-03, R1
- **Obtenu :** §25 sans section « COMPTABILISATION », B120 rattaché à la mauvaise section.
- **Cause :** le filtre des notes de bas de page (petite police, bas de page) supprimait aussi les titres en capitales tombant en bas de page (même taille, 8,5 pt).
- **Décision :** un texte entièrement en capitales n'est jamais une note de bas de page ; les titres sur deux lignes sont recollés.
- **Vérification :** §25 est rattaché à « COMPTABILISATION », B120 à « PRODUITS DES ACTIVITÉS D'ASSURANCE (PARAGRAPHES 83 ET 85) », et le titre sur deux lignes du §80 est complet.

## F-005 — BM25 rate les questions formulées avec d'autres mots que la norme

- **Date / auteur :** 2026-10-03, R1
- **Obtenu :** 8 questions sur 50 sans aucun paragraphe attendu dans le top 10 (meilleure config BM25), par exemple « reconnaître un groupe » (la norme dit « comptabiliser »), « retiré du bilan » (« décomptabiliser »), « qu'est-ce que le passif au titre de la couverture restante » (les §46 à §51 répètent l'expression plus souvent que la définition).
- **Cause :** recherche purement lexicale ; synonymes et reformulations non couverts.
- **Décision :** ne pas ajouter ces mots au glossaire (ce serait ajuster le système au jeu de test). À mesurer : recherche dense BGE-M3 et hybride (S2), puis réécriture de requête et filtre « définition → annexe A » choisi par le routeur (S3).
- **Mesure avant :** voir eval/retrieval_report.md.
- **Mesure après (BGE-M3 dense, B) :** Recall@5 0,653 → 0,837 et MRR 0,546 → 0,642 par rapport à la meilleure config BM25 : la recherche sémantique corrige la plupart des reformulations.

## F-006 — L'hybride naïf est moins bon que le dense seul

- **Date / auteur :** 2026-10-03, R1
- **Attendu :** l'hybride (BM25 + BGE-M3 fusionnés par RRF) au moins aussi bon que chacun des deux.
- **Obtenu :** sur B, Recall@5 0,683 en hybride contre 0,837 en dense seul ; MRR 0,567 contre 0,642.
- **Cause :** la fusion RRF donne le même poids aux deux listes ; or BM25 seul est nettement plus faible (Recall@5 0,563) et fait remonter des paragraphes hors sujet.
- **Décision :** l'hybride n'est gardé qu'avec le glossaire, qui rend la liste BM25 meilleure : B hybride + glossaire atteint MRR 0,661 et un rappel à 1 000 tokens de 0,773, les meilleurs scores. Pistes S3 : pondérer la fusion, ou ajouter un reranker sur les 20 premiers résultats.
- **Leçon :** « hybride » n'est pas automatiquement meilleur ; il faut mesurer chaque composant séparément.

## F-007 — Accents abîmés entre PowerShell et l'API

- **Date / auteur :** 2026-10-03, R2
- **Obtenu :** (1) requête avec accents → `There was an error parsing the body` ; (2) une fois la requête corrigée, réponse affichée « libÃ©rÃ©e » au lieu de « libérée ».
- **Cause :** Windows PowerShell 5.1 envoie le corps dans l'encodage local (pas en UTF-8) et décode en Latin-1 toute réponse JSON qui n'annonce pas `charset=utf-8`. Les données dans l'API étaient correctes (B119 bien trouvé).
- **Décision :** l'API annonce `application/json; charset=utf-8` sur toutes ses réponses ; pour les tests manuels, le corps est converti en octets UTF-8 (commande dans le README). n8n n'est pas concerné (UTF-8 natif).

## F-008 — Le routeur LLM donne exactement le même score que l'heuristique

- **Date / auteur :** 2026-10-03, R4
- **Obtenu :** premier test Groq : 95 % pour le routeur LLM, avec la même erreur (r18) que l'heuristique.
- **Cause probable :** chaque appel LLM échouait et le routeur basculait en silence sur l'heuristique (repli prévu pour la robustesse). Le repli masquait la panne dans l'évaluation.
- **Décision :** l'évaluation compte et affiche les replis avec leur raison ; la raison de l'échec est gardée dans le plan. Une évaluation de composant LLM n'est valide que si le nombre de replis est 0.
- **Leçon :** un mécanisme de secours doit toujours être observable, sinon il fausse les mesures.

## F-009 — Modèles Llama introuvables sur Groq

- **Date / auteur :** 2026-10-03, R4
- **Obtenu :** `HTTP 404 : The model llama-3.3-70b-versatile does not exist or you do not have access to it`, pour le modèle de secours ; le message du modèle principal était masqué.
- **Cause :** les modèles Llama, encore listés dans la documentation, ne sont pas accessibles avec ce compte gratuit (le tableau des limites gratuites ne liste que gpt-oss, Qwen, Whisper…). Le client n'affichait que l'erreur du dernier essai.
- **Décision :** modèles pris dans le tableau des limites gratuites : `openai/gpt-oss-20b` (petit), `openai/gpt-oss-120b` (grand), `qwen/qwen3.8-27b` (secours). Le client affiche désormais les erreurs du principal et du secours. Pour les modèles à raisonnement (gpt-oss) : `reasoning_effort=low`, raisonnement non renvoyé, au moins 1 024 tokens de sortie.
- **Leçon :** toujours vérifier les modèles réellement accessibles avec sa propre clé, pas seulement la documentation.

## Gabarit

```
## F-0xx — <titre court>
- Date / auteur :
- Attendu :
- Obtenu :
- Cause :
- Décision :
- Mesure avant / après :
```
