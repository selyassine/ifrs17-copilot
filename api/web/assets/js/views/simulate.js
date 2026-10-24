/* Simulateur : modèle général sur plusieurs années (BBA) et méthode d'affectation des primes (PAA). */
import { $, $$, esc, fr, icon, getJSON } from "../core.js";
import { mount, lines, legend } from "../charts.js";

const numList = (s, pct = false) => String(s || "").split(";").map(x => x.trim()).filter(Boolean).map(x => {
  const v = Number(x.replace(/\s/g, "").replace(",", "."));
  if (!Number.isFinite(v)) throw new Error(`« ${x} » n'est pas un nombre`);
  return pct ? v / 100 : v;
});
const numOf = s => numList(s)[0] ?? 0;
const money = v => { const x = Math.abs(v) < 0.5 ? 0 : v; return `<td class="${x < 0 ? "neg" : ""}">${fr(x, 0)}</td>`; };

export async function render(main, _p, query) {
  let mode = query.get("m") === "paa" ? "paa" : "bba";
  let unmount = () => {};
  main.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>Simulateur</h1>
      <p>Le moteur suit un groupe de contrats dans le temps, sans modèle de langage. Les exemples chargés viennent d'un cours IFRS 17 ; le moteur les retrouve à l'euro près.</p></div></div>
    <div class="tabs" role="tablist"><button role="tab" data-m="bba" aria-selected="${mode === "bba"}">Modèle général (BBA)</button>
      <button role="tab" data-m="paa" aria-selected="${mode === "paa"}">Affectation des primes (PAA)</button></div>
    <div id="sm-body"></div></div>`;

  function bba(el) {
    el.innerHTML = `<div class="sim"><form class="panel" id="b-form"><div class="panel-head"><h2>Hypothèses</h2><button class="btn sm ghost" type="button" id="b-ex">${icon("refresh")}Exemple du cours</button></div>
      <div class="panel-body" style="display:grid;gap:14px">
        <label class="field">Prime unique à l'origine<input id="b-premium" inputmode="decimal"></label>
        <label class="field">Sinistres attendus par année<input id="b-expected"><small>une valeur par année, séparées par « ; »</small></label>
        <label class="field">Sinistres réels par année<input id="b-actual"><small>vide : comme attendus</small></label>
        <label class="field">Taux d'actualisation (%)<input id="b-rates"><small>à l'origine, puis à chaque clôture</small></label>
        <div class="two"><label class="field">Ajustement pour risque<input id="b-ra" inputmode="decimal"></label>
          <label class="field">Effet des taux<select id="b-option"><option value="OCI">en OCI (§88 b)</option><option value="PL">en résultat</option></select></label></div>
        <label class="field">Variation du RA (services futurs)<input id="b-rachg"><small>par année ; vide : aucune</small></label>
        <label class="field">Révision des sinistres futurs<input id="b-rev"><small>« 3 : 200000 ; 200000 ; 200000 ; 220000 » = connue à la clôture de l'année 3</small></label>
        <label class="field">Unités de couverture<input id="b-cu"><small>par année ; vide : 1 par an</small></label>
        <button class="btn primary" type="submit">${icon("chart")}Calculer</button></div></form>
      <div class="stack" id="b-out"></div></div>`;
    const ex = () => {
      $("#b-premium").value = "1000000"; $("#b-expected").value = "200000 ; 200000 ; 200000 ; 200000";
      $("#b-actual").value = "200000 ; 220000 ; 220000 ; 220000"; $("#b-rates").value = "4,2 ; 4,3 ; 4,4 ; 3,5 ; 3,0";
      $("#b-ra").value = "50000"; $("#b-rachg").value = "0 ; 5000 ; 0 ; 0"; $("#b-rev").value = "3 : 200000 ; 200000 ; 200000 ; 220000";
      $("#b-cu").value = "100 ; 100 ; 100 ; 100"; $("#b-option").value = "OCI";
    };
    $("#b-ex").addEventListener("click", () => { ex(); $("#b-form").requestSubmit(); });
    ex();
    $("#b-form").addEventListener("submit", async e => {
      e.preventDefault();
      const out = $("#b-out");
      try {
        const rev = $("#b-rev").value.trim();
        const revisions = rev ? [{ at_end_of_year: Number(rev.split(":")[0]), expected_claims: numList(rev.split(":")[1]) }] : [];
        const body = { group_id: "SIMULATION", single_premium: numOf($("#b-premium").value), expected_claims: numList($("#b-expected").value),
          actual_claims: $("#b-actual").value.trim() ? numList($("#b-actual").value) : null, rates: numList($("#b-rates").value, true),
          ra_initial: numOf($("#b-ra").value), ra_changes: $("#b-rachg").value.trim() ? numList($("#b-rachg").value) : null,
          claim_revisions: revisions, coverage_units: $("#b-cu").value.trim() ? numList($("#b-cu").value) : null, finance_option: $("#b-option").value };
        const r = await getJSON("/v1/csm/rollforward", { method: "POST", json: body });
        const ys = r.years;
        const head = ys.map(y => `<th>Année ${y.year}</th>`).join("");
        const line = (l, f) => `<tr><td>${l}</td>${ys.map(y => money(f(y))).join("")}</tr>`;
        const tot = (l, f) => `<tr class="tot"><td>${l}</td>${ys.map(y => money(f(y))).join("")}</tr>`;
        const grp = t => `<tr class="grp"><td colspan="${ys.length + 1}">${t}</td></tr>`;
        out.innerHTML = `<section class="panel"><div class="panel-body"><dl class="figs">
            <div><dt>Meilleure estimation à l'origine</dt><dd class="num">${fr(r.bel_initial, 0)}</dd></div>
            <div class="hero ${r.loss_initial > 0 ? "loss" : ""}"><dt>${r.loss_initial > 0 ? "Perte à l'origine" : "Marge à l'origine"}</dt><dd class="num">${fr(r.loss_initial > 0 ? r.loss_initial : r.csm_initial, 0)}</dd></div>
            <div><dt>Résultat total</dt><dd class="num">${fr(r.total_profit, 0)}</dd></div><div><dt>OCI cumulé</dt><dd class="num">${fr(r.total_oci, 0)}</dd></div></dl></div></section>
          <section class="panel"><div class="panel-head"><h2>Passif d'assurance en fin d'année</h2></div><div class="panel-body">
            ${legend([{ name: "Meilleure estimation (BEL)" }, { name: "Marge (CSM)" }, { name: "Ajustement pour risque" }])}<div class="chart-box" id="b-chart" style="height:250px"></div></div></section>
          <section class="panel flush"><div class="panel-head"><h2>Mouvements année par année</h2><span class="meta">unités monétaires</span></div>
            <div class="panel-body table-wrap"><table class="sim-table"><thead><tr><th></th>${head}</tr></thead><tbody>
            ${grp("Meilleure estimation (BEL)")}<tr><td>Taux d'ouverture puis de clôture</td>${ys.map(y => `<td>${fr(y.rate_open * 100, 1)} % → ${fr(y.rate_close * 100, 1)} %</td>`).join("")}</tr>
            ${line("BEL d'ouverture", y => y.bel_open)}${line("Intérêts au taux d'ouverture", y => y.bel_interest)}${line("Sinistres attendus de l'année", y => y.bel_claims_expected)}
            ${line("Révision des sinistres futurs", y => y.bel_estimate_change)}${line("Effet du changement de taux", y => y.bel_rate_effect)}${tot("BEL de clôture", y => y.bel_close)}
            ${grp("Ajustement pour risque (RA)")}${line("RA d'ouverture", y => y.ra_open)}${line("Variation pour services futurs", y => y.ra_future_change)}${line("Libération", y => -y.ra_release)}${tot("RA de clôture", y => y.ra_close)}
            ${grp("Marge sur services contractuels (CSM)")}${line("CSM d'ouverture", y => y.csm_open)}${line("Capitalisation au taux bloqué", y => y.csm_accretion)}${line("Ajustement pour services futurs", y => y.csm_adjustment)}
            <tr><td>Part libérée (unités de couverture)</td>${ys.map(y => `<td>${fr(y.coverage_ratio * 100, 0)} %</td>`).join("")}</tr>
            ${line("Libération en résultat", y => -y.csm_release)}${tot("CSM de clôture", y => y.csm_close)}${line("Composante de perte en clôture", y => y.loss_component_close)}
            ${grp("Compte de résultat IFRS 17")}${line("Produits des activités d'assurance", y => y.insurance_revenue)}${line("Charges des activités d'assurance", y => -y.insurance_service_expenses)}
            ${line("dont écart d'expérience", y => -y.experience_adjustment)}${tot("Résultat des activités d'assurance", y => y.insurance_service_result)}
            ${line("Charges financières d'assurance", y => y.insurance_finance_expense)}${tot("Résultat", y => y.profit)}${line("Autres éléments du résultat global (OCI)", y => y.oci)}
            </tbody></table></div></section>`;
        unmount();
        unmount = mount($("#b-chart"), lines(ys.map(y => `Année ${y.year}`), [
          { name: "BEL", values: ys.map(y => y.bel_close) }, { name: "CSM", values: ys.map(y => y.csm_close) }, { name: "RA", values: ys.map(y => y.ra_close) }]), 250);
      } catch (err) { out.innerHTML = `<div class="callout bad">${icon("alert")}<div><b>Calcul impossible</b><p>${esc(err.message)}</p></div></div>`; }
    });
    $("#b-form").requestSubmit();
  }

  function paa(el) {
    el.innerHTML = `<div class="sim"><form class="panel" id="p-form"><div class="panel-head"><h2>Contrat et sinistre</h2><button class="btn sm ghost" type="button" id="p-ex">${icon("refresh")}Cas n°1 du cours</button></div>
      <div class="panel-body" style="display:grid;gap:14px">
        <div class="two"><label class="field">Prime<input id="p-premium" inputmode="decimal"></label><label class="field">Frais d'acquisition<input id="p-acq" inputmode="decimal"></label></div>
        <div class="two"><label class="field">Début de couverture<input type="date" id="p-start"></label><label class="field">Durée (mois)<input id="p-months" inputmode="numeric"></label></div>
        <label class="field">Traitement des frais d'acquisition<select id="p-option"><option value="1">en charge à leur paiement (§59 a)</option><option value="0">dans la LRC, amortis</option></select></label>
        <div class="two"><label class="field">Survenance du sinistre<input type="date" id="p-occ"></label><label class="field">Provision<input id="p-est" inputmode="decimal"></label></div>
        <div class="two"><label class="field">Ajustement pour risque<input id="p-ra" inputmode="decimal"></label><label class="field">Date du règlement<input type="date" id="p-paidon"></label></div>
        <label class="field">Montant réglé<input id="p-paid" inputmode="decimal"></label>
        <label class="field">Dates de clôture<input id="p-dates"><small>AAAA-MM-JJ séparées par « ; »</small></label>
        <button class="btn primary" type="submit">${icon("chart")}Calculer</button></div></form>
      <div class="stack" id="p-out"></div></div>`;
    const ex = () => {
      $("#p-premium").value = "1000"; $("#p-start").value = "2025-07-01"; $("#p-months").value = "12"; $("#p-acq").value = "30"; $("#p-option").value = "1";
      $("#p-occ").value = "2026-05-15"; $("#p-est").value = "750"; $("#p-ra").value = "50"; $("#p-paidon").value = "2026-10-15"; $("#p-paid").value = "900";
      $("#p-dates").value = "2025-12-31 ; 2026-06-30 ; 2026-12-31";
    };
    $("#p-ex").addEventListener("click", () => { ex(); $("#p-form").requestSubmit(); });
    ex();
    $("#p-form").addEventListener("submit", async e => {
      e.preventDefault();
      const out = $("#p-out");
      try {
        const claims = $("#p-occ").value ? [{ occurred: $("#p-occ").value, estimate: numOf($("#p-est").value), risk_adjustment: numOf($("#p-ra").value),
          paid_on: $("#p-paidon").value || null, paid_amount: $("#p-paidon").value ? numOf($("#p-paid").value) : null }] : [];
        const body = { contract: { group_id: "PAA", premium: numOf($("#p-premium").value), coverage_start: $("#p-start").value, coverage_months: Number($("#p-months").value),
          acquisition_costs: numOf($("#p-acq").value), expense_acquisition_costs: $("#p-option").value === "1", claims },
        at: $("#p-dates").value.split(";").map(x => x.trim()).filter(Boolean) };
        const rows = await getJSON("/v1/paa/position", { method: "POST", json: body });
        const line = (l, f) => `<tr><td>${l}</td>${rows.map(p => money(f(p))).join("")}</tr>`;
        const last = rows.at(-1);
        out.innerHTML = `<section class="panel"><div class="panel-body"><dl class="figs">
            <div><dt>Couverture restante (LRC)</dt><dd class="num">${fr(last.lrc, 0)}</dd></div><div><dt>Sinistres survenus (LIC)</dt><dd class="num">${fr(last.lic, 0)}</dd></div>
            <div class="hero"><dt>Résultat cumulé</dt><dd class="num">${fr(last.result_to_date, 0)}</dd></div><div><dt>Au</dt><dd class="num" style="font-size:18px">${esc(last.at)}</dd></div></dl></div></section>
          <section class="panel"><div class="panel-head"><h2>Passifs à chaque clôture</h2></div><div class="panel-body">${legend([{ name: "LRC" }, { name: "LIC" }])}<div class="chart-box" id="p-chart" style="height:230px"></div></div></section>
          <section class="panel flush"><div class="panel-head"><h2>Positions</h2></div><div class="panel-body table-wrap"><table class="sim-table"><thead><tr><th></th>${rows.map(p => `<th>${esc(p.at)}</th>`).join("")}</tr></thead><tbody>
            <tr><td>Mois de couverture écoulés</td>${rows.map(p => `<td>${p.months_elapsed}</td>`).join("")}</tr>
            ${line("Passif pour couverture restante (LRC)", p => p.lrc)}${line("Passif pour sinistres survenus (LIC)", p => p.lic)}
            <tr class="grp"><td colspan="${rows.length + 1}">Résultat cumulé</td></tr>
            ${line("Produits des activités d'assurance", p => p.revenue_to_date)}${line("Frais d'acquisition en charge", p => -p.acquisition_expense_to_date)}
            ${line("Sinistres et ajustement pour risque", p => -p.claims_expense_to_date)}<tr class="tot"><td>Résultat cumulé</td>${rows.map(p => money(p.result_to_date)).join("")}</tr></tbody></table></div></section>`;
        unmount();
        unmount = mount($("#p-chart"), lines(rows.map(p => p.at), [{ name: "LRC", values: rows.map(p => p.lrc) }, { name: "LIC", values: rows.map(p => p.lic) }]), 230);
      } catch (err) { out.innerHTML = `<div class="callout bad">${icon("alert")}<div><b>Calcul impossible</b><p>${esc(err.message)}</p></div></div>`; }
    });
    $("#p-form").requestSubmit();
  }

  const show = m => {
    mode = m; unmount(); unmount = () => {};
    $$(".tabs [role=tab]", main).forEach(b => b.setAttribute("aria-selected", String(b.dataset.m === m)));
    history.replaceState(null, "", `#/simulateur${m === "paa" ? "?m=paa" : ""}`);
    (m === "paa" ? paa : bba)($("#sm-body"));
  };
  $$(".tabs [role=tab]", main).forEach(b => b.addEventListener("click", () => show(b.dataset.m)));
  show(mode);
  return () => unmount();
}
