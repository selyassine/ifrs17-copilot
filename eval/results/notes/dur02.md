# Note IFRS 17 — groupe PREV-2022-B

**Statut : À VALIDER PAR UN HUMAIN** · montants en TND

## Synthèse

Le groupe PREV-2022-B présente une marge sur services contractuels initiale de 964 931,53 TND, ce qui indique une situation bénéficiaire avec une marge différée selon le principe de la CSM. Cette marge sera progressivement reconnue en résultat net au fur et à mesure de la libération, dont le montant total prévu est de 1 051 412,54 TND, avec une première libération de 220 453,18 TND pour la première période. Conformément au paragraphe [§38], la CSM représente le profit non acquis qui doit être reporté jusqu’à la prestation des services futurs. À la clôture, la marge non encore reconnue correspond à la différence entre la CSM et les libérations effectuées, comme le précise [§43]. Un contrôle humain reste nécessaire pour vérifier l’absence du champ « risk_adjustment_pct » dans l’extraction.

## Résultats du modèle général

| Élément | Montant |
| --- | --- |
| Valeur actuelle des entrées (primes) | 3 771 533,80 |
| Valeur actuelle des sorties (sinistres et frais) | 2 806 602,27 |
| Ajustement au titre du risque non financier | 0,00 |
| Flux de trésorerie d'exécution (négatif : entrées nettes) | -964 931,53 |
| CSM initiale (§38) | 964 931,53 |
| Perte initiale, groupe déficitaire (§47) | 0,00 |

## Évolution de la CSM

| Période | Ouverture | Intérêt (§44 b) | Libération (B119) | Clôture |
| --- | --- | --- | --- | --- |
| 1 | 964 931,53 | 23 737,32 | 220 453,18 | 768 215,67 |
| 2 | 768 215,67 | 21 973,97 | 214 432,35 | 575 757,28 |
| 3 | 575 757,28 | 18 776,42 | 209 359,66 | 385 174,04 |
| 4 | 385 174,04 | 14 106,37 | 205 206,77 | 194 073,65 |
| 5 | 194 073,65 | 7 886,94 | 201 960,58 | 0,00 |

## Fondements dans la norme

**Comment la marge sur services contractuels est-elle déterminée lors de la comptabilisation initiale d'un groupe de contrats ?**

Lors de la comptabilisation initiale, la marge sur services contractuels est évaluée comme le profit non acquis du groupe de contrats, c’est‑à‑dire le montant qui, sauf application des paragraphes spécifiques (ex. §47 ou §B123A), fait en sorte qu’aucun produit ou charge ne résulte de : (a) la comptabilisation initiale des flux de trésorerie d'exécution, (b) les flux de trésorerie des contrats du groupe à cette date, et (c) la décomptabilisation à cette date de tout actif lié aux frais d'acquisition ou tout autre actif/passif antérieurement comptabilisé au titre des flux de trésorerie du groupe [§38].

> [§38] « La marge sur services contractuels est une composante de l'actif ou du passif afférent au groupe de contrats d'assurance qui représente le profit non acquis... L'entité doit évaluer la marge sur services contractuels au moment de la comptabilisation initiale du groupe de contrats d'assurance à un montant qui, à moins que le paragraphe 47 ... ne s'appliquent, fait qu'aucun produit ou charge ne déco »

**Comment la marge sur services contractuels est-elle comptabilisée en résultat au fil des périodes, selon les unités de couverture ?**

À chaque période, l’entité comptabilise en résultat net le montant de la marge sur services contractuels correspondant aux unités de couverture réellement fournies durant la période, en répartissant la marge résiduelle du groupe entre les unités déjà fournies et celles qui resteront à fournir, puis en reconnaissant la part affectée aux unités fournies [§B119]. Cette marge représente le profit du groupe qui n’a pas encore été reconnu car il se rattache à des services futurs, et la reconnaissance périodique reflète la fourniture progressive de ces services [§43].

> [§B119] « comptabilise en résultat net le montant affecté aux unités de couverture fournies dans la période considérée »
> [§43] « La marge sur services contractuels à la date de clôture représente le profit afférent au groupe de contrats d'assurance qui n'a pas encore été comptabilisé en résultat net, car il se rattache à des services futurs »

## Contrôles

- Calcul effectué par le moteur Python (le LLM ne calcule jamais)
- Chiffres extraits contrôlés contre le document (document)
- Citations de la norme vérifiées par le code, réponses relues par le vérificateur
- Synthèse : chaque nombre et chaque paragraphe cité vérifiés par le code
- ⚠ extraction : champ absent du document (risk_adjustment_pct)

*Note générée par IFRS 17 Copilot (projet pédagogique, sans valeur de conseil). Les montants viennent du moteur de calcul, jamais du LLM.*
