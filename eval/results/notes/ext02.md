# Note actuarielle IFRS 17 — Évaluation IFRS 17 du groupe EMP-2023-B

**Statut : Contrôles automatiques passés** · montants en milliers de EUR · établie le 19/10/2026 à 03:03

| Élément | Valeur |
| --- | ---: |
| Entité | Compagnie d'assurance fictive (projet pédagogique) |
| Groupe de contrats | EMP-2023-B |
| Méthode | Modèle général (BBA) |
| Monnaie et unité | Montants en milliers de EUR |
| Durée de couverture | 6 périodes (années) |
| Date d'établissement | 19/10/2026 à 03:03 |
| Référence du dossier | case-20261019-025924-ext02 |
| Document source | ext02.pdf |
| Version de la note | IFRS 17 Copilot 0.7.0 |
| Diffusion | Usage interne · données fictives · sans valeur de conseil |

## 1. Résumé exécutif

- **Perte à la comptabilisation initiale (§47)** : 87,76
- **Flux de trésorerie d'exécution** : 87,76
- **Perte rapportée aux primes actualisées** : −11,53 %
- **Seuil d'équilibre : variation des sinistres et frais** : −10,34 %

Le groupe EMP-2023-B est déficitaire : le flux de trésorerie d'exécution s'élève à 87,76 milliers de EUR, l'ajustement pour risque est de 24,73 milliers de EUR, d'où une perte initiale de 87,76 milliers de EUR [§32]. Le résultat sera reconnu progressivement selon les unités de couverture, conformément à la comptabilisation périodique de la marge sur services contractuels (CSM) [§B119], le résultat des services d'assurance attendu sur la durée étant de -60,82 milliers de EUR. La marge de sécurité correspond à une variation des sorties de -10,34 % qui annulerait la marge [§38]. Aucun point ne nécessite de validation supplémentaire par un humain.

## 2. Objet, périmètre et méthode

Cette note présente l'évaluation du groupe de contrats EMP-2023-B selon le modèle général d'IFRS 17 : évaluation à la comptabilisation initiale, écoulement prévu de la marge sur services contractuels (CSM), projection du compte de résultat et du passif dans le scénario central, et sensibilité des résultats aux principales hypothèses. Elle est destinée à la direction financière et à la revue actuarielle.

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
| Document source | ext02.pdf |
| Empreinte SHA-256 | 285ac650fb52e049… |
| Mode de lecture | lecture de la couche texte du PDF |
| Contrôle d'ancrage | chaque nombre retrouvé dans le document |
| Données validées par un humain | non |

| Période | Primes (début) | Sinistres et frais (fin) | Unités de couverture | Taux spot | Facteur d'actualisation (fin) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 135,25 | 133,13 | 3 319 | 2,50 % | 0,9756 |
| 2 | 143,92 | 143,16 | 2 945 | 2,50 % | 0,9518 |
| 3 | 139,70 | 146,77 | 2 613 | 2,50 % | 0,9286 |
| 4 | 121,34 | 220,27 | 2 319 | 2,50 % | 0,9060 |
| 5 | 132,73 | 127,01 | 2 058 | 2,50 % | 0,8839 |
| 6 | 135,47 | 127,65 | 1 826 | 2,50 % | 0,8623 |
| Total (non actualisé) | 808,41 | 897,99 | 15 080 |  |  |

## 4. Hypothèses

| Hypothèse | Valeur retenue | Référence |
| --- | ---: | ---: |
| Méthode d'évaluation | Modèle général (BBA) | §32 à §52 |
| Flux de trésorerie | Estimations explicites et à jour ; primes en début, sorties en fin de période | §33 à §35 |
| Taux d'actualisation | taux plat de 2,50 % | §36 |
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
| Valeur actuelle des entrées (primes) | 761,29 |
| Valeur actuelle des sorties (sinistres et frais) | 824,32 |
| Meilleure estimation, BEL (sorties − entrées) | 63,03 |
| Ajustement au titre du risque non financier | 24,73 |
| Flux de trésorerie d'exécution (BEL + RA) | 87,76 |
| CSM initiale (§38) | 0,00 |
| Perte initiale, groupe déficitaire (§47) | 87,76 |
| Passif à la comptabilisation initiale (FCF + CSM) | 87,76 |

Sur 100 de primes actualisées, 108,3 couvrent les sinistres et frais attendus et 3,2 l'ajustement pour risque ; il manque 11,5, passés immédiatement en perte.

## 6. Évolution de la marge sur services contractuels

Le groupe étant déficitaire, la CSM est nulle à l'origine et le reste sur toute la durée : aucun profit futur n'est différé. La composante de perte est reprise au fil de la couverture ; son évolution figure dans le passif de la section 7.

## 7. Projection : compte de résultat et passif

Scénario central : les flux réalisés sont égaux aux flux attendus et les taux courants suivent les taux à terme de la courbe initiale. Les produits des activités d'assurance comprennent les sinistres et frais attendus de la période, l'ajustement pour risque libéré et la CSM libérée (B124) ; la part affectée à la composante de perte en est exclue (§49 à §52).

**Compte de résultat IFRS 17 attendu**

| Compte de résultat | P1 | P2 | P3 | P4 | P5 | P6 | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Produits des activités d'assurance | 122,95 | 132,21 | 135,55 | 203,43 | 117,30 | 117,89 | 829,32 |
| dont ajustement pour risque libéré | 3,58 | 3,85 | 3,95 | 5,93 | 3,42 | 3,43 | 24,16 |
| Charges des services d'assurance | <span class="neg">−206,72</span> | <span class="neg">−127,92</span> | <span class="neg">−131,14</span> | <span class="neg">−196,82</span> | <span class="neg">−113,49</span> | <span class="neg">−114,06</span> | <span class="neg">−890,15</span> |
| dont perte à la comptabilisation initiale (§47) | <span class="neg">−87,76</span> | 0,00 | 0,00 | 0,00 | 0,00 | 0,00 | <span class="neg">−87,76</span> |
| dont reprise de la composante de perte | 14,17 | 15,24 | 15,63 | 23,45 | 13,52 | 13,59 | 95,61 |
| Résultat des services d'assurance | <span class="neg">−83,77</span> | 4,29 | 4,40 | 6,61 | 3,81 | 3,83 | <span class="neg">−60,82</span> |
| Charges financières d'assurance | <span class="neg">−5,58</span> | <span class="neg">−5,88</span> | <span class="neg">−5,84</span> | <span class="neg">−5,24</span> | <span class="neg">−3,02</span> | <span class="neg">−3,21</span> | <span class="neg">−28,76</span> |

**Passif pour couverture restante**

| Passif (fin de période) | Origine | P1 | P2 | P3 | P4 | P5 | P6 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Meilleure estimation (BEL) | 63,03 | 70,11 | 76,22 | 74,55 | <span class="neg">−19,48</span> | <span class="neg">−10,93</span> | 0,00 |
| Ajustement pour risque | 24,73 | 21,35 | 17,59 | 13,63 | 7,36 | 3,74 | 0,00 |
| CSM | 0,00 | 0,00 | 0,00 | 0,00 | 0,00 | 0,00 | 0,00 |
| dont composante de perte | 87,76 | 75,78 | 62,44 | 48,37 | 26,13 | 13,26 | 0,00 |
| Passif pour couverture restante | 87,76 | 91,46 | 93,81 | 88,18 | <span class="neg">−12,12</span> | <span class="neg">−7,20</span> | 0,00 |

## 8. Sensibilités

| Hypothèse choquée | Flux d'exécution | CSM | Perte | Variation du résultat à l'origine | Statut |
| --- | ---: | ---: | ---: | ---: | ---: |
| Scénario central | 87,76 | 0,00 | 87,76 | — | déficitaire |
| Taux d'actualisation +100 pb | 77,42 | 0,00 | 77,42 | +10,34 | déficitaire |
| Taux d'actualisation −100 pb | 98,74 | 0,00 | 98,74 | <span class="neg">−10,98</span> | déficitaire |
| Sinistres et frais +10 % | 172,67 | 0,00 | 172,67 | <span class="neg">−84,90</span> | déficitaire |
| Sinistres et frais −10 % | 2,86 | 0,00 | 2,86 | +84,90 | déficitaire |
| Primes −10 % | 163,89 | 0,00 | 163,89 | <span class="neg">−76,13</span> | déficitaire |
| Ajustement pour risque +50 % (relatif) | 100,13 | 0,00 | 100,13 | <span class="neg">−12,36</span> | déficitaire |

- Variation des sinistres et frais qui annule la marge : −10,34 %.
- Aucune translation des taux comprise entre −5 et +5 points ne fait changer le groupe de statut.
- Duration des sorties (Macaulay) : 3,43 périodes.

L'hypothèse la plus sensible est le choc « Sinistres et frais +10 % », qui augmente la perte initiale à 172,67 milliers de EUR et entraîne une variation du résultat de -84,90 milliers de EUR. Les variations de taux d'actualisation modifient le résultat de +10,34 ou -10,98 milliers de EUR, mais le groupe reste déficitaire. Aucun choc ne fait basculer le groupe de statut (bascule = false).

**Ajustement pour risque et niveau de confiance**

L'ajustement retenu (3,00 % des sorties, soit 24,73) correspond à un niveau de confiance de 60,7 % : méthode des quantiles, valeur actuelle des sorties supposée lognormale de coefficient de variation 15 %. Le tableau donne l'ajustement qu'exigerait chaque niveau de confiance usuel et son effet sur la CSM ; §119 demande de publier ce niveau.

| Niveau de confiance | Ajustement pour risque | En % des sorties | CSM | Perte | Statut |
| --- | ---: | ---: | ---: | ---: | ---: |
| 65,0 % | 39,11 | 4,74 % | 0,00 | 102,14 | déficitaire |
| 75,0 % | 77,17 | 9,36 % | 0,00 | 140,20 | déficitaire |
| 85,0 % | 127,18 | 15,43 % | 0,00 | 190,21 | déficitaire |
| 90,0 % | 162,61 | 19,73 % | 0,00 | 225,64 | déficitaire |
| 99,5 % | 372,78 | 45,22 % | 0,00 | 435,82 | déficitaire |

## 9. Fondements dans la norme

**Comment la marge sur services contractuels est-elle déterminée lors de la comptabilisation initiale d'un groupe de contrats ?**

Lors de la comptabilisation initiale, la marge sur services contractuels représente le profit non acquis que l'entité reconnaîtra au fur et à mesure de la prestation des services. Elle est évaluée à un montant qui, sauf si les paragraphes spécifiques sur les contrats déficitaires ou les produits d’assurance s’appliquent, garantit qu’aucun produit ou charge ne résulte : (a) de la comptabilisation initiale des flux de trésorerie d’exécution, (b) des flux de trésorerie des contrats inclus dans le groupe à cette date, et (c) de la décomptabilisation à cette date de tout actif lié aux frais d’acquisition ou tout autre actif/passif antérieurement comptabilisé pour le groupe de contrats [§38].

> [§38] « La marge sur services contractuels est une composante de l'actif ou du passif afférent au groupe de contrats d'assurance qui représente le profit non acquis que l'entité comptabilisera à mesure qu'elle fournira les services prévus au contrat d'assurance. »

**Comment la marge sur services contractuels est-elle comptabilisée en résultat au fil des périodes, selon les unités de couverture ?**

À chaque période, l'entité comptabilise en résultat net le montant de la marge sur services contractuels correspondant aux unités de couverture réellement fournies durant la période, après avoir réparti la marge totale du groupe entre toutes les unités de couverture attendues, y compris celles à fournir ultérieurement [§B119]. La répartition s’effectue à la date de clôture, avant la comptabilisation du montant lié aux services fournis, puis le montant affecté aux unités de couverture fournies dans la période est reconnu en résultat net [§B119].

> [§B119] « À chaque période, l'entité comptabilise en résultat net un montant de la marge sur services contractuels du groupe de contrats d'assurance pour représenter les services prévus aux contrats d'assurance fournis au titre de ce groupe au cours de la période »

**Comment comptabiliser un groupe de contrats d'assurance déficitaire lors de la comptabilisation initiale ?**

Lors de la comptabilisation initiale, l'entité doit d'abord identifier le groupe de contrats déficitaires en regroupant les contrats dont la somme des flux de trésorerie d'exécution, des frais d'acquisition déjà comptabilisés et des flux de trésorerie découlant du contrat donne une sortie nette de trésorerie [§47]. Le groupe ainsi identifié est évalué en incluant les flux de trésorerie d'exécution, l'ajustement de la valeur temps de l'argent et des risques financiers, ainsi que l'ajustement du risque non financier, puis la marge sur services contractuels conformément aux exigences d'évaluation initiale [§32]. La perte correspondant à la sortie nette de trésorerie doit être reconnue en résultat net, de façon à ce que la valeur comptable du passif du groupe soit égale aux flux de trésorerie d'exécution et que la marge sur services contractuels du groupe soit nulle [§47].

> [§47] « Un contrat d'assurance est déficitaire à la date de comptabilisation initiale ... l'entité doit regrouper ces contrats séparément des contrats qui ne sont pas déficitaires. »
> [§32] « Lors de la comptabilisation initiale, l'entité doit évaluer le groupe de contrats d'assurance comme la somme: a) des flux de trésorerie d'exécution ... b) de la marge sur services contractuels. »

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
| Préparée par | IFRS 17 Copilot (génération automatique) | Agents : extracteur, calculateur, chercheur, vérificateur, rédacteur | 19/10/2026 à 03:03 |  |
| Revue par |  | Actuaire |  |  |
| Approuvée par |  | Direction financière |  |  |

## Annexe A. Traçabilité

| Élément | Valeur |
| --- | ---: |
| Référence du dossier | case-20261019-025924-ext02 |
| Établie le | 19/10/2026 à 03:03 |
| Application | IFRS 17 Copilot 0.7.0 |
| Moteur de calcul | engine/csm.py et engine/analysis.py (Python, déterministe ; le LLM ne calcule jamais) |
| Texte du résumé et du commentaire | LLM, contrôlé par le code |
| Document source | ext02.pdf |
| Empreinte SHA-256 | 285ac650fb52e049eba8538516c60aff2458d82dbde37e34c87cf6f210c4e08b |
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
