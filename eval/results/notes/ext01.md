# Note actuarielle IFRS 17 — Évaluation IFRS 17 du groupe PREV-2023-A

**Statut : Contrôles automatiques passés** · montants en milliers de USD · établie le 19/10/2026 à 03:00

| Élément | Valeur |
| --- | ---: |
| Entité | Compagnie d'assurance fictive (projet pédagogique) |
| Groupe de contrats | PREV-2023-A |
| Méthode | Modèle général (BBA) |
| Monnaie et unité | Montants en milliers de USD |
| Durée de couverture | 6 périodes (années) |
| Date d'établissement | 19/10/2026 à 03:00 |
| Référence du dossier | case-20261019-025924-ext01 |
| Document source | ext01.pdf |
| Version de la note | IFRS 17 Copilot 0.7.0 |
| Diffusion | Usage interne · données fictives · sans valeur de conseil |

## 1. Résumé exécutif

- **CSM initiale (§38)** : 397,89
- **Flux de trésorerie d'exécution** : −397,89
- **Marge attendue : CSM sur primes actualisées** : 26,53 %
- **Seuil d'équilibre : variation des sinistres et frais** : 36,10 %

Le groupe PREV-2023-A est bénéficiaire : les flux de trésorerie d'exécution s'élèvent à -397,89 milliers de USD, l'ajustement pour risque est de 32,10 milliers de USD, d'où une marge sur services contractuels (CSM) initiale de 397,89 milliers de USD [§38]. Le résultat sera reconnu progressivement au fur et à mesure que les unités de couverture seront fournies, conformément à la répartition de la CSM décrite au [§B119], avec un résultat des services d'assurance attendu sur la durée de 467,00 milliers de USD. La marge de sécurité correspond à une variation des sorties de 36,10 % qui annulerait la marge. Aucun point ne nécessite de validation supplémentaire par un humain.

## 2. Objet, périmètre et méthode

Cette note présente l'évaluation du groupe de contrats PREV-2023-A selon le modèle général d'IFRS 17 : évaluation à la comptabilisation initiale, écoulement prévu de la marge sur services contractuels (CSM), projection du compte de résultat et du passif dans le scénario central, et sensibilité des résultats aux principales hypothèses. Elle est destinée à la direction financière et à la revue actuarielle.

La méthode simplifiée d'affectation des primes (PAA, §53) n'est pas retenue : la période de couverture du groupe s'étend sur 6 périodes et le modèle général est la méthode de référence.

**Inclus :**

- Un groupe de contrats, constitué en amont selon le niveau d'agrégation de la norme (§14 à §24).
- Flux de trésorerie d'exécution : primes, sinistres et frais attendus, actualisés.
- Ajustement au titre du risque non financier, CSM ou composante de perte, et leur évolution.

**Exclus :**

- Contrats participatifs directs (VFA), réassurance détenue, frais d'acquisition, composantes d'investissement : hors du périmètre de l'outil.
- Produits des placements (côté actif) : non modélisés ; seules les charges financières d'assurance figurent.
- Écarts d'expérience et révisions d'hypothèses postérieures : le module pluriannuel (engine/bba.py) les traite séparément.

## 3. Données en entrée

| Origine des données |  |
| --- | ---: |
| Document source | ext01.pdf |
| Empreinte SHA-256 | 6932dd646d25ce8b… |
| Mode de lecture | lecture de la couche texte du PDF |
| Contrôle d'ancrage | chaque nombre retrouvé dans le document |
| Données validées par un humain | non |

| Période | Primes (début) | Sinistres et frais (fin) | Unités de couverture | Taux spot | Facteur d'actualisation (fin) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 500,00 | 231,77 | 1 309 | 1,79 % | 0,9824 |
| 2 | 0,00 | 161,88 | 1 253 | 1,99 % | 0,9614 |
| 3 | 0,00 | 151,33 | 1 199 | 2,19 % | 0,9371 |
| 4 | 0,00 | 196,63 | 1 147 | 2,39 % | 0,9099 |
| 5 | 0,00 | 242,55 | 1 098 | 2,59 % | 0,8800 |
| 6 | 0,00 | 179,92 | 1 051 | 2,79 % | 0,8478 |
| Total (non actualisé) | 1 500,00 | 1 164,08 | 7 057 |  |  |

## 4. Hypothèses

| Hypothèse | Valeur retenue | Référence |
| --- | ---: | ---: |
| Méthode d'évaluation | Modèle général (BBA) | §32 à §52 |
| Flux de trésorerie | Estimations explicites et à jour ; primes en début, sorties en fin de période | §33 à §35 |
| Taux d'actualisation | courbe de taux spot : 1,79 % ; 1,99 % ; 2,19 % ; 2,39 % ; 2,59 % ; 2,79 % | §36 |
| Ajustement au titre du risque | 3,00 % de la valeur actuelle des sorties, soit un niveau de confiance de 60,7 % (quantile, loi lognormale, coefficient de variation supposé 15 %) | §37, B86 à B92, §119 |
| Taux bloqué de la CSM | Courbe à la date de comptabilisation initiale | §44(b), B72(b) |
| Libération de la CSM | Unités de couverture de la période / unités restantes | §44(e), B119 |
| Ajustements liés aux services futurs | aucun | §44(c), B96 |
| Groupe déficitaire | Perte immédiate, composante de perte reprise de façon systématique | §47 à §52 |
| Variation de l'ajustement pour risque | Ventilée entre résultat des services et résultat financier | §81 |
| Produits et charges financières | En résultat, sans option OCI | §87, §88 |

## 5. Évaluation à la comptabilisation initiale

| Élément | Montant |
| --- | ---: |
| Valeur actuelle des entrées (primes) | 1 500,00 |
| Valeur actuelle des sorties (sinistres et frais) | 1 070,01 |
| Meilleure estimation, BEL (sorties − entrées) | <span class="neg">−429,99</span> |
| Ajustement au titre du risque non financier | 32,10 |
| Flux de trésorerie d'exécution (BEL + RA) | <span class="neg">−397,89</span> |
| CSM initiale (§38) | 397,89 |
| Perte initiale, groupe déficitaire (§47) | 0,00 |
| Passif à la comptabilisation initiale (FCF + CSM) | 0,00 |

Sur 100 de primes actualisées, 71,3 couvrent les sinistres et frais attendus et 2,1 l'ajustement pour risque ; le solde, 26,5, forme la CSM.

## 6. Évolution de la marge sur services contractuels

| Période | Ouverture | Intérêts au taux bloqué §44(b) | Services futurs §44(c) | Libération B119 | Clôture | Part libérée |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 397,89 | 7,12 | 0,00 | 75,13 | 329,89 | 17,4 % |
| 2 | 329,89 | 7,23 | 0,00 | 73,49 | 263,63 | 17,0 % |
| 3 | 263,63 | 6,83 | 0,00 | 72,14 | 198,32 | 16,7 % |
| 4 | 198,32 | 5,93 | 0,00 | 71,08 | 133,17 | 16,5 % |
| 5 | 133,17 | 4,52 | 0,00 | 70,35 | 67,34 | 16,3 % |
| 6 | 67,34 | 2,56 | 0,00 | 69,90 | 0,00 | 16,2 % |
| Total | 397,89 | 34,19 | 0,00 | 432,08 | 0,00 | 100,0 % |

**Analyse des mouvements :** CSM initiale 397,89 ; Intérêts +34,19 ; Libérations −432,08 ; Clôture 0,00

## 7. Projection : compte de résultat et passif

Scénario central : les flux réalisés sont égaux aux flux attendus et les taux courants suivent les taux à terme de la courbe initiale. Les produits des activités d'assurance comprennent les sinistres et frais attendus de la période, l'ajustement pour risque libéré et la CSM libérée (B124).

**Compte de résultat IFRS 17 attendu**

| Compte de résultat | P1 | P2 | P3 | P4 | P5 | P6 | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Produits des activités d'assurance | 313,85 | 240,22 | 228,01 | 273,61 | 320,18 | 255,21 | 1 631,08 |
| dont CSM libérée | 75,13 | 73,49 | 72,14 | 71,08 | 70,35 | 69,90 | 432,08 |
| dont ajustement pour risque libéré | 6,95 | 4,86 | 4,54 | 5,90 | 7,28 | 5,40 | 34,92 |
| Charges des services d'assurance | <span class="neg">−231,77</span> | <span class="neg">−161,88</span> | <span class="neg">−151,33</span> | <span class="neg">−196,63</span> | <span class="neg">−242,55</span> | <span class="neg">−179,92</span> | <span class="neg">−1 164,08</span> |
| Résultat des services d'assurance | 82,08 | 78,34 | 76,68 | 76,98 | 77,63 | 75,29 | 467,00 |
| Charges financières d'assurance | <span class="neg">−26,85</span> | <span class="neg">−26,57</span> | <span class="neg">−25,89</span> | <span class="neg">−23,86</span> | <span class="neg">−18,58</span> | <span class="neg">−9,33</span> | <span class="neg">−131,08</span> |

**Passif pour couverture restante**

| Passif (fin de période) | Origine | P1 | P2 | P3 | P4 | P5 | P6 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Meilleure estimation (BEL) | <span class="neg">−429,99</span> | 857,39 | 714,29 | 581,47 | 402,24 | 173,34 | 0,00 |
| Ajustement pour risque | 32,10 | 25,72 | 21,43 | 17,44 | 12,07 | 5,20 | 0,00 |
| CSM | 397,89 | 329,89 | 263,63 | 198,32 | 133,17 | 67,34 | 0,00 |
| Passif pour couverture restante | 0,00 | 1 213,00 | 999,35 | 797,23 | 547,48 | 245,88 | 0,00 |

## 8. Sensibilités

| Hypothèse choquée | Flux d'exécution | CSM | Perte | Variation du résultat à l'origine | Statut |
| --- | ---: | ---: | ---: | ---: | ---: |
| Scénario central | <span class="neg">−397,89</span> | 397,89 | 0,00 | — | bénéficiaire |
| Taux d'actualisation +100 pb | <span class="neg">−433,78</span> | 433,78 | 0,00 | +35,89 | bénéficiaire |
| Taux d'actualisation −100 pb | <span class="neg">−360,10</span> | 360,10 | 0,00 | <span class="neg">−37,80</span> | bénéficiaire |
| Sinistres et frais +10 % | <span class="neg">−287,68</span> | 287,68 | 0,00 | <span class="neg">−110,21</span> | bénéficiaire |
| Sinistres et frais −10 % | <span class="neg">−508,10</span> | 508,10 | 0,00 | +110,21 | bénéficiaire |
| Primes −10 % | <span class="neg">−247,89</span> | 247,89 | 0,00 | <span class="neg">−150,00</span> | bénéficiaire |
| Ajustement pour risque +50 % (relatif) | <span class="neg">−381,84</span> | 381,84 | 0,00 | <span class="neg">−16,05</span> | bénéficiaire |

- Variation des sinistres et frais qui annule la marge : 36,10 %.
- Aucune translation des taux comprise entre −5 et +5 points ne fait changer le groupe de statut.
- Duration des sorties (Macaulay) : 3,42 périodes.

L'hypothèse la plus sensible est la variation des primes de -10 % avec une diminution de 150,00 milliers de USD du résultat à l'origine. Une hausse du taux d'actualisation de +100 pb augmente le résultat de 35,89 milliers de USD, tandis qu'une baisse du taux d'actualisation de 100 pb diminue le résultat de 37,80 milliers de USD. Aucun choc ne fait basculer le groupe en situation déficitaire.

**Ajustement pour risque et niveau de confiance**

L'ajustement retenu (3,00 % des sorties, soit 32,10) correspond à un niveau de confiance de 60,7 % : méthode des quantiles, valeur actuelle des sorties supposée lognormale de coefficient de variation 15 %. Le tableau donne l'ajustement qu'exigerait chaque niveau de confiance usuel et son effet sur la CSM ; §119 demande de publier ce niveau.

| Niveau de confiance | Ajustement pour risque | En % des sorties | CSM | Perte | Statut |
| --- | ---: | ---: | ---: | ---: | ---: |
| 65,0 % | 50,76 | 4,74 % | 379,23 | 0,00 | bénéficiaire |
| 75,0 % | 100,17 | 9,36 % | 329,83 | 0,00 | bénéficiaire |
| 85,0 % | 165,08 | 15,43 % | 264,91 | 0,00 | bénéficiaire |
| 90,0 % | 211,07 | 19,73 % | 218,92 | 0,00 | bénéficiaire |
| 99,5 % | 483,89 | 45,22 % | 0,00 | 53,90 | déficitaire |

## 9. Fondements dans la norme

**Comment la marge sur services contractuels est-elle déterminée lors de la comptabilisation initiale d'un groupe de contrats ?**

Lors de la comptabilisation initiale, la marge sur services contractuels représente le profit non acquis que l'entité reconnaîtra au fur et à mesure de la fourniture des services. Elle est évaluée à un montant qui, sauf si les paragraphes spécifiques sur les contrats déficitaires ou les produits d’assurance s’appliquent, garantit qu’aucun produit ou charge ne résulte : (a) de la comptabilisation initiale des flux de trésorerie d’exécution, (b) des flux de trésorerie des contrats inclus dans le groupe à cette date, et (c) de la décomptabilisation à cette date de tout actif lié aux frais d’acquisition ou tout autre actif/passif antérieurement comptabilisé pour le groupe de contrats [§38].

> [§38] « La marge sur services contractuels est une composante de l'actif ou du passif afférent au groupe de contrats d'assurance qui représente le profit non acquis que l'entité comptabilisera à mesure qu'elle fournira les services prévus au contrat d'assurance. »

**Comment la marge sur services contractuels est-elle comptabilisée en résultat au fil des périodes, selon les unités de couverture ?**

À chaque période, l'entité comptabilise en résultat net le montant de la marge sur services contractuels correspondant aux unités de couverture réellement fournies durant la période, après avoir réparti la marge totale du groupe entre toutes les unités de couverture attendues, puis en affectant la part des unités fournies à la période considérée [§B119]. Cette répartition se fait en définissant les unités de couverture du groupe, en répartissant la marge à la clôture entre toutes les unités (fournies et à fournir) et en comptabilisant en résultat net la part affectée aux unités effectivement fournies pendant la période [§B119].

> [§B119] « À chaque période, l'entité comptabilise en résultat net un montant de la marge sur services contractuels du groupe de contrats d'assurance...b) répartit la marge sur services contractuels à la date de clôture...c) comptabilise en résultat net le montant affecté aux unités de couverture fournies dans la période considérée. »

## 10. Contrôles, limites et validation

**Contrôles effectués**

- ✓ Calcul effectué par le moteur Python (le LLM ne calcule jamais)
- ✓ Chiffres extraits contrôlés contre le document (document)
- ✓ Citations de la norme vérifiées par le code, réponses relues par le vérificateur
- ✓ Projection du passif rapprochée période par période, sensibilités recalculées par le moteur
- ✓ Résumé et commentaire : chaque nombre et chaque paragraphe cité vérifiés par le code

**Points à valider**

- Aucun.

**Limites**

- Niveau de confiance de l'ajustement pour risque calculé sous une hypothèse de loi (lognormale) et de volatilité (coefficient de variation) à calibrer sur des données réelles.
- Un seul groupe, sans frais d'acquisition, sans composante d'investissement ni réassurance.
- Scénario central déterministe ; les sensibilités sont des chocs isolés, sans corrélation entre hypothèses.
- Produits des placements non modélisés : le résultat financier net n'est pas présenté.

| Rôle | Nom | Fonction | Date | Visa |
| --- | ---: | ---: | ---: | ---: |
| Préparée par | IFRS 17 Copilot (génération automatique) | Agents : extracteur, calculateur, chercheur, vérificateur, rédacteur | 19/10/2026 à 03:00 |  |
| Revue par |  | Actuaire |  |  |
| Approuvée par |  | Direction financière |  |  |

## Annexe A. Traçabilité

| Élément | Valeur |
| --- | ---: |
| Référence du dossier | case-20261019-025924-ext01 |
| Établie le | 19/10/2026 à 03:00 |
| Application | IFRS 17 Copilot 0.7.0 |
| Moteur de calcul | engine/csm.py et engine/analysis.py (Python, déterministe ; le LLM ne calcule jamais) |
| Texte du résumé et du commentaire | LLM, contrôlé par le code |
| Document source | ext01.pdf |
| Empreinte SHA-256 | 6932dd646d25ce8b9f7b9f70ebfcdc2292a4c5e03b01da9ce373bf13e43de7c2 |
| Prompt agentic_plan | version 1 |
| Prompt extract_portfolio | version 2 |
| Prompt grade_passages | version 1 |
| Prompt rag_answer | version 2 |
| Prompt verify_answer | version 2 |
| Prompt write_note | version 3 |
| Modèle grand (raisonnement) | openai/gpt-oss-120b |
| Modèle petit (évaluation) | openai/gpt-oss-20b |

## Annexe B. Glossaire

- **BBA** : Building Block Approach, modèle général d'évaluation d'IFRS 17.
- **BEL** : Best Estimate of Liabilities : valeur actuelle des sorties futures moins celle des entrées futures.
- **CSM** : Marge sur services contractuels : profit non acquis, reconnu au fil des services rendus.
- **FCF** : Flux de trésorerie d'exécution : BEL plus ajustement au titre du risque non financier.
- **LC** : Composante de perte : part du passif d'un groupe déficitaire qui a déjà été passée en perte.
- **LRC** : Passif au titre de la couverture restante.
- **PAA** : Premium Allocation Approach, méthode simplifiée d'affectation des primes.
- **RA** : Ajustement au titre du risque non financier.
- **Unités de couverture** : Mesure du service rendu par période, qui règle la libération de la CSM.

*Note générée par IFRS 17 Copilot, projet pédagogique, sur des données fictives ; sans valeur de conseil. Les montants viennent du moteur de calcul, jamais du LLM.*
