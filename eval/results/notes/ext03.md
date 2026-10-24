# Note actuarielle IFRS 17 — Évaluation IFRS 17 du groupe VIE-2023-C

**Statut : Contrôles automatiques passés** · montants en TND · établie le 19/10/2026 à 03:06

| Élément | Valeur |
| --- | ---: |
| Entité | Compagnie d'assurance fictive (projet pédagogique) |
| Groupe de contrats | VIE-2023-C |
| Méthode | Modèle général (BBA) |
| Monnaie et unité | Montants en TND |
| Durée de couverture | 5 périodes (années) |
| Date d'établissement | 19/10/2026 à 03:06 |
| Référence du dossier | case-20261019-025924-ext03 |
| Document source | ext03.pdf |
| Version de la note | IFRS 17 Copilot 0.7.0 |
| Diffusion | Usage interne · données fictives · sans valeur de conseil |

## 1. Résumé exécutif

- **CSM initiale (§38)** : 524 425,29
- **Flux de trésorerie d'exécution** : −524 425,29
- **Marge attendue : CSM sur primes actualisées** : 14,18 %
- **Seuil d'équilibre : variation des sinistres et frais** : 16,52 %

Le groupe VIE-2023-C est bénéficiaire, les flux de trésorerie d'exécution s'élèvent à -524 425,29 TND, incluant un ajustement pour risque de 179 720,09 TND, ce qui génère une marge sur services contractuels (CSM) initiale de 524 425,29 TND [§38]. Ce profit est différé à l'origine et sera reconnu dans le temps au fur et à mesure de la fourniture des services, réparti entre les unités de couverture [§B119]. Le résultat des services d'assurance attendu sur la durée du groupe s'élève à 792 597,79 TND. La robustesse du groupe est confirmée par une marge de sécurité de 16,52 %, représentant la variation des sorties nécessaire pour annuler la marge. Aucun point spécifique n'a été identifié nécessitant une validation humaine supplémentaire.

## 2. Objet, périmètre et méthode

Cette note présente l'évaluation du groupe de contrats VIE-2023-C selon le modèle général d'IFRS 17 : évaluation à la comptabilisation initiale, écoulement prévu de la marge sur services contractuels (CSM), projection du compte de résultat et du passif dans le scénario central, et sensibilité des résultats aux principales hypothèses. Elle est destinée à la direction financière et à la revue actuarielle.

La méthode simplifiée d'affectation des primes (PAA, §53) n'est pas retenue : la période de couverture du groupe s'étend sur 5 périodes et le modèle général est la méthode de référence.

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
| Document source | ext03.pdf |
| Empreinte SHA-256 | 29f2931f87a98fb5… |
| Mode de lecture | lecture de la couche texte du PDF |
| Contrôle d'ancrage | chaque nombre retrouvé dans le document |
| Données validées par un humain | non |

| Période | Primes (début) | Sinistres et frais (fin) | Unités de couverture | Taux spot | Facteur d'actualisation (fin) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 865 606,58 | 798 926,09 | 3 384 | 4,28 % | 0,9590 |
| 2 | 723 305,82 | 708 623,41 | 3 035 | 4,28 % | 0,9196 |
| 3 | 810 269,57 | 619 524,51 | 2 722 | 4,28 % | 0,8819 |
| 4 | 829 759,73 | 644 886,54 | 2 441 | 4,28 % | 0,8457 |
| 5 | 784 482,04 | 599 130,10 | 2 189 | 4,28 % | 0,8110 |
| Total (non actualisé) | 4 013 423,74 | 3 371 090,65 | 13 771 |  |  |

## 4. Hypothèses

| Hypothèse | Valeur retenue | Référence |
| --- | ---: | ---: |
| Méthode d'évaluation | Modèle général (BBA) | §32 à §52 |
| Flux de trésorerie | Estimations explicites et à jour ; primes en début, sorties en fin de période | §33 à §35 |
| Taux d'actualisation | taux plat de 4,28 % | §36 |
| Ajustement au titre du risque | 6,00 % de la valeur actuelle des sorties, soit un niveau de confiance de 67,9 % (quantile, loi lognormale, coefficient de variation supposé 15 %) | §37, B86 à B92, §119 |
| Taux bloqué de la CSM | Courbe à la date de comptabilisation initiale | §44(b), B72(b) |
| Libération de la CSM | Unités de couverture de la période / unités restantes | §44(e), B119 |
| Ajustements liés aux services futurs | aucun | §44(c), B96 |
| Groupe déficitaire | Perte immédiate, composante de perte reprise de façon systématique | §47 à §52 |
| Variation de l'ajustement pour risque | Ventilée entre résultat des services et résultat financier | §81 |
| Produits et charges financières | En résultat, sans option OCI | §87, §88 |

## 5. Évaluation à la comptabilisation initiale

| Élément | Montant |
| --- | ---: |
| Valeur actuelle des entrées (primes) | 3 699 480,29 |
| Valeur actuelle des sorties (sinistres et frais) | 2 995 334,90 |
| Meilleure estimation, BEL (sorties − entrées) | <span class="neg">−704 145,39</span> |
| Ajustement au titre du risque non financier | 179 720,09 |
| Flux de trésorerie d'exécution (BEL + RA) | <span class="neg">−524 425,29</span> |
| CSM initiale (§38) | 524 425,29 |
| Perte initiale, groupe déficitaire (§47) | 0,00 |
| Passif à la comptabilisation initiale (FCF + CSM) | 0,00 |

Sur 100 de primes actualisées, 81,0 couvrent les sinistres et frais attendus et 4,9 l'ajustement pour risque ; le solde, 14,2, forme la CSM.

## 6. Évolution de la marge sur services contractuels

| Période | Ouverture | Intérêts au taux bloqué §44(b) | Services futurs §44(c) | Libération B119 | Clôture | Part libérée |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 524 425,29 | 22 445,40 | 0,00 | 134 384,61 | 412 486,09 | 22,8 % |
| 2 | 412 486,09 | 17 654,40 | 0,00 | 125 683,68 | 304 456,81 | 21,3 % |
| 3 | 304 456,81 | 13 030,75 | 0,00 | 117 546,40 | 199 941,16 | 19,9 % |
| 4 | 199 941,16 | 8 557,48 | 0,00 | 109 923,37 | 98 575,28 | 18,6 % |
| 5 | 98 575,28 | 4 219,02 | 0,00 | 102 794,30 | 0,00 | 17,4 % |
| Total | 524 425,29 | 65 907,06 | 0,00 | 590 332,36 | 0,00 | 100,0 % |

**Analyse des mouvements :** CSM initiale 524 425,29 ; Intérêts +65 907,06 ; Libérations −590 332,36 ; Clôture 0,00

## 7. Projection : compte de résultat et passif

Scénario central : les flux réalisés sont égaux aux flux attendus et les taux courants suivent les taux à terme de la courbe initiale. Les produits des activités d'assurance comprennent les sinistres et frais attendus de la période, l'ajustement pour risque libéré et la CSM libérée (B124).

**Compte de résultat IFRS 17 attendu**

| Compte de résultat | P1 | P2 | P3 | P4 | P5 | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Produits des activités d'assurance | 981 246,26 | 876 824,50 | 774 242,38 | 793 503,10 | 737 872,20 | 4 163 688,44 |
| dont CSM libérée | 134 384,61 | 125 683,68 | 117 546,40 | 109 923,37 | 102 794,30 | 590 332,36 |
| dont ajustement pour risque libéré | 47 935,57 | 42 517,40 | 37 171,47 | 38 693,19 | 35 947,81 | 202 265,44 |
| Charges des services d'assurance | <span class="neg">−798 926,09</span> | <span class="neg">−708 623,41</span> | <span class="neg">−619 524,51</span> | <span class="neg">−644 886,54</span> | <span class="neg">−599 130,10</span> | <span class="neg">−3 371 090,65</span> |
| Résultat des services d'assurance | 182 320,17 | 168 201,09 | 154 717,87 | 148 616,56 | 138 742,10 | 792 597,79 |
| Charges financières d'assurance | <span class="neg">−37 047,96</span> | <span class="neg">−27 593,76</span> | <span class="neg">−25 926,23</span> | <span class="neg">−29 412,01</span> | <span class="neg">−30 284,74</span> | <span class="neg">−150 264,70</span> |

**Passif pour couverture restante**

| Passif (fin de période) | Origine | P1 | P2 | P3 | P4 | P5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Meilleure estimation (BEL) | <span class="neg">−704 145,39</span> | <span class="neg">−630 554,36</span> | <span class="neg">−611 902,19</span> | <span class="neg">−412 667,00</span> | <span class="neg">−209 942,24</span> | 0,00 |
| Ajustement pour risque | 179 720,09 | 139 476,55 | 102 928,74 | 70 162,62 | 34 472,39 | 0,00 |
| CSM | 524 425,29 | 412 486,09 | 304 456,81 | 199 941,16 | 98 575,28 | 0,00 |
| Passif pour couverture restante | 0,00 | <span class="neg">−78 591,72</span> | <span class="neg">−204 516,63</span> | <span class="neg">−142 563,22</span> | <span class="neg">−76 894,58</span> | 0,00 |

## 8. Sensibilités

| Hypothèse choquée | Flux d'exécution | CSM | Perte | Variation du résultat à l'origine | Statut |
| --- | ---: | ---: | ---: | ---: | ---: |
| Scénario central | <span class="neg">−524 425,29</span> | 524 425,29 | 0,00 | — | bénéficiaire |
| Taux d'actualisation +100 pb | <span class="neg">−541 018,02</span> | 541 018,02 | 0,00 | +16 592,73 | bénéficiaire |
| Taux d'actualisation −100 pb | <span class="neg">−506 744,78</span> | 506 744,78 | 0,00 | <span class="neg">−17 680,51</span> | bénéficiaire |
| Sinistres et frais +10 % | <span class="neg">−206 919,79</span> | 206 919,79 | 0,00 | <span class="neg">−317 505,50</span> | bénéficiaire |
| Sinistres et frais −10 % | <span class="neg">−841 930,79</span> | 841 930,79 | 0,00 | +317 505,50 | bénéficiaire |
| Primes −10 % | <span class="neg">−154 477,26</span> | 154 477,26 | 0,00 | <span class="neg">−369 948,03</span> | bénéficiaire |
| Ajustement pour risque +50 % (relatif) | <span class="neg">−434 565,25</span> | 434 565,25 | 0,00 | <span class="neg">−89 860,05</span> | bénéficiaire |

- Variation des sinistres et frais qui annule la marge : 16,52 %.
- Aucune translation des taux comprise entre −5 et +5 points ne fait changer le groupe de statut.
- Duration des sorties (Macaulay) : 2,78 périodes.

L'hypothèse la plus sensible est celle des primes, dont une baisse de 10 % entraîne une variation du résultat à l'origine de -369 948,03 TND. Les variations des taux d'actualisation ont un effet inverse sur la CSM : une hausse de 100 pb l'augmente de 16 592,73 TND, tandis qu'une baisse de 100 pb la diminue de 17 680,51 TND. Aucun des chocs testés ne provoque de bascule du groupe dans le déficit, la perte initiale restant à 0,00 TND dans tous les scénarios.

**Ajustement pour risque et niveau de confiance**

L'ajustement retenu (6,00 % des sorties, soit 179 720,09) correspond à un niveau de confiance de 67,9 % : méthode des quantiles, valeur actuelle des sorties supposée lognormale de coefficient de variation 15 %. Le tableau donne l'ajustement qu'exigerait chaque niveau de confiance usuel et son effet sur la CSM ; §119 demande de publier ce niveau.

| Niveau de confiance | Ajustement pour risque | En % des sorties | CSM | Perte | Statut |
| --- | ---: | ---: | ---: | ---: | ---: |
| 65,0 % | 142 106,41 | 4,74 % | 562 038,97 | 0,00 | bénéficiaire |
| 75,0 % | 280 399,00 | 9,36 % | 423 746,39 | 0,00 | bénéficiaire |
| 85,0 % | 462 116,60 | 15,43 % | 242 028,79 | 0,00 | bénéficiaire |
| 90,0 % | 590 872,28 | 19,73 % | 113 273,11 | 0,00 | bénéficiaire |
| 99,5 % | 1 354 586,93 | 45,22 % | 0,00 | 650 441,54 | déficitaire |

## 9. Fondements dans la norme

**Comment la marge sur services contractuels est-elle déterminée lors de la comptabilisation initiale d'un groupe de contrats ?**

Lors de la comptabilisation initiale, l'entité évalue la marge sur services contractuels du groupe de contrats d'assurance à un montant qui, sauf application des paragraphes spécifiques sur les contrats déficitaires ou certains produits d'assurance, ne génère aucun produit ou charge lié à (a) la comptabilisation initiale des flux de trésorerie d'exécution, (b) les flux de trésorerie des contrats inclus dans le groupe à cette date, ni (c) la décomptabilisation à cette date d'actifs liés aux frais d'acquisition ou d'autres actifs ou passifs précédemment comptabilisés pour le groupe. [§38]

> [§38] « La marge sur services contractuels est une composante de l'actif ou du passif afférent au groupe de contrats d'assurance qui représente le profit non acquis que l'entité comptabilisera à mesure qu'elle fournira les services prévus au contrat d'assurance. »

**Comment la marge sur services contractuels est-elle comptabilisée en résultat au fil des périodes, selon les unités de couverture ?**

À chaque période, l'entité comptabilise en résultat net le montant de la marge sur services contractuels correspondant aux unités de couverture réellement fournies durant la période. Elle détermine d'abord le nombre d'unités de couverture du groupe (volume de services prévus), répartit la marge totale à la clôture également entre toutes les unités de couverture attendues, puis enregistre en résultat le montant affecté aux unités effectivement fournies dans la période considérée [§B119].

> [§B119] « À chaque période, l'entité comptabilise en résultat net un montant de la marge sur services contractuels du groupe de contrats d'assurance pour représenter les services prévus aux contrats d'assurance fournis au titre de ce groupe au cours de la période [...] b) répartit la marge sur services contractuels à la date de clôture [...] également entre chacune des unités de couverture qu'elle a fournie »

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
| Préparée par | IFRS 17 Copilot (génération automatique) | Agents : extracteur, calculateur, chercheur, vérificateur, rédacteur | 19/10/2026 à 03:06 |  |
| Revue par |  | Actuaire |  |  |
| Approuvée par |  | Direction financière |  |  |

## Annexe A. Traçabilité

| Élément | Valeur |
| --- | ---: |
| Référence du dossier | case-20261019-025924-ext03 |
| Établie le | 19/10/2026 à 03:06 |
| Application | IFRS 17 Copilot 0.7.0 |
| Moteur de calcul | engine/csm.py et engine/analysis.py (Python, déterministe ; le LLM ne calcule jamais) |
| Texte du résumé et du commentaire | LLM, contrôlé par le code |
| Document source | ext03.pdf |
| Empreinte SHA-256 | 29f2931f87a98fb5893a21bdaf3dd84ec8b022fa38968371e6995ef75cadf481 |
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
