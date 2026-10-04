# Note IFRS 17 — groupe PREV-2024-J

**Statut : À VALIDER PAR UN HUMAIN** · montants en milliers de USD

## Synthèse

Le groupe PREV-2024-J présente une marge sur services contractuels initiale (CSM) de 1 126,25 k USD, ce qui indique une situation bénéficiaire avec une marge différée [§38]. La libération totale prévue de la CSM s’élève à 1 201,75 k USD, dont 328,81 k USD seront reconnus dès la première période. Le reste de la marge sera reconnu progressivement au cours des trois périodes suivantes, conformément à la répartition prévue par le paragraphe [§44] et comptabilisé en résultat net selon [§B119]. Aucun profit n’est reconnu immédiatement, les flux d’exécution étant négatifs (‑1 126,25 k USD) et les entrées attendues dépassent les sorties. Les contrôles listés doivent être effectués par un humain avant validation.

## Résultats du modèle général

| Élément | Montant |
| --- | --- |
| Valeur actuelle des entrées (primes) | 4 000,00 |
| Valeur actuelle des sorties (sinistres et frais) | 2 736,91 |
| Ajustement au titre du risque non financier | 136,85 |
| Flux de trésorerie d'exécution (négatif : entrées nettes) | -1 126,25 |
| CSM initiale (§38) | 1 126,25 |
| Perte initiale, groupe déficitaire (§47) | 0,00 |

## Évolution de la CSM

| Période | Ouverture | Intérêt (§44 b) | Libération (B119) | Clôture |
| --- | --- | --- | --- | --- |
| 1 | 1 126,25 | 26,47 | 328,81 | 823,91 |
| 2 | 823,91 | 22,66 | 308,27 | 538,30 |
| 3 | 538,30 | 16,96 | 290,28 | 264,99 |
| 4 | 264,99 | 9,41 | 274,40 | 0,00 |

## Fondements dans la norme

**Comment la marge sur services contractuels est-elle déterminée lors de la comptabilisation initiale d'un groupe de contrats ?**

Lors de la comptabilisation initiale, la marge sur services contractuels représente le profit non acquis du groupe de contrats et est évaluée à un montant qui, sauf application de dispositions spécifiques (ex. §47 ou §B123A), garantit qu'aucun produit ou charge ne résulte : (a) de la comptabilisation initiale des flux de trésorerie d'exécution, (b) des flux de trésorerie des contrats inclus dans le groupe à cette date, et (c) de la décomptabilisation à cette date de tout actif lié aux frais d'acquisition ou tout autre actif/passif antérieur lié au groupe de contrats. [§38]

> [§38] « La marge sur services contractuels est une composante de l'actif ou du passif afférent au groupe de contrats d'assurance qui représente le profit non acquis... L'entité doit évaluer la marge sur services contractuels au moment de la comptabilisation initiale du groupe de contrats d'assurance à un montant qui, à moins que le paragraphe 47 ... ne s'appliquent, fait qu'aucun produit ou charge ne déco »

**Comment la marge sur services contractuels est-elle comptabilisée en résultat au fil des périodes, selon les unités de couverture ?** *(vérificateur : validation_humaine)*

À chaque période, l’entité comptabilise en résultat net le montant de la marge sur services contractuels affecté aux unités de couverture réellement fournies durant la période considérée ; ce montant est déterminé en répartissant la marge résiduelle à la date de clôture entre toutes les unités de couverture du groupe, puis en reconnaissant en résultat net la part correspondant aux unités fournies dans la période [§B119] . La marge résiduelle à la clôture est obtenue en ajustant la valeur comptable de la marge pour les nouveaux contrats, l’intérêt capitalisé, les variations des flux de trésorerie d’exécution, les écarts de change et le montant déjà reconnu en produits d’assurance, selon les règles d’évaluation ultérieure [§44].

> [§B119] « comptabilise en résultat net le montant affecté aux unités de couverture fournies dans la période considérée »
> [§44] « le montant comptabilisé en produits des activités d'assurance en raison de la fourniture des services prévus aux contrats d'assurance au cours de la période, déterminé par répartition, selon le paragraphe B119, de la marge sur services contractuels restante à la date de clôture »

## Contrôles

- Calcul effectué par le moteur Python (le LLM ne calcule jamais)
- Chiffres extraits contrôlés contre le document (document)
- Citations de la norme vérifiées par le code, réponses relues par le vérificateur
- Synthèse : chaque nombre et chaque paragraphe cité vérifiés par le code
- ⚠ extraction : plusieurs groupes de contrats dans le document (PREV-2024-J, VIE-2025-D) : choisir le groupe à calculer
- ⚠ norme : réponse non validée par le vérificateur (Comment la marge sur services contractuels est-elle comptabi…)

*Note générée par IFRS 17 Copilot (projet pédagogique, sans valeur de conseil). Les montants viennent du moteur de calcul, jamais du LLM.*
