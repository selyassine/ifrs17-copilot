# Back-testing des hypothèses actuarielles

Généré le 21/10/2026 par `python -m actuariat.backtest`. Données réelles CAS Schedule P ; registre des hypothèses v2.

## 1. Projection : sinistres attendus au 1er janvier contre sinistres réellement payés

Rapport = sinistres réels / sinistres attendus (1 = projection exacte).

| Branche | Dossiers | Rapport moyen | Médian | Étendue | Dans ±20 % |
| --- | --- | --- | --- | --- | --- |
| Accidents du travail | 10 | 0.97 | 0.94 | 0.66 à 1.64 | 5/10 |
| Auto particuliers (RC) | 10 | 0.86 | 0.89 | 0.54 à 1.06 | 7/10 |
| Auto commerciale (RC) | 10 | 0.97 | 0.94 | 0.69 à 1.37 | 7/10 |
| Responsabilité civile générale | 10 | 0.93 | 0.83 | 0.46 à 1.57 | 2/10 |
| Responsabilité médicale | 10 | 1.43 | 1.07 | 0.58 à 3.68 | 4/10 |
| Ensemble | 50 | 1.03 | 0.92 | 0.46 à 3.68 | 25/50 |

Écarts les plus forts :

| Groupe | S/P attendu | S/P réel | Rapport |
| --- | --- | --- | --- |
| MM-2007-41467 | 21.5% | 78.9% | 3.68 |
| MM-2007-35904 | 66.0% | 153.3% | 2.32 |
| MM-1997-33111 | 50.7% | 100.5% | 1.98 |
| WC-1997-24017 | 38.3% | 62.9% | 1.64 |
| OL-1997-42439 | 58.4% | 91.9% | 1.57 |

Lecture : une projection mécanique (Chain Ladder et S/P moyen du passé, sans jugement) se trompe fortement pour certaines compagnies (changement de souscription, sinistres graves, données de peu d'années). C'est l'incertitude que l'ajustement pour risque doit couvrir, et la raison pour laquelle une note n'est jamais diffusée sans revue actuarielle.

## 2. Première clôture sur le réalisé

25 dossiers dont le réalisé est publié (survenance 2007, clôture au 31/12/2007). Paiement réel de l'année et sinistres futurs révisés par Bornhuetter-Ferguson ; la couverture d'un an étant achevée, la révision va en charges (services passés, B97(b)).

| Groupe | Payé attendu | Payé réel | Écart d'expérience | Révision des flux futurs | Résultat des services | Attendu |
| --- | --- | --- | --- | --- | --- | --- |
| WC-2007-24017 | 27,025 | 27,723 | -698 | -463 | 41,266 | 41,501 |
| WC-2007-38733 | 15,801 | 11,292 | +4,509 | -145 | 67,433 | 62,779 |
| WC-2007-11347 | 20,057 | 16,131 | +3,926 | -359 | 36,978 | 32,693 |
| WC-2007-10385 | 16,178 | 15,433 | +745 | -557 | 51,468 | 50,166 |
| WC-2007-18767 | 11,087 | 10,390 | +697 | -109 | 39,721 | 38,914 |
| PPA-2007-33499 | 16,426 | 14,031 | +2,395 | -695 | 28,764 | 25,674 |
| PPA-2007-12360 | 19,254 | 17,271 | +1,983 | +94 | 22,508 | 20,619 |
| PPA-2007-25275 | 11,271 | 11,959 | -688 | -198 | 20,807 | 21,297 |
| PPA-2007-13889 | 10,489 | 11,661 | -1,172 | -24 | 15,343 | 16,491 |
| PPA-2007-15024 | 7,727 | 7,737 | -10 | +76 | 11,739 | 11,825 |
| CA-2007-26077 | 8,518 | 8,913 | -395 | -296 | 37,930 | 38,030 |
| CA-2007-26433 | 8,503 | 8,165 | +338 | +313 | 16,807 | 16,783 |
| CA-2007-26905 | 5,893 | 5,783 | +110 | +251 | 24,445 | 24,586 |
| CA-2007-21172 | 4,640 | 3,452 | +1,188 | -28 | 20,368 | 19,152 |
| CA-2007-18767 | 6,182 | 3,992 | +2,190 | +16 | 18,810 | 16,636 |
| OL-2007-42439 | 3,280 | 1,357 | +1,923 | +64 | 34,795 | 32,936 |
| OL-2007-10020 | 393 | 257 | +136 | +908 | 31,748 | 32,520 |
| OL-2007-42846 | 2,510 | 2,339 | +171 | -352 | 26,122 | 25,599 |
| OL-2007-12866 | 1,123 | 828 | +295 | -58 | 22,332 | 21,980 |
| OL-2007-26797 | 261 | 155 | +106 | -22 | 15,861 | 15,733 |
| MM-2007-41467 | 1,619 | 160 | +1,459 | +474 | 184,568 | 183,584 |
| MM-2007-35904 | 404 | 115 | +289 | -180 | 18,663 | 18,194 |
| MM-2007-31429 | 127 | 252 | -125 | -3 | 4,883 | 5,005 |
| MM-2007-33049 | 169 | 81 | +88 | -5 | -445 | -539 |
| MM-2007-43656 | 123 | 55 | +68 | -7 | 1,853 | 1,777 |

Rapprochement du passif (ouverture + flux + charges financières − résultat des services = clôture) : écart maximal 1.46e-11 sur 25 dossiers.

## 3. Calibration de l'ajustement pour risque (registre)

Niveau de confiance cible : 75%. Méthode : quantile (value at risk) d'une loi lognormale de la valeur actuelle des sorties, CV mesuré par back-testing (actuariat/calibration.py).

| Branche | Cohortes | Biais moyen | P10 | P90 | CV | RA au niveau cible |
| --- | --- | --- | --- | --- | --- | --- |
| Auto commerciale (RC) | 67 | 0.96 | 0.63 | 1.32 | 27.0% | 15.5% |
| Responsabilité civile générale | 58 | 1.02 | 0.41 | 1.73 | 62.1% | 24.9% |
| Auto particuliers (RC) | 67 | 0.95 | 0.74 | 1.11 | 14.5% | 9.1% |
| Accidents du travail | 53 | 0.94 | 0.60 | 1.34 | 35.0% | 18.7% |

Non calibrées (moins de 30 cohortes exploitables) : Responsabilité médicale, Responsabilité civile produits ; par prudence, la note leur applique la plus forte volatilité calibrée et le signale (le back-testing de la responsabilité médicale montre des écarts jusqu'à × 3,7 : une volatilité faible par défaut serait dangereuse).

Les dossiers du script R portent un RA de 3 % des sorties : selon la branche, cela correspond à un niveau de confiance d'environ 60 % (la loi lognormale est asymétrique : un RA nul vaut déjà plus de 50 %), loin du niveau cible ; la note le signale à l'actuaire.

