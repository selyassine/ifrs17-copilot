# Bibliothèque de prompts

C'est le cœur de l'évaluation (20 %). Chaque prompt est une **fiche YAML versionnée** : `prompts/<agent>/<id>.vN.yaml`.
On ne modifie jamais une version existante : on crée `vN+1` et on garde l'ancienne pour le comparatif avant/après.

## Champs d'une fiche

| Champ | Contenu |
| --- | --- |
| `id`, `version`, `agent` | Doivent correspondre au nom du fichier et au dossier (vérifié par les tests) |
| `role` | Ce que fait le prompt, en une phrase |
| `techniques` | Parmi : `zero_shot`, `few_shot`, `chain_of_thought`, `role_prompting`, `structured_output`, `guardrails`, `self_consistency`, `prompt_chaining`, `generated_knowledge`, `llm_as_judge`, `tool_use`, `delimiters`, `query_rewriting`, `synthetic_data`, `step_back_prompting`, `corrective_rag` |
| `params` | `model` (`small`, `large` ou nom exact), `temperature`, `max_tokens` |
| `system`, `template` | Le gabarit utilise `$variable` (pas `{variable}`), pour que les exemples JSON puissent contenir des accolades |
| `output_schema` | Classe Pydantic de `agents/schemas.py` qui valide la sortie |
| `failures_observed` | Échecs constatés sur la version précédente |
| `changes` | Ce qui a changé et pourquoi (une seule chose à la fois) |
| `eval` | Jeu de test, métrique, scores par version : `{v1: 0.62, v2: 0.81}` |

## Méthode d'itération

1. Écrire v1 et la lancer sur son jeu de test.
2. Classer les échecs par type.
3. Changer **une seule chose** (exemples, règle, format) → v2.
4. Relancer le même test, noter le score dans `eval.scores`.
5. Garder la meilleure version ; noter l'échec dans `docs/failures.md` s'il est instructif.

## État

| Agent | Prompt | Version | Score |
| --- | --- | --- | --- |
| router | `route` | v1 | 100 % sur 20 cas (gpt-oss-20b) ; heuristique : 95 % |
| chercheur_rag | `rag_answer` | v1 | 56 questions : 6/6 pièges refusés, 0 faux refus, 0 citation inventée ; précision 0,63 (élargie 0,83) ; relecture humaine 39/50 fidèles et complètes |
| extracteur | `extract_portfolio` | v1 | mode texte (gpt-oss-120b) : 15/15 documents justes, 15/15 CSM justes, 1 relance |
| extracteur | `extract_portfolio` | v2 (par défaut) | jeu facile 15/15 ; jeu difficile 0 cas dangereux |
| extracteur | `extract_portfolio_vision` | v2 (par défaut) | jeu difficile : 0 cas dangereux (v1 : 2), photo dégradée rattrapée par la double lecture |
| extracteur | `extract_portfolio_vision` | v1 | Gemini 3.8 Flash : vision 15/15 (dont 7/7 scans), hybride 15/15 ; 30 à 60 fois plus lent que le mode texte |
| redacteur | `write_note` | v1 | synthèse ancrée (nombres et paragraphes vérifiés, repli écrit par le code) ; à mesurer |
| verificateur | `verify_answer` | v2 (par défaut) | « juge ancré » : 5/7 erreurs détectées (v1 : 3/7), 6/41 fausses alertes (v1 : 3/41), kappa 0,46 |
| verificateur | `verify_answer` | v1 | 3/7 erreurs détectées (portée : 3/4, attribution : 0/3), 3/41 fausses alertes, kappa 0,38 |
| chercheur_rag | `rag_answer` | v2 (par défaut) | portée des paragraphes (D-024) : fidèles 42/50 (v1 : 40), fidèles et complètes 39/50 (v1 : 39), précision élargie 0,84 (v1 : 0,83) |

Le livrable `prompt_library.md` sera généré à partir de ces fiches en S5.
