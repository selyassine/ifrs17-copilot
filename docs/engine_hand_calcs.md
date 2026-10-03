# Calculs manuels du moteur CSM (référence des tests)

Conventions : primes encaissées en début de période, sorties payées en fin de période, montants positifs.
Toutes les valeurs sont arrondies à 4 décimales ; tolérance des tests : 0,01.

## Cas 1 — taux 0 %, RA 0

- Primes : 100 en début de période 1. Sorties : 20 en fin de chaque période (3 périodes).
- PV entrées = 100 ; PV sorties = 60 ; flux d'exécution (FCF) = 60 − 100 = −40 → **CSM initial = 40** (§38).
- Unités de couverture 1, 1, 1 → libération 40 × 1/3 = 13,3333 ; puis 26,6667 × 1/2 = 13,3333 ; puis 13,3333.

## Cas 2 — taux plat 5 %, RA = 5 % des sorties actualisées, sorties de 30

| Élément | Calcul | Valeur |
| --- | --- | --- |
| PV sorties | 30/1,05 + 30/1,05² + 30/1,05³ = 28,5714 + 27,2109 + 25,9151 | 81,6974 |
| Ajustement pour risque | 5 % × 81,6974 | 4,0849 |
| FCF | 81,6974 + 4,0849 − 100 | −14,2177 |
| CSM initial | −FCF | 14,2177 |

| Période | Ouverture | Intérêts 5 % (§44(b)) | Après intérêts | Part CU | Libération (§44(e)) | Clôture |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 14,2177 | 0,7109 | 14,9286 | 1/3 | 4,9762 | 9,9524 |
| 2 | 9,9524 | 0,4976 | 10,4500 | 1/2 | 5,2250 | 5,2250 |
| 3 | 5,2250 | 0,2613 | 5,4863 | 1/1 | 5,4863 | 0,0000 |

Contrôle : total libéré 15,6874 = CSM initial 14,2177 + intérêts 1,4697.

## Cas 3 — groupe onéreux

Primes 50, sorties 3 × 20 à 0 % : FCF = 60 − 50 = +10 → composante perte 10 (§47), CSM = 0.

## Cas 4 — ajustement défavorable (§44(c) puis §48)

Cas 1, puis hausse de 30 des flux futurs en période 2.
Ouverture P2 = 26,6667 ; 26,6667 − 30 = −3,3333 → CSM ramené à 0, **perte de 3,3333** comptabilisée.

## Cas 5 — ajustement favorable

Cas 1, puis baisse de 6 des flux futurs en période 2 : 26,6667 + 6 = 32,6667 → libération 16,3333 en P2 et P3. Total libéré = 13,3333 + 16,3333 + 16,3333 = 46.

## À faire (S3)

Reproduire un exemple illustratif officiel de la norme et le faire relire par un enseignant d'actuariat avant de l'ajouter aux tests.
