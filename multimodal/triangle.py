"""Lecture d'un dossier de sinistres survenus : triangle de paiements → ``TriangleData`` vérifié (D-083).

Même principe que l'extracteur de portefeuille (D-005, D-028) : le LLM recopie, le code vérifie.
1. ``looks_like_triangle`` : le code reconnaît un dossier LIC (triangle en escalier, sans tableau de flux
   « Année 1, Année 2… » d'un état de portefeuille) ;
2. LLM, prompt ``extract_triangle`` → JSON → Pydantic (``TriangleData`` refuse un triangle qui n'est pas en
   escalier) ;
3. **ancrage** : chaque montant, taux et pourcentage doit figurer dans le document ; **unité** écrite (D-081) ;
4. **double lecture** : le code relit lui-même le triangle (lignes « année | valeurs ») et compare cellule par
   cellule ; un désaccord part en validation humaine ;
5. **vraisemblance** : cumul qui recule, facteur de développement démesuré, sinistres ultimes sans rapport avec
   la prime, taux hors de [−2 % ; 25 %] ;
6. une relance du LLM avec la liste des problèmes, puis statut ``ok`` / ``a_verifier`` / ``echec``.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from pydantic import ValidationError

from agents.schemas import TriangleData
from core.llm import LLMClient, LLMError
from core.prompts import load_prompt
from multimodal.documents import DocumentText, parse_number
from multimodal.extract import NumberIndex, Status, _coerce, _validation_messages, unit_evidence

MAX_CORRECTIONS = 1
OPTIONAL_MISSING = {"premiums", "line_of_business", "valuation_date", "confidence_level", "declared_cv", "tail_factor"}
EXTRA_KEYS = ("manquants", "remarques")
_YEAR_ROW = re.compile(r"^\s*((?:19|20)\d{2})\b")
_FLOW_ROW = re.compile(r"^\s*(?:Année|Annee|Période|Periode|Year)\s*\d+\s*\|", re.I | re.M)
_LIC_WORDS = re.compile(r"sinistres\s+survenus|triangle|LIC\b|provision\s+pour\s+sinistres|survenance", re.I)


@dataclass
class ParsedTriangle:
    years: list[str]
    premiums: list[float] | None
    triangle: list[list[float]]


def _cells(line: str) -> list[str]:
    parts = [c.strip() for c in line.split("|")]
    while parts and parts[-1] == "":
        parts.pop()
    return parts


def parse_triangle(doc: DocumentText) -> ParsedTriangle | None:
    """Relecture du triangle par le code : la plus longue suite de lignes « année | nombres » en escalier
    (années consécutives, une valeur de moins à chaque ligne). Une colonne de primes en tête est reconnue
    quand l'escalier commence à n + 1 valeurs. None si aucun escalier d'au moins 3 lignes."""
    lines = doc.text.splitlines()
    best: ParsedTriangle | None = None
    k = 0
    while k < len(lines):
        m = _YEAR_ROW.match(lines[k])
        if not m:
            k += 1
            continue
        rows: list[tuple[str, list[float]]] = []
        j = k
        while j < len(lines) and (mm := _YEAR_ROW.match(lines[j])):
            cells = _cells(lines[j])
            first = cells[0][len(mm.group(1)):].strip() if cells else ""
            raw = ([first] if first else []) + cells[1:]
            vals = [parse_number(c) for c in raw]
            if any(v is None for v in vals) or not vals:
                break
            if rows and int(mm.group(1)) != int(rows[-1][0]) + 1:
                break
            rows.append((mm.group(1), [float(v) for v in vals]))
            j += 1
        n = len(rows)
        if n >= 3:
            lens = [len(v) for _, v in rows]
            for p in (0, 1):
                if all(n - i + p == L for i, L in enumerate(lens)):
                    cand = ParsedTriangle(years=[y for y, _ in rows],
                                          premiums=[v[0] for _, v in rows] if p else None,
                                          triangle=[v[p:] for _, v in rows])
                    if best is None or n > len(best.years):
                        best = cand
                    break
        k = max(j, k + 1)
    return best


def looks_like_triangle(doc: DocumentText) -> bool:
    """Dossier LIC : un triangle en escalier et du vocabulaire de sinistres survenus, sans le tableau de flux
    par période d'un état de portefeuille (un état de portefeuille peut citer un triangle en annexe : dossier
    A du camarade, D-074)."""
    if _FLOW_ROW.search(doc.text):
        return False
    return parse_triangle(doc) is not None and bool(_LIC_WORDS.search(doc.text))


@dataclass
class TriangleResult:
    data: TriangleData | None
    status: Status
    issues: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    remarks: str = ""
    warnings: list[str] = field(default_factory=list)
    corrections: int = 0
    latency_ms: float = 0.0
    first_attempt_issues: list[str] = field(default_factory=list)
    double_read: str = ""                 # « concordante », « divergente », « impossible »
    mode: str = "texte"
    grounding: str = "document"


def _clean(data: dict) -> tuple[dict, list[str], str, list[str]]:
    notes = []
    missing = [str(m) for m in (data.get("manquants") or [])]
    remarks = str(data.get("remarques") or "")
    fields = {k: v for k, v in data.items() if k in TriangleData.model_fields}
    unknown = sorted(set(data) - set(fields) - set(EXTRA_KEYS))
    if unknown:
        notes.append(f"champs inconnus ignorés : {', '.join(unknown)}")
    for k in ("line_of_business", "valuation_date", "confidence_level", "declared_cv", "premiums"):
        if fields.get(k) in (None, "", 0, []):
            fields.pop(k, None)
    if fields.get("tail_factor") in (None, "", 0):
        fields.pop("tail_factor", None)
    for k in ("premiums", "discount_rates", "confidence_level", "declared_cv", "tail_factor"):
        if k in fields:
            fields[k] = _coerce(fields[k])
    for k in ("confidence_level", "declared_cv"):
        v = fields.get(k)
        if isinstance(v, int | float) and not isinstance(v, bool) and 1 < v < 100:
            fields[k] = v / 100
            notes.append(f"{k} : pourcentage converti en décimal")
    if "triangle" in fields and isinstance(fields["triangle"], list):
        fields["triangle"] = [_coerce(r) if isinstance(r, list) else r for r in fields["triangle"]]
    if "origin_years" in fields and isinstance(fields["origin_years"], list):
        fields["origin_years"] = [str(y).strip() for y in fields["origin_years"]]
    return fields, missing, remarks, notes


def grounding_issues(t: TriangleData, idx: NumberIndex) -> list[str]:
    out = []
    for i, row in enumerate(t.triangle):
        for k, v in enumerate(row):
            if not idx.has(v):
                out.append(f"triangle[{t.origin_years[i]}][retard {k + 1}] = {v} introuvable dans le document")
    for i, v in enumerate(t.premiums or []):
        if not idx.has(v):
            out.append(f"premiums[{t.origin_years[i]}] = {v} introuvable dans le document")
    rates = t.discount_rates if isinstance(t.discount_rates, list) else [t.discount_rates]
    for k, r in enumerate(rates):
        if not idx.has(r):
            out.append(f"discount_rates[{k}] = {r} introuvable dans le document")
    for name in ("confidence_level", "declared_cv"):
        v = getattr(t, name)
        if v is not None and not idx.has(v):
            out.append(f"{name} = {v} introuvable dans le document")
    if t.tail_factor != 1.0 and not idx.has(t.tail_factor):
        out.append(f"tail_factor = {t.tail_factor} introuvable dans le document")
    return out


def plausibility_issues(t: TriangleData) -> list[str]:
    out = []
    cum = t.cumulative_triangle()
    for i, row in enumerate(cum):
        for k in range(1, len(row)):
            if row[k - 1] > 0 and row[k] < 0.9 * row[k - 1]:
                out.append(f"{t.origin_years[i]}, retard {k + 1} : le cumul recule de plus de 10 % "
                           f"({row[k - 1]:g} → {row[k]:g}) : incréments lus comme cumuls, ou cellule décalée ?")
    n = len(cum)
    for k in range(n - 1):
        base = sum(cum[i][k] for i in range(n - k - 1))
        if base > 0:
            f = sum(cum[i][k + 1] for i in range(n - k - 1)) / base
            if f > 20:
                out.append(f"facteur de développement {k + 1}→{k + 2} = {f:.1f} : invraisemblable, à vérifier")
    if t.premiums:
        for i, (p, row) in enumerate(zip(t.premiums, cum, strict=True)):
            if p > 0 and row[-1] > 5 * p:
                out.append(f"{t.origin_years[i]} : paiements cumulés ({row[-1]:g}) supérieurs à 5 fois la prime ({p:g})")
    rates = t.discount_rates if isinstance(t.discount_rates, list) else [t.discount_rates]
    for k, r in enumerate(rates):
        if not -0.02 <= r <= 0.25:
            out.append(f"discount_rates[{k}] = {r} hors de [−2 % ; 25 %] : taux invraisemblable")
    return out


def unit_issues(t: TriangleData, doc: DocumentText) -> list[str]:
    names = {1: "unités", 1000: "milliers", 1_000_000: "millions"}
    found = unit_evidence(doc.text)
    m = t.unit_multiplier
    if not found:
        return [] if m == 1 else [f"unit_multiplier = {m:g} ({names[m]}) : aucune mention de cette unité dans le document"]
    if m not in found:
        return [f"unit_multiplier = {m:g} ({names[m]}) alors que le document indique des montants en "
                + " ou ".join(names[u] for u in sorted(found))]
    return []


def compare_with_parsed(t: TriangleData, parsed: ParsedTriangle) -> list[str]:
    """Désaccords entre la lecture du LLM et la relecture du code (au plus 5 listés)."""
    diffs = []
    if [str(y) for y in t.origin_years] != parsed.years:
        diffs.append(f"années de survenance : {', '.join(t.origin_years)} / {', '.join(parsed.years)}")
    else:
        for i, (a, b) in enumerate(zip(t.triangle, parsed.triangle, strict=True)):
            if len(a) != len(b):
                diffs.append(f"{t.origin_years[i]} : {len(a)} valeurs / {len(b)}")
                continue
            diffs += [f"{t.origin_years[i]}, retard {k + 1} : {x:g} / {y:g}"
                      for k, (x, y) in enumerate(zip(a, b, strict=True)) if abs(x - y) > 0.005]
        if t.premiums is not None and parsed.premiums is not None:
            diffs += [f"prime {t.origin_years[i]} : {x:g} / {y:g}"
                      for i, (x, y) in enumerate(zip(t.premiums, parsed.premiums, strict=True)) if abs(x - y) > 0.005]
    return diffs


def extract_triangle(doc: DocumentText, client: LLMClient | None = None, version: int | None = None,
                     case_id: str = "", mode: str = "texte") -> TriangleResult:
    t0 = time.perf_counter()
    spec = load_prompt("extract_triangle", version)
    client = client or LLMClient()
    messages = [{"role": "system", "content": spec.system},
                {"role": "user", "content": spec.render(document=doc.text)}]
    idx = NumberIndex(doc)
    parsed = parse_triangle(doc)
    data: TriangleData | None = None
    raw: dict = {}
    issues: list[str] = []
    first: list[str] = []
    missing: list[str] = []
    remarks = ""
    warnings: list[str] = []
    corrections = 0
    for attempt in range(MAX_CORRECTIONS + 1):
        resp = client.chat(messages, model=spec.params.model, temperature=spec.params.temperature,
                           max_tokens=spec.params.max_tokens, json_mode=True,
                           trace={"agent": "extracteur", "prompt_id": spec.id, "mode": mode,
                                  "prompt_version": spec.version, "case_id": case_id, "attempt": attempt})
        try:
            raw = resp.json()
            if not isinstance(raw, dict):
                raise LLMError("la réponse JSON n'est pas un objet")
        except LLMError as exc:
            raw, data, issues = {}, None, [f"réponse illisible : {exc}"]
        else:
            fields, missing, remarks, warnings = _clean(raw)
            try:
                data = TriangleData(**fields)
                issues = grounding_issues(data, idx) + plausibility_issues(data) + unit_issues(data, doc)
                if parsed is not None:
                    diffs = compare_with_parsed(data, parsed)
                    if diffs:
                        issues.append("double lecture : la relecture du triangle par le code diffère ("
                                      + " ; ".join(diffs[:5]) + (" ; …" if len(diffs) > 5 else "") + ")")
            except ValidationError as exc:
                data, issues = None, _validation_messages(exc)
        if attempt == 0:
            first = issues[:]
        if not issues or attempt == MAX_CORRECTIONS:
            break
        corrections += 1
        messages += [
            {"role": "assistant", "content": json.dumps(raw, ensure_ascii=False)},
            {"role": "user", "content": ("Le contrôle automatique a trouvé ces problèmes :\n- " + "\n- ".join(issues)
                                         + "\nRelis le document et corrige. Ne mets que des valeurs présentes dans le "
                                           "document. Réponds avec le même format JSON.")}]
    # champs facultatifs déclarés absents (pas de colonne de primes, pas de date…) : remarque, pas un blocage ;
    # un taux absent reste bloquant (mesure du 24/10 : lc05 envoyé à un humain pour « premiums » absent)
    optional = [m for m in missing if m in OPTIONAL_MISSING]
    if optional:
        warnings.append("non indiqué dans le document : " + ", ".join(optional))
        missing = [m for m in missing if m not in OPTIONAL_MISSING]
    if data is not None and data.line_of_business:
        norm = lambda s: "".join(ch for ch in s.upper() if ch.isalnum())     # noqa: E731
        if norm(data.line_of_business) not in norm(doc.text):
            warnings.append(f"branche « {data.line_of_business} » introuvable dans le document : ignorée")
            data = data.model_copy(update={"line_of_business": None})
    issues += [p for p in doc.problems if p not in issues]
    warnings += [n for n in doc.notes if n not in warnings]
    double = ("impossible" if parsed is None or data is None else
              "divergente" if any(i.startswith("double lecture") for i in issues) else "concordante")
    if parsed is None and data is not None:
        warnings.append("relecture du triangle par le code impossible (mise en page non reconnue) : ancrage seul")
    status: Status = "echec" if data is None else ("a_verifier" if issues or missing or doc.truncated else "ok")
    if doc.truncated:
        issues.append(f"document tronqué : seules les premières pages ont été lues ({doc.pages} pages)")
    return TriangleResult(data=data, status=status, issues=issues, missing=missing, remarks=remarks,
                          warnings=warnings, corrections=corrections,
                          latency_ms=round((time.perf_counter() - t0) * 1000, 1), first_attempt_issues=first,
                          double_read=double, mode=mode)
