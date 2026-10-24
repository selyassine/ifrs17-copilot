"""Rendu de la note actuarielle IFRS 17 (D-055) : HTML imprimable (A4, PDF) et Markdown.

Tout ce module est déterministe : il met en page des chiffres calculés par ``engine/`` et deux
textes du LLM déjà contrôlés par ``agents/writer.py``. Structure :

    page de garde · sommaire
    1. Résumé exécutif            6. Évolution de la CSM
    2. Objet, périmètre, méthode  7. Projection : compte de résultat et passif
    3. Données en entrée          8. Sensibilités
    4. Hypothèses                 9. Fondements dans la norme
    5. Évaluation initiale        10. Contrôles, limites et validation
    annexes : A. traçabilité · B. glossaire

Le HTML est autonome (aucune ressource externe) : il part tel quel par e-mail (n8n), s'affiche
dans le site et s'imprime en PDF depuis le navigateur (feuille de style @page A4).
"""

from __future__ import annotations

import html
import re

from agents.schemas import CsmResult, PortfolioData
from agents.writer import NormPoint, NoteContext, fr, unit_label
from agents.writer import pct as _pct
from engine.analysis import (
    Projection,
    SensitivityReport,
    csm_movements,
    macaulay_duration,
    margin_ratio,
)
from engine.csm import acquisition_costs, discount_factors
from engine.paa import PaaView
from engine.risk import ConfidenceReport, declared_risk_check, ra_at_level

MINUS = "\u2212"
NBSP = "\u00a0"


def pct(x: float, d: int = 2) -> str:
    """Pourcentage affiché : espace insécable avant %, vrai signe moins."""
    return _pct(x, d).replace(" %", NBSP + "%").replace("-", MINUS)


def num(x: float, d: int = 2) -> str:
    """Montant affiché : espace pour les milliers, virgule décimale, vrai signe moins."""
    v = round(x, d)
    if v == 0:
        return fr(0, d)
    return (MINUS if v < 0 else "") + fr(abs(v), d)


def snum(x: float, d: int = 2) -> str:
    """Variation signée : +1 234,56 ou −1 234,56."""
    v = round(x, d)
    return fr(0, d) if v == 0 else ("+" if v > 0 else MINUS) + fr(abs(v), d)


def esc(s: object) -> str:
    return html.escape(str(s))


def _rates(p: PortfolioData) -> list[float]:
    return p.discount_rates if isinstance(p.discount_rates, list) else [p.discount_rates] * p.n_periods


GLOSSARY = [
    ("BBA", "Building Block Approach, modèle général d'évaluation d'IFRS 17."),
    ("BEL", "Best Estimate of Liabilities : valeur actuelle des sorties futures moins celle des entrées futures."),
    ("CSM", "Marge sur services contractuels : profit non acquis, reconnu au fil des services rendus."),
    ("FCF", "Flux de trésorerie d'exécution : BEL plus ajustement au titre du risque non financier."),
    ("LC", "Composante de perte : part du passif d'un groupe déficitaire qui a déjà été passée en perte."),
    ("LIC", "Passif au titre des sinistres survenus."),
    ("LRC", "Passif au titre de la couverture restante."),
    ("PAA", "Premium Allocation Approach, méthode simplifiée d'affectation des primes."),
    ("RA", "Ajustement au titre du risque non financier."),
    ("Unités de couverture", "Mesure du service rendu par période, qui règle la libération de la CSM."),
]

CSS = """
:root{--ink:#18212c;--muted:#5b6573;--rule:#d5dbe3;--soft:#f3f5f8;--accent:#1f3a5f;--ok:#1d6b45;--warn:#8a5300;--neg:#a3271f}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:var(--ink);font:14px/1.55 "Segoe UI",system-ui,-apple-system,Roboto,Helvetica,Arial,sans-serif}
.page{max-width:820px;margin:0 auto;padding:40px 44px 56px}
h1,h2,h3{font-family:Georgia,"Times New Roman",serif;color:var(--accent);font-weight:600;line-height:1.25}
h1{font-size:30px;margin:6px 0 4px}
h2{font-size:20px;margin:38px 0 10px;padding-bottom:6px;border-bottom:2px solid var(--accent)}
h3{font-size:15.5px;margin:22px 0 6px}
p{margin:8px 0}
.kicker{color:var(--muted);font-size:13px;margin:0}
.subtitle{color:var(--muted);font-size:15px;margin:0 0 22px}
.cover{border-top:6px solid var(--accent);padding-top:22px}
dl.meta{display:grid;grid-template-columns:200px 1fr;gap:6px 18px;margin:18px 0;padding:16px 18px;background:var(--soft);border-radius:6px}
dl.meta dt{color:var(--muted)}
dl.meta dd{margin:0;font-weight:500}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12.5px;font-weight:600;border:1px solid}
.badge.ok{color:var(--ok);border-color:var(--ok);background:#e9f4ee}
.badge.warn{color:var(--warn);border-color:var(--warn);background:#fbf1e1}
nav.toc ol{columns:2;column-gap:32px;padding-left:20px;margin:6px 0}
nav.toc a{color:var(--ink);text-decoration:none}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0 6px}
.kpi{border:1px solid var(--rule);border-radius:6px;padding:10px 12px}
.kpi .v{font-size:19px;font-weight:650;font-variant-numeric:tabular-nums;margin-top:2px}
.kpi .l{color:var(--muted);font-size:12.5px;line-height:1.35}
.kpi.neg .v{color:var(--neg)}
table{border-collapse:collapse;width:100%;margin:10px 0;font-size:13px;font-variant-numeric:tabular-nums}
th,td{padding:5px 8px;border-bottom:1px solid var(--rule);text-align:right;vertical-align:top}
td:not(.l){white-space:nowrap}
th{background:var(--soft);color:var(--accent);font-weight:600;border-bottom:1px solid #b9c3cf}
th:first-child,td:first-child{text-align:left}
td.l,th.l{text-align:left}
tr.total td{font-weight:650;border-top:1.5px solid var(--ink);border-bottom:none}
tr.sub td{color:var(--muted);font-size:12.5px}
tr.sub td:first-child{padding-left:20px}
tr.hl td{background:#eef3f9;font-weight:600}
.neg{color:var(--neg)}
.note{color:var(--muted);font-size:12.5px}
.callout{border-left:3px solid var(--accent);background:var(--soft);padding:10px 14px;margin:12px 0}
.callout.warn{border-color:var(--warn);background:#fbf4e8}
blockquote{margin:6px 0 6px 0;padding:6px 12px;border-left:3px solid var(--rule);color:#3c4652;font-size:13px}
.qa{margin:12px 0 16px}
.qa .q{font-weight:600}
figure{margin:12px 0}
figcaption{color:var(--muted);font-size:12.5px;margin-top:2px}
svg{max-width:100%;height:auto}
ul.plain{padding-left:18px;margin:6px 0}
ul.plain li{margin:3px 0}
ul.checks{list-style:none;padding-left:0}
ul.checks li{padding-left:22px;text-indent:-22px}
table.sign td{height:42px}
table.sign td:first-child{white-space:nowrap}
dl.trace{display:grid;grid-template-columns:230px 1fr;gap:4px 16px;font-size:13px}
dl.trace dt{color:var(--muted)}
dl.trace dd{margin:0;overflow-wrap:anywhere}
dl.gloss{grid-template-columns:150px 1fr}
footer{margin-top:40px;padding-top:10px;border-top:1px solid var(--rule);color:var(--muted);font-size:12px}
@media (max-width:640px){.page{padding:20px 16px}.kpis{grid-template-columns:1fr 1fr}dl.meta,dl.trace{grid-template-columns:1fr}nav.toc ol{columns:1}
 .wide{overflow-x:auto}}
@page{size:A4;margin:16mm 14mm 18mm}
@media print{.page{padding:0;max-width:none}h2{break-after:avoid}table,figure,.kpis,.qa,.callout,.keep{break-inside:avoid}h3{break-after:avoid}
 .annex{break-before:page}nav.toc{break-after:page}a{color:inherit;text-decoration:none}}
"""


# --------------------------------------------------------------------------- #
# Graphiques SVG (autonomes, lisibles à l'impression)
# --------------------------------------------------------------------------- #
def _svg(w: int, h: int, body: str, label: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'role="img" aria-label="{esc(label)}" font-family="Segoe UI,Helvetica,Arial,sans-serif">{body}</svg>')


def svg_csm(r: CsmResult) -> str:
    """Barres : CSM en fin de période ; points reliés : libération en résultat de la période."""
    rows = r.rollforward
    if not rows or r.initial_csm <= 0:
        return ""
    w, h, left, right, top, bottom = 700, 250, 70, 20, 30, 34
    vmax = max([r.initial_csm] + [x.closing for x in rows] + [x.release for x in rows]) * 1.08
    ph = h - top - bottom
    y = lambda v: top + ph * (1 - v / vmax)                                   # noqa: E731
    slot = (w - left - right) / (len(rows) + 1)
    parts = []
    for k in range(5):                                                         # grille
        v = vmax * k / 4
        parts.append(f'<line x1="{left}" y1="{y(v):.1f}" x2="{w - right}" y2="{y(v):.1f}" stroke="#e3e7ed"/>'
                     f'<text x="{left - 8}" y="{y(v) + 4:.1f}" font-size="11" fill="#5b6573" text-anchor="end">{num(v, 0)}</text>')
    bars = [("Origine", r.initial_csm)] + [(f"P{x.period}", x.closing) for x in rows]
    for i, (lab, v) in enumerate(bars):
        cx = left + slot * (i + 0.5)
        parts.append(f'<rect x="{cx - slot * 0.3:.1f}" y="{y(v):.1f}" width="{slot * 0.6:.1f}" height="{y(0) - y(v):.1f}" '
                     f'fill="#1f3a5f"><title>CSM {lab} : {num(v)}</title></rect>'
                     f'<text x="{cx:.1f}" y="{h - bottom + 16}" font-size="11.5" fill="#18212c" text-anchor="middle">{lab}</text>')
    pts = [(left + slot * (i + 1.5), y(x.release)) for i, x in enumerate(rows)]
    parts.append('<polyline points="' + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts)
                 + '" fill="none" stroke="#c2410c" stroke-width="2.2"/>')
    parts += [f'<circle cx="{a:.1f}" cy="{b:.1f}" r="3.6" fill="#c2410c"><title>Libération P{i + 1} : '
              f'{num(rows[i].release)}</title></circle>' for i, (a, b) in enumerate(pts)]
    parts.append(f'<rect x="{left}" y="8" width="11" height="11" fill="#1f3a5f"/>'
                 f'<text x="{left + 16}" y="18" font-size="12" fill="#18212c">CSM en fin de période</text>'
                 f'<line x1="{left + 190}" y1="13.5" x2="{left + 212}" y2="13.5" stroke="#c2410c" stroke-width="2.2"/>'
                 f'<text x="{left + 218}" y="18" font-size="12" fill="#18212c">Libération en résultat de la période</text>')
    return _svg(w, h, "".join(parts), "Évolution de la CSM")


def svg_waterfall(steps: list[tuple[str, float, str]]) -> str:
    """Cascade : (libellé, montant, type) avec type ∈ {total, delta}."""
    w, h, left, right, top, bottom = 700, 240, 70, 20, 16, 40
    run, spans = 0.0, []
    for lab, v, kind in steps:
        if kind == "total":
            spans.append((lab, 0.0, v, kind, v))
            run = v
        else:
            spans.append((lab, run, run + v, kind, v))
            run += v
    vmax = max(max(a, b) for _, a, b, _, _ in spans) * 1.1 or 1.0
    vmin = min(0.0, min(min(a, b) for _, a, b, _, _ in spans))
    ph = h - top - bottom
    y = lambda v: top + ph * (vmax - v) / (vmax - vmin)                       # noqa: E731
    slot = (w - left - right) / len(spans)
    parts = [f'<line x1="{left}" y1="{y(0):.1f}" x2="{w - right}" y2="{y(0):.1f}" stroke="#9aa5b3"/>']
    for i, (lab, a, b, kind, v) in enumerate(spans):
        x = left + slot * i + slot * 0.18
        bw = slot * 0.64
        color = "#1f3a5f" if kind == "total" else ("#2f7d5b" if v >= 0 else "#a3271f")
        top_y, bot_y = y(max(a, b)), y(min(a, b))
        parts.append(f'<rect x="{x:.1f}" y="{top_y:.1f}" width="{bw:.1f}" height="{max(bot_y - top_y, 1):.1f}" fill="{color}">'
                     f'<title>{esc(lab)} : {num(v)}</title></rect>'
                     f'<text x="{x + bw / 2:.1f}" y="{top_y - 5:.1f}" font-size="11.5" text-anchor="middle" fill="#18212c">'
                     f'{num(v) if kind == "total" else snum(v)}</text>'
                     f'<text x="{x + bw / 2:.1f}" y="{h - bottom + 16}" font-size="11.5" text-anchor="middle" fill="#18212c">{esc(lab)}</text>')
        if i + 1 < len(spans):
            parts.append(f'<line x1="{x + bw:.1f}" y1="{y(b):.1f}" x2="{x + slot:.1f}" y2="{y(b):.1f}" '
                         f'stroke="#9aa5b3" stroke-dasharray="3 3"/>')
    return _svg(w, h, "".join(parts), "Analyse des mouvements de la CSM")


def _in_label(r: CsmResult) -> str:
    return "Valeur actuelle des primes et recouvrements" if r.pv_recoveries > 0 else "Valeur actuelle des primes"


def svg_composition(r: CsmResult) -> str:
    """Barre empilée : comment la valeur actuelle des primes se répartit (ou ce qui manque)."""
    if r.onerous:
        segs = [(_in_label(r), r.pv_inflows, "#1f3a5f"), ("Perte à l'origine", r.initial_loss_component, "#a3271f")]
        other = [("Valeur actuelle des sorties", r.pv_outflows, "#5b7fa6")]
        other += [("Frais d'acquisition", r.pv_acquisition, "#7a6aa8")] if r.pv_acquisition > 0 else []
        other += [("Ajustement pour risque", r.risk_adjustment, "#9fb4cc")]
        rows = [("Ressources", segs), ("Engagements", other)]
    else:
        uses = [("Valeur actuelle des sorties", r.pv_outflows, "#5b7fa6")]
        uses += [("Frais d'acquisition", r.pv_acquisition, "#7a6aa8")] if r.pv_acquisition > 0 else []
        uses += [("Ajustement pour risque", r.risk_adjustment, "#9fb4cc"), ("CSM", r.initial_csm, "#2f7d5b")]
        rows = [("Entrées" if r.pv_recoveries > 0 else "Primes", [(_in_label(r), r.pv_inflows, "#1f3a5f")]),
                ("Emplois", uses)]
    total = max(sum(v for _, v, _ in segs) for _, segs in rows) or 1.0
    w, left, bar_h = 700, 92, 30
    parts, legend = [], []
    for i, (lab, segs) in enumerate(rows):
        yy = 14 + i * (bar_h + 18)
        parts.append(f'<text x="0" y="{yy + bar_h / 2 + 4}" font-size="12" fill="#18212c">{esc(lab)}</text>')
        x = left
        for name, v, color in segs:
            ww = (w - left - 10) * v / total
            parts.append(f'<rect x="{x:.1f}" y="{yy}" width="{ww:.1f}" height="{bar_h}" fill="{color}"><title>{esc(name)} : {num(v)}</title></rect>')
            if ww > 60:
                parts.append(f'<text x="{x + ww / 2:.1f}" y="{yy + bar_h / 2 + 4}" font-size="11.5" fill="#fff" text-anchor="middle">{num(v)}</text>')
            x += ww
            if name not in [n for n, _ in legend]:
                legend.append((name, color))
    ly = 14 + len(rows) * (bar_h + 18) + 4
    lx = left
    for name, color in legend:
        width = 22 + 6.4 * len(name)
        if lx + width > w:
            lx, ly = left, ly + 18
        parts.append(f'<rect x="{lx:.0f}" y="{ly}" width="10" height="10" fill="{color}"/>'
                     f'<text x="{lx + 14:.0f}" y="{ly + 9}" font-size="11.5" fill="#18212c">{esc(name)}</text>')
        lx += width + 14
    h = ly + 20
    return _svg(w, h, "".join(parts), "Décomposition de l'évaluation initiale")


def svg_tornado(sens: SensitivityReport) -> str:
    items = sens.items
    if not items:
        return ""
    w, left, right, row_h = 700, 250, 70, 26
    h = 16 + row_h * len(items) + 10
    m = max(abs(s.delta_result_at_inception) for s in items) or 1.0
    mid = left + (w - left - right) / 2
    half = (w - left - right) / 2
    parts = [f'<line x1="{mid:.1f}" y1="8" x2="{mid:.1f}" y2="{h - 6}" stroke="#9aa5b3"/>']
    for i, s in enumerate(items):
        yy = 12 + i * row_h
        v = s.delta_result_at_inception
        ww = half * abs(v) / m
        x = mid if v >= 0 else mid - ww
        color = "#2f7d5b" if v >= 0 else "#a3271f"
        parts.append(f'<text x="0" y="{yy + 13}" font-size="12" fill="#18212c">{esc(s.label)}{" *" if s.flips else ""}</text>'
                     f'<rect x="{x:.1f}" y="{yy}" width="{max(ww, 1):.1f}" height="{row_h - 9}" fill="{color}"><title>{esc(s.label)} : {snum(v)}</title></rect>'
                     f'<text x="{(x + ww + 6) if v >= 0 else (x - 6):.1f}" y="{yy + 13}" font-size="11.5" '
                     f'text-anchor="{"start" if v >= 0 else "end"}" fill="#18212c">{snum(v)}</text>')
    return _svg(w, h, "".join(parts), "Sensibilité du résultat à l'origine")


# --------------------------------------------------------------------------- #
# Petites briques HTML / Markdown
# --------------------------------------------------------------------------- #
def h_table(head: list[str], rows: list[list[str]], classes: list[str] | None = None, left_cols: int = 1) -> str:
    th = "".join(f'<th class="l">{esc(c)}</th>' if i < left_cols else f"<th>{esc(c)}</th>" for i, c in enumerate(head))
    body = []
    for k, row in enumerate(rows):
        cls = f' class="{classes[k]}"' if classes and classes[k] else ""
        tds = "".join(f'<td class="l">{c}</td>' if i < left_cols else f"<td>{c}</td>" for i, c in enumerate(row))
        body.append(f"<tr{cls}>{tds}</tr>")
    return f'<div class="wide"><table><thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def m_table(head: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "| " + " | ".join(["---"] + ["---:"] * (len(head) - 1)) + " |"]
    out += ["| " + " | ".join(html.unescape(c).replace("|", "/") for c in row) + " |" for row in rows]
    return out + [""]


def neg_span(x: float, d: int = 2) -> str:
    return f'<span class="neg">{num(x, d)}</span>' if x < -0.5 * 10 ** -d else num(x, d)


# --------------------------------------------------------------------------- #
# La note
# --------------------------------------------------------------------------- #
SECTIONS = [("resume", "Résumé exécutif"), ("objet", "Objet, périmètre et méthode"), ("donnees", "Données en entrée"),
            ("hypotheses", "Hypothèses"), ("initiale", "Évaluation à la comptabilisation initiale"),
            ("csm", "Évolution de la marge sur services contractuels"),
            ("projection", "Projection : compte de résultat et passif"), ("sensibilites", "Sensibilités"),
            ("norme", "Fondements dans la norme"), ("controles", "Contrôles, limites et validation")]


def _paa_section(H: list[str], M: list[str], p: PortfolioData, r: CsmResult, paa: PaaView, unit: str) -> None:
    """Section 7 (suite) : mesure PAA d'un groupe éligible et comparaison avec le modèle général (D-073)."""
    intro = (f"Couverture de {paa.months} mois ({paa.months_source}) : la PAA est admissible (§53(b)). Passif pour "
             f"couverture restante à la comptabilisation initiale : primes reçues"
             + (" moins frais d'acquisition payés" if r.pv_acquisition > 0 else "") + f", soit {num(paa.lrc_initial)} "
             "(§55(a)). La couverture s'achève avec la première période : tous les sinistres sont survenus à sa clôture "
             "et forment le passif pour sinistres survenus (LIC), "
             + ("actualisé car des règlements sont attendus au-delà de douze mois (l'exemption du §59(b) ne s'applique pas)"
                if paa.discounted else "sans actualisation, les règlements intervenant dans l'année (§59(b))")
             + ", chargé du même ajustement pour risque.")
    onerous = (f"Test du groupe déficitaire (§57 et §58) : les flux d'exécution de la couverture restante dépassent le "
               f"passif de {num(paa.onerous_loss)}, passés immédiatement en perte."
               if paa.onerous_loss > 0 else
               "Test du groupe déficitaire (§57) : aucun fait ni circonstance ne l'indique, les flux d'exécution de la "
               "couverture restante restant inférieurs au passif.")
    head = ["Période", "Produits (B126)", "Frais d'acquisition", "Sinistres survenus (LIC initial)", "RA libéré",
            "Résultat des services PAA", "Résultat des services modèle général", "LIC en fin de période"]
    rows, cls = [], []
    for k, y in enumerate(paa.years):
        if k > 0 and abs(y.service_result) < 0.005 and abs(y.lic_closing) < 0.005 and \
                (not paa.bba_service_results or abs(paa.bba_service_results[k]) < 0.005):
            continue
        bba = paa.bba_service_results[k] if paa.bba_service_results else None
        rows.append([f"P{y.period}", num(y.revenue), neg_span(-y.acquisition_expense), neg_span(-y.claims_incurred),
                     num(y.ra_release), neg_span(y.service_result), neg_span(bba) if bba is not None else "—",
                     num(y.lic_closing)])
        cls.append("")
    rows.append(["Total", num(sum(y.revenue for y in paa.years)), neg_span(-sum(y.acquisition_expense for y in paa.years)),
                 neg_span(-sum(y.claims_incurred for y in paa.years)), num(sum(y.ra_release for y in paa.years)),
                 neg_span(paa.total_paa), neg_span(paa.total_bba) if paa.bba_service_results else "—", ""])
    cls.append("total")
    finance_gap = paa.total_bba - paa.total_paa
    compare = ("Les deux méthodes donnent le même résultat total (services d'assurance et résultat financier d'assurance "
               "réunis) : elles ne diffèrent que par sa présentation. "
               f"Sur l'année de couverture, le résultat des services PAA s'écarte de {snum(paa.first_year_gap)} du modèle "
               f"général : le modèle général capitalise la CSM au taux bloqué (§44(b)) et en libère les intérêts en "
               f"produits, la PAA ne connaît pas de CSM ; l'écart, {num(abs(finance_gap))} sur la durée, se retrouve en "
               "sens inverse dans les charges financières d'assurance.") if paa.bba_service_results else ""
    H.append('<div class="keep"><h3>Méthode simplifiée (PAA) : mesure et comparaison</h3>'
             f"<p>{esc(intro)}</p><p>{esc(onerous)}</p>" + h_table(head, rows, cls)
             + f'<p class="note">Montants en {esc(unit)}. Scénario central (réalisé = attendu) ; produits reconnus selon '
             "l'écoulement du temps sur les douze mois de couverture ; mêmes flux, courbe et RA que le modèle général. "
             "Charges en négatif.</p>" + (f"<p>{esc(compare)}</p>" if compare else "") + "</div>")
    M += ["**Méthode simplifiée (PAA) : mesure et comparaison**", "", intro, "", onerous, ""] + m_table(head, rows) \
        + ([compare, ""] if compare else [])


def declared_text(p: PortfolioData, r: CsmResult, conf: ConfidenceReport) -> tuple[str, bool]:
    """Volatilité et niveau de confiance annoncés par le document, rapprochés du calcul et du registre (D-082).
    Renvoie le texte et s'il signale un écart à arbitrer."""
    chk = declared_risk_check(r.pv_outflows, r.risk_adjustment, conf.cv, p.declared_cv, p.declared_confidence)
    if chk is None:
        return "", False
    parts = []
    if chk.declared_cv is not None:
        parts.append(f"Le document annonce une volatilité (coefficient de variation) de {pct(chk.declared_cv, 1)} : avec "
                     f"cette hypothèse, l'ajustement retenu correspond à un niveau de confiance de "
                     f"{pct(chk.level_with_declared_cv, 1)}, contre {pct(chk.level_with_registry_cv, 1)} avec la volatilité "
                     f"du registre ({pct(chk.registry_cv, 1)}).")
    if chk.declared_confidence is not None:
        ref = chk.level_with_declared_cv if chk.level_with_declared_cv is not None else chk.level_with_registry_cv
        basis = "sa propre volatilité" if chk.level_with_declared_cv is not None else "la volatilité du registre"
        parts.append(f"Il annonce un niveau de confiance de {pct(chk.declared_confidence, 1)} ; recalculé avec {basis}, "
                     f"son ajustement donne {pct(ref, 1)} : "
                     + ("écart de plus de 2,5 points, l'annonce du document est à vérifier."
                        if chk.confidence_disagrees else "cohérent."))
    if chk.cv_disagrees:
        parts.append(f"Écart d'hypothèse de {pct(abs(chk.cv_gap), 0)} entre la volatilité du document et celle du registre : "
                     "le calcul garde le registre (hypothèse validée de l'entité) ; l'actuaire arbitre (grille, point H3).")
    return " ".join(parts), chk.cv_disagrees or chk.confidence_disagrees


def render_note(p: PortfolioData, r: CsmResult, synthesis: str, commentary: str, source: str,
                norm: list[NormPoint], controls: list[str], checks: list[str],
                sens: SensitivityReport, proj: Projection | None, ctx: NoteContext,
                conf: ConfidenceReport | None = None, paa: PaaView | None = None) -> tuple[str, str]:
    unit = unit_label(p)
    n = p.n_periods
    status_ok = not controls
    status = "Contrôles automatiques passés" if status_ok else "À VALIDER PAR UN HUMAIN"
    badge = f'<span class="badge {"ok" if status_ok else "warn"}">{esc(status)}</span>'
    date_txt = ctx.generated_at.strftime("%d/%m/%Y à %H:%M")
    title = f"Évaluation IFRS 17 du groupe {p.group_id}"
    H: list[str] = []
    M: list[str] = [f"# Note actuarielle IFRS 17 — {title}", "",
                    f"**Statut : {status}** · montants en {unit} · établie le {date_txt}", ""]

    # ---------------------------------------------------------------- page de garde
    source_txt = ctx.source_name or ("données validées par un humain" if ctx.validated_by_human else "données fournies à l'API")
    paa_ok = paa is not None and paa.eligible
    cover_txt = (f"{paa.months} mois ({paa.months_source}) ; flux sur {n} période{'s' if n > 1 else ''}" if paa is not None
                 else f"{n} période{'s' if n > 1 else ''} (années)")
    meta = [("Entité", ctx.entity), ("Groupe de contrats", p.group_id),
            *([("Branche", p.line_of_business)] if p.line_of_business else []),
            ("Méthode", "Modèle général (BBA), PAA admissible et présentée en comparaison (§53(b))" if paa_ok
             else "Modèle général (BBA)"), ("Monnaie et unité", f"Montants en {unit}"),
            ("Durée de couverture", cover_txt),
            ("Date d'établissement", date_txt), ("Référence du dossier", ctx.case_id or "—"),
            ("Document source", source_txt), ("Version de la note", f"IFRS 17 Copilot {ctx.app_version or ''}".strip()),
            ("Diffusion", "Usage interne · données fictives · sans valeur de conseil")]
    H.append(f'<header class="cover"><p class="kicker">Note actuarielle IFRS 17</p><h1>{esc(title)}</h1>'
             f'<p class="subtitle">Comptabilisation initiale, écoulement de la CSM, projection du résultat et sensibilités</p>'
             f'<p>{badge}</p><dl class="meta">'
             + "".join(f"<dt>{esc(a)}</dt><dd>{esc(b)}</dd>" for a, b in meta) + "</dl></header>")
    H.append('<nav class="toc"><h3>Sommaire</h3><ol>' + "".join(f'<li><a href="#{k}">{esc(t)}</a></li>' for k, t in SECTIONS)
             + '</ol><p class="note">Annexes : A. Traçabilité · B. Glossaire</p></nav>')
    M += m_table(["Élément", "Valeur"], [[a, esc(b)] for a, b in meta])

    def section(i: int) -> None:
        key, name = SECTIONS[i]
        H.append(f'<h2 id="{key}">{i + 1}. {esc(name)}</h2>')
        M.extend([f"## {i + 1}. {name}", ""])

    # ---------------------------------------------------------------- 1. résumé
    section(0)
    margin = margin_ratio(r)
    if r.onerous:
        k1 = ("Perte à la comptabilisation initiale (§47)", num(r.initial_loss_component), True)
    else:
        k1 = ("CSM initiale (§38)", num(r.initial_csm), False)
    kpis = [k1, ("Flux de trésorerie d'exécution", num(r.fulfilment_cash_flows), False),
            ("Perte rapportée aux primes actualisées" if r.onerous else "Marge attendue : CSM sur primes actualisées",
             pct(margin), margin < 0)]
    if sens.outflow_breakeven is not None:
        kpis.append(("Seuil d'équilibre : variation des sinistres et frais", pct(sens.outflow_breakeven), False))
    H.append('<div class="kpis">' + "".join(f'<div class="kpi{" neg" if bad else ""}"><div class="l">{esc(lab)}</div>'
                                           f'<div class="v">{esc(v)}</div></div>' for lab, v, bad in kpis) + "</div>")
    H.append(f'<p class="note">Montants en {esc(unit)}.</p><p>{esc(synthesis)}</p>')
    if source != "llm":
        H.append('<p class="note">Résumé écrit par le code : le texte proposé par le LLM n\'a pas passé le contrôle des nombres et des citations.</p>')
    M += [f"- **{lab}** : {v}" for lab, v, _ in kpis] + ["", synthesis, ""]
    if controls:
        H.append('<div class="callout warn"><b>Points à valider avant diffusion</b><ul class="plain">'
                 + "".join(f"<li>{esc(c)}</li>" for c in controls) + "</ul></div>")
        M += ["**Points à valider avant diffusion :**", ""] + [f"- {c}" for c in controls] + [""]
    else:
        H.append('<div class="callout"><b>Aucun point bloquant.</b> Données, calculs et citations ont passé les '
                 'contrôles automatiques ; la note reste soumise à la revue d\'un actuaire (section 10).</div>')

    # ---------------------------------------------------------------- 2. objet
    section(1)
    obj = (f"Cette note présente l'évaluation du groupe de contrats {p.group_id} selon le modèle général d'IFRS 17 : "
           f"évaluation à la comptabilisation initiale, écoulement prévu de la marge sur services contractuels (CSM), "
           f"projection du compte de résultat et du passif dans le scénario central, et sensibilité des résultats aux "
           f"principales hypothèses. Elle est destinée à la direction financière et à la revue actuarielle.")
    if paa_ok:
        paa_txt = (f"La couverture des contrats n'excède pas un an ({paa.months} mois, {paa.months_source}) : la méthode "
                   "simplifiée d'affectation des primes (PAA) est admissible sans démonstration (§53(b)). Le modèle "
                   "général reste la mesure de référence de cette note ; la mesure PAA et la comparaison des deux figurent "
                   "en section 7.")
    elif paa is not None:
        paa_txt = (f"La méthode simplifiée (PAA, §53) n'est pas retenue : la couverture dure {paa.months} mois "
                   f"({paa.months_source}), au-delà d'un an ; le modèle général est la méthode de référence.")
    else:
        paa_txt = "Le modèle général est la méthode de référence."
    scope_in = ["Un groupe de contrats, constitué en amont selon le niveau d'agrégation de la norme (§14 à §24).",
                "Flux de trésorerie d'exécution : primes, sinistres et frais attendus, recouvrements et frais "
                "d'acquisition s'ils sont fournis, actualisés.",
                "Ajustement au titre du risque non financier, CSM ou composante de perte, et leur évolution."]
    scope_out = ["Contrats participatifs directs (VFA), réassurance détenue, composantes d'investissement : hors du "
                 "périmètre de l'outil.",
                 "Produits des placements (côté actif) : non modélisés ; seules les charges financières d'assurance figurent.",
                 "Écarts d'expérience et révisions d'hypothèses des clôtures suivantes : note de clôture distincte "
                 "(réalisé de l'année, D-076)."]
    H.append(f"<p>{esc(obj)}</p><p>{esc(paa_txt)}</p><h3>Inclus</h3><ul class=\"plain\">"
             + "".join(f"<li>{esc(x)}</li>" for x in scope_in) + "</ul><h3>Exclus</h3><ul class=\"plain\">"
             + "".join(f"<li>{esc(x)}</li>" for x in scope_out) + "</ul>")
    M += [obj, "", paa_txt, "", "**Inclus :**", ""] + [f"- {x}" for x in scope_in] + ["", "**Exclus :**", ""] + [f"- {x}" for x in scope_out] + [""]

    # ---------------------------------------------------------------- 3. données
    section(2)
    if ctx.extraction_mode:
        mode = {"texte": "lecture de la couche texte du PDF", "vision": "lecture visuelle (scan ou image)",
                "tableur": "lecture des cellules du classeur (valeurs exactes, sans OCR)",
                "hybride": "lecture visuelle contrôlée par la couche texte"}.get(ctx.extraction_mode, ctx.extraction_mode)
        anchor = ("chaque nombre retrouvé dans le document" if ctx.grounding == "document"
                  else "chaque nombre retrouvé dans la transcription du document")
    else:
        mode, anchor = "aucune (données saisies ou corrigées)", "sans objet"
    src_rows = [["Document source", esc(source_txt)],
                ["Empreinte SHA-256", esc(ctx.source_sha256[:16] + "…") if ctx.source_sha256 else "—"],
                ["Mode de lecture", esc(mode)], ["Contrôle d'ancrage", esc(anchor)],
                ["Données validées par un humain", "oui" if ctx.validated_by_human else "non"]]
    if ctx.reader_notes:
        src_rows.append(["Remarques de lecture", esc(" ; ".join(ctx.reader_notes))])
    if ctx.validated_by_human:
        src_rows.append(["Modifications du valideur", esc(" ; ".join(ctx.human_changes)) if ctx.human_changes
                         else "aucune : données extraites approuvées telles quelles"])
    H.append('<div class="keep"><h3>Origine des données</h3><dl class="trace">'
             + "".join(f"<dt>{a}</dt><dd>{b}</dd>" for a, b in src_rows) + "</dl></div>")
    M += m_table(["Origine des données", ""], src_rows)
    rates = _rates(p)
    df = discount_factors(p.discount_rates, n)
    has_rec = bool(p.recoveries and any(x > 0 for x in p.recoveries))
    rec = list(p.recoveries) if has_rec else []
    has_acq = bool(p.acquisition_costs and any(x > 0 for x in p.acquisition_costs))
    acq = acquisition_costs(p)
    flow_rows = [[str(t + 1), num(p.premiums[t])] + ([num(acq[t])] if has_acq else []) + [num(p.outflows[t])]
                 + ([num(rec[t])] if has_rec else [])
                 + [num(p.coverage_units[t], 0), pct(rates[t]), fr(df[t + 1], 4)] for t in range(n)]
    flow_rows.append(["Total (non actualisé)", num(sum(p.premiums))] + ([num(sum(acq))] if has_acq else [])
                     + [num(sum(p.outflows))] + ([num(sum(rec))] if has_rec else [])
                     + [num(sum(p.coverage_units), 0), "", ""])
    head = (["Période", "Primes (début)"] + (["Frais d'acquisition (début)"] if has_acq else [])
            + ["Sinistres et frais (fin)"] + (["Recouvrements (fin)"] if has_rec else [])
            + ["Unités de couverture", "Taux spot", "Facteur d'actualisation (fin)"])
    H.append('<div class="keep"><h3>Flux par période</h3>' + h_table(head, flow_rows, ["" for _ in range(n)] + ["total"])
             + f'<p class="note">Montants en {esc(unit)}. Primes encaissées en début de période, sinistres et frais payés '
             'en fin de période' + (', recouvrements (récupération, subrogation) encaissés en fin de période (B65 k)' if has_rec else '')
             + (", frais d'acquisition payés en début de période (B65 e)" if has_acq else '')
             + '.</p></div>')
    M += m_table(head, flow_rows)
    if ctx.provenance:
        prov = [[esc(k), esc(v)] for k, v in ctx.provenance.items()]
        H.append('<div class="keep"><h3>Où chaque donnée a été lue</h3>' + h_table(["Donnée", "Emplacement dans le document"], prov)
                 + '<p class="note">Retrouvé par le code dans la couche texte du PDF, indépendamment du LLM.</p></div>')
        M += ["**Où chaque donnée a été lue**", ""] + m_table(["Donnée", "Emplacement dans le document"], prov)
    if ctx.field_confidence:
        conf = [[esc(k), pct(v, 0)] for k, v in sorted(ctx.field_confidence.items())]
        H.append("<h3>Confiance de la lecture, par champ</h3>" + h_table(["Champ", "Confiance"], conf))
        M += ["**Confiance de la lecture, par champ**", ""] + m_table(["Champ", "Confiance"], conf)

    # ---------------------------------------------------------------- 4. hypothèses
    section(3)
    flat = not isinstance(p.discount_rates, list)
    fsa = bool(p.future_service_adjustments and any(abs(x) > 1e-12 for x in p.future_service_adjustments))
    hyp = [["Méthode d'évaluation", "Modèle général (BBA)", "§32 à §52"],
           ["Flux de trésorerie", "Estimations explicites et à jour ; primes en début, sorties en fin de période", "§33 à §35"],
           *([["Recouvrements", "Récupération et subrogation : entrées de trésorerie en fin de période, comprises dans le "
               "périmètre du contrat ; l'ajustement pour risque reste calculé sur les sorties brutes", "B65 k)"]]
             if p.recoveries and any(x > 0 for x in p.recoveries) else []),
           *([["Frais d'acquisition", "Flux de trésorerie d'exécution payés en début de période, sans ajustement pour "
               "risque ; ils réduisent la CSM ; en résultat, la part des primes qui les couvre est affectée aux périodes "
               "selon les unités de couverture et le même montant est passé en charges", "B65 e), §28A, B125"]]
             if has_acq else []),
           ["Taux d'actualisation", (f"taux plat de {pct(p.discount_rates)}" if flat else
                                     "courbe de taux spot : " + " ; ".join(pct(x) for x in rates)), "§36"],
           ["Ajustement au titre du risque", f"{pct(p.risk_adjustment_pct)} de la valeur actuelle des sorties"
            + (f", soit un niveau de confiance de {pct(conf.level_of_retained_ra, 1)} (quantile, loi lognormale, coefficient "
               f"de variation {pct(conf.cv, 1)} : {ctx.ra_cv_source or 'hypothèse supposée'})" if conf else ""),
            "§37, B86 à B92, §119"],
           ["Taux bloqué de la CSM", "Courbe à la date de comptabilisation initiale", "§44(b), B72(b)"],
           ["Libération de la CSM", "Unités de couverture de la période / unités restantes", "§44(e), B119"],
           ["Ajustements liés aux services futurs", "fournis dans les données" if fsa else "aucun", "§44(c), B96"],
           ["Groupe déficitaire", "Perte immédiate, composante de perte reprise de façon systématique", "§47 à §52"],
           ["Variation de l'ajustement pour risque", "Ventilée entre résultat des services et résultat financier", "§81"],
           ["Produits et charges financières", "En résultat, sans option OCI", "§87, §88"]]
    H.append(h_table(["Hypothèse", "Valeur retenue", "Référence"],
                     [[esc(a), esc(b), esc(c).replace(" ", NBSP)] for a, b, c in hyp], left_cols=2))
    calibrated = ctx.ra_cv_source.startswith("volatilité calibrée")
    prudent = ctx.ra_cv_source.startswith("volatilité prudente")
    H.append('<p class="note">Jugements à confirmer par l\'actuaire : le coefficient de variation des sorties, qui fixe le '
             'niveau de confiance de l\'ajustement pour risque ('
             + ("mesuré par back-testing sur des données réelles de la branche" if calibrated else
                "retenu par prudence, faute d'historique suffisant pour la branche" if prudent else
                "supposé, la branche n'étant pas indiquée dans le document" if "non indiquée" in ctx.ra_cv_source else
                "supposé, faute de calibration pour cette branche")
             + '), et le profil des unités de couverture.'
             + (f' Registre des hypothèses : version {esc(ctx.registry_version)}.' if ctx.registry_version else '') + '</p>')
    M += m_table(["Hypothèse", "Valeur retenue", "Référence"], hyp)

    # ---------------------------------------------------------------- 5. évaluation initiale
    section(4)
    bel = r.pv_outflows + r.pv_acquisition - r.pv_inflows
    items: list[tuple[str, str, str]] = []
    if r.pv_recoveries > 0:
        items += [("Valeur actuelle des primes", num(r.pv_inflows - r.pv_recoveries), ""),
                  ("Valeur actuelle des recouvrements (B65 k)", num(r.pv_recoveries), ""),
                  ("Valeur actuelle des entrées (primes + recouvrements)", num(r.pv_inflows), "")]
    else:
        items.append(("Valeur actuelle des entrées (primes)", num(r.pv_inflows), ""))
    items.append(("Valeur actuelle des sorties (sinistres et frais)", num(r.pv_outflows), ""))
    if r.pv_acquisition > 0:
        items.append(("Valeur actuelle des frais d'acquisition (B65 e)", num(r.pv_acquisition), ""))
    items += [("Meilleure estimation, BEL (sorties − entrées)", neg_span(bel), ""),
              ("Ajustement au titre du risque non financier", num(r.risk_adjustment), ""),
              ("Flux de trésorerie d'exécution (BEL + RA)", neg_span(r.fulfilment_cash_flows), "hl"),
              ("CSM initiale (§38)", num(r.initial_csm), "hl" if not r.onerous else ""),
              ("Perte initiale, groupe déficitaire (§47)", num(r.initial_loss_component), "hl" if r.onerous else ""),
              ("Passif à la comptabilisation initiale (FCF + CSM)", num(r.fulfilment_cash_flows + r.initial_csm), "total")]
    init = [[a, b] for a, b, _ in items]
    cls = [c for _, _, c in items]
    H.append(h_table(["Élément", "Montant"], init, cls))
    M += m_table(["Élément", "Montant"], init)
    if r.pv_inflows > 0:
        shares = (r.pv_outflows / r.pv_inflows, r.risk_adjustment / r.pv_inflows, margin)
        what = "d'entrées actualisées (primes et recouvrements)" if r.pv_recoveries > 0 else "de primes actualisées"
        acq_part = (f", {fr(r.pv_acquisition / r.pv_inflows * 100, 1)} les frais d'acquisition"
                    if r.pv_acquisition > 0 else "")
        txt = (f"Sur 100 {what}, {fr(shares[0] * 100, 1)} couvrent les sinistres et frais attendus{acq_part} et "
               f"{fr(shares[1] * 100, 1)} l'ajustement pour risque ; "
               + (f"le solde, {fr(shares[2] * 100, 1)}, forme la CSM." if not r.onerous else
                  f"il manque {fr(-shares[2] * 100, 1)}, passés immédiatement en perte."))
        H.append(f"<p>{esc(txt)}</p>")
        M += [txt, ""]
    H.append(f'<figure>{svg_composition(r)}<figcaption>Décomposition de l\'évaluation initiale ({esc(unit)}).</figcaption></figure>')

    # ---------------------------------------------------------------- 6. CSM
    section(5)
    rf = r.rollforward
    if r.onerous:
        txt = ("Le groupe étant déficitaire, la CSM est nulle à l'origine et le reste sur toute la durée : aucun profit "
               "futur n'est différé. La composante de perte est reprise au fil de la couverture ; son évolution figure "
               "dans le passif de la section 7.")
        H.append(f"<p>{esc(txt)}</p>")
        M += [txt, ""]
    else:
        total_cu = sum(p.coverage_units) or 1.0
        rows = [[str(x.period), num(x.opening), num(x.interest_accretion), snum(x.future_service_adjustment),
                 num(x.release), num(x.closing), pct(x.release / r.total_release if r.total_release else 0, 1)]
                for x in rf]
        mv = csm_movements(r)
        rows.append(["Total", num(r.initial_csm), num(mv.interest), snum(mv.future_service), num(mv.release), num(mv.closing), "100,0 %"])
        head = ["Période", "Ouverture", "Intérêts au taux bloqué §44(b)", "Services futurs §44(c)",
                "Libération B119", "Clôture", "Part libérée"]
        H.append(h_table(head, rows, ["" for _ in rf] + ["total"]))
        M += m_table(head, rows)
        H.append(f'<figure>{svg_csm(r)}<figcaption>CSM en fin de période et libération annuelle en résultat ({esc(unit)}). '
                 f'Profil des unités de couverture : ' + " ; ".join(pct(c / total_cu, 1) for c in p.coverage_units)
                 + "</figcaption></figure>")
        steps = [("CSM initiale", r.initial_csm, "total"), ("Intérêts", mv.interest, "delta")]
        if abs(mv.future_service) > 1e-9:
            steps.append(("Services futurs", mv.future_service, "delta"))
        steps += [("Libérations", -mv.release, "delta"), ("Clôture", mv.closing, "total")]
        H.append('<div class="keep"><h3>Analyse des mouvements sur la durée du groupe</h3>'
                 
                 f"<figure>{svg_waterfall(steps)}<figcaption>De la CSM initiale à la CSM de clôture : intérêts capitalisés "
                 f"au taux bloqué, ajustements liés aux services futurs, libérations en résultat ({esc(unit)}).</figcaption></figure></div>")
        M += ["**Analyse des mouvements :** " + " ; ".join(f"{lab} {num(v) if k == 'total' else snum(v)}" for lab, v, k in steps), ""]

    # ---------------------------------------------------------------- 7. projection
    section(6)
    if proj is None:
        txt = ("La projection du compte de résultat n'est pas produite : des ajustements liés aux services futurs sont "
               "fournis, ce qui sort du scénario central. Ils sont repris dans le roll-forward de la CSM (section 6) ; "
               "le module pluriannuel du projet (engine/bba.py) traite ces révisions année par année.")
        H.append(f'<div class="callout">{esc(txt)}</div>')
        M += [txt, ""]
    else:
        intro = ("Scénario central : les flux réalisés sont égaux aux flux attendus et les taux courants suivent les taux à "
                 "terme de la courbe initiale. Les produits des activités d'assurance comprennent les sinistres et frais "
                 "attendus de la période, l'ajustement pour risque libéré et la CSM libérée (B124)"
                 + (" ; la part affectée à la composante de perte en est exclue (§49 à §52)." if r.onerous else "."))
        H.append(f"<p>{esc(intro)}</p>")
        M += [intro, ""]
        periods = [f"P{x.period}" for x in proj.rows]
        def line(lab: str, attr: str, sign: float = 1.0, cls: str = "") -> tuple[list[str], str]:
            vals = [getattr(x, attr) * sign for x in proj.rows]
            return [esc(lab)] + [neg_span(v) for v in vals] + [neg_span(sum(vals))], cls
        keep = 1 - proj.systematic_loss_ratio            # part des libérations qui va aux produits (§49 à §52)
        ra_in_rev = [x.ra_release * keep for x in proj.rows]
        lines = [line("Produits des activités d'assurance", "insurance_revenue")]
        if not r.onerous:
            lines.append(line("dont CSM libérée", "csm_release", cls="sub"))
        lines += [([esc("dont ajustement pour risque libéré")] + [num(v) for v in ra_in_rev] + [num(sum(ra_in_rev))], "sub")]
        if has_acq:
            lines.append(line("dont frais d'acquisition couverts par les primes (B125)", "acquisition_amortisation", cls="sub"))
        lines += [
                 line("Charges des services d'assurance", "insurance_service_expense", -1.0),
                 line("Résultat des services d'assurance", "insurance_service_result", cls="total"),
                 line("Charges financières d'assurance", "insurance_finance_expense", -1.0)]
        if r.onerous:
            initial = [0.0] * len(proj.rows)
            initial[0] = -r.initial_loss_component
            lines.insert(3, ([esc("dont perte à la comptabilisation initiale (§47)")] + [neg_span(v) for v in initial]
                             + [neg_span(sum(initial))], "sub"))
            lines.insert(4, line("dont reprise de la composante de perte", "loss_component_reversal", cls="sub"))
        head = ["Compte de résultat"] + periods + ["Total"]
        H.append('<div class="keep"><h3>Compte de résultat IFRS 17 attendu</h3>'
                 + h_table(head, [row for row, _ in lines], [c for _, c in lines])
                 + '<p class="note">Charges présentées en négatif. Les charges financières d\'assurance (désactualisation '
                 'du passif) sont compensées dans les comptes par les produits des placements, non modélisés ici.</p></div>')
        M += ["**Compte de résultat IFRS 17 attendu**", ""] + m_table(head, [row for row, _ in lines])
        bal_head = ["Passif (fin de période)", "Origine"] + periods
        bal = [["Meilleure estimation (BEL)", neg_span(r.pv_outflows + r.pv_acquisition - r.pv_inflows)]
               + [neg_span(x.bel_closing) for x in proj.rows],
               ["Ajustement pour risque", num(r.risk_adjustment)] + [num(x.ra_closing) for x in proj.rows],
               ["CSM", num(r.initial_csm)] + [num(x.csm_closing) for x in proj.rows]]
        cls2 = ["", "", ""]
        if r.onerous:
            bal.append(["dont composante de perte", num(r.initial_loss_component)] + [num(x.loss_component_closing) for x in proj.rows])
            cls2.append("sub")
        bal.append(["Passif pour couverture restante", neg_span(proj.opening_lrc)] + [neg_span(x.lrc_closing) for x in proj.rows])
        cls2.append("total")
        H.append('<div class="keep"><h3>Passif pour couverture restante</h3>' + h_table(bal_head, bal, cls2)
                 + '<p class="note">Valeurs avant l\'encaissement de la prime de la période suivante. Rapprochement vérifié par '
                 'le code à chaque période : passif de clôture = ouverture + primes − sinistres et frais' + (' + recouvrements' if has_rec else '')
                 + (" − frais d'acquisition" if has_acq else '') + ' + charges '
                 'financières − libérations ; tous les postes s\'éteignent en fin de couverture.</p></div>')
        M += ["**Passif pour couverture restante**", ""] + m_table(bal_head, bal)
    if paa is not None and paa.eligible:
        _paa_section(H, M, p, r, paa, unit)

    # ---------------------------------------------------------------- 8. sensibilités
    section(7)
    base_row = [["Scénario central", neg_span(r.fulfilment_cash_flows), num(r.initial_csm), num(r.initial_loss_component), "—",
                 "déficitaire" if r.onerous else "bénéficiaire"]]
    srows = base_row + [[esc(s.label), neg_span(s.fulfilment_cash_flows), num(s.csm), num(s.loss),
                         ('<span class="neg">' if s.delta_result_at_inception < 0 else "") + snum(s.delta_result_at_inception)
                         + ("</span>" if s.delta_result_at_inception < 0 else ""),
                         ("<b>" if s.flips else "") + ("déficitaire" if s.onerous else "bénéficiaire")
                         + (" (bascule)</b>" if s.flips else "")] for s in sens.items]
    head = ["Hypothèse choquée", "Flux d'exécution", "CSM", "Perte", "Variation du résultat à l'origine", "Statut"]
    H.append(h_table(head, srows, ["hl"] + ["" for _ in sens.items]))
    H.append(f'<figure>{svg_tornado(sens)}<figcaption>Variation du résultat à l\'origine (CSM moins perte) par choc, '
             f'en {esc(unit)}. * : le groupe change de statut.</figcaption></figure>')
    M += m_table(head, srows)
    thresholds = []
    if sens.outflow_breakeven is not None:
        thresholds.append(f"Variation des sinistres et frais qui annule la marge : {pct(sens.outflow_breakeven)}.")
    if sens.rate_breakeven_shift is not None:
        thresholds.append(f"Translation parallèle des taux qui annule la marge : {snum(sens.rate_breakeven_shift * 100)} points.")
    else:
        thresholds.append("Aucune translation des taux comprise entre −5 et +5 points ne fait changer le groupe de statut.")
    thresholds.append(f"Duration des sorties (Macaulay) : {fr(macaulay_duration(p), 2)} périodes.")
    H.append('<div class="keep"><h3>Seuils et commentaire</h3><ul class="plain">'
             + "".join(f"<li>{esc(t)}</li>" for t in thresholds) + "</ul>"
             + (f"<p>{esc(commentary)}</p>" if commentary else "") + "</div>")
    M += [f"- {t}" for t in thresholds] + ["", commentary, ""]
    if conf is not None:
        crow = [[pct(c.level, 1), num(c.ra), pct(c.ra_pct), num(c.csm), num(c.loss),
                 "déficitaire" if c.onerous else "bénéficiaire"] for c in conf.rows]
        chead = ["Niveau de confiance", "Ajustement pour risque", "En % des sorties", "CSM", "Perte", "Statut"]
        ctext = (f"L'ajustement retenu ({pct(p.risk_adjustment_pct)} des sorties, soit {num(r.risk_adjustment)}) correspond à "
                 f"un niveau de confiance de {pct(conf.level_of_retained_ra, 1)} : méthode des quantiles, valeur actuelle des "
                 f"sorties supposée lognormale de coefficient de variation {pct(conf.cv, 1)} "
                 f"({ctx.ra_cv_source or 'hypothèse supposée'}). Le tableau donne l'ajustement "
                 f"qu'exigerait chaque niveau de confiance usuel et son effet sur la CSM ; §119 demande de publier ce niveau.")
        target = ""
        if ctx.ra_target_level:
            ra_t = ra_at_level(r.pv_outflows, conf.cv, ctx.ra_target_level)
            gap = r.risk_adjustment - ra_t
            target = (f"Niveau de confiance cible du registre des hypothèses : {pct(ctx.ra_target_level, 0)}, soit un "
                      f"ajustement de {num(ra_t)} ({pct(ra_t / r.pv_outflows if r.pv_outflows else 0)} des sorties). "
                      + (f"L'ajustement du document est inférieur de {num(-gap)} : à revoir avec l'actuaire."
                         if gap < -0.005 * max(ra_t, 1.0) else "L'ajustement du document atteint ce niveau."))
        declared, declared_warn = declared_text(p, r, conf)
        H.append('<div class="keep"><h3>Ajustement pour risque et niveau de confiance</h3>'
                 f"<p>{esc(ctext)}</p>" + (f'<div class="callout{" warn" if "à revoir" in target else ""}">{esc(target)}</div>'
                                           if target else "")
                 + (f'<div class="callout{" warn" if declared_warn else ""}">{esc(declared)}</div>' if declared else "")
                 + h_table(chead, crow) + "</div>")
        M += ["**Ajustement pour risque et niveau de confiance**", "", ctext, ""] + ([target, ""] if target else []) \
            + ([declared, ""] if declared else []) + m_table(chead, crow)

    # ---------------------------------------------------------------- 9. norme
    section(8)
    if not norm:
        H.append("<p>Norme non indexée : la note ne comporte pas de fondements cités.</p>")
        M += ["Norme non indexée : la note ne comporte pas de fondements cités.", ""]
    for nq in norm:
        if nq.answer.refused:
            H.append(f'<div class="qa"><p class="q">{esc(nq.question)}</p><p>Pas de réponse fiable dans la norme indexée.</p></div>')
            M += [f"**{nq.question}** — pas de réponse fiable dans la norme indexée.", ""]
            continue
        flag = "" if nq.verdict == "ok" else f' <span class="badge warn">vérificateur : {esc(nq.verdict)}</span>'
        quotes = "".join(f"<blockquote>[§{esc(c.paragraph_id)}] « {esc(c.quote)} »</blockquote>" for c in nq.answer.citations)
        H.append(f'<div class="qa"><p class="q">{esc(nq.question)}{flag}</p><p>{esc(nq.answer.answer or "")}</p>{quotes}</div>')
        M += [f"**{nq.question}**" + ("" if nq.verdict == "ok" else f" *(vérificateur : {nq.verdict})*"), "",
              nq.answer.answer or "", ""] + [f"> [§{c.paragraph_id}] « {c.quote} »" for c in nq.answer.citations] + [""]
    H.append('<p class="note">Source : règlement (UE) 2021/2036, texte officiel d\'IFRS 17 en français. Chaque citation est '
             'recopiée mot pour mot et vérifiée par le code ; chaque réponse est relue par l\'agent vérificateur.</p>')

    # ---------------------------------------------------------------- 10. contrôles
    section(9)
    limits = ["Niveau de confiance de l'ajustement pour risque calculé sous une hypothèse de loi (lognormale) ; volatilité "
              + ("mesurée sur des compagnies américaines (CAS Schedule P), à confirmer sur l'historique propre de l'entité."
                 if calibrated else "prudente (plus forte volatilité calibrée), faute d'historique pour cette branche."
                 if prudent else "supposée, la branche n'étant pas indiquée dans le document."
                 if "non indiquée" in ctx.ra_cv_source else "supposée, faute de calibration pour cette branche."),
              "Sans composante d'investissement, réassurance détenue ni contrats participatifs (VFA).",
              "Scénario central déterministe ; les sensibilités sont des chocs isolés, sans corrélation entre hypothèses.",
              "Produits des placements non modélisés : le résultat financier net n'est pas présenté."]
    H.append("<h3>Contrôles effectués</h3><ul class=\"plain checks\">" + "".join(f"<li>✓ {esc(c)}</li>" for c in checks) + "</ul>")
    H.append("<h3>Points à valider</h3>" + ("<ul class=\"plain checks\">" + "".join(f"<li>⚠ {esc(c)}</li>" for c in controls) + "</ul>"
                                             if controls else "<p>Aucun.</p>"))
    H.append("<h3>Limites</h3><ul class=\"plain\">" + "".join(f"<li>{esc(c)}</li>" for c in limits) + "</ul>")
    sign_rows = [["Préparée par", "IFRS 17 Copilot (génération automatique)", "Agents : extracteur, calculateur, chercheur, vérificateur, rédacteur", date_txt, ""],
                 ["Revue par", "", "Actuaire", "", ""], ["Approuvée par", "", "Direction financière", "", ""]]
    H.append('<div class="keep"><h3>Validation</h3>' + h_table(["Rôle", "Nom", "Fonction", "Date", "Visa"], [[esc(c) for c in row] for row in sign_rows], left_cols=5)
             .replace("<table>", '<table class="sign">')
             + '<p class="note">Relecture selon la grille actuarielle du projet (docs/grille_relecture_actuarielle.md) : '
             'données, hypothèses, calculs, norme, puis décision écrite.</p></div>')
    M += ["**Contrôles effectués**", ""] + [f"- ✓ {c}" for c in checks] + ["", "**Points à valider**", ""] \
        + ([f"- ⚠ {c}" for c in controls] or ["- Aucun."]) + ["", "**Limites**", ""] + [f"- {c}" for c in limits] + [""] \
        + m_table(["Rôle", "Nom", "Fonction", "Date", "Visa"], sign_rows)

    # ---------------------------------------------------------------- annexes
    trace = [("Référence du dossier", ctx.case_id or "—"), ("Établie le", date_txt),
             ("Application", f"IFRS 17 Copilot {ctx.app_version}".strip()),
             ("Moteur de calcul", "engine/csm.py, engine/analysis.py et engine/paa.py (Python, déterministe ; le LLM ne calcule jamais)"),
             *([("Registre des hypothèses", f"version {ctx.registry_version} (hypotheses/registre.json)")]
               if ctx.registry_version else []),
             ("Texte du résumé et du commentaire", "LLM, contrôlé par le code" if source == "llm" else "écrit par le code (repli)"),
             ("Document source", source_txt), ("Empreinte SHA-256", ctx.source_sha256 or "—")]
    trace += [(f"Prompt {k}", f"version {v}") for k, v in sorted(ctx.prompt_versions.items())]
    trace += [(f"Modèle {k}", v) for k, v in sorted(ctx.models.items()) if v]
    H.append('<section class="annex"><h2 id="annexes">Annexe A. Traçabilité</h2><dl class="trace">'
             + "".join(f"<dt>{esc(a)}</dt><dd>{esc(b)}</dd>" for a, b in trace) + "</dl>"
             "<h2>Annexe B. Glossaire</h2><dl class=\"trace gloss\">"
             + "".join(f"<dt>{esc(a)}</dt><dd>{esc(b)}</dd>" for a, b in GLOSSARY) + "</dl></section>")
    M += ["## Annexe A. Traçabilité", ""] + m_table(["Élément", "Valeur"], [[a, esc(b)] for a, b in trace])
    M += ["## Annexe B. Glossaire", ""] + [f"- **{a}** : {b}" for a, b in GLOSSARY] + [""]
    footer = ("Note générée par IFRS 17 Copilot, projet pédagogique, sur des données fictives ; sans valeur de conseil. "
              "Les montants viennent du moteur de calcul, jamais du LLM.")
    H.append(f"<footer>{esc(footer)}</footer>")
    M += [f"*{footer}*", ""]

    page = (f'<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>Note IFRS 17 — {esc(p.group_id)}</title><style>{CSS}</style></head>"
            f'<body><main class="page">{"".join(H)}</main></body></html>')
    return "\n".join(M), page


def combine_notes(case_id: str, groups: list[tuple[PortfolioData, CsmResult, object, list[str]]]) -> tuple[str, str]:
    """Document à plusieurs groupes (D-078) : une page de synthèse, puis la note complète de chaque groupe.
    Chaque groupe garde son évaluation, son test du groupe déficitaire (§16 à §17) et ses contrôles."""
    rows, cls = [], []
    for p, r, _, controls in groups:
        rows.append([esc(p.group_id), esc(unit_label(p)), num(r.fulfilment_cash_flows), num(r.initial_csm),
                     num(r.initial_loss_component), "déficitaire" if r.onerous else "bénéficiaire",
                     f'<span class="badge warn">{len(controls)} à valider</span>' if controls
                     else '<span class="badge ok">contrôles passés</span>'])
        cls.append("hl" if r.onerous else "")
    head = ["Groupe", "Unité", "Flux d'exécution", "CSM initiale", "Perte initiale", "Statut", "Contrôles"]
    n_bad = sum(1 for g in groups if g[3])
    intro = (f"Le document contient {len(groups)} groupes de contrats. Conformément au niveau d'agrégation de la norme "
             "(§14 à §24), chaque groupe est lu, évalué et testé séparément : un groupe déficitaire ne peut pas être "
             "compensé par un groupe bénéficiaire (§16, §47). Les notes complètes suivent, une par groupe.")
    toc = "".join(f'<li><a href="#g{k}">{esc(p.group_id)}</a></li>' for k, (p, _, _, _) in enumerate(groups))
    H = ['<header class="cover"><p class="kicker">Dossier IFRS 17 à plusieurs groupes</p>'
         f"<h1>Dossier {esc(case_id or '—')} : {len(groups)} groupes de contrats</h1>"
         f'<p><span class="badge {"warn" if n_bad else "ok"}">'
         f'{"À VALIDER PAR UN HUMAIN" if n_bad else "Contrôles automatiques passés"}</span></p></header>',
         f"<p>{esc(intro)}</p>", h_table(head, rows, cls),
         '<p class="note">Montants de chaque groupe dans sa propre unité ; aucune somme entre groupes.</p>',
         f'<nav class="toc"><h3>Notes par groupe</h3><ol>{toc}</ol></nav>']
    M = [f"# Dossier {case_id} : {len(groups)} groupes de contrats", "", intro, ""] \
        + m_table(head, [[re.sub(r"<[^>]+>", "", c) for c in row] for row in rows])
    for k, (_, _, note, _) in enumerate(groups):
        body = note.html.split('<main class="page">', 1)[1].rsplit("</main>", 1)[0]
        body = body.replace(' id="', f' id="g{k}-').replace('href="#', f'href="#g{k}-')   # ancres uniques
        H.append(f'<section class="annex" id="g{k}">{body}</section>')
        M += ["", "---", "", note.markdown]
    page = (f'<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>Dossier IFRS 17 — {len(groups)} groupes</title><style>{CSS}</style></head>"
            f'<body><main class="page">{"".join(H)}</main></body></html>')
    return "\n".join(M), page
