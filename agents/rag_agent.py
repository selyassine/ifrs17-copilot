"""Agent Chercheur RAG : recherche dans la norme puis réponse citée, ou refus.

Étapes :
1. recherche des paragraphes (hybride BGE-M3 + BM25 + glossaire, découpage B) ;
2. appel du LLM avec le prompt ``rag_answer`` : extraits numérotés E1…En et liste des
   paragraphes citables ;
3. **vérification par le code** (le LLM n'est pas cru sur parole) :
   - chaque paragraphe cité, dans le texte ([§44]) ou dans la liste des citations, doit
     appartenir aux extraits fournis ; sinon c'est une citation inventée ;
   - chaque phrase « copiée » doit se retrouver dans l'extrait (sinon elle est remplacée par
     le vrai texte et signalée) ;
4. en cas de citation inventée : **une** relance du LLM avec la liste des erreurs
   (boucle de correction bornée) ; si l'erreur persiste, les citations fausses sont retirées,
   et une réponse sans plus aucune source devient un refus.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from pydantic import ValidationError

from agents.schemas import Citation, GroundedAnswer
from core.llm import LLMClient, LLMError
from core.prompts import load_prompt
from rag.retrieve import Hit, Retriever, fold

MAX_CORRECTIONS = 1
_REF_RE = re.compile(r"\[([^\[\]]{1,80})\]")


@dataclass
class RagResult:
    answer: GroundedAnswer
    sources: list[dict]
    warnings: list[str] = field(default_factory=list)
    corrections: int = 0
    latency_ms: float = 0.0
    raw_invalid_refs: list[str] = field(default_factory=list)   # avant nettoyage (pour l'évaluation)


# --------------------------------------------------------------------------- #
# Préparation des extraits
# --------------------------------------------------------------------------- #
def context_path(chunk) -> str:
    """Chemin dans la norme (« IFRS 17, annexe C … > Dispositions transitoires > … ») : première
    ligne de l'en-tête de contexte du découpage B ; à défaut, le titre du bloc."""
    head = chunk.embed_text[: len(chunk.embed_text) - len(chunk.text)] \
        if chunk.embed_text.endswith(chunk.text) else ""
    lines = [ln for ln in head.strip().splitlines() if ln.strip()]
    return lines[0] if lines else chunk.heading


def format_extracts(hits: list[Hit], with_path: bool = False) -> tuple[str, dict[str, Hit], list[str]]:
    """Extraits numérotés E1…En. ``with_path`` (prompt v2, D-024) remplace le titre court par le
    chemin complet, pour que le LLM voie la portée du paragraphe (transition, réassurance…)."""
    blocks, by_id, allowed = [], {}, []
    for i, h in enumerate(hits, start=1):
        eid = f"E{i}"
        by_id[eid] = h
        pids = h.chunk.paragraph_ids
        allowed.extend(p for p in pids if p not in allowed)
        label = ", ".join(_display(p) for p in pids)
        title = context_path(h.chunk) if with_path else h.chunk.heading
        head = f" — {title}" if title else ""
        blocks.append(f"[{eid}] Paragraphe(s) {label}{head}\n{h.chunk.text}")
    return "\n\n".join(blocks), by_id, allowed


def _display(pid: str) -> str:
    return pid if pid.startswith(("def:", "art-", "cons-")) else f"§{pid}"


# --------------------------------------------------------------------------- #
# Vérification des citations
# --------------------------------------------------------------------------- #
def normalize_ref(ref: str) -> list[str]:
    """« §44(c) ; B119 » → ["44", "B119"] ; « art. 2 » → ["art-2"] ; « def:… » conservé."""
    out = []
    for part in re.split(r"[;,]|\bet\b", ref):
        p = part.strip()
        if not p:
            continue
        if p.lower().startswith("def:"):
            out.append("def:" + p[4:].strip())
            continue
        p = re.sub(r"paragraphes?", "", p.replace("§", ""), flags=re.I).strip()
        m = re.match(r"^(art|article)\.?\s*-?\s*(\d+|premier)", p, re.I)
        if m:
            out.append("art-" + ("1" if m.group(2).lower() == "premier" else m.group(2)))
            continue
        m = re.match(r"^(cons|considérant)\.?\s*-?\s*(\d+)", p, re.I)
        if m:
            out.append(f"cons-{m.group(2)}")
            continue
        m = re.match(r"^([BC]?\d{1,3}[A-Z]{0,2})(\(.*)?$", p.replace(" ", ""))
        if m:
            out.append(m.group(1))
    return out


def inline_refs(text: str) -> list[str]:
    refs: list[str] = []
    for m in _REF_RE.finditer(text or ""):
        refs.extend(normalize_ref(m.group(1)))
    return refs


def quote_found(quote: str, source: str) -> bool:
    q = re.sub(r"\s+", " ", fold(quote)).strip(" .;:«»\"'")
    s = re.sub(r"\s+", " ", fold(source))
    if not q:
        return False
    if q in s:
        return True
    words = [w for w in re.findall(r"\w+", q) if len(w) > 2]
    return bool(words) and sum(w in s for w in words) / len(words) >= 0.85


def check(data: dict, by_id: dict[str, Hit], allowed: list[str]) -> list[str]:
    """Liste des problèmes de citation (vide = tout est vérifiable)."""
    problems = []
    for ref in inline_refs(data.get("answer") or ""):
        if ref not in allowed:
            problems.append(f"[{ref}] cité dans la réponse mais absent des extraits")
    for c in data.get("citations") or []:
        pid = normalize_ref(str(c.get("paragraph_id", "")))
        pid = pid[0] if pid else str(c.get("paragraph_id", ""))
        if pid not in allowed:
            problems.append(f"citation {pid} absente des extraits")
        eid = c.get("extrait")
        if eid and eid in by_id and pid in allowed and pid not in by_id[eid].chunk.paragraph_ids:
            problems.append(f"citation {pid} attribuée à {eid}, qui ne contient pas ce paragraphe")
    return problems


def build_answer(data: dict, by_id: dict[str, Hit], allowed: list[str],
                 warnings: list[str]) -> GroundedAnswer:
    """Construit la réponse finale en ne gardant que ce qui est vérifiable."""
    if data.get("refused") or not data.get("answer"):
        return GroundedAnswer(answer=None, citations=[], refused=True,
                              refusal_reason=str(data.get("refusal_reason") or "Les extraits ne répondent pas.")[:300])

    answer = str(data["answer"])
    # retire du texte les références inventées qui auraient survécu à la correction
    def _clean(m: re.Match) -> str:
        refs = normalize_ref(m.group(1))
        if refs and not any(r in allowed for r in refs):
            warnings.append(f"référence retirée : [{m.group(1)}]")
            return ""
        return m.group(0)

    answer = _REF_RE.sub(_clean, answer)
    answer = re.sub(r"[ \t]{2,}", " ", answer)
    answer = re.sub(r" +([.,;:])", r"\1", answer).strip()

    citations: list[Citation] = []
    seen = set()
    for c in data.get("citations") or []:
        pids = normalize_ref(str(c.get("paragraph_id", "")))
        if not pids or pids[0] not in allowed or pids[0] in seen:
            continue
        pid = pids[0]
        hit = by_id.get(c.get("extrait")) if c.get("extrait") in by_id else None
        if hit is None or pid not in hit.chunk.paragraph_ids:
            hit = next(h for h in by_id.values() if pid in h.chunk.paragraph_ids)
        quote = str(c.get("quote") or "")
        if not quote_found(quote, hit.chunk.text):
            if quote:
                warnings.append(f"extrait cité pour {pid} non retrouvé mot pour mot : remplacé par le texte source")
            quote = hit.chunk.text[:300]
        citations.append(Citation(paragraph_id=pid, doc=hit.chunk.doc_id, quote=quote[:400],
                                  chunk_id=hit.chunk.chunk_id))
        seen.add(pid)

    # paragraphes cités dans le texte mais oubliés dans la liste : on les ajoute depuis la source
    for pid in inline_refs(answer):
        if pid in allowed and pid not in seen:
            hit = next(h for h in by_id.values() if pid in h.chunk.paragraph_ids)
            citations.append(Citation(paragraph_id=pid, doc=hit.chunk.doc_id,
                                      quote=hit.chunk.text[:300], chunk_id=hit.chunk.chunk_id))
            seen.add(pid)

    if not citations:
        warnings.append("réponse sans aucune source vérifiable : transformée en refus")
        return GroundedAnswer(answer=None, citations=[], refused=True,
                              refusal_reason="Je n'ai pas trouvé de passage de la norme qui étaye une réponse.")
    return GroundedAnswer(answer=answer, citations=citations, refused=False)


# --------------------------------------------------------------------------- #
# Agent
# --------------------------------------------------------------------------- #
def answer_question(question: str, retriever: Retriever, client: LLMClient | None = None,
                    k: int = 5, mode: str = "hybrid", expand: bool = True,
                    version: int | None = None, case_id: str = "") -> RagResult:
    t0 = time.perf_counter()
    client = client or LLMClient()
    spec = load_prompt("rag_answer", version)
    hits = retriever.search(question, k=k, mode=mode, expand=expand)
    extracts, by_id, allowed = format_extracts(hits)
    extracts_path, _, _ = format_extracts(hits, with_path=True)
    sources = [{"extrait": eid, "chunk_id": h.chunk.chunk_id, "paragraph_ids": h.chunk.paragraph_ids,
                "heading": h.chunk.heading, "page_start": h.chunk.page_start, "score": round(h.score, 4)}
               for eid, h in by_id.items()]

    messages = [
        {"role": "system", "content": spec.system},
        {"role": "user", "content": spec.render(
            chunks=extracts, chunks_portee=extracts_path, question=question,
            allowed=", ".join(_display(p) for p in allowed) or "(aucun)")},
    ]
    warnings: list[str] = []
    raw_invalid: list[str] = []
    corrections = 0
    data: dict = {}
    for attempt in range(MAX_CORRECTIONS + 1):
        resp = client.chat(messages, model=spec.params.model, temperature=spec.params.temperature,
                           max_tokens=spec.params.max_tokens, json_mode=True,
                           trace={"agent": "chercheur_rag", "prompt_id": spec.id,
                                  "prompt_version": spec.version, "case_id": case_id,
                                  "attempt": attempt})
        try:
            data = resp.json()
            if not isinstance(data, dict):
                raise LLMError("la réponse JSON n'est pas un objet")
        except LLMError as exc:
            data = {"answer": None, "refused": True, "refusal_reason": f"réponse illisible ({exc})"[:200]}
            warnings.append("réponse du LLM illisible")
            break
        problems = [] if data.get("refused") else check(data, by_id, allowed)
        if attempt == 0:
            raw_invalid = problems[:]
        if not problems:
            break
        if attempt < MAX_CORRECTIONS:
            corrections += 1
            messages += [
                {"role": "assistant", "content": json.dumps(data, ensure_ascii=False)},
                {"role": "user", "content": (
                    "Ta réponse contient des citations non vérifiables :\n- " + "\n- ".join(problems)
                    + f"\nCorrige-la en ne citant QUE ces paragraphes : {', '.join(_display(p) for p in allowed)}. "
                    "Si les extraits ne suffisent pas, refuse. Réponds avec le même format JSON.")},
            ]
        else:
            warnings.extend(problems)

    try:
        answer = build_answer(data, by_id, allowed, warnings)
    except (ValidationError, StopIteration) as exc:
        warnings.append(f"réponse invalide : {type(exc).__name__}")
        answer = GroundedAnswer(answer=None, refused=True, refusal_reason="Réponse du modèle invalide.")
    return RagResult(answer=answer, sources=sources, warnings=warnings, corrections=corrections,
                     latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                     raw_invalid_refs=raw_invalid)
