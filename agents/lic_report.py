"""Note d'évaluation du passif pour sinistres survenus (LIC, D-083), écrite entièrement par le code.

Tous les montants viennent de ``engine/lic.py`` (Chain Ladder, Mack, actualisation, RA) ; aucun LLM n'écrit dans
cette note (D-005). Les références à la norme sont fixes : elles désignent les paragraphes qui fondent chaque
étape du calcul, pas une réponse du chercheur RAG.
"""

from __future__ import annotations

from datetime import datetime

from agents.note_report import CSS, esc, h_table, m_table, num, pct
from agents.schemas import TriangleData
from engine.lic import LicResult

UNIT = {1: "", 1_000: "milliers de ", 1_000_000: "millions de "}


def _f(x: float, d: int = 4) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def render_lic_note(t: TriangleData, r: LicResult, case_id: str = "", controls: list[str] | None = None,
                    checks: list[str] | None = None, entity: str = "Compagnie d'assurance fictive (projet pédagogique)",
                    source_name: str = "", source_sha256: str = "", double_read: str = "", warnings: list[str] | None = None,
                    human_changes: list[str] | None = None, validated_by: str = "") -> tuple[str, str]:
    controls = controls or []
    checks = checks or []
    unit = f"{UNIT[t.unit_multiplier]}{t.currency}"
    date_txt = datetime.now().strftime("%d/%m/%Y à %H:%M")
    title = f"Passif pour sinistres survenus — {t.portfolio_id}"
    status = "À VALIDER PAR UN HUMAIN" if controls else "Contrôles automatiques passés"
    H: list[str] = []
    M: list[str] = [f"# Note IFRS 17 — {title}", "", f"**Statut : {status}**", ""]
    meta = [("Entité", entity), ("Portefeuille", t.portfolio_id),
            ("Branche", t.line_of_business or "non indiquée"),
            ("Date de clôture", t.valuation_date or "non indiquée"),
            ("Années de survenance", f"{t.origin_years[0]} à {t.origin_years[-1]} ({t.n_years})"),
            ("Monnaie et unité", f"Montants en {unit}"),
            ("Document source", source_name or "—"), ("Référence du dossier", case_id or "—"), ("Établie le", date_txt)]
    H.append('<header class="cover"><p class="kicker">Note IFRS 17 · passif pour sinistres survenus (LIC)</p>'
             f'<h1>{esc(title)}</h1><p class="subtitle">Meilleure estimation actualisée des paiements futurs, ajustement '
             f'au titre du risque non financier et niveau de confiance</p>'
             f'<p><span class="badge {"warn" if controls else "ok"}">{esc(status)}</span></p><dl class="meta">'
             + "".join(f"<dt>{esc(a)}</dt><dd>{esc(b)}</dd>" for a, b in meta) + "</dl></header>")
    M += m_table(["Élément", "Valeur"], [[a, esc(b)] for a, b in meta])

    def h2(i: int, name: str) -> None:
        H.append(f"<h2>{i}. {esc(name)}</h2>")
        M.extend([f"## {i}. {name}", ""])

    # 1. résumé
    h2(1, "Résumé")
    kpis = [("Provision non actualisée (Chain Ladder)", num(r.reserve)),
            ("Meilleure estimation actualisée (BEL)", num(r.bel)),
            (f"Ajustement pour risque (quantile {pct(r.level, 0)})", num(r.risk_adjustment)),
            ("Passif pour sinistres survenus (LIC)", num(r.lic))]
    H.append('<div class="kpis">' + "".join(f'<div class="kpi"><div class="l">{esc(a)}</div><div class="v">{esc(b)}</div>'
                                           "</div>" for a, b in kpis) + "</div>")
    summary = (f"Au {t.valuation_date or 'jour de la clôture'}, les paiements futurs des {t.n_years} années de survenance "
               f"sont estimés à {num(r.reserve)} ({unit}) par la méthode Chain Ladder. Actualisés aux taux spot, ils "
               f"valent {num(r.bel)} (effet de l'actualisation : {num(r.discount_effect)}, duration "
               f"{_f(r.duration, 2)} ans). L'erreur de prédiction de Mack est de {num(r.mack_se)}, soit un coefficient "
               f"de variation de {pct(r.mack_se / r.reserve if r.reserve else 0, 1)}. L'ajustement pour risque au "
               f"quantile {pct(r.level, 0)} d'une loi lognormale de coefficient de variation {pct(r.cv, 1)} est de "
               f"{num(r.risk_adjustment)} ({pct(r.risk_adjustment / r.bel if r.bel else 0, 1)} de la meilleure "
               f"estimation). Le passif pour sinistres survenus s'élève à {num(r.lic)}.")
    H.append(f"<p>{esc(summary)}</p>")
    M += [f"- **{a}** : {b}" for a, b in kpis] + ["", summary, ""]
    if controls:
        H.append('<div class="callout warn"><b>Points à valider avant diffusion</b><ul>'
                 + "".join(f"<li>{esc(c)}</li>" for c in controls) + "</ul></div>")
        M += ["**Points à valider avant diffusion :**", ""] + [f"- {c}" for c in controls] + [""]

    # 2. données
    h2(2, "Données : triangle des paiements")
    n = t.n_years
    cum = t.cumulative_triangle()
    head = ["Survenance"] + (["Prime"] if t.premiums else []) + [f"Ret. {k + 1}" for k in range(n)]
    rows = []
    for i in range(n):
        rows.append([esc(t.origin_years[i])] + ([num(t.premiums[i], 0)] if t.premiums else [])
                    + [num(x, 0) for x in cum[i]] + [""] * i)
    H.append(h_table(head, rows))
    M += m_table(head, rows)
    how = ("paiements cumulés tels que lus" if t.cumulative else "paiements de l'année lus dans le document, cumulés par le code")
    read = {"concordante": "lecture du modèle de langage et relecture du triangle par le code concordantes, cellule par cellule",
            "divergente": "la relecture du triangle par le code diffère de la lecture du modèle : voir les points à valider",
            "impossible": "relecture du triangle par le code impossible (mise en page) : contrôle d'ancrage seul",
            "": "données fournies ou validées par un humain"}[double_read]
    txt = (f"Montants en {unit} ; {how}. Chaque montant a été retrouvé dans le document (contrôle d'ancrage) ; {read}."
           + (f" Document : {source_name}" + (f", empreinte SHA-256 {source_sha256[:16]}…" if source_sha256 else "") + "."
              if source_name else ""))
    H.append(f'<p class="note">{esc(txt)}</p>')
    M += [txt, ""]
    if human_changes:
        H.append("<p><b>Modifications du valideur :</b> " + esc(" ; ".join(human_changes)) + "</p>")
        M += ["**Modifications du valideur :** " + " ; ".join(human_changes), ""]

    # 3. méthode
    h2(3, "Méthode et hypothèses")
    rates = r.rates
    hyp = [["Estimation des paiements futurs", "Chain Ladder, facteurs de développement pondérés par les volumes"
            + ("" if r.tail == 1.0 else f", facteur de queue {_f(r.tail, 4)}") + ", sans facteur de queue" * (r.tail == 1.0),
            "§33, B37 à B41"],
           ["Calendrier des paiements", "Diagonales futures du triangle complété, payées en fin d'année calendaire", "§33(c)"],
           ["Actualisation", ("taux plat de " + pct(rates[0]) if len(set(rates)) == 1 else
                              "taux spot par échéance : " + " ; ".join(pct(x) for x in rates)), "§36, B72(a)"],
           ["Incertitude de la provision", "Erreur de prédiction de Mack (1993), covariance entre années comprise", "B86 à B92"],
           ["Ajustement pour risque", f"quantile {pct(r.level, 0)} d'une loi lognormale de la meilleure estimation, "
            f"coefficient de variation {pct(r.cv, 1)} ({r.cv_source})", "§37, B86 à B92"],
           ["Niveau de confiance publié", f"{pct(r.level, 0)}", "§119"],
           ["Passif pour sinistres survenus", "Flux d'exécution relatifs aux services passés : BEL + RA", "§40(b), annexe A"]]
    H.append(h_table(["Étape", "Hypothèse retenue", "Référence"], [[esc(a), esc(b), esc(c)] for a, b, c in hyp], left_cols=2))
    M += m_table(["Étape", "Hypothèse retenue", "Référence"], hyp)

    # 4. développement
    h2(4, "Facteurs de développement et variances de Mack")
    drow = [[f"{k + 1} → {k + 2}", _f(r.factors[k]), _f(r.sigma2[k], 3)] for k in range(n - 1)]
    H.append(h_table(["Retard", "Facteur f", "σ² de Mack"], drow))
    M += m_table(["Retard", "Facteur f", "σ² de Mack"], drow)
    note_s = "Le dernier σ² (une seule observation) est extrapolé selon Mack (1993) : min(σ⁴ₙ₋₂ / σ²ₙ₋₃ ; σ²ₙ₋₃ ; σ²ₙ₋₂)."
    H.append(f'<p class="note">{esc(note_s)}</p>')
    M += [note_s, ""]

    # 5. par survenance
    h2(5, "Résultats par année de survenance")
    yhead = ["Survenance", "Dernier cumul", "Facteur restant", "Ultime", "Provision", "Erreur de Mack", "CV"] + \
        (["S/P ultime"] if t.premiums else [])
    yrows = [[esc(x.label), num(x.latest, 0), _f(x.development), num(x.ultimate), num(x.reserve), num(x.mack_se),
              pct(x.mack_se / x.reserve, 1) if x.reserve > 0.005 else "—"]
             + ([pct(x.loss_ratio, 1) if x.loss_ratio is not None else "—"] if t.premiums else []) for x in r.rows]
    tot = ["Total", num(sum(x.latest for x in r.rows), 0), "", num(sum(x.ultimate for x in r.rows)), num(r.reserve),
           num(r.mack_se), pct(r.mack_se / r.reserve, 1) if r.reserve else "—"] + ([""] if t.premiums else [])
    H.append(h_table(yhead, yrows + [tot], [""] * len(yrows) + ["total"]))
    M += m_table(yhead, yrows + [tot])

    # 6. paiements futurs et actualisation
    h2(6, "Paiements futurs et actualisation")
    crow = [[f"Année {k + 1}", num(c), pct(r.rates[k]), _f(r.discount[k]), num(c * r.discount[k])]
            for k, c in enumerate(r.cash_flows)]
    ctot = ["Total", num(sum(r.cash_flows)), "", "", num(r.bel)]
    H.append(h_table(["Échéance", "Paiements attendus", "Taux spot", "Facteur d'actualisation", "Valeur actuelle"],
                     crow + [ctot], [""] * len(crow) + ["total"]))
    M += m_table(["Échéance", "Paiements attendus", "Taux spot", "Facteur d'actualisation", "Valeur actuelle"], crow + [ctot])

    # 7. RA et niveau de confiance
    h2(7, "Ajustement pour risque et niveau de confiance")
    lrow = [[pct(lv, 1), num(ra), pct(ra / r.bel if r.bel else 0, 1), num(lic)] for lv, ra, lic in r.levels]
    ltxt = (f"Méthode des quantiles : la meilleure estimation est supposée suivre une loi lognormale de coefficient de "
            f"variation {pct(r.cv, 1)} ({r.cv_source}). Le tableau donne l'ajustement et le passif à chaque niveau de "
            f"confiance usuel ; le niveau retenu, {pct(r.level, 0)}, est publié (§119).")
    H.append(f"<p>{esc(ltxt)}</p>" + h_table(["Niveau de confiance", "Ajustement pour risque", "En % du BEL", "LIC"], lrow))
    M += [ltxt, ""] + m_table(["Niveau de confiance", "Ajustement pour risque", "En % du BEL", "LIC"], lrow)

    # 8. sensibilités
    h2(8, "Sensibilités")
    srow = [[f"Taux {'+' if s > 0 else '−'}{_f(abs(s), 0)} point", num(b), num(lic), num(lic - r.lic)]
            for s, b, lic in r.rate_shocks]
    H.append(h_table(["Scénario", "BEL", "LIC", "Écart sur le LIC"], srow))
    M += m_table(["Scénario", "BEL", "LIC", "Écart sur le LIC"], srow)

    # 9. contrôles, limites, validation
    h2(9, "Contrôles, limites et validation")
    limits = ["Méthode de Mack : facteurs de développement indépendants des années de survenance et variance "
              "proportionnelle aux montants cumulés ; à vérifier sur les résidus avant diffusion.",
              "Sans facteur de queue sauf indication du document : un développement au-delà du dernier retard observé "
              "n'est pas provisionné." if r.tail == 1.0 else f"Facteur de queue {_f(r.tail, 4)} : payé l'année qui suit "
              "la dernière diagonale ; non pris en compte dans l'erreur de Mack.",
              "Paiements nets de réassurance tels que fournis : la réassurance détenue n'est pas évaluée à part (§60 à §70).",
              "Ajustement pour risque calculé sous une hypothèse de loi (lognormale) ; la diversification entre "
              "portefeuilles n'est pas prise en compte.",
              "Montants calculés par le moteur Python ; aucune partie de cette note n'est écrite par un LLM."]
    if checks:
        H.append("<h3>Contrôles effectués</h3><ul class=\"plain checks\">" + "".join(f"<li>✓ {esc(c)}</li>" for c in checks)
                 + "</ul>")
    H.append("<h3>Points à valider</h3>" + ("<ul class=\"plain checks\">" + "".join(f"<li>⚠ {esc(c)}</li>" for c in controls)
                                             + "</ul>" if controls else "<p>Aucun.</p>"))
    if warnings:
        H.append("<h3>Remarques du lecteur</h3><ul class=\"plain\">" + "".join(f"<li>{esc(w)}</li>" for w in warnings) + "</ul>")
    H.append("<h3>Limites</h3><ul class=\"plain\">" + "".join(f"<li>{esc(x)}</li>" for x in limits) + "</ul>")
    sign = [["Préparée par", "IFRS 17 Copilot", date_txt, ""],
            ["Revue par", validated_by, "", ""], ["Approuvée par", "", "", ""]]
    H.append('<div class="keep"><h3>Validation</h3>' + h_table(["Rôle", "Nom", "Date", "Visa"], sign, left_cols=4)
             .replace("<table>", '<table class="sign">') + "</div>")
    M += ["**Contrôles effectués**", ""] + [f"- ✓ {c}" for c in checks] + ["", "**Points à valider**", ""] \
        + ([f"- ⚠ {c}" for c in controls] or ["- Aucun."]) + ["", "**Limites**", ""] + [f"- {x}" for x in limits] + [""]
    page = (f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>LIC IFRS 17 — {esc(t.portfolio_id)}</title>'
            f'<style>{CSS}</style></head><body><main class="page">{"".join(H)}'
            '<footer>Note générée par IFRS 17 Copilot, projet pédagogique ; sans valeur de conseil. Les montants viennent '
            "du moteur de calcul, jamais du LLM.</footer></main></body></html>")
    return "\n".join(M), page
