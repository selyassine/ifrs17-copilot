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
| `extract.py` | Agent Extracteur, trois modes : **texte** (couche texte du PDF → Groq), **vision** (image seule → Gemini), **hybride** (couche texte + image → Gemini). Puis validation Pydantic → ancrage des chiffres → une relance si besoin |
| `synth_hard.py` | 10 documents piégés : ligne Total, instruction cachée, unités dans les en-têtes, tableau en page 2, photo dégradée, colonne « Total des sorties », millions ; et 3 cas qui doivent lever une alerte (ajustement absent, unités absentes, deux groupes) |
| `vision.py` | Rendu des pages PDF en images, détection du format, client Gemini (point d'accès compatible OpenAI) |
| à venir | Question vocale (Whisper sur Groq) |

## Contrôle d'ancrage

Modes texte et hybride : chaque chiffre extrait doit exister dans la couche texte du document (les sorties peuvent être la somme de deux montants : sinistres + frais).
Il détecte les chiffres inventés ou mal lus et l'inclusion des produits financiers (15/15 sur les documents de test).
**Limite connue** : il ne voit pas une colonne prise pour une autre quand le chiffre existe ailleurs (ex. sinistres sans les frais) ;
c'est le rôle du vérificateur et de l'évaluation.

Mode vision (scan sans couche texte) : le modèle recopie d'abord le tableau (« transcription »), puis le code vérifie que
chaque chiffre saisi figure dans cette transcription. Contrôle plus faible : il attrape les inventions et les erreurs
d'addition ou d'unité, pas un chiffre mal lu de la même façon des deux côtés.

## Commandes

```powershell
python -m multimodal.synth                        # data/synth/ : ext01…ext15 (.pdf, .png/.jpg)
python -m eval.eval_extraction --mode texte       # rapport eval/extraction_report_texte.md
python -m eval.eval_extraction --mode vision      # images (8 nettes + 7 « scannées ») → Gemini
python -m eval.eval_extraction --mode hybride     # PDF : texte + image → Gemini
python -m multimodal.synth_hard                   # jeu difficile
python -m eval.eval_extraction --mode texte --jeu difficile    # idem avec vision, hybride
```

API : `POST /v1/extract` (PDF, PNG ou JPEG → données) et `POST /v1/case/document` (PDF → données vérifiées → CSM si « ok »).
