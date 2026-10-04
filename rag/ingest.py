"""Ingestion : PDF du Journal officiel → unités structurées (une par paragraphe de la norme).

Pourquoi une ingestion « consciente de la mise en page » plutôt que du texte brut :
- les numéros de paragraphe (44, B119, C5A) sont en marge gauche (x ≈ 68 pt), le texte
  à x ≈ 95 pt : c'est la seule façon fiable de savoir où commence un paragraphe ;
- les intertitres sont en gras ou en italique, précédés d'un saut vertical ;
- l'annexe A (définitions) est sur deux colonnes : terme à gauche, définition à droite ;
- l'en-tête du Journal officiel et les notes de bas de page polluent le texte.

Zones reconnues dans le règlement (UE) 2021/2036 :
    reglement  : considérants (1)…(16) et articles 1 à 4 (dont l'exemption de cohorte annuelle)
    norme      : IFRS 17 §1 à §132
    annexe_A   : définitions
    annexe_B   : guide d'application B1…B137
    annexe_C   : date d'entrée en vigueur et transition C1…C34
    annexe_D   : modifications d'autres normes → exclue (ses numéros de paragraphe sont
                 ceux d'autres normes et créeraient de fausses citations, voir D-012)

Extracteur : pdfplumber. pypdf a été écarté : il coupe les mots (« ser vices »,
« tr ésorer ie ») sur ce PDF, voir docs/failures.md F-003.

    python -m rag.ingest data/corpus/C002_reg_2021_2036_fr.pdf --doc-id C002
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

ZONES_ORDER = ["reglement", "norme", "annexe_A", "annexe_B", "annexe_C"]

# Marge gauche des numéros de paragraphe et frontière des colonnes de l'annexe A (en points)
PARA_X_MAX = 80
DEF_COLUMN_X = 185
FOOTNOTE_MAX_SIZE = 9.0      # notes de bas de page : 8,5 pt…
FOOTNOTE_MIN_TOP = 700.0     # …et en bas de page (le texte courant fait 9,6 pt)
HEADING_GAP = 13.0

_HEADER_RE = re.compile(r"Journal officiel de l.Union européenne")
_LIST_RE = re.compile(r"^(?:[a-z]{1,2}|[ivx]{1,5})\)\s")
_PARA_RE = {
    "norme": re.compile(r"^(\d{1,3}[A-Z]{0,2})(?:\s+(?=\S)|$)"),
    "annexe_B": re.compile(r"^(B\d{1,3}[A-Z]{0,2})(?:\s+(?=\S)|$)"),
    "annexe_C": re.compile(r"^(C\d{1,2}[A-Z]{0,2})(?:\s+(?=\S)|$)"),
}
_CONSIDERANT_RE = re.compile(r"^\((\d{1,2})\)\s")
_ARTICLE_RE = re.compile(r"^Article (premier|\d+)$")


@dataclass
class Line:
    text: str
    page: int
    x0: float
    top: float
    size: float
    font: str          # "bold", "italic", "bolditalic" ou "regular"
    gap: float = 0.0   # espace vertical depuis la ligne précédente de la même page
    words: list[dict] = field(default_factory=list, repr=False)


@dataclass
class Unit:
    unit_id: str          # identifiant unique dans le corpus : "C002:44", "C002:B119", "C002:def:..."
    doc_id: str
    zone: str
    paragraph_id: str     # ce qu'on cite : "44", "B119", "art-2", "cons-10", "def:marge sur services contractuels"
    heading: str          # intertitres en vigueur, du plus large au plus précis : « Contrats de
                          # réassurance détenus > Évaluation » (gras, puis italique, puis gras italique)
    section: str          # grand titre en vigueur (ex. « ÉVALUATION »)
    text: str
    page_start: int
    page_end: int


# --------------------------------------------------------------------------- #
# 1. Extraction des lignes avec leur mise en page
# --------------------------------------------------------------------------- #
def _font_kind(chars: list[dict]) -> str:
    names = Counter(c.get("fontname", "").split("+")[-1].lower() for c in chars)
    name = names.most_common(1)[0][0] if names else ""
    bold, italic = "bold" in name, "ital" in name
    return "bolditalic" if bold and italic else "bold" if bold else "italic" if italic else "regular"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return text.replace("’", "'").replace(" ", " ").strip()


def extract_lines(pdf_path: Path) -> list[Line]:
    import pdfplumber  # import local : seule l'ingestion en a besoin

    lines: list[Line] = []
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(extra_attrs=["fontname", "size"], keep_blank_chars=False)
            prev_top = None
            for raw in page.extract_text_lines(return_chars=True):
                chars = raw["chars"]
                if not chars:
                    continue
                size = Counter(round(c["size"], 1) for c in chars).most_common(1)[0][0]
                text = normalize(raw["text"])
                letters = [c for c in text if c.isalpha()]
                is_caps_title = bool(letters) and all(c.isupper() for c in letters)
                # une note de bas de page est petite ET en bas de page ; un titre de section en
                # capitales peut aussi tomber en bas de page (même taille) : on le garde
                is_footnote = (size < FOOTNOTE_MAX_SIZE and raw["top"] > FOOTNOTE_MIN_TOP
                               and not is_caps_title)
                if not text or _HEADER_RE.search(text) or is_footnote:
                    continue
                top = raw["top"]
                line_words = [w for w in words if abs(w["top"] - top) < 2.5]
                lines.append(Line(
                    text=text, page=pno, x0=raw["x0"], top=top, size=size,
                    font=_font_kind(chars), gap=(top - prev_top) if prev_top is not None else 99.0,
                    words=line_words,
                ))
                prev_top = top
    return lines


# --------------------------------------------------------------------------- #
# 2. Découpage en zones puis en unités
# --------------------------------------------------------------------------- #
def _zone_switch(line: Line, zone: str) -> str | None:
    t = line.text
    if zone == "reglement" and t == "ANNEXE":
        return "norme"
    if t in ("Annexe A", "Annexe B", "Annexe C", "Annexe D") and line.x0 < PARA_X_MAX:
        nxt = "annexe_" + t[-1]
        if ZONES_ORDER.index(zone) < ZONES_ORDER.index(nxt) if nxt in ZONES_ORDER else True:
            return nxt
    return None


def _para_key(pid: str) -> tuple[int, str]:
    m = re.match(r"^[BC]?(\d+)([A-Z]*)$", pid)
    return (int(m.group(1)), m.group(2)) if m else (-1, "")


def _join(parts: list[str]) -> str:
    out = ""
    for p in parts:
        if not out:
            out = p
        elif out.endswith("­") or out.endswith("-­"):
            out = out.rstrip("­") + p
        elif _LIST_RE.match(p):
            out += "\n" + p
        else:
            out += " " + p
    return re.sub(r"[ \t]+", " ", out.replace("­", "")).strip()


# profondeur d'un intertitre selon sa police, dans la mise en page du Journal officiel
_HEADING_DEPTH = {"bold": 0, "italic": 1, "bolditalic": 2}


def _push_heading(levels: list[str], title: str, font: str) -> str:
    """Range l'intertitre à son niveau, efface les niveaux inférieurs, renvoie le chemin complet."""
    depth = _HEADING_DEPTH.get(font, 0)
    levels[depth:] = [title] + [""] * (2 - depth)
    return " > ".join(x for x in levels if x)


def _is_major_heading(line: Line) -> bool:
    """Titres de section en petites capitales : OBJECTIF, CHAMP D'APPLICATION, ÉVALUATION…"""
    letters = [c for c in line.text if c.isalpha()]
    return (len(letters) >= 4 and all(c.isupper() for c in letters)
            and line.size < 9.0 and line.x0 < PARA_X_MAX)


def _is_minor_heading(line: Line, nxt: Line | None, zone: str) -> bool:
    if line.font == "regular" or _LIST_RE.match(line.text) or line.gap < HEADING_GAP:
        return False
    is_paragraph_start = zone in _PARA_RE and _PARA_RE[zone].match(line.text) and line.x0 < PARA_X_MAX
    return not is_paragraph_start


def parse_units(lines: list[Line], doc_id: str) -> list[Unit]:
    units: list[Unit] = []
    zone = "reglement"
    section = heading = ""
    levels = ["", "", ""]           # intertitres en vigueur : gras, italique, gras italique (D-025)
    pending_font = "bold"
    cur: dict | None = None
    last_key: dict[str, tuple[int, str]] = {}
    pending_heading: list[str] = []

    def flush():
        nonlocal cur
        if cur and cur["parts"]:
            units.append(Unit(
                unit_id=f"{doc_id}:{cur['pid']}", doc_id=doc_id, zone=cur["zone"],
                paragraph_id=cur["pid"], heading=cur["heading"], section=cur["section"],
                text=_join(cur["parts"]), page_start=cur["p0"], page_end=cur["p1"],
            ))
        cur = None

    def start(pid: str, first_text: str, line: Line):
        nonlocal cur
        flush()
        cur = {"pid": pid, "zone": zone, "heading": heading, "section": section,
               "parts": [first_text] if first_text else [], "p0": line.page, "p1": line.page}

    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        new_zone = _zone_switch(line, zone)
        if new_zone:
            flush()
            if new_zone == "annexe_D":
                break
            zone, section, heading, pending_heading = new_zone, "", "", []
            levels = ["", "", ""]
            continue

        t = line.text

        # ---------------- règlement : considérants et articles
        if zone == "reglement":
            m_art = _ARTICLE_RE.match(t)
            m_cons = _CONSIDERANT_RE.match(t)
            if m_art:
                num = "1" if m_art.group(1) == "premier" else m_art.group(1)
                start(f"art-{num}", "", line)
                cur["heading"] = f"Article {m_art.group(1)}"
            elif m_cons and line.x0 < PARA_X_MAX:
                start(f"cons-{m_cons.group(1)}", t[m_cons.end():], line)
                cur["heading"] = "Considérants"
            elif cur is not None and not t.startswith(("Fait à", "Par la Commission", "La présidente")):
                cur["parts"].append(t)
                cur["p1"] = line.page
            continue

        # ---------------- annexe A : définitions sur deux colonnes
        if zone == "annexe_A":
            left = " ".join(w["text"] for w in line.words if w["x0"] < DEF_COLUMN_X)
            right = " ".join(w["text"] for w in line.words if w["x0"] >= DEF_COLUMN_X)
            left, right = normalize(left), normalize(right)
            if t in ("Définitions",) or t.startswith("La présente annexe"):
                continue
            if left and right and right[:1].isupper():
                flush()
                cur = {"pid": None, "zone": zone, "heading": "Définitions", "section": "Annexe A",
                       "term": [left], "parts": [right], "p0": line.page, "p1": line.page}
            elif cur is not None:
                if left:
                    cur["term"].append(left)
                if right:
                    cur["parts"].append(right)
                cur["p1"] = line.page
            if cur is not None:
                term = " ".join(cur["term"])
                cur["pid"] = f"def:{term}"
            continue

        # ---------------- norme et annexes B, C : paragraphes numérotés
        if _is_major_heading(line):
            flush()
            section, heading, pending_heading = t, "", []
            levels = ["", "", ""]
            continue
        prev = lines[i - 1] if i else None
        if (prev is not None and _is_major_heading(prev) and line.size < 9.0
                and line.gap < HEADING_GAP and line.page == prev.page):
            section = f"{section} {t}"          # titre de section sur deux lignes
            continue

        m = _PARA_RE[zone].match(t) if line.x0 < PARA_X_MAX else None
        if m:
            pid = m.group(1)
            key = _para_key(pid)
            prev = last_key.get(zone, (0, ""))
            if key > prev and key[0] - prev[0] <= 6:
                if pending_heading:
                    heading = _push_heading(levels, _join(pending_heading), pending_font)
                    pending_heading = []
                last_key[zone] = key
                start(pid, t[m.end():].strip(), line)
                continue

        if t.startswith("La présente annexe fait partie intégrante"):
            continue
        if _is_minor_heading(line, nxt, zone) or (pending_heading and line.font != "regular"
                                                   and line.gap < HEADING_GAP):
            # un intertitre peut tenir sur deux lignes ; il s'applique au paragraphe suivant
            if not pending_heading or line.gap >= HEADING_GAP:
                if pending_heading:     # deux intertitres de suite : le premier devient parent
                    _push_heading(levels, _join(pending_heading), pending_font)
                pending_heading = [t]
                pending_font = line.font
            else:
                pending_heading.append(t)
            continue

        if pending_heading and cur is not None:
            # fausse alerte : c'était la suite du paragraphe (paragraphe en gras)
            cur["parts"].extend(pending_heading)
            pending_heading = []
        if cur is not None:
            cur["parts"].append(t)
            cur["p1"] = line.page

    flush()
    return units


def ingest(pdf_path: Path, doc_id: str) -> list[Unit]:
    """Parseur structuré, écrit pour la mise en page du Journal officiel (C002)."""
    return parse_units(extract_lines(pdf_path), doc_id)


def ingest_generic(pdf_path: Path, doc_id: str, zone: str = "autre") -> list[Unit]:
    """Repli pour un document sans parseur dédié : une unité par page.

    Les citations seront alors « p12 » au lieu d'un numéro de paragraphe : à remplacer par
    un parseur dédié pour chaque source importante (documents ifrs.org en S2-S3).
    """
    import pdfplumber

    units = []
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            text = normalize(page.extract_text() or "")
            if len(text.split()) < 20:
                continue
            units.append(Unit(unit_id=f"{doc_id}:p{pno}", doc_id=doc_id, zone=zone,
                              paragraph_id=f"p{pno}", heading="", section="", text=text,
                              page_start=pno, page_end=pno))
    return units


# Parseurs dédiés par document du manifeste ; les autres passent par ingest_generic
STRUCTURED_PARSERS = {"C002": ingest}


def save_units(units: list[Unit], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for u in units:
            f.write(json.dumps(asdict(u), ensure_ascii=False) + "\n")


def load_units(path: Path) -> list[Unit]:
    with path.open(encoding="utf-8") as f:
        return [Unit(**json.loads(line)) for line in f if line.strip()]


def summary(units: list[Unit]) -> dict:
    by_zone = Counter(u.zone for u in units)
    words = [len(u.text.split()) for u in units]
    return {
        "unites": len(units),
        "par_zone": dict(by_zone),
        "mots_moyen": round(sum(words) / max(len(words), 1), 1),
        "mots_max": max(words, default=0),
        "sans_intertitre": sum(1 for u in units if u.zone in ("norme", "annexe_B") and not u.heading),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--doc-id", required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    out = args.out or Path("data/processed") / f"{args.doc_id}_units.jsonl"
    units = ingest(args.pdf, args.doc_id)
    save_units(units, out)
    print(json.dumps(summary(units), ensure_ascii=False, indent=2))
    print(f"→ {out}")


if __name__ == "__main__":
    main()
