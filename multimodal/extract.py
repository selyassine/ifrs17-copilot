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
import re
import time
from dataclasses import dataclass, field
from itertools import combinations
from typing import Literal

from pydantic import ValidationError

from agents.schemas import PortfolioData
from core.llm import LLMClient, LLMError
from core.prompts import load_prompt
from multimodal.documents import DocumentText, document_numbers, numbers_in_text, parse_number

MAX_CORRECTIONS = 1
EXTRA_KEYS = ("manquants", "remarques", "transcription", "groupes_detectes")
COMPARED = ("group_id", "currency", "unit_multiplier", "premiums", "outflows", "recoveries", "acquisition_costs",
            "coverage_units", "discount_rates", "risk_adjustment_pct")
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
    mode: str = "texte"                                   # texte | vision | hybride
    grounding: str = "document"                           # document | transcription
    groups: list[str] = field(default_factory=list)      # groupes vus dans le document
    reads: int = 1                                        # 2 = double lecture (mode vision)
    provenance: dict[str, str] = field(default_factory=dict)   # champ → page et tableau où il a été lu (D-067)


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
        table = sorted({round(v, 6) for v in source if v > 0})
        pairs = [a + b for a, b in combinations(table, 2)] + [2 * a for a in table]
        self.pair_sums4 = {round(x, 4) for x in pairs}          # exact (montants en millions…)
        self.pair_sums = {round(x, 2) for x in pairs}           # à un centime près

    def has(self, v: float, allow_sum: bool = False) -> bool:
        if v == 0:
            return True                    # cellule vide, « — », « 0,00 »
        if round(v, 4) in self.values4 or (abs(v) >= 1 and round(v, 2) in self.values2):
            return True
        # somme de deux montants arrondis : tolérance d'un centime
        if not allow_sum:
            return False
        if round(v, 4) in self.pair_sums4:
            return True
        return abs(v) >= 1 and any(round(v + d, 2) in self.pair_sums for d in (0, 0.01, -0.01))


FIELD_LABELS = {"premiums": "Primes", "outflows": "Sinistres et frais", "recoveries": "Recouvrements",
                "acquisition_costs": "Frais d'acquisition", "declared_cv": "Volatilité déclarée (RA)",
                "declared_confidence": "Niveau de confiance déclaré (RA)",
                "coverage_units": "Unités de couverture",
                "discount_rates": "Taux d'actualisation", "risk_adjustment_pct": "Ajustement pour risque"}


def provenance(p: PortfolioData, doc: DocumentText) -> dict[str, str]:
    """Pour chaque donnée extraite, la page et le tableau (ou le texte) où le code l'a retrouvée (D-067).
    Les sorties lues comme « sinistres + frais » sont signalées comme une somme de deux colonnes."""
    rates = p.discount_rates if isinstance(p.discount_rates, list) else [p.discount_rates]
    values = {"premiums": p.premiums, "outflows": p.outflows, "recoveries": p.recoveries or [],
              "acquisition_costs": p.acquisition_costs or [],
              "coverage_units": p.coverage_units,
              "discount_rates": rates, "risk_adjustment_pct": [p.risk_adjustment_pct]}
    for name in ("declared_cv", "declared_confidence"):
        if getattr(p, name) is not None:
            values[name] = [getattr(p, name)]
    out = {}
    for name, vals in values.items():
        places: set[str] = set()
        summed = False
        for v in vals:
            if v == 0:
                continue
            where = doc.where(v) | (doc.where(-v) if name == "recoveries" else set())
            if where:
                places |= where
            elif name == "outflows":
                summed = True
        if not places and not summed:
            continue
        if summed and not places:
            places = {loc for loc in set().union(*doc.locations.values()) if "tableau" in loc}
        text = " ; ".join(sorted(places))
        out[FIELD_LABELS[name]] = text + (" (somme de deux colonnes : sinistres + frais)" if summed else "")
    return out


def grounding_issues(p: PortfolioData, idx: NumberIndex) -> list[str]:
    issues = []
    checks = [("premiums", p.premiums, False), ("outflows", p.outflows, True),
              ("coverage_units", p.coverage_units, False)]
    rates = p.discount_rates if isinstance(p.discount_rates, list) else [p.discount_rates]
    checks.append(("discount_rates", rates, False))
    checks.append(("risk_adjustment_pct", [p.risk_adjustment_pct], False))
    if p.recoveries:
        checks.append(("recoveries", p.recoveries, False))
    if p.acquisition_costs:
        checks.append(("acquisition_costs", p.acquisition_costs, False))
    for name in ("declared_cv", "declared_confidence"):           # D-082
        if getattr(p, name) is not None:
            checks.append((name, [getattr(p, name)], False))
    for name, values, allow_sum in checks:
        for k, v in enumerate(values):
            # un recouvrement peut être affiché comme un paiement négatif (« -12,00 ») : B65 k, D-071
            found = idx.has(v, allow_sum) or (name == "recoveries" and idx.has(-v))
            if not found:
                where = f"{name}[{k}]" if len(values) > 1 else name
                how = " (ni comme somme de deux montants du tableau)" if allow_sum else ""
                issues.append(f"{where} = {v} introuvable dans le document{how}")
    return issues


SPIKE = 30.0          # une période vaut plus de 30 fois la plus grande des autres : invraisemblable (D-080)


def plausibility_issues(p: PortfolioData) -> list[str]:
    """Contrôle de vraisemblance (D-080). L'ancrage vérifie qu'un chiffre EXISTE dans le document ; il ne voit pas
    un chiffre aberrant que le document affiche bel et bien (cellule mal formatée « 6 424 107 % », ligne de total
    prise pour une période, colonne décalée). Seuils réglés sur les données : aucune alerte sur les jeux de test
    (synthétiques, pièges, tableurs, dossiers prospectifs, script R) et 0,4 % sur 5 055 cohortes réelles CAS, qui
    sont de vraies anomalies de la source (prime presque nulle, paiement isolé démesuré)."""
    out = []
    for name, values in (("premiums", p.premiums), ("outflows", p.outflows), ("coverage_units", p.coverage_units),
                         ("recoveries", p.recoveries or []), ("acquisition_costs", p.acquisition_costs or [])):
        if sum(1 for v in values if v > 0) < 3:
            continue
        for k, v in enumerate(values):
            others = [w for j, w in enumerate(values) if j != k and w > 0]
            if others and v > SPIKE * max(others):
                out.append(f"{name}[{k}] = {v} vaut plus de {SPIKE:.0f} fois la plus grande des autres périodes "
                           f"({max(others):.2f}) : valeur invraisemblable, à vérifier dans le document")
    rates = p.discount_rates if isinstance(p.discount_rates, list) else [p.discount_rates]
    for k, r in enumerate(rates):
        if not -0.02 <= r <= 0.25:
            where = f"discount_rates[{k}]" if len(rates) > 1 else "discount_rates"
            out.append(f"{where} = {r} hors de [−2 % ; 25 %] : taux invraisemblable (pourcentage lu deux fois ?)")
    if p.risk_adjustment_pct > 0.5:
        out.append(f"risk_adjustment_pct = {p.risk_adjustment_pct} : ajustement pour risque supérieur à 50 % des sorties")
    if sum(p.premiums) > 0 and sum(p.outflows) > 50 * sum(p.premiums):
        out.append("sorties totales supérieures à 50 fois les primes : unité ou colonne à vérifier")
    return out


# --------------------------------------------------------------------------- #
# Ancrage de l'unité des montants (D-081)
# --------------------------------------------------------------------------- #
_CUR = r"(?:€|\$|eur|usd|tnd|mad|dt|chf|gbp|xof)"
_UNIT_PATTERNS: dict[int, list[re.Pattern]] = {
    1_000: [re.compile(p, re.I) for p in (
        r"\ben\W{0,4}milliers\b",                                   # « en milliers », « Montants en | milliers »
        r"\bmilliers\s+(?:d'|d’|de\s+)(?:euros?|dollars|dinars|dirhams|francs|" + _CUR[3:-1] + r")",
        r"(?<![a-z])k\s?" + _CUR + r"(?![a-z])",                    # k€, k$, kEUR, K USD
        r"\(\s*'?000\s*\)|'000\b|\b000s\b",                         # (000), '000
        r"\bin\s+thousands\b|\bthousands\s+of\b")],
    1_000_000: [re.compile(p, re.I) for p in (
        r"\ben\W{0,4}millions\b",
        r"\bmillions\s+(?:d'|d’|de\s+)(?:euros?|dollars|dinars|dirhams|francs|" + _CUR[3:-1] + r")",
        r"(?<![a-z])m\s?€|\bM(?:EUR|USD|TND|MAD|DT)\b|\bmn\s?" + _CUR,
        r"\bin\s+millions\b|\bmillions\s+of\b")],
    1: [re.compile(p, re.I) for p in (
        r"\ben\W{0,4}unités\b(?!\s+de\s+couverture)",               # « en unités (dollars) »
        r"\ben\s+(?:euros?|dollars|dinars|dirhams|francs)\b",       # « Montants en euros »
        r"\bmontants?\s+en\s+" + _CUR + r"(?![a-z])")],
}
_UNIT_NAMES = {1: "unités", 1_000: "milliers", 1_000_000: "millions"}


def unit_evidence(text: str) -> set[int]:
    """Unités de montant écrites dans un texte : {1, 1000, 1000000} selon les mentions trouvées."""
    return {m for m, pats in _UNIT_PATTERNS.items() if any(p.search(text) for p in pats)}


def _group_section(text: str, group: str) -> str:
    """Partie du texte qui décrit un groupe : de sa première mention jusqu'au groupe suivant (D-078)."""
    lines = text.splitlines()
    key = _norm_group(group)
    start = next((k for k, ln in enumerate(lines) if key and key in _norm_group(ln)), None)
    if start is None:
        return ""
    end = next((k for k in range(start + 1, len(lines))
                if re.search(r"groupe\s+de\s+contrats", lines[k], re.I)), len(lines))
    return "\n".join(lines[start:end])


def unit_issues(p: PortfolioData, doc: DocumentText) -> list[str]:
    """D-081. Une erreur d'unité multiplie la CSM par 1 000 sans changer aucun chiffre du tableau : l'ancrage
    ne la voit pas. Le multiplicateur lu par le LLM doit donc être écrit dans le document (« en milliers »,
    « k€ », « (000) »…), de préférence dans la partie du groupe saisi ; un document muet sur l'unité est lu en
    unités."""
    m = p.unit_multiplier
    found = unit_evidence(_group_section(doc.text, p.group_id)) or unit_evidence(doc.text)
    if not found:
        return [] if m == 1 else [f"unit_multiplier = {m:g} ({_UNIT_NAMES[m]}) : aucune mention de cette unité "
                                  "dans le document, à vérifier"]
    if m not in found:
        said = " ou ".join(_UNIT_NAMES[u] for u in sorted(found))
        return [f"unit_multiplier = {m:g} ({_UNIT_NAMES[m]}) alors que le document indique des montants en {said} : "
                "unité à vérifier"]
    return []


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
    if "recoveries" in fields:
        rec = _coerce(fields["recoveries"])
        if rec is None or rec == [] or (isinstance(rec, list) and all(x in (0, None) for x in rec)):
            fields.pop("recoveries")                  # « aucun recouvrement » : champ absent
        elif isinstance(rec, list) and any(isinstance(x, int | float) and x < 0 for x in rec):
            rec = [abs(x) if isinstance(x, int | float) else x for x in rec]
            notes.append("recoveries : montants négatifs convertis en recouvrements positifs")
            fields["recoveries"] = rec
        else:
            fields["recoveries"] = rec
    if "acquisition_costs" in fields:
        acq = _coerce(fields["acquisition_costs"])
        if not isinstance(acq, list) or all(x in (0, None) for x in acq):
            fields.pop("acquisition_costs")           # « aucun frais d'acquisition » : champ absent
        else:
            fields["acquisition_costs"] = acq
    for k in ("coverage_months", "line_of_business", "declared_cv", "declared_confidence"):
        if fields.get(k) in (None, "", 0):
            fields.pop(k, None)
    for k in ("declared_cv", "declared_confidence"):
        if k in fields:
            v = _coerce(fields[k])
            if isinstance(v, int | float) and not isinstance(v, bool) and 1 < v < 100:
                v = v / 100                               # « 12 » au lieu de 0.12 : signalé, pas silencieux
                notes.append(f"{k} : pourcentage converti en décimal")
            fields[k] = v
    if "coverage_months" in fields:
        try:
            fields["coverage_months"] = int(round(float(_coerce(fields["coverage_months"]))))
        except (TypeError, ValueError):
            notes.append(f"coverage_months illisible ({fields['coverage_months']!r}) : ignoré")
            fields.pop("coverage_months")
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
def transcription_doc(data: dict) -> DocumentText:
    """Mode vision : le modèle recopie aussi le tableau tel qu'il le lit (« transcription »).
    Les chiffres structurés sont ensuite ancrés sur cette transcription : on vérifie que le
    modèle n'a rien inventé ni mal additionné par rapport à sa propre lecture. Contrôle plus
    faible que l'ancrage sur la couche texte (une erreur de lecture recopiée des deux côtés passe)."""
    rows = data.get("transcription") or []
    if isinstance(rows, str):
        rows = rows.splitlines()
    table: list[float] = []
    prose: list[str] = []
    for row in map(str, rows):
        if "|" in row:
            for cell in row.split("|"):
                v = parse_number(cell)
                if v is not None:
                    table += [v, v / 100] if "%" in cell else [v]
        else:
            prose.append(row)
    # phrases lues d'un bloc : « 7,50 » en fin de ligne et « % » au début de la suivante
    return DocumentText(text="\n".join(map(str, rows)), table_numbers=table,
                        text_numbers=numbers_in_text("\n".join(prose)))


def _render(spec, document: str, target_group: str | None) -> str:
    """Texte du message : le document, puis la consigne de groupe (D-078) si le code en demande un."""
    ask = (f"Groupe à saisir : {target_group} (saisis ce groupe et lui seul)." if target_group else "")
    if "groupe_demande" in spec.variables():
        return spec.render(document=document, groupe_demande=ask)
    return spec.render(document=document) + (f"\n{ask}" if ask else "")


def _norm_group(g: str) -> str:
    return "".join(ch for ch in str(g).upper() if ch.isalnum())


def _run(spec, user_content, client: LLMClient, case_id: str, mode: str,
         fixed_doc: DocumentText | None, target_group: str | None = None) -> ExtractionResult:
    """Boucle commune : appel → nettoyage → validation → ancrage → une relance au besoin.
    ``fixed_doc`` : couche texte du PDF (ancrage fort) ; None : ancrage sur la transcription."""
    t0 = time.perf_counter()
    messages = [{"role": "system", "content": spec.system}, {"role": "user", "content": user_content}]
    portfolio: PortfolioData | None = None
    issues: list[str] = []
    first: list[str] = []
    missing: list[str] = []
    remarks = ""
    warnings: list[str] = []
    corrections = 0
    data: dict = {}
    fixed_idx = NumberIndex(fixed_doc) if fixed_doc is not None else None
    for attempt in range(MAX_CORRECTIONS + 1):
        resp = client.chat(messages, model=spec.params.model, temperature=spec.params.temperature,
                           max_tokens=spec.params.max_tokens, json_mode=True,
                           trace={"agent": "extracteur", "prompt_id": spec.id, "mode": mode,
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
                idx = fixed_idx
                unit_doc = fixed_doc
                if idx is None:
                    tdoc = unit_doc = transcription_doc(data)
                    if len(tdoc.table_numbers) + len(tdoc.text_numbers) < 3:
                        issues = ["transcription du tableau absente : impossible de vérifier les chiffres"]
                        idx = None
                    else:
                        idx = NumberIndex(tdoc)
                if idx is not None:
                    issues = grounding_issues(portfolio, idx)
                issues += plausibility_issues(portfolio)
                if idx is not None:
                    issues += unit_issues(portfolio, unit_doc)      # vision : sur la transcription (plus faible)
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

    groups = sorted({str(g).strip() for g in (data.get("groupes_detectes") or []) if str(g).strip()})
    # la branche choisit la volatilité du RA : elle doit être écrite dans le document (sinon ignorée)
    if (portfolio is not None and portfolio.line_of_business and fixed_doc is not None
            and _norm_group(portfolio.line_of_business) not in _norm_group(fixed_doc.text)):
        warnings.append(f"branche « {portfolio.line_of_business} » introuvable dans le document : ignorée")
        portfolio = portfolio.model_copy(update={"line_of_business": None})
    if target_group is not None:
        if portfolio is not None and _norm_group(portfolio.group_id) != _norm_group(target_group):
            issues.append(f"groupe saisi « {portfolio.group_id} » au lieu du groupe demandé « {target_group} »")
    elif portfolio is not None and len(groups) > 1:
        # plusieurs groupes : le modèle ne doit pas choisir à la place de l'utilisateur (D-032)
        issues.append(f"plusieurs groupes de contrats dans le document ({', '.join(groups)}) : "
                      "choisir le groupe à calculer")
    if fixed_doc is not None:
        # tableur (D-079) : une formule sans valeur est une donnée inconnue ; une feuille cachée est signalée
        issues += [p for p in fixed_doc.problems if p not in issues]
        warnings += [n for n in fixed_doc.notes if n not in warnings]
    truncated = fixed_doc is not None and fixed_doc.truncated
    if portfolio is None:
        status: Status = "echec"
    elif issues or missing or truncated:
        status = "a_verifier"
    else:
        status = "ok"
    if truncated:
        issues.append(f"document tronqué : seules les premières pages ont été lues ({fixed_doc.pages} pages)")
    return ExtractionResult(portfolio=portfolio, status=status, issues=issues, missing=missing,
                            remarks=remarks, warnings=warnings, corrections=corrections,
                            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                            first_attempt_issues=first, mode=mode,
                            grounding="document" if fixed_doc is not None else "transcription",
                            groups=groups,
                            provenance=provenance(portfolio, fixed_doc) if portfolio is not None and fixed_doc is not None else {})


def extract_from_text(doc: DocumentText, client: LLMClient | None = None, version: int | None = None,
                      case_id: str = "", target_group: str | None = None, mode: str = "texte") -> ExtractionResult:
    """Mode texte : PDF à couche texte → LLM texte (Groq). Ancrage sur la couche texte.
    ``target_group`` : document à plusieurs groupes, un appel par groupe (D-078)."""
    spec = load_prompt("extract_portfolio", version)
    return _run(spec, _render(spec, doc.text, target_group), client or LLMClient(), case_id, mode, doc,
                target_group)


def compare_portfolios(a: PortfolioData, b: PortfolioData) -> list[str]:
    """Champs sur lesquels deux lectures du même document ne sont pas d'accord."""
    diffs = []
    da, db = a.model_dump(), b.model_dump()
    for d, p in ((da, a), (db, b)):              # « pas de recouvrement » = des zéros
        if d.get("recoveries") is None:
            d["recoveries"] = [0.0] * p.n_periods
    for f in COMPARED:
        x, y = da[f], db[f]
        tol = 1e-6 if f in ("discount_rates", "risk_adjustment_pct") else 0.011
        if isinstance(x, list) != isinstance(y, list):
            diffs.append(f"{f} : {x} / {y}")
        elif isinstance(x, list):
            if len(x) != len(y):
                diffs.append(f"{f} : {len(x)} périodes / {len(y)}")
            else:
                diffs += [f"{f}[{k}] : {u} / {v}" for k, (u, v) in enumerate(zip(x, y, strict=True))
                          if abs(u - v) > tol]
        elif isinstance(x, int | float) and not isinstance(x, bool):
            if abs(x - y) > tol:
                diffs.append(f"{f} : {x} / {y}")
        elif str(x).strip().upper() != str(y).strip().upper():
            diffs.append(f"{f} : {x} / {y}")
    return diffs


def extract_from_images(images: list[tuple[bytes, str]], client: LLMClient,
                        doc: DocumentText | None = None, version: int | None = None,
                        case_id: str = "", double_read: bool = True,
                        target_group: str | None = None) -> ExtractionResult:
    """Mode vision (images seules, ex. scan) ou hybride (images + couche texte du PDF).

    Hybride : ancrage sur la couche texte. Vision : ancrage sur la transcription du modèle, puis
    **double lecture** (self-consistency, D-032) : une seconde lecture de l'image nettoyée
    (contraste, netteté) ; si les deux lectures divergent, validation humaine. La transcription
    seule ne voit pas un chiffre mal lu des deux côtés ; deux lectures indépendantes, souvent si."""
    from multimodal.vision import enhance_variant, image_part

    spec = load_prompt("extract_portfolio_vision", version)
    text = doc.text if doc is not None else "(aucune couche texte : lire uniquement l'image)"

    def content(imgs):
        return [{"type": "text", "text": _render(spec, text, target_group)}] + [image_part(d, m) for d, m in imgs]

    mode = "hybride" if doc is not None else "vision"
    first = _run(spec, content(images), client, case_id, mode, doc, target_group)
    if doc is not None or not double_read or first.portfolio is None:
        return first
    second = _run(spec, content([enhance_variant(d) for d, _ in images]), client, case_id, mode, None, target_group)
    first.reads = 2
    first.corrections += second.corrections
    first.latency_ms = round(first.latency_ms + second.latency_ms, 1)
    if second.portfolio is None:
        first.issues.append("seconde lecture de l'image impossible : vérification humaine")
    else:
        diffs = compare_portfolios(first.portfolio, second.portfolio)
        if diffs:
            first.issues.append("les deux lectures de l'image divergent : " + " ; ".join(diffs[:8]))
    if first.issues and first.status == "ok":
        first.status = "a_verifier"
    return first
