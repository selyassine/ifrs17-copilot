"""Agent Extracteur : document client → ``PortfolioData`` vérifié.

Étapes (mode « texte », PDF à couche texte) :
1. ``documents.pdf_text`` : texte + tableaux cellule par cellule ;
2. LLM avec le prompt ``extract_portfolio`` → JSON ;
3. validation Pydantic (listes de même longueur, montants positifs, unités > 0…) ;
4. **contrôle d'ancrage par le code** : chaque chiffre extrait doit figurer dans le document
   (les sorties peuvent être la somme de deux montants : sinistres + frais). Un chiffre absent
   du document est une hallucination ou une erreur de lecture ;
5. si la validation ou l'ancrage échoue : **une** relance du LLM avec la liste des erreurs ;
6. statut : ``ok`` (tout est ancré, rien ne manque) → le calcul peut partir ; ``a_verifier``
   → un humain valide dans n8n avant le calcul ; ``echec`` → pas de données exploitables.

Le LLM ne calcule jamais le CSM : il ne fait que recopier (D-005). La seule addition qu'il fait
(sinistres + frais) est revérifiée par le code.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from itertools import combinations
from typing import Literal

from pydantic import ValidationError

from agents.schemas import PortfolioData
from core.llm import LLMClient, LLMError
from core.prompts import load_prompt
from multimodal.documents import DocumentText, document_numbers, parse_number

MAX_CORRECTIONS = 1
EXTRA_KEYS = ("manquants", "remarques")
Status = Literal["ok", "a_verifier", "echec"]


@dataclass
class ExtractionResult:
    portfolio: PortfolioData | None
    status: Status
    issues: list[str] = field(default_factory=list)       # problèmes détectés par le code
    missing: list[str] = field(default_factory=list)      # champs déclarés absents par le LLM
    remarks: str = ""
    warnings: list[str] = field(default_factory=list)     # conversions faites par le code
    corrections: int = 0
    latency_ms: float = 0.0
    first_attempt_issues: list[str] = field(default_factory=list)   # pour l'évaluation


# --------------------------------------------------------------------------- #
# Contrôle d'ancrage
# --------------------------------------------------------------------------- #
class NumberIndex:
    """Nombres du document, plus les sommes de deux montants du tableau (sinistres + frais)."""

    def __init__(self, doc: DocumentText):
        nums = document_numbers(doc)
        self.values4 = {round(v, 4) for v in nums}
        self.values2 = {round(v, 2) for v in nums}
        # sinistres + frais : sommes des montants du tableau (ou du texte s'il n'y a pas de tableau)
        source = doc.table_numbers or doc.text_numbers
        table = sorted({round(v, 2) for v in source if v > 0})
        self.pair_sums = {round(a + b, 2) for a, b in combinations(table, 2)} | \
                         {round(2 * a, 2) for a in table}

    def has(self, v: float, allow_sum: bool = False) -> bool:
        if v == 0:
            return True                    # cellule vide, « — », « 0,00 »
        if round(v, 4) in self.values4 or (abs(v) >= 1 and round(v, 2) in self.values2):
            return True
        # somme de deux montants arrondis : tolérance d'un centime
        return allow_sum and any(round(v + d, 2) in self.pair_sums for d in (0, 0.01, -0.01))


def grounding_issues(p: PortfolioData, idx: NumberIndex) -> list[str]:
    issues = []
    checks = [("premiums", p.premiums, False), ("outflows", p.outflows, True),
              ("coverage_units", p.coverage_units, False)]
    rates = p.discount_rates if isinstance(p.discount_rates, list) else [p.discount_rates]
    checks.append(("discount_rates", rates, False))
    checks.append(("risk_adjustment_pct", [p.risk_adjustment_pct], False))
    for name, values, allow_sum in checks:
        for k, v in enumerate(values):
            if not idx.has(v, allow_sum):
                where = f"{name}[{k}]" if len(values) > 1 else name
                how = " (ni comme somme de deux montants du tableau)" if allow_sum else ""
                issues.append(f"{where} = {v} introuvable dans le document{how}")
    return issues


# --------------------------------------------------------------------------- #
# Nettoyage de la sortie du LLM
# --------------------------------------------------------------------------- #
def _coerce(value):
    """Tolère « 1 234,5 » ou « 2,5 % » renvoyés en texte par le LLM (signalé, pas silencieux)."""
    if isinstance(value, str):
        v = parse_number(value)
        if v is not None:
            return v / 100 if value.strip().endswith("%") else v
    if isinstance(value, list):
        return [_coerce(x) for x in value]
    return value


def clean(data: dict) -> tuple[dict, list[str], str, list[str]]:
    notes = []
    missing = [str(m) for m in (data.get("manquants") or [])]
    remarks = str(data.get("remarques") or "")
    fields = {k: v for k, v in data.items() if k not in EXTRA_KEYS and k in PortfolioData.model_fields}
    unknown = sorted(set(data) - set(fields) - set(EXTRA_KEYS))
    if unknown:
        notes.append(f"champs inconnus ignorés : {', '.join(unknown)}")
    for k in ("premiums", "outflows", "coverage_units", "discount_rates", "risk_adjustment_pct",
              "future_service_adjustments"):
        if k in fields:
            coerced = _coerce(fields[k])
            if coerced != fields[k]:
                notes.append(f"{k} : nombres en texte convertis")
            fields[k] = coerced
    return fields, missing, remarks, notes


def _validation_messages(exc: ValidationError) -> list[str]:
    return [f"{'.'.join(str(x) for x in e['loc']) or 'données'} : {e['msg']}" for e in exc.errors()]


# --------------------------------------------------------------------------- #
# Agent
# --------------------------------------------------------------------------- #
def extract_from_text(doc: DocumentText, client: LLMClient | None = None, version: int | None = None,
                      case_id: str = "") -> ExtractionResult:
    t0 = time.perf_counter()
    client = client or LLMClient()
    spec = load_prompt("extract_portfolio", version)
    idx = NumberIndex(doc)
    messages = [{"role": "system", "content": spec.system},
                {"role": "user", "content": spec.render(document=doc.text)}]

    portfolio: PortfolioData | None = None
    issues: list[str] = []
    first: list[str] = []
    missing: list[str] = []
    remarks = ""
    warnings: list[str] = []
    corrections = 0
    data: dict = {}
    for attempt in range(MAX_CORRECTIONS + 1):
        resp = client.chat(messages, model=spec.params.model, temperature=spec.params.temperature,
                           max_tokens=spec.params.max_tokens, json_mode=True,
                           trace={"agent": "extracteur", "prompt_id": spec.id,
                                  "prompt_version": spec.version, "case_id": case_id,
                                  "attempt": attempt})
        try:
            data = resp.json()
            if not isinstance(data, dict):
                raise LLMError("la réponse JSON n'est pas un objet")
        except LLMError as exc:
            data, portfolio, issues = {}, None, [f"réponse illisible : {exc}"]
        else:
            fields, missing, remarks, warnings = clean(data)
            try:
                portfolio = PortfolioData(**fields)
                issues = grounding_issues(portfolio, idx)
            except ValidationError as exc:
                portfolio = None
                issues = _validation_messages(exc)
        if attempt == 0:
            first = issues[:]
        if not issues or attempt == MAX_CORRECTIONS:
            break
        corrections += 1
        messages += [
            {"role": "assistant", "content": json.dumps(data, ensure_ascii=False)},
            {"role": "user", "content": (
                "Le contrôle automatique a trouvé ces problèmes :\n- " + "\n- ".join(issues)
                + "\nRelis le document et corrige. Ne mets que des valeurs présentes dans le document "
                  "(seules les sorties peuvent être une somme sinistres + frais). "
                  "Réponds avec le même format JSON.")},
        ]

    if portfolio is None:
        status: Status = "echec"
    elif issues or missing or doc.truncated:
        status = "a_verifier"
    else:
        status = "ok"
    if doc.truncated:
        issues.append(f"document tronqué : seules les premières pages ont été lues ({doc.pages} pages)")
    return ExtractionResult(portfolio=portfolio, status=status, issues=issues, missing=missing,
                            remarks=remarks, warnings=warnings, corrections=corrections,
                            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                            first_attempt_issues=first)
