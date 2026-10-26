"""Client LLM unique pour tous les agents.

- Fournisseur ``openai_compatible`` : tout service exposant ``POST {base_url}/chat/completions``
  (fournisseurs cloud, OpenRouter, ou vLLM / Ollama sur Colab derrière un tunnel).
- Fournisseur ``fake`` : réponses scriptées, pour les tests et la CI (aucun appel réseau).

Chaque appel : timeout, réessais avec backoff exponentiel, repli sur un modèle
de secours, trace JSONL (tokens, coût estimé, latence). Changer de fournisseur
se fait dans .env, sans toucher au code des agents.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.config import Settings, get_settings
from core.tracing import traced

# Prix indicatifs en USD par million de tokens (entrée, sortie), à remplir en S1
# depuis la page tarifaire du fournisseur choisi (voir docs/decisions.md).
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {}


class LLMError(RuntimeError):
    retryable = True


class LLMRateLimit(LLMError):
    """HTTP 429 : quota par minute atteint ; ``wait`` = secondes conseillées par le fournisseur."""

    def __init__(self, message: str, wait: float):
        super().__init__(message)
        self.wait = wait


class LLMFatal(LLMError):
    """Erreur qu'un nouvel essai ne corrigera pas (clé invalide, modèle inconnu, requête refusée)."""

    retryable = False


MAX_RATE_LIMIT_WAITS = 5
# D-092 : modèle principal bloqué par son quota par minute → jusqu'à quand (horloge monotone), par modèle
_BLOCKED: dict[str, float] = {}


@dataclass
class LLMResponse:
    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    def json(self) -> Any:
        """Extrait le premier objet JSON de la réponse (tolère un bloc ```json)."""
        return extract_json(self.text)


def extract_json(text: str) -> Any:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    candidate = fenced.group(1) if fenced else text
    start = min((i for i in (candidate.find("{"), candidate.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise LLMError(f"aucun JSON dans la réponse : {text[:200]!r}")
    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(candidate[start:])
    except json.JSONDecodeError as exc:
        raise LLMError(f"JSON invalide : {exc}") from exc
    return obj


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    p_in, p_out = PRICES_PER_MTOK.get(model, (0.0, 0.0))
    return (tokens_in * p_in + tokens_out * p_out) / 1_000_000


class LLMClient:
    def __init__(
        self,
        settings: Settings | None = None,
        fake_responder: Callable[[list[dict[str, str]], str], str] | None = None,
    ) -> None:
        self.s = settings or get_settings()
        self._fake = fake_responder

    # ------------------------------------------------------------------ #
    def resolve_model(self, name: str) -> str:
        if name == "small":
            return self.s.llm_model_small or "fake-small"
        if name == "large":
            return self.s.llm_model_large or "fake-large"
        return name

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = "small",
        temperature: float = 0.0,
        max_tokens: int = 800,
        json_mode: bool = False,
        trace: dict[str, Any] | None = None,
    ) -> LLMResponse:
        model_id = self.resolve_model(model)
        fast = bool(self.s.llm_fallback_model) and self.s.llm_quota_max_wait_s >= 0
        # D-093 : budget d'attente (quota, nouveaux essais) pour tout l'appel, principal et secours compris. Mesure du
        # 25/10 : le secours sur le même fournisseur attendait son propre quota 5 × 60 s = 300 s par appel.
        deadline = time.monotonic() + self.s.llm_max_wait_s if self.s.llm_max_wait_s >= 0 else None
        with traced(self.s.trace_path, kind="llm", model=model_id, **(trace or {})) as rec:
            try:
                if fast and _BLOCKED.get(model_id, 0.0) > time.monotonic():
                    rec["quota_skipped"] = True          # quota encore épuisé : directement au modèle de secours
                    raise LLMRateLimit("quota du modèle principal encore épuisé", wait=0.0)
                resp = self._call_with_retries(
                    messages, model_id, temperature, max_tokens, json_mode,
                    self.s.llm_base_url, self.s.llm_api_key, rec,
                    max_wait=self.s.llm_quota_max_wait_s if fast else None, deadline=deadline,
                )
            except LLMError as primary_error:
                if not self.s.llm_fallback_model:
                    raise
                rec["fallback"] = True
                rec["primary_error"] = str(primary_error)[:300]
                try:
                    resp = self._call_with_retries(
                        messages, self.s.llm_fallback_model, temperature, max_tokens, json_mode,
                        self.s.llm_fallback_base_url or self.s.llm_base_url,
                        self.s.llm_fallback_api_key or self.s.llm_api_key, rec, deadline=deadline,
                    )
                except LLMError as fallback_error:
                    # les deux causes sont utiles au diagnostic (F-009)
                    raise LLMError(f"principal ({model_id}) : {primary_error} | secours "
                                   f"({self.s.llm_fallback_model}) : {fallback_error}") from fallback_error
            rec.update(model=resp.model, tokens_in=resp.tokens_in,
                       tokens_out=resp.tokens_out, cost_usd=round(resp.cost_usd, 6))
            return resp

    # ------------------------------------------------------------------ #
    def _call_with_retries(self, messages, model, temperature, max_tokens, json_mode,
                           base_url, api_key, rec: dict | None = None,
                           max_wait: float | None = None, deadline: float | None = None) -> LLMResponse:
        last: Exception | None = None
        attempt, waits = 0, 0
        while attempt <= self.s.llm_max_retries:
            try:
                return self._call_once(messages, model, temperature, max_tokens, json_mode,
                                       base_url, api_key)
            except LLMRateLimit as exc:
                # quota par minute : on attend ce que demande le fournisseur, sans consommer d'essai
                last, waits = exc, waits + 1
                if waits > MAX_RATE_LIMIT_WAITS:
                    break
                if max_wait is not None and exc.wait > max_wait:
                    # D-092 : un modèle de secours est prêt ; attendre 30 à 60 s le quota du principal coûtait jusqu'à
                    # plusieurs minutes par requête. On bascule tout de suite et on retient le blocage.
                    _BLOCKED[model] = time.monotonic() + exc.wait
                    if rec is not None:
                        rec["quota_switch"] = True
                    raise exc
                pause = min(exc.wait, 60)
                if deadline is not None and time.monotonic() + pause > deadline:
                    if rec is not None:
                        rec["wait_budget_exceeded"] = True
                    raise LLMError(f"quota : attente de {pause:.0f} s au-delà du budget d'attente "
                                   f"({self.s.llm_max_wait_s:.0f} s, LLM_MAX_WAIT_S)") from exc
                if rec is not None:          # temps perdu à attendre le quota, visible dans la trace (D-091)
                    rec["quota_waits"] = rec.get("quota_waits", 0) + 1
                    rec["quota_wait_s"] = round(rec.get("quota_wait_s", 0.0) + pause, 1)
                time.sleep(pause)
            except LLMError as exc:
                last = exc
                if not exc.retryable:
                    raise
                attempt += 1
                if rec is not None:
                    rec["retries"] = rec.get("retries", 0) + 1
                if attempt <= self.s.llm_max_retries:
                    pause = min(2 ** attempt, 8)
                    if deadline is not None and time.monotonic() + pause > deadline:
                        break
                    time.sleep(pause)
        raise LLMError(f"échec après {attempt} tentatives et {waits} attentes de quota : {last}")

    def _call_once(self, messages, model, temperature, max_tokens, json_mode,
                   base_url, api_key) -> LLMResponse:
        if self.s.llm_provider == "fake":
            if self._fake is None:
                raise LLMError("fournisseur 'fake' sans réponse scriptée")
            text = self._fake(messages, model)
            t_in = sum(len(m["content"]) for m in messages) // 4
            return LLMResponse(text=text, model=model, tokens_in=t_in, tokens_out=len(text) // 4)

        if self.s.llm_provider != "openai_compatible":
            raise LLMError(f"fournisseur inconnu : {self.s.llm_provider}")
        if not base_url:
            raise LLMError("LLM_BASE_URL manquant dans .env")

        import httpx  # import local : inutile pour les tests et la CI

        payload: dict[str, Any] = {
            "model": model, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if "gpt-oss" in model:
            # modèles « à raisonnement » : raisonnement court et non renvoyé, et assez de
            # tokens pour que le raisonnement ne consomme pas toute la réponse (Groq, doc reasoning)
            payload["reasoning_effort"] = "low"
            payload["include_reasoning"] = False
            payload["max_tokens"] = max(max_tokens, 1024)
        try:
            r = httpx.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
                json=payload,
                timeout=self.s.llm_timeout_s,
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"réseau : {exc}") from exc
        if r.status_code == 429:
            try:
                wait = float(r.headers.get("retry-after", "10"))
            except ValueError:
                wait = 10.0
            raise LLMRateLimit(f"HTTP 429 (quota) : {r.text[:200]}", wait=wait + 0.5)
        if r.status_code in (400, 401, 403, 404, 413, 422):
            raise LLMFatal(f"HTTP {r.status_code} : {r.text[:300]}")
        if r.status_code >= 400:
            raise LLMError(f"HTTP {r.status_code} : {r.text[:300]}")
        data = r.json()
        usage = data.get("usage") or {}
        t_in, t_out = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        return LLMResponse(
            text=data["choices"][0]["message"]["content"] or "",
            model=data.get("model", model),
            tokens_in=t_in, tokens_out=t_out,
            cost_usd=estimate_cost(model, t_in, t_out),
            raw=data,
        )
