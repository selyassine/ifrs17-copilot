# Données

Rien ici n'est versionné, sauf `corpus_manifest.csv` et ce fichier.

- `data/corpus/` : documents téléchargés par chaque membre, nommés `<id>_<nom>.pdf` comme dans le manifeste.
- `data/qdrant/` : index vectoriel local (S2), reconstruit par `make index`.
- `data/pdfs_test/` : PDF d'évaluation de l'extraction (S3).

Après avoir téléchargé un document : `python -m scripts.manifest_hash --write`, puis passer son statut à `ok`.
Aucun document du corpus ne doit être publié ni envoyé à un tiers (droits de l'IFRS Foundation, voir D-010).
