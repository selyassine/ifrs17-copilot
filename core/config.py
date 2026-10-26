"""Configuration lue depuis l'environnement (fichier .env à la racine)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:  # python-dotenv est optionnel : la CI n'a pas de .env
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover
    pass


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    # LLM : n'importe quel fournisseur compatible avec l'API « chat completions »
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "fake"))
    llm_base_url: str = field(default_factory=lambda: _env("LLM_BASE_URL"))
    llm_api_key: str = field(default_factory=lambda: _env("LLM_API_KEY"))
    llm_model_small: str = field(default_factory=lambda: _env("LLM_MODEL_SMALL"))
    llm_model_large: str = field(default_factory=lambda: _env("LLM_MODEL_LARGE"))
    llm_fallback_base_url: str = field(default_factory=lambda: _env("LLM_FALLBACK_BASE_URL"))
    llm_fallback_api_key: str = field(default_factory=lambda: _env("LLM_FALLBACK_API_KEY"))
    llm_fallback_model: str = field(default_factory=lambda: _env("LLM_FALLBACK_MODEL"))
    llm_timeout_s: float = field(default_factory=lambda: float(_env("LLM_TIMEOUT_S", "60")))
    # D-092 : au-delà de cette attente de quota (s), passer au modèle de secours s'il est configuré ; -1 = toujours attendre
    llm_quota_max_wait_s: float = field(default_factory=lambda: float(_env("LLM_QUOTA_MAX_WAIT_S", "10")))
    # D-093 : attente totale permise par appel (quota et nouveaux essais, principal et secours) ; -1 = sans limite
    llm_max_wait_s: float = field(default_factory=lambda: float(_env("LLM_MAX_WAIT_S", "45")))
    llm_max_retries: int = field(default_factory=lambda: int(_env("LLM_MAX_RETRIES", "2")))

    router_mode: str = field(default_factory=lambda: _env("ROUTER_MODE", "heuristic"))

    # RAG : stratégie de découpage, mode de recherche et modèle d'embedding (si index dense)
    rag_strategy: str = field(default_factory=lambda: _env("RAG_STRATEGY", "B"))
    rag_mode: str = field(default_factory=lambda: _env("RAG_MODE", "bm25"))
    rag_embed_model: str = field(default_factory=lambda: _env("RAG_EMBED_MODEL"))
    # stockage des vecteurs (D-052) : numpy (fichier .npy en mémoire) ou qdrant (base vectorielle)
    rag_store: str = field(default_factory=lambda: _env("RAG_STORE", "numpy"))
    qdrant_url: str = field(default_factory=lambda: _env("QDRANT_URL"))          # vide : Qdrant embarqué
    qdrant_api_key: str = field(default_factory=lambda: _env("QDRANT_API_KEY"))
    rag_glossary: bool = field(default_factory=lambda: _env("RAG_GLOSSARY", "1") == "1")
    # version du prompt rag_answer : v3 retenue (D-098) ; 2 pour reproduire la mesure de D-024, 1 pour la v1
    rag_prompt_version: int = field(default_factory=lambda: int(_env("RAG_PROMPT_VERSION", "3")))
    # réécriture de la question par le LLM avant la recherche (D-045) ; 0 tant que le gain n'est pas mesuré
    rag_rewrite: bool = field(default_factory=lambda: _env("RAG_REWRITE", "0") == "1")
    # options de recherche avancées (D-048, D-049), chacune mesurée avant d'être activée
    rag_rerank_model: str = field(default_factory=lambda: _env("RAG_RERANK_MODEL"))
    rag_questions: bool = field(default_factory=lambda: _env("RAG_QUESTIONS", "0") == "1")
    rag_graph: bool = field(default_factory=lambda: _env("RAG_GRAPH", "0") == "1")
    # agent de recherche LangGraph (planifier → chercher → évaluer → reboucler), D-050
    rag_agentic: bool = field(default_factory=lambda: _env("RAG_AGENTIC", "0") == "1")
    # Vérificateur (LLM-juge) après l'agent RAG, et nombre de corrections autorisées (D-033)
    verifier_enabled: bool = field(default_factory=lambda: _env("VERIFIER", "1") == "1")
    verifier_max_rounds: int = field(default_factory=lambda: int(_env("VERIFIER_MAX_ROUNDS", "1")))
    # Réponses de référence aux questions fixes de la note (data/norm_reference.json, D-037)
    use_norm_reference: bool = field(default_factory=lambda: _env("NORM_REFERENCE", "1") == "1")
    norm_reference_path: Path = field(default_factory=lambda: ROOT / "data" / "norm_reference.json")
    # coefficient de variation des sorties : niveau de confiance de l'ajustement pour risque (D-056)
    ra_cv: float = field(default_factory=lambda: float(_env("RA_CV", "0.15")))
    # document à plusieurs groupes : une lecture et une note par groupe (D-078) ; 0 = validation humaine (D-032)
    multi_group: bool = field(default_factory=lambda: _env("MULTI_GROUPE", "1") == "1")
    # note actuarielle (D-055) : entité affichée en page de garde
    note_entity: str = field(default_factory=lambda: _env("NOTE_ENTITY", "Compagnie d'assurance fictive (projet pédagogique)"))
    # Voix : Whisper sur Groq (même clé que le LLM) (D-035)
    speech_model: str = field(default_factory=lambda: _env("SPEECH_MODEL", "whisper-large-v3-turbo"))
    # Vision (lecture d'images) : Gemini via son point d'accès compatible OpenAI (D-029)
    vision_base_url: str = field(default_factory=lambda: _env(
        "VISION_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"))
    vision_api_key: str = field(default_factory=lambda: _env("VISION_API_KEY") or _env("GEMINI_API_KEY"))
    vision_model: str = field(default_factory=lambda: _env("VISION_MODEL", "gemini-3.8-flash"))
    vision_fallback_model: str = field(default_factory=lambda: _env("VISION_FALLBACK_MODEL",
                                                                    "gemini-3.5-flash-lite"))
    # mode vision : seconde lecture de l'image nettoyée, divergence → validation humaine (D-032)
    vision_double_read: bool = field(default_factory=lambda: _env("VISION_DOUBLE_READ", "1") == "1")
    # lecture d'un PDF à couche texte : « texte » (Groq) ou « hybride » (texte + image, vision)
    extract_pdf_mode: str = field(default_factory=lambda: _env("EXTRACT_PDF_MODE", "texte"))
    api_token: str = field(default_factory=lambda: _env("API_TOKEN"))
    # validation humaine demandée sur le site : l'API transmet le dossier au workflow n8n 06,
    # qui envoie l'e-mail avec le formulaire pré-rempli (D-041) ; vide = pas d'e-mail
    n8n_validation_url: str = field(default_factory=lambda: _env("N8N_VALIDATION_URL"))
    trace_path: Path = field(
        default_factory=lambda: ROOT / _env("TRACE_PATH", "logs/traces.jsonl")
    )
    budget_usd: float = field(default_factory=lambda: float(_env("BUDGET_USD", "20")))
    # registre des dossiers, piste d'audit et comptes (D-058) ; fichier SQLite hors Git
    registry_path: Path = field(default_factory=lambda: ROOT / _env("REGISTRY_PATH", "data/registry.db"))
    # questions à la norme d'un dossier traitées en parallèle (D-063) ; 1 = l'une après l'autre
    norm_parallel: int = field(default_factory=lambda: int(_env("NORM_PARALLEL", "1")))
    # état du Copilot sauvegardé après chaque nœud du graphe (checkpointer LangGraph, D-061)
    copilot_checkpoints: Path = field(default_factory=lambda: ROOT / _env("COPILOT_CHECKPOINTS", "data/copilot_checkpoints.db"))
    # navigateur qui imprime la note en PDF (D-065) ; vide = Edge, Chrome ou Chromium trouvé automatiquement
    note_pdf_browser: str = field(default_factory=lambda: _env("NOTE_PDF_BROWSER"))
    # premier compte administrateur, créé au démarrage si la base n'a encore aucun compte
    admin_username: str = field(default_factory=lambda: _env("ADMIN_USERNAME"))
    admin_password: str = field(default_factory=lambda: _env("ADMIN_PASSWORD"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
