"""Question vocale : audio → texte avec Whisper (Groq, même clé que le LLM), puis chaîne habituelle (D-035).

Whisper accepte une « consigne » (prompt) qui oriente l'orthographe : on lui donne le vocabulaire
IFRS 17 (sigles, termes, numéros de paragraphe), sinon « CSM » devient « C. S. M. » ou « cé ès
aime ». L'effet est mesuré par eval/eval_speech.py (avec et sans vocabulaire).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

from core.config import Settings
from core.llm import LLMError, LLMFatal

MAX_AUDIO_BYTES = 25 * 1024 * 1024        # limite du niveau gratuit Groq
AUDIO_TYPES = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".mp4": "audio/mp4",
               ".ogg": "audio/ogg", ".webm": "audio/webm", ".flac": "audio/flac", ".mpeg": "audio/mpeg"}
VOCABULARY = ("IFRS 17, CSM, marge sur services contractuels, PAA, méthode d'affectation des primes, "
              "VFA, ajustement au titre du risque non financier, unités de couverture, contrats "
              "déficitaires, réassurance détenue, flux de trésorerie d'exécution, paragraphe B119, "
              "paragraphe 44, annexe C.")


@dataclass
class Transcription:
    text: str
    language: str = ""
    duration_s: float = 0.0
    model: str = ""


def audio_type(filename: str) -> str | None:
    for ext, mime in AUDIO_TYPES.items():
        if filename.lower().endswith(ext):
            return mime
    return None


def transcribe(audio: bytes, filename: str, settings: Settings, with_vocabulary: bool = True,
               fake: Callable[[bytes, str], str] | None = None) -> Transcription:
    """Whisper via l'API compatible OpenAI de Groq (POST /audio/transcriptions)."""
    if len(audio) > MAX_AUDIO_BYTES:
        raise LLMFatal("fichier audio trop volumineux (25 Mo maximum)")
    if settings.llm_provider == "fake":
        if fake is None:
            raise LLMError("fournisseur 'fake' sans transcription scriptée")
        return Transcription(text=fake(audio, filename), language="fr", model="fake-whisper")
    import httpx

    data = {"model": settings.speech_model, "language": "fr", "response_format": "verbose_json",
            "temperature": "0"}
    if with_vocabulary:
        data["prompt"] = VOCABULARY
    try:
        r = httpx.post(f"{settings.llm_base_url.rstrip('/')}/audio/transcriptions",
                       headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                       data=data, files={"file": (filename, audio, audio_type(filename) or "application/octet-stream")},
                       timeout=settings.llm_timeout_s)
    except httpx.HTTPError as exc:
        raise LLMError(f"réseau : {exc}") from exc
    if r.status_code in (400, 401, 403, 404, 413, 422):
        raise LLMFatal(f"HTTP {r.status_code} : {r.text[:300]}")
    if r.status_code >= 400:
        raise LLMError(f"HTTP {r.status_code} : {r.text[:300]}")
    body = r.json()
    return Transcription(text=(body.get("text") or "").strip(), language=body.get("language", ""),
                         duration_s=float(body.get("duration") or 0.0), model=settings.speech_model)


# --------------------------------------------------------------------------- #
# Mesure : taux d'erreur sur les mots (WER) et termes clés reconnus
# --------------------------------------------------------------------------- #
def _words(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", text)


def wer(reference: str, hypothesis: str) -> float:
    """Distance d'édition au niveau des mots / nombre de mots de la référence (accents et ponctuation ignorés)."""
    ref, hyp = _words(reference), _words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, rw in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, hw in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rw != hw))
        prev = cur
    return prev[-1] / len(ref)


def terms_found(terms: list[str], hypothesis: str) -> list[str]:
    hyp = " ".join(_words(hypothesis))
    return [t for t in terms if " ".join(_words(t)) in hyp]
