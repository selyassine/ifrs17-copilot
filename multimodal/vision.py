"""Images pour le modèle vision : rendu des pages PDF, encodage, client dédié (D-029).

Le modèle vision (Gemini, niveau gratuit) est appelé par le même client que Groq, grâce à son
point d'accès compatible OpenAI ; seuls l'URL, la clé et le modèle changent.
"""

from __future__ import annotations

import base64
import io
from dataclasses import replace

from core.config import Settings
from core.llm import LLMClient

MAX_IMAGE_SIDE = 1600      # px : assez pour lire un tableau, sans gaspiller de tokens


def detect_mime(data: bytes) -> str | None:
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    return None


def normalize_image(data: bytes) -> tuple[bytes, str]:
    """Réduit les très grandes images et les convertit en JPEG (taille de requête maîtrisée)."""
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    out = io.BytesIO()
    img.convert("RGB").save(out, format="JPEG", quality=85)
    return out.getvalue(), "image/jpeg"


def enhance_variant(data: bytes) -> tuple[bytes, str]:
    """Seconde version d'une image pour la double lecture : niveaux de gris, contraste
    automatique, netteté, légère mise à l'échelle. Lire deux versions différentes évite que
    deux lectures identiques confirment la même erreur."""
    from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

    try:
        img = ImageOps.autocontrast(Image.open(io.BytesIO(data)).convert("L"), cutoff=1)
    except (UnidentifiedImageError, OSError):
        return data, detect_mime(data) or "image/jpeg"     # image illisible : même image relue
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=160, threshold=2))
    w, h = img.size
    factor = min(1.3, MAX_IMAGE_SIDE / max(w, h)) if max(w, h) < MAX_IMAGE_SIDE else 1.0
    if factor > 1.0:
        img = img.resize((int(w * factor), int(h * factor)), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue(), "image/jpeg"


def pdf_page_images(pdf: bytes, max_pages: int = 2, dpi: int = 150) -> list[tuple[bytes, str]]:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(pdf)
    images = []
    for k in range(min(len(doc), max_pages)):
        buf = io.BytesIO()
        doc[k].render(scale=dpi / 72).to_pil().convert("RGB").save(buf, format="JPEG", quality=85)
        images.append((buf.getvalue(), "image/jpeg"))
    return images


def image_part(data: bytes, mime: str) -> dict:
    url = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    return {"type": "image_url", "image_url": {"url": url}}


def vision_client(settings: Settings, fake_responder=None) -> LLMClient:
    """Client LLM pointé sur le modèle vision ; le prompt demande le modèle « large »."""
    if settings.llm_provider != "fake" and not settings.vision_api_key:
        from core.llm import LLMError

        raise LLMError("clé du modèle vision absente : ajouter GEMINI_API_KEY dans .env")
    vs = replace(settings, llm_base_url=settings.vision_base_url, llm_api_key=settings.vision_api_key,
                 llm_model_large=settings.vision_model, llm_model_small=settings.vision_model,
                 llm_fallback_model=settings.vision_fallback_model,
                 llm_fallback_base_url=settings.vision_base_url,
                 llm_fallback_api_key=settings.vision_api_key)
    return LLMClient(vs, fake_responder=fake_responder)
