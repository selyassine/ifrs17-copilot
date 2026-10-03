# RAG (responsable R1)

```
PDF ──► ingest.py ──► unités (1 par paragraphe) ──► chunking.py ──► chunks A et B
                                                                      │
             requête ──► query.py (glossaire) ──► retrieve.py : BM25 │ dense │ hybride RRF
```

| Fichier | Rôle |
| --- | --- |
| `ingest.py` | PDF du Journal officiel → unités : considérants, articles, §1-132, définitions, B1-B137, C1-C34. Lit la mise en page (marge, polices, colonnes) avec pdfplumber |
| `chunking.py` | A : fenêtres de 512 tokens, chevauchement 64. B : un paragraphe par chunk avec en-tête de contexte (fusion des < 40 tokens, découpe des > 800) |
| `retrieve.py` | BM25 avec analyseur français, encodeurs (BGE-M3, Qwen3-Embedding, factice), stockage NumPy ou Qdrant embarqué, fusion RRF |
| `query.py` | Glossaire : CSM, PAA, VFA, onéreux, bilan… → termes officiels |
| `build_index.py` | Tout reconstruire depuis le manifeste du corpus |
| `service.py` | Chargement du moteur pour l'API (`POST /v1/search`) |

## Commandes

```powershell
python -m rag.build_index                 # unités + chunks (BM25), 20 s
python -m eval.eval_retrieval             # rapport eval/retrieval_report.md

pip install -r requirements-rag.txt       # une fois (~2 Go)
python -m rag.build_index --dense --model BAAI/bge-m3
python -m eval.eval_retrieval --model BAAI/bge-m3
```

Sans GPU, encoder ~520 chunks avec BGE-M3 prend quelques minutes. Sur Colab, cloner le dépôt, déposer le PDF dans `data/corpus/`, lancer les mêmes commandes, puis rapatrier `data/index/` et `data/processed/`.

## État (03/10/2026)

| Configuration (découpage B) | Recall@5 | Rappel à 1 000 tokens | MRR@10 |
| --- | --- | --- | --- |
| BM25 | 0,563 | 0,533 | 0,454 |
| BM25 + glossaire | 0,653 | 0,623 | 0,546 |
| Dense BGE-M3 | **0,837** | 0,737 | 0,642 |
| Hybride (RRF), sans glossaire | 0,683 | 0,673 | 0,567 |
| **Hybride + glossaire (par défaut)** | 0,823 | **0,773** | **0,661** |

Avec BGE-M3, B bat nettement A à volume de texte égal (0,737 contre 0,423). Détail et intervalles de confiance : `eval/retrieval_report.md`.

## Ajouter un document

1. Le déclarer dans `data/corpus_manifest.csv` et placer le PDF dans `data/corpus/`.
2. Sans parseur dédié, il est découpé page par page (citations « p12 »). Pour un document important, écrire un parseur et l'ajouter à `STRUCTURED_PARSERS`.
3. `python -m rag.build_index`, puis ajouter des questions dans `eval/rag_questions.jsonl`.
