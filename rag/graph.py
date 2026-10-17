"""Graph RAG léger : le graphe des renvois entre paragraphes de la norme (D-049).

IFRS 17 renvoie sans cesse à d'autres paragraphes (« voir paragraphes B96 à B100 », « selon le
paragraphe 44(c) »). Ces renvois sont des liens écrits par l'IASB lui-même : un graphe exact, sans
LLM ni extraction d'entités. Quand la recherche trouve un paragraphe, ses renvois donnent souvent
la règle qui le complète (une définition, une exception, la méthode de calcul).

Règles d'extraction :
- « paragraphe(s) » suivi d'une liste d'identifiants (« 44(c) », « B96 à B100 », « 47 à 52 et 57 ») ;
- les renvois vers une autre norme sont ignorés (« paragraphe 7 d'IFRS 15 », « du règlement (CE) ») ;
- une plage de plus de MAX_RANGE paragraphes est ignorée (« B36 à B92 » désigne une section entière,
  pas une règle précise : elle noierait les résultats).

    python -m rag.graph          # statistiques du graphe sur le découpage B
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from rag.chunking import Chunk

MAX_RANGE = 6
_ID = r"(?:[BC]\d{1,3}[A-Z]{0,2}|\d{1,3}[A-Z]{0,2})(?:\([a-z]{1,2}\))?(?:\([ivx]{1,5}\))?"
_LIST = rf"{_ID}(?:\s*(?:,|et|ou|à)\s*{_ID})*"
_REF = re.compile(rf"\bparagraphes?\s+({_LIST})")
_OTHER_STANDARD = re.compile(r"^\s*(?:,\s*)?(?:d['’]|de l['’]|du |de la )\s*(?:IFRS|IAS|IFRIC|SIC|règlement|annexe|directive)",
                             re.IGNORECASE)
_TOKEN = re.compile(rf"{_ID}|à")


def _base(pid: str) -> str:
    return re.sub(r"\(.*$", "", pid)


def parse_references(text: str, known: list[str]) -> list[str]:
    """Paragraphes d'IFRS 17 cités dans ``text`` (identifiants de base, dans l'ordre, sans doublon)."""
    order = {p: i for i, p in enumerate(known)}
    out: list[str] = []
    for m in _REF.finditer(text):
        if _OTHER_STANDARD.match(text[m.end():m.end() + 40]):
            continue
        tokens = _TOKEN.findall(m.group(1))
        ids: list[str] = []
        i = 0
        while i < len(tokens):
            t = tokens[i]
            if t == "à" and ids and i + 1 < len(tokens):
                a, b = _base(ids[-1]), _base(tokens[i + 1])
                if a in order and b in order and 0 < order[b] - order[a] <= MAX_RANGE:
                    ids += known[order[a] + 1: order[b] + 1]
                elif a in order and b in order:
                    ids.pop()                     # plage trop large : on ne garde rien
                i += 2
                continue
            if t != "à":
                ids.append(t)
            i += 1
        for pid in ids:
            b = _base(pid)
            if b in order and b not in out:
                out.append(b)
    return out


def paragraph_graph(units: list[dict]) -> dict[str, list[str]]:
    known = [u["paragraph_id"] for u in units]
    graph: dict[str, list[str]] = {}
    for u in units:
        refs = [r for r in parse_references(u["text"], known) if r != u["paragraph_id"]]
        if refs:
            graph[u["paragraph_id"]] = refs
    return graph


def chunk_graph(chunks: list[Chunk], pgraph: dict[str, list[str]]) -> dict[int, list[int]]:
    """Graphe entre morceaux : i → j si un paragraphe de i renvoie à un paragraphe de j."""
    where: dict[str, list[int]] = defaultdict(list)
    for j, c in enumerate(chunks):
        for p in c.paragraph_ids:
            where[p].append(j)
    out: dict[int, list[int]] = {}
    for i, c in enumerate(chunks):
        nb: list[int] = []
        for p in c.paragraph_ids:
            for r in pgraph.get(p, []):
                for j in where.get(r, []):
                    if j != i and j not in nb:
                        nb.append(j)
        if nb:
            out[i] = nb
    return out


def load_chunk_graph(units_path: Path, chunks: list[Chunk]) -> dict[int, list[int]]:
    units = [json.loads(line) for line in units_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return chunk_graph(chunks, paragraph_graph(units))


if __name__ == "__main__":
    from rag.chunking import load_chunks
    from rag.service import PROCESSED

    units = [json.loads(line) for line in (PROCESSED / "C002_units.jsonl").read_text(encoding="utf-8").splitlines()]
    pg = paragraph_graph(units)
    cg = chunk_graph(load_chunks(PROCESSED / "chunks_B.jsonl"), pg)
    n_edges = sum(len(v) for v in pg.values())
    print(json.dumps({"paragraphes": len(units), "paragraphes_avec_renvois": len(pg), "renvois": n_edges,
                      "morceaux_avec_voisins": len(cg), "exemple_44": pg.get("44"), "exemple_B96": pg.get("B96")},
                     ensure_ascii=False, indent=1))
