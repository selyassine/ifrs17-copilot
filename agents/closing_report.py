"""Note de première clôture (D-076) : réalisé contre attendu, révision des estimations, CSM, résultat et
rapprochement du passif. Entièrement écrite par le code : aucun LLM, tous les montants viennent de
``engine/cloture.py`` (D-005)."""

from __future__ import annotations

from datetime import datetime

from agents.note_report import CSS, MINUS, esc, h_table, m_table, neg_span, num, pct, snum
from agents.schemas import CsmResult, PortfolioData
from agents.writer import unit_label
from engine.cloture import ClosingResult


def render_closing_note(p: PortfolioData, r: CsmResult, c: ClosingResult, case_id: str = "",
                        entity: str = "Compagnie d'assurance fictive (projet pédagogique)",
                        registry_version: str = "") -> tuple[str, str]:
    unit = unit_label(p)
    date_txt = datetime.now().strftime("%d/%m/%Y à %H:%M")
    title = f"Première clôture du groupe {p.group_id}" + (f" au {c.as_of}" if c.as_of else "")
    H: list[str] = []
    M: list[str] = [f"# Note de clôture IFRS 17 — {title}", ""]
    meta = [("Entité", entity), ("Groupe de contrats", p.group_id), ("Clôture", c.as_of or "fin de la période 1"),
            ("Méthode", "Modèle général (BBA), résultat financier d'assurance en résultat (sans OCI)"),
            ("Monnaie et unité", f"Montants en {unit}"), ("Référence du dossier", case_id or "—"),
            ("Établie le", date_txt)] + ([("Registre des hypothèses", f"version {registry_version}")]
                                         if registry_version else [])
    H.append('<header class="cover"><p class="kicker">Note de clôture IFRS 17</p>'
             f"<h1>{esc(title)}</h1><p class=\"subtitle\">Réalisé de la période, révision des estimations, CSM, "
             "résultat et rapprochement du passif</p><dl class=\"meta\">"
             + "".join(f"<dt>{esc(a)}</dt><dd>{esc(b)}</dd>" for a, b in meta) + "</dl></header>")
    M += m_table(["Élément", "Valeur"], [[a, esc(b)] for a, b in meta])

    def h2(i: int, name: str) -> None:
        H.append(f"<h2>{i}. {esc(name)}</h2>")
        M.extend([f"## {i}. {name}", ""])

    # 1. résumé
    h2(1, "Résumé")
    kpis = [("Résultat de la période", num(c.profit), c.profit < 0),
            ("dont résultat des services d'assurance", num(c.insurance_service_result), c.insurance_service_result < 0),
            ("Écarts d'expérience (effet sur le résultat)", snum(c.experience_adjustment), c.experience_adjustment < 0),
            ("Passif de clôture", num(c.closing_liability), False)]
    H.append('<div class="kpis">' + "".join(f'<div class="kpi{" neg" if bad else ""}"><div class="l">{esc(a)}</div>'
                                           f'<div class="v">{esc(b)}</div></div>' for a, b, bad in kpis) + "</div>")
    gap_res = c.insurance_service_result - c.expected_service_result
    where = ("ajuste la CSM (services futurs, B96(b))" if c.future_coverage
             else "passe en charges des services d'assurance (sinistres survenus, services passés, B97(b))")
    summary = (f"Le résultat des services d'assurance de la période est de {num(c.insurance_service_result)}, contre "
               f"{num(c.expected_service_result)} attendus à l'origine ({snum(gap_res)}). Les écarts d'expérience de la "
               f"période pèsent {snum(c.experience_adjustment)} sur le résultat (B97(c)). La révision des flux futurs, "
               f"{snum(c.future_flows_change + c.ra_future_change)} au taux bloqué (ajustement pour risque compris, "
               f"{'défavorable' if c.future_flows_change + c.ra_future_change > 0 else 'favorable'}), {where}"
               + (f" ; {num(c.new_loss)} dépassent la CSM et sont passés en perte (§48)" if c.new_loss > 0 else "")
               + (f" ; elle reprend {num(c.loss_reversal)} de composante de perte (§50(b))" if c.loss_reversal > 0 else "")
               + f". Le changement de taux pèse {snum(-c.rate_effect)} sur le résultat financier d'assurance.")
    H.append(f"<p>{esc(summary)}</p>")
    M += [f"- **{a}** : {b}" for a, b, _ in kpis] + ["", summary, ""]

    # 2. réalisé contre attendu
    h2(2, "Réalisé contre attendu de la période")
    rows = [["Primes (début de période)", num(c.expected_premium), num(c.actual_premium), snum(c.actual_premium - c.expected_premium)],
            ["Sinistres et frais payés (fin)", num(c.expected_outflow), num(c.actual_outflow), snum(c.actual_outflow - c.expected_outflow)]]
    if c.expected_recovery or c.actual_recovery:
        rows.append(["Recouvrements (fin, B65 k)", num(c.expected_recovery), num(c.actual_recovery),
                     snum(c.actual_recovery - c.expected_recovery)])
    if c.expected_acquisition or c.actual_acquisition:
        rows.append(["Frais d'acquisition (début, B65 e)", num(c.expected_acquisition), num(c.actual_acquisition),
                     snum(c.actual_acquisition - c.expected_acquisition)])
    rows.append(["Effet sur le résultat (+ favorable)", "", "", snum(c.experience_adjustment)])
    head = ["Flux de la période", "Attendu", "Réalisé", "Écart"]
    H.append(h_table(head, rows, [""] * (len(rows) - 1) + ["total"])
             + '<p class="note">Écarts d\'expérience : en résultat des services d\'assurance de la période, jamais dans '
             "la CSM (B97(c)) ; un écart de primes relatif à la période va en produits.</p>")
    M += m_table(head, rows)

    # 3. révision
    h2(3, "Révision des estimations à la clôture")
    rrows = [["Flux futurs nets (BEL) au taux bloqué", snum(c.future_flows_change)],
             ["Ajustement pour risque des flux futurs", snum(c.ra_future_change)],
             ["dont ajustement de la CSM (services futurs, §44(c))", snum(c.csm_adjustment)],
             ["dont perte, au-delà de la CSM (§48)", num(c.new_loss)],
             ["dont reprise de composante de perte (§50(b))", num(c.loss_reversal)],
             ["dont services passés, en charges (B97(b))", snum(c.past_service_change)],
             ["Effet du changement de taux (BEL et RA), en charges financières", snum(c.rate_effect)]]
    H.append(h_table(["Révision (+ = flux sortants plus élevés)", "Montant"], rrows,
                     ["", "", "sub", "sub", "sub", "sub", ""])
             + '<p class="note">Révisions mesurées au taux bloqué de la comptabilisation initiale (B72(c)) ; l\'écart '
             "entre taux courant et taux bloqué est financier (§87). Simplification : dès qu'il reste de la couverture, "
             "toute révision des flux futurs est rattachée aux services futurs.</p>")
    M += m_table(["Révision", "Montant"], rrows)

    # 4. CSM
    h2(4, "Marge sur services contractuels")
    crow = [["Ouverture", num(c.csm_open)], ["Intérêts au taux bloqué (§44(b))", num(c.csm_accretion)],
            ["Ajustement lié aux services futurs (§44(c))", snum(c.csm_adjustment)],
            ["Libération (unités de couverture, B119)", (MINUS if c.csm_release else "") + num(c.csm_release)],
            ["Clôture", num(c.csm_close)], ["Composante de perte en clôture", num(c.loss_component_close)]]
    H.append(h_table(["CSM", "Montant"], crow, ["", "", "", "", "total", "sub"]))
    M += m_table(["CSM", "Montant"], crow)

    # 5. compte de résultat
    h2(5, "Compte de résultat de la période")
    prow = [["Produits des activités d'assurance", num(c.insurance_revenue)],
            ["Charges des services d'assurance", neg_span(-c.insurance_service_expense)],
            ["Résultat des services d'assurance", neg_span(c.insurance_service_result)],
            ["Charges financières d'assurance", neg_span(-c.insurance_finance_expense)],
            ["Résultat de la période (hors produits des placements)", neg_span(c.profit)],
            ["Pour mémoire : résultat des services attendu à l'origine", neg_span(c.expected_service_result)]]
    H.append(h_table(["Compte de résultat", "Montant"], prow, ["", "", "total", "", "total", "sub"]))
    M += m_table(["Compte de résultat", "Montant"], prow)

    # 6. rapprochement
    h2(6, "Rapprochement du passif")
    cash = c.actual_premium - c.actual_acquisition - c.actual_outflow + c.actual_recovery
    arow = [["Passif avant la comptabilisation initiale", num(c.opening_liability)],
            ["+ primes encaissées", num(c.actual_premium)],
            *([["− frais d'acquisition payés", neg_span(-c.actual_acquisition)]] if c.actual_acquisition else []),
            ["− sinistres et frais payés", neg_span(-c.actual_outflow)],
            *([["+ recouvrements encaissés", num(c.actual_recovery)]] if c.actual_recovery else []),
            ["+ charges financières d'assurance", num(c.insurance_finance_expense)],
            ["− résultat des services d'assurance", neg_span(-c.insurance_service_result)],
            ["= passif de clôture (BEL + RA + CSM)", num(c.closing_liability)],
            ["dont meilleure estimation (BEL)", neg_span(c.bel_close)], ["dont ajustement pour risque", num(c.ra_close)],
            ["dont CSM", num(c.csm_close)],
            ["Écart de rapprochement (contrôle du code)", num(c.reconciliation_gap, 6)],
            ["Pour mémoire : passif de clôture attendu à l'origine", num(c.expected_closing_liability)]]
    H.append(h_table(["Mouvement", "Montant"], arow,
                     [""] * (len(arow) - 6) + ["total", "sub", "sub", "sub", "hl", "sub"])
             + f'<p class="note">Flux de trésorerie nets de la période : {esc(num(cash))}. L\'écart de rapprochement '
             "est recalculé par le code ; une valeur non nulle bloquerait la diffusion.</p>")
    M += m_table(["Mouvement", "Montant"], arow)

    # 7. méthode
    h2(7, "Méthode, limites et validation")
    limits = ["Première clôture seulement : les clôtures suivantes repartent de cet état (BEL, RA, CSM et taux bloqué).",
              "Toute révision des flux futurs est rattachée aux services futurs tant qu'il reste de la couverture ; "
              "l'entité devrait distinguer sinistres survenus et à survenir.",
              "Produits des placements non modélisés ; option OCI non retenue (§88(a)).",
              "Montants calculés par le moteur Python ; aucune partie de cette note n'est écrite par un LLM."]
    H.append("<ul class=\"plain\">" + "".join(f"<li>{esc(x)}</li>" for x in limits) + "</ul>")
    sign = [["Préparée par", "IFRS 17 Copilot", date_txt, ""], ["Revue par", "", "", ""], ["Approuvée par", "", "", ""]]
    H.append('<div class="keep"><h3>Validation</h3>' + h_table(["Rôle", "Nom", "Date", "Visa"], sign, left_cols=4)
             .replace("<table>", '<table class="sign">') + "</div>")
    M += [f"- {x}" for x in limits] + [""]
    page = (f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>Clôture IFRS 17 — {esc(p.group_id)}</title>'
            f'<style>{CSS}</style></head><body><main class="page">{"".join(H)}'
            '<footer>Note générée par IFRS 17 Copilot, projet pédagogique ; sans valeur de conseil.</footer>'
            "</main></body></html>")
    return "\n".join(M), page


__all__ = ["render_closing_note", "pct"]
