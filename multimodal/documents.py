"""Lecture d'un document client (PDF à couche texte) et repérage des nombres qu'il contient.

Deux usages :
1. ``pdf_text`` produit le texte donné au LLM : le texte courant, puis chaque tableau ligne par
   ligne avec des cellules séparées par « | ». Sans ces séparateurs, « 865 606,58 612 425,72 »
   serait ambigu (espaces des milliers ou changement de colonne ?).
2. ``document_numbers`` liste tous les nombres présents dans le document. L'extracteur s'en sert
   pour vérifier que chaque chiffre extrait par le LLM existe vraiment dans la source
   (contrôle d'ancrage : le LLM n'est pas cru sur parole, comme pour les citations du RAG).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path

# « 1 234,56 », « 1 234 », « 2,50 », « 0.035 », « -12 »
_NUM_RE = re.compile(r"-?\d{1,3}(?:[   ]\d{3})+(?:,\d+)?|-?\d+(?:[.,]\d+)?")
MAX_PAGES = 5
MAX_CHARS = 15_000


@dataclass
class DocumentText:
    text: str                                        # ce que lit le LLM
    table_numbers: list[float] = field(default_factory=list)
    text_numbers: list[float] = field(default_factory=list)
    pages: int = 0
    truncated: bool = False


def parse_number(s: str) -> float | None:
    """« 1 234,50 » → 1234.5 ; « 2,50 % » → 2.5 (le % est traité par l'appelant)."""
    s = s.strip().replace(" ", " ").replace(" ", " ").rstrip("%").strip()
    if not s:
        return None
    if re.fullmatch(r"-?\d{1,3}( \d{3})+(,\d+)?", s):
        s = s.replace(" ", "")
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _cell_number(cell: str) -> list[float]:
    """Une cellule de tableau = un nombre (les espaces y sont des séparateurs de milliers)."""
    v = parse_number(cell)
    if v is None:
        return []
    return [v, v / 100] if "%" in cell else [v]


def numbers_in_text(text: str) -> list[float]:
    out = []
    for m in _NUM_RE.finditer(text):
        v = parse_number(m.group())
        if v is None:
            continue
        out.append(v)
        if text[m.end():m.end() + 3].lstrip().startswith("%"):
            out.append(v / 100)
    return out


def pdf_text(source: str | Path | bytes, max_pages: int = MAX_PAGES,
             max_chars: int = MAX_CHARS) -> DocumentText:
    import pdfplumber

    stream = io.BytesIO(source) if isinstance(source, bytes) else source
    parts: list[str] = []
    table_nums: list[float] = []
    text_nums: list[float] = []
    with pdfplumber.open(stream) as pdf:
        n_pages = len(pdf.pages)
        for p_no, page in enumerate(pdf.pages[:max_pages], start=1):
            # texte et tableaux remis dans l'ordre de la page (de haut en bas) : sinon un titre
            # « Groupe B » se retrouve loin de son tableau
            tables = page.find_tables()
            rest = page
            for t in tables:
                rest = rest.outside_bbox(t.bbox)
            items: list[tuple[float, str]] = []
            text_lines = rest.extract_text_lines()
            for line in text_lines:
                items.append((line["top"], line["text"]))
            # « 7,50 » en fin de ligne et « % » au début de la suivante : lecture d'un seul bloc
            text_nums += numbers_in_text("\n".join(line["text"] for line in text_lines))
            for k, t in enumerate(tables, start=1):
                lines = []
                for row in t.extract():
                    cells = [(c or "").replace("\n", " ").strip() for c in row]
                    lines.append(" | ".join(cells))
                    for c in cells:
                        table_nums += _cell_number(c)
                items.append((t.bbox[1], f"[Tableau {k}, page {p_no}]\n" + "\n".join(lines)))
            items.sort(key=lambda it: it[0])
            parts.append(f"[Page {p_no}]\n" + "\n".join(text for _, text in items))
    text = "\n\n".join(parts)
    truncated = len(text) > max_chars or n_pages > max_pages
    return DocumentText(text=text[:max_chars], table_numbers=table_nums, text_numbers=text_nums,
                        pages=n_pages, truncated=truncated)


def document_numbers(doc: DocumentText) -> list[float]:
    return doc.table_numbers + doc.text_numbers
