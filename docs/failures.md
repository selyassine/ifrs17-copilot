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

## F-010 — Plantage silencieux de PyTorch sous Windows (0xC0000005)

- **Date / auteur :** 2026-10-03, R5
- **Obtenu :** `python -m eval.eval_rag` s'arrête juste après le chargement de BGE-M3, sans message ; code de sortie -1073741819 (violation d'accès). Le même programme fonctionne à la relance.
- **Cause probable :** conflit intermittent entre les fils parallèles OpenMP/MKL de PyTorch et de NumPy sous Windows, au premier encodage.
- **Décision :** nombre de fils limité (4) avant le chargement de PyTorch ; l'évaluation sauvegarde chaque réponse au fur et à mesure et peut reprendre (`--resume`), pour qu'un plantage ne gaspille ni temps ni quota Groq.
- **Leçon :** une évaluation longue qui consomme un quota payant ou limité doit être reprenable.

## F-011 — Réponses justes en apparence mais hors de portée

- **Date / auteur :** 2026-10-03, R6
- **Attendu :** une réponse fidèle aux paragraphes cités et à la question posée.
- **Obtenu :** relecture humaine des 50 réponses du prompt v1 : 39 fidèles et complètes. Les 11 autres : 7 confusions de portée
  (q02 répond à une question générale avec §65, propre à la réassurance détenue ; q25 présente le taux de transition C13 comme
  la règle générale ; q32 mélange l'approche juste valeur et l'approche rétrospective modifiée…), 2 réponses reconstruites faute
  du bon paragraphe (q22, q42), 1 mauvaise attribution (q50), 1 réponse incomplète (q43).
  Les mesures automatiques ne voyaient rien : 0 citation inventée, et toutes les citations étaient bien dans les extraits.
- **Cause :** le paragraphe cité existe et contient bien la phrase, mais il vise un cas particulier. L'extrait n'affichait que
  le titre court (« Évaluation »), pas sa place dans la norme (annexe C, réassurance détenue…).
- **Décision :** prompt v2 (chemin complet de chaque extrait, règles de portée, D-024) ; annotation élargie (D-023).
  Le futur agent vérificateur devra contrôler la portée, pas seulement l'existence de la citation.
- **Mesure avant / après :** fidèles 40 → 42/50, fidèles et complètes 39 → 39/50. v2 corrige q32, q45, q50, dégrade q28 ; q02, q22, q25, q42, q46 restent fausses : sauf q25, l'information nécessaire n'est pas dans les extraits (bon paragraphe non trouvé, ou chemin sans « réassurance » car les titres n'ont qu'un niveau). Titres hiérarchiques (D-025) : q02 reste fausse alors que le titre affiche « Contrats de réassurance détenus » ; le modèle utilise l'extrait qui ressemble le plus à la question, quelle que soit sa portée. → contrôle de portée confié au vérificateur.
- **Leçon :** une citation vérifiable n'est pas forcément une citation juste. La vérification automatique prouve que le texte
  existe, seule la relecture (ou un juge) dit s'il répond à la question.

## F-012 — Le RAG ne généralise pas aux questions d'un enseignant, et la réécriture de requête n'y change rien

- **Date / auteur :** 2026-10-10, R3
- **Attendu :** sur les 15 questions des quiz d'un cours IFRS 17 (jeu hors échantillon, D-044), un niveau proche du jeu principal.
- **Obtenu :** recherche hybride BGE-M3 + glossaire : Recall@5 0,267 contre 0,833 sur le jeu principal. Agent RAG : bon paragraphe
  cité dans 27 % des réponses, 4 faux refus sur 15. Le vérificateur juge pourtant 14 réponses sur 15 « ok » : il contrôle la
  fidélité aux extraits, pas le choix des extraits.
- **Cause :** écart de vocabulaire. Le jeu principal a été écrit par l'équipe avec les mots de la norme ; le cours dit « maille »,
  « option OCI », « tacite reconduction », la norme « niveau d'agrégation », « autres éléments du résultat global », « périmètre du contrat ».
- **Décision :** réécriture de la question par le petit modèle avant la recherche (D-045), mesurée puis **non retenue** :
  plafond de la recherche 0,267 → 0,267, bon paragraphe cité 0,273 → 0,300, faux refus 4 → 5, tokens +46 %, latence ×2,2.
  Les reformulations restent dans le même voisinage sémantique que la question : elles ne font pas apparaître le paragraphe manquant.
  Prochaine piste : adapter le modèle de vecteurs au domaine (fine-tuning de BGE-M3 sur des paires question–paragraphe), mesuré sur ce quiz.
- **Mesure avant / après :** voir eval/rag_answer_report_v2_course_quiz.md et eval/rag_answer_report_v2_course_quiz_reecriture.md.
- **Leçon :** un jeu de test écrit par l'équipe surestime la qualité ; un jeu écrit par quelqu'un d'autre est indispensable.
  Et un vérificateur de fidélité ne détecte pas un mauvais choix de paragraphe : une réponse fidèle à de mauvais extraits passe.

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
