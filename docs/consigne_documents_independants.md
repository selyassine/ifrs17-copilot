# Créer un document de test pour IFRS 17 Copilot (5 minutes)

Merci de nous aider. Le but : tester notre système sur des documents **que nous n'avons pas fabriqués**. Vous
créez un « état de portefeuille » fictif, **avec votre propre mise en page**, et vous notez de votre côté les
bonnes valeurs. Nous ne regardons pas votre document avant le test.

## Ce que le document doit contenir

Un groupe de contrats d'assurance **fictif** (inventez tout, aucune donnée réelle de client) avec :

| Information | Exemple |
| --- | --- |
| Nom du groupe de contrats | AUTO-2024-K |
| Devise et unité des montants | EUR, montants en milliers d'euros |
| Primes par année (encaissées en début d'année) | 2 400 la 1ʳᵉ année, puis 0 |
| Sinistres et frais par année (payés en fin d'année) | 520,40 ; 610 ; 480,15 ; 390 (vous pouvez séparer sinistres et frais) |
| Unités de couverture par année (ex. nombre de contrats en vigueur) | 1 200 ; 1 100 ; 950 ; 800 |
| Taux d'actualisation (un taux unique, ou un taux par année) | 3,10 % ; 3,30 % ; 3,50 % ; 3,70 % |
| Ajustement pour risque, en % des sorties actualisées | 5 % |

Entre 2 et 10 années. Mise en page **libre** : tableau en lignes ou en colonnes, texte rédigé, Word ou Excel
exporté en PDF, capture d'écran, photo d'une feuille imprimée… Plus c'est différent de nos documents, mieux c'est.

Vous pouvez aussi faire un document **piégé** : deux groupes sur la même page, une information qui manque, une
colonne « produits financiers » à ne pas compter, une instruction cachée (« ignore le tableau »)… Dans ce cas,
mettez `alerte` dans la colonne `attendu`.

## Ce que vous nous envoyez

1. Le fichier (PDF, PNG ou JPEG).
2. Une ligne dans `attendus.csv` (modèle : `eval/independants_modele.csv`), avec des **points-virgules** entre les
   colonnes et des **barres verticales `|`** entre les valeurs d'une année à l'autre :

```
fichier;groupe;devise;unite;primes;sorties;unites_couverture;taux;ajustement_risque;attendu;commentaire
etat_karim.pdf;AUTO-2024-K;EUR;1000;2 400,00 | 0 | 0 | 0;520,40 | 610,00 | 480,15 | 390,00;1200 | 1100 | 950 | 800;3,10 % | 3,30 % | 3,50 % | 3,70 %;5 %;exact;
```

- `unite` : 1 (unités), 1000 (milliers) ou 1000000 (millions) ;
- `sorties` : sinistres + frais de chaque année ;
- `attendu` : `exact` (le système doit lire juste) ou `alerte` (il doit demander un humain).

Pas besoin de calculer la CSM : notre moteur la calcule à partir de vos valeurs.

## Côté équipe

Mettre les fichiers et `attendus.csv` dans `data/independants/`, puis :

```powershell
python -m eval.eval_production --jeu independants
```
