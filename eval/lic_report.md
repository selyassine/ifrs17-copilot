# Évaluation LIC (triangles) — 20261024-161518

Modèle : openai/gpt-oss-120b · prompt extract_triangle · 8 documents (7 propres, 1 pièges)

- Triangle juste (toutes les cellules) : 7/7
- LIC juste au centime : 7/7
- Statut « ok » sur les propres : 6/7
- Alertes levées sur les pièges : 1/1
- **Cas dangereux : 0**

| Document | Piège | Statut | Double lecture | LIC lu | LIC attendu | Verdict | Problèmes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| lc01 | — | ok | concordante | 197090.57 | 197090.57 | juste | — |
| lc02 | — | ok | concordante | 17634.74 | 17634.74 | juste | — |
| lc03 | — | ok | concordante | 126098.26 | 126098.26 | juste | — |
| lc04 | — | ok | concordante | 25872.48 | 25872.48 | juste | — |
| lc05 | — | ok | concordante | 199577.4 | 199577.4 | juste | — |
| lc06 | — | ok | concordante | 16605.87 | 16605.87 | juste | — |
| lc07 | cumul_en_recul | a_verifier | concordante | 17544.07 | 17544.07 | alerte levee | 1991, retard 3 : le cumul recule de plus de 10 % (9537 → 4768) : incréments lus comme cumuls, ou cellule décalée ? |
| lc08 | unite_absente | a_verifier | concordante | 65955.25 | 65955.25 | juste mais a verifier | absent : unit_multiplier |
