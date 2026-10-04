# Multimodalité (responsable R5)

```
PDF client ──► documents.py ──► texte + tableaux (cellules « | ») ──► extract.py ──► LLM (prompt extract_portfolio)
                                       │                                  │
                                       └── nombres du document ──► contrôle d'ancrage ──► statut ok / à vérifier / échec
                                                                                   │
                                                          ok ──► engine/csm.py ──► CSM      à vérifier ──► validation humaine (n8n)
```

| Fichier | Rôle |
| --- | --- |
| `synth.py` | 15 états de portefeuille fictifs (PDF + image, dont 7 « scannés ») avec leur vérité exacte et leur CSM attendu |
| `documents.py` | Lecture d'un PDF à couche texte (pdfplumber) ; repérage des nombres (format français « 1 234,50 », pourcentages) |
| `extract.py` | Agent Extracteur : LLM → `PortfolioData` → validation Pydantic → ancrage des chiffres → une relance si besoin |
| à venir | Mode image (modèle vision), mode hybride, question vocale (Whisper) |

## Contrôle d'ancrage

Chaque chiffre extrait doit exister dans le document (les sorties peuvent être la somme de deux montants : sinistres + frais).
Il détecte les chiffres inventés ou mal lus et l'inclusion des produits financiers (15/15 sur les documents de test).
**Limite connue** : il ne voit pas une colonne prise pour une autre quand le chiffre existe ailleurs (ex. sinistres sans les frais) ;
c'est le rôle du vérificateur et de l'évaluation.

## Commandes

```powershell
python -m multimodal.synth                        # data/synth/ : ext01…ext15 (.pdf, .png/.jpg)
python -m eval.eval_extraction --mode texte       # rapport eval/extraction_report_texte.md
```

API : `POST /v1/extract` (PDF → données) et `POST /v1/case/document` (PDF → données vérifiées → CSM si « ok »).
