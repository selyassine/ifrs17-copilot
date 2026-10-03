"""Deux stratégies de découpage comparées sur le même corpus (section 6.2 du planning).

A — taille fixe récursive : le texte est vu comme un flux continu (numéros de paragraphe
    et intertitres compris, comme dans une extraction PDF classique), découpé en phrases,
    puis regroupé en morceaux d'au plus ``max_tokens`` avec ``overlap`` de chevauchement.
    La stratégie ignore la structure ; on garde seulement, pour l'évaluation, la liste des
    paragraphes que chaque morceau recouvre.

B — par structure : un morceau = un paragraphe numéroté (44, B119…), précédé d'un
    en-tête de contexte (norme, section, intertitre, numéro). Les paragraphes trop courts
    sont fusionnés avec le suivant du même intertitre ; les trop longs sont redécoupés.

Les deux partent des mêmes unités (rag/ingest.py) : seule la façon de couper change,
ce qui isole l'effet du découpage dans la comparaison.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from rag.ingest import Unit

ZONE_LABEL = {
    "reglement": "Règlement (UE) 2021/2036",
    "norme": "IFRS 17",
    "annexe_A": "IFRS 17, annexe A (définitions)",
    "annexe_B": "IFRS 17, annexe B (guide d'application)",
    "annexe_C": "IFRS 17, annexe C (entrée en vigueur et transition)",
}

TOKENS_PER_WORD = 1.4  # approximation pour un tokenizer multilingue (XLM-R / BGE-M3) en français


def count_tokens(text: str) -> int:
    """Approximation sans dépendance ; remplaçable par le tokenizer du modèle d'embedding."""
    return math.ceil(len(text.split()) * TOKENS_PER_WORD)


@dataclass
class Chunk:
    chunk_id: str
    strategy: str
    doc_id: str
    text: str                    # texte montré au LLM et cité
    embed_text: str              # texte indexé (B : avec l'en-tête de contexte)
    paragraph_ids: list[str]     # paragraphes recouverts (vérité terrain pour l'évaluation)
    zone: str
    heading: str = ""
    page_start: int = 0
    page_end: int = 0
    n_tokens: int = 0
    meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Outil commun : découpage en phrases avec positions, puis regroupement
# --------------------------------------------------------------------------- #
_SENT_RE = re.compile(r"[^\n]+?(?:[.;:!?](?=\s)|$)|\n", re.M)


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Spans (début, fin) de « phrases » : coupe sur . ; : ! ? et sur les retours à la ligne."""
    spans = []
    for m in _SENT_RE.finditer(text):
        s, e = m.span()
        while s < e and text[s].isspace():
            s += 1
        if s < e:
            spans.append((s, e))
    return spans


def _split_long_span(text: str, span: tuple[int, int], max_tokens: int) -> list[tuple[int, int]]:
    s, e = span
    if count_tokens(text[s:e]) <= max_tokens:
        return [span]
    words = [(m.start() + s, m.end() + s) for m in re.finditer(r"\S+", text[s:e])]
    per = max(1, int(max_tokens / TOKENS_PER_WORD))
    return [(words[i][0], words[min(i + per, len(words)) - 1][1]) for i in range(0, len(words), per)]


def pack(text: str, max_tokens: int, overlap: int) -> list[tuple[int, int]]:
    """Regroupe les phrases en fenêtres ≤ max_tokens, avec ~overlap tokens repris d'une fenêtre à l'autre."""
    atoms: list[tuple[int, int]] = []
    for sp in sentence_spans(text):
        atoms.extend(_split_long_span(text, sp, max_tokens))
    sizes = [count_tokens(text[s:e]) for s, e in atoms]

    windows: list[tuple[int, int]] = []
    i = 0
    while i < len(atoms):
        j, total = i, 0
        while j < len(atoms) and (total + sizes[j] <= max_tokens or j == i):
            total += sizes[j]
            j += 1
        windows.append((atoms[i][0], atoms[j - 1][1]))
        if j >= len(atoms):
            break
        # recul pour le chevauchement, sans jamais revenir au début de la fenêtre
        k, back = j, 0
        while k - 1 > i and back + sizes[k - 1] <= overlap:
            k -= 1
            back += sizes[k]
        i = k
    return windows


# --------------------------------------------------------------------------- #
# Stratégie A
# --------------------------------------------------------------------------- #
def chunk_fixed(units: list[Unit], max_tokens: int = 512, overlap: int = 64) -> list[Chunk]:
    chunks: list[Chunk] = []
    by_doc: dict[str, list[Unit]] = {}
    for u in units:
        by_doc.setdefault(u.doc_id, []).append(u)

    for doc_id, us in by_doc.items():
        parts, spans = [], []          # spans[i] = (début, fin, unité) dans le flux
        pos, last_heading = 0, None
        for u in us:
            prefix = ""
            if u.heading and u.heading != last_heading and u.zone != "reglement":
                prefix = u.heading + "\n"
                last_heading = u.heading
            label = u.paragraph_id.removeprefix("def:") if u.zone == "annexe_A" else u.paragraph_id
            block = f"{prefix}{label} {u.text}\n\n"
            spans.append((pos, pos + len(block), u))
            parts.append(block)
            pos += len(block)
        stream = "".join(parts)

        for n, (s, e) in enumerate(pack(stream, max_tokens, overlap)):
            covered = [u for (us_, ue, u) in spans if us_ < e and ue > s]
            text = stream[s:e].strip()
            chunks.append(Chunk(
                chunk_id=f"A:{doc_id}:{n:04d}", strategy="A", doc_id=doc_id,
                text=text, embed_text=text,
                paragraph_ids=[u.paragraph_id for u in covered],
                zone=covered[0].zone if covered else "",
                heading=covered[0].heading if covered else "",
                page_start=min((u.page_start for u in covered), default=0),
                page_end=max((u.page_end for u in covered), default=0),
                n_tokens=count_tokens(text),
            ))
    return chunks


# --------------------------------------------------------------------------- #
# Stratégie B
# --------------------------------------------------------------------------- #
def _sentence_case(title: str) -> str:
    """« ÉVALUATION (PARAGRAPHES B36 À B119F) » → « Évaluation (paragraphes B36 à B119F) »."""
    if not title.isupper():
        return title
    low = title[0] + title[1:].lower()
    return re.sub(r"\b([bc])(\d+[a-z]*)", lambda m: (m.group(1) + m.group(2)).upper(), low)


def context_header(u: Unit) -> str:
    bits = [ZONE_LABEL.get(u.zone, u.zone)]
    if u.section:
        bits.append(_sentence_case(u.section))
    if u.heading and u.heading != "Considérants":
        bits.append(u.heading)
    if u.zone == "annexe_A":
        ref = f"Définition : {u.paragraph_id.removeprefix('def:')}"
    elif u.zone == "reglement":
        ref = u.heading if u.paragraph_id.startswith("art-") else f"Considérant {u.paragraph_id[5:]}"
    else:
        ref = f"Paragraphe {u.paragraph_id}"
    return " > ".join(bits) + f"\n{ref}\n"


def chunk_structural(units: list[Unit], min_tokens: int = 40, max_tokens: int = 800,
                     overlap: int = 64) -> list[Chunk]:
    chunks: list[Chunk] = []
    i = 0
    while i < len(units):
        group = [units[i]]
        # fusion des paragraphes très courts avec le(s) suivant(s) du même intertitre
        while (sum(count_tokens(u.text) for u in group) < min_tokens and i + 1 < len(units)
               and units[i + 1].zone == group[0].zone and units[i + 1].heading == group[0].heading
               and units[i + 1].doc_id == group[0].doc_id):
            i += 1
            group.append(units[i])
        i += 1

        head = group[0]
        header = context_header(head)
        if len(group) > 1:
            header = header.rstrip("\n") + " à " + group[-1].paragraph_id + "\n"
        body = "\n\n".join(
            (f"{u.paragraph_id} " if len(group) > 1 else "") + u.text for u in group)
        pids = [u.paragraph_id for u in group]
        base_id = f"B:{head.doc_id}:{head.paragraph_id}"

        windows = [(0, len(body))] if count_tokens(body) <= max_tokens else pack(body, max_tokens, overlap)
        for k, (s, e) in enumerate(windows):
            text = body[s:e].strip()
            chunks.append(Chunk(
                chunk_id=base_id if len(windows) == 1 else f"{base_id}#{k + 1}",
                strategy="B", doc_id=head.doc_id, text=text, embed_text=header + text,
                paragraph_ids=pids, zone=head.zone, heading=head.heading,
                page_start=group[0].page_start, page_end=group[-1].page_end,
                n_tokens=count_tokens(header + text),
                meta={"part": k + 1, "parts": len(windows)} if len(windows) > 1 else {},
            ))
    return chunks


STRATEGIES = {"A": chunk_fixed, "B": chunk_structural}


def save_chunks(chunks: list[Chunk], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")


def load_chunks(path: Path) -> list[Chunk]:
    with path.open(encoding="utf-8") as f:
        return [Chunk(**json.loads(line)) for line in f if line.strip()]


def stats(chunks: list[Chunk]) -> dict:
    sizes = sorted(c.n_tokens for c in chunks)
    n = len(sizes)
    return {
        "chunks": n,
        "tokens_moyen": round(sum(sizes) / max(n, 1), 1),
        "tokens_median": sizes[n // 2] if n else 0,
        "tokens_max": sizes[-1] if n else 0,
        "paragraphes_par_chunk": round(sum(len(c.paragraph_ids) for c in chunks) / max(n, 1), 2),
    }
