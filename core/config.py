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
    llm_max_retries: int = field(default_factory=lambda: int(_env("LLM_MAX_RETRIES", "2")))

    router_mode: str = field(default_factory=lambda: _env("ROUTER_MODE", "heuristic"))

    # RAG : stratégie de découpage, mode de recherche et modèle d'embedding (si index dense)
    rag_strategy: str = field(default_factory=lambda: _env("RAG_STRATEGY", "B"))
    rag_mode: str = field(default_factory=lambda: _env("RAG_MODE", "bm25"))
    rag_embed_model: str = field(default_factory=lambda: _env("RAG_EMBED_MODEL"))
    rag_glossary: bool = field(default_factory=lambda: _env("RAG_GLOSSARY", "1") == "1")
    # version du prompt rag_answer : v2 mesurée et retenue (D-024) ; 1 pour reproduire la v1
    rag_prompt_version: int = field(default_factory=lambda: int(_env("RAG_PROMPT_VERSION", "2")))
    api_token: str = field(default_factory=lambda: _env("API_TOKEN"))
    trace_path: Path = field(
        default_factory=lambda: ROOT / _env("TRACE_PATH", "logs/traces.jsonl")
    )
    budget_usd: float = field(default_factory=lambda: float(_env("BUDGET_USD", "20")))


@lru_cache
def get_settings() -> Settings:
    return Settings()
