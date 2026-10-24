/* Vue d'ensemble : ce qui attend l'utilisateur, l'activité de l'équipe, la qualité et l'état du service. */
import { $, esc, fr, pct, ago, icon, me, canDo, getJSON, state, statusChip, SOURCE_LABEL, countUp, compact } from "../core.js";
import { mount, columns } from "../charts.js";

function spark(values) {
  const w = 160, h = 30, max = Math.max(1, ...values);
  const x = i => (i / Math.max(1, values.length - 1)) * w;
  const y = v => h - 2 - (v / max) * (h - 4);
  const d = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join("");
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><path class="sa" d="${d}L${w} ${h}L0 ${h}Z"/><path d="${d}"/></svg>`;
}

function hello() {
  const u = me();
  const first = u ? (u.display_name || u.username).split(/\s+/)[0] : "";
  const h = new Date().getHours();
  return `${h < 18 ? "Bonjour" : "Bonsoir"}${first ? `, ${esc(first)}` : ""}`;
}

export async function render(main) {
  main.innerHTML = `<div class="page">
    <div class="hello"><div>
      <h1>${hello()}</h1>
      <p id="ov-sub">${new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</p></div>
    </div>
    <dl class="kpis" id="ov-kpis">${'<div class="kpi"><dt>&nbsp;</dt><dd>&nbsp;</dd></div>'.repeat(4)}</dl>
    <div class="grid g-main">
      <div class="stack">
        <section class="panel"><div class="panel-head"><h2>Dossiers déposés, 30 derniers jours</h2><span class="meta" id="ov-total"></span></div>
          <div class="panel-body"><div class="chart-box" id="ov-chart" style="height:220px"></div></div></section>
        <section class="panel flush"><div class="panel-head"><h2>Derniers dossiers</h2><a class="more" href="#/dossiers">Tous les dossiers${icon("chevronR")}</a></div>
          <div class="panel-body" id="ov-recent"></div></section>
      </div>
      <div class="stack">
        <section class="panel flush"><div class="panel-head"><h2>À valider</h2><span class="meta" id="ov-wait-n"></span></div><div class="panel-body" id="ov-queue"></div></section>
        <section class="panel"><div class="panel-head"><h2>Répartition par statut</h2></div><div class="panel-body"><div class="rows" id="ov-status"></div></div>
          <div class="panel-head" style="padding-top:4px"><h2>Par canal de dépôt</h2></div><div class="panel-body"><div class="rows" id="ov-src"></div></div></section>
        <section class="panel"><div class="panel-head"><h2>Qualité et coût</h2></div><div class="panel-body"><dl class="health" id="ov-quality"></dl></div></section>
        <section class="panel"><div class="panel-head"><h2>État du service</h2></div><div class="panel-body"><dl class="health" id="ov-health"></dl></div></section>
      </div>
    </div></div>`;

  let unmount = () => {};
  const [d, recent, wait] = await Promise.all([getJSON("/v1/dashboard"), getJSON("/v1/cases?limit=6"), getJSON("/v1/cases?status=validation_humaine&limit=5")]);
  const days = d.par_jour;
  const last30 = days.reduce((a, j) => a + j.dossiers, 0);
  const waiting = d.par_statut.validation_humaine || 0;
  const oldest = d.en_attente[0];

  $("#ov-sub").textContent += waiting && canDo("valideur")
    ? ` · ${waiting} dossier${waiting > 1 ? "s attendent" : " attend"} votre décision` : waiting ? ` · ${waiting} dossier${waiting > 1 ? "s" : ""} en validation` : " · aucun dossier en attente";

  const kpis = [
    { label: "Dossiers sur 30 jours", value: last30, sub: `dont ${days.slice(-7).reduce((a, j) => a + j.dossiers, 0)} ces 7 derniers jours`, extra: spark(days.map(j => j.dossiers)) },
    { label: "Notes produites sans intervention", value: d.taux_note_directe * 100, fmt: v => `${fr(v, 0)} %`, sub: "tous les contrôles passés du premier coup" },
    { label: "En attente de validation", value: waiting, sub: oldest ? `le plus ancien ${ago(oldest.depuis)}` : "rien en attente" },
    { label: "Durée médiane d'analyse", value: d.duree_mediane_s ?? NaN, fmt: v => Number.isFinite(v) ? `${fr(v, 0)} s` : "—", sub: "du dépôt à la note" },
  ];
  $("#ov-kpis").innerHTML = kpis.map((k, i) => `<div class="kpi"><dt>${esc(k.label)}</dt><dd data-k="${i}">0</dd><small>${esc(k.sub)}</small>${k.extra || ""}</div>`).join("");
  kpis.forEach((k, i) => countUp($(`[data-k="${i}"]`), k.value, k.fmt || (v => fr(v, 0))));

  $("#ov-total").textContent = `${last30} dossier${last30 > 1 ? "s" : ""}`;
  const fmtDay = iso => new Date(iso + "T00:00:00").toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
  unmount = mount($("#ov-chart"), columns(days.map(j => ({ label: fmtDay(j.jour), value: j.dossiers,
    tip: new Date(j.jour + "T00:00:00").toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" }) })),
  { tickEvery: 7, format: v => `${fr(v, 0)} dossier${v > 1 ? "s" : ""}` }), 220);

  $("#ov-recent").innerHTML = recent.dossiers.length ? `<div class="table-wrap"><table class="table"><thead><tr>
      <th>Dossier</th><th>Statut</th><th class="r">CSM ou perte</th><th class="hide-sm">Canal</th><th class="r hide-sm">Mis à jour</th></tr></thead><tbody>
      ${recent.dossiers.map(c => `<tr class="click" data-href="#/dossiers/${encodeURIComponent(c.case_id)}">
        <td><a class="ref" href="#/dossiers/${encodeURIComponent(c.case_id)}">${esc(c.group_id || c.case_id)}</a><small>${esc(c.case_id)}</small></td>
        <td>${statusChip(c.status)}</td>
        <td class="r num">${c.csm == null ? "—" : c.onerous ? `<span class="neg">−${fr(c.loss)}</span>` : fr(c.csm)}${c.currency ? `<small>${esc(c.currency)}</small>` : ""}</td>
        <td class="hide-sm">${esc(SOURCE_LABEL[c.source] || c.source)}</td><td class="r hide-sm">${ago(c.updated_at)}</td></tr>`).join("")}
      </tbody></table></div>`
    : `<div class="empty">${icon("folder")}<h3>Aucun dossier pour l'instant</h3><p>Déposez un état de portefeuille pour obtenir votre première note.</p>
        ${canDo("analyste") ? `<a class="btn primary" href="#/nouveau">Déposer un dossier</a>` : ""}</div>`;
  main.querySelectorAll("tr[data-href]").forEach(tr => tr.addEventListener("click", e => { if (!e.target.closest("a")) location.hash = tr.dataset.href; }));

  $("#ov-wait-n").textContent = waiting ? `${waiting} dossier${waiting > 1 ? "s" : ""}` : "";
  $("#ov-queue").innerHTML = wait.dossiers.length ? `<div class="queue">${wait.dossiers.slice().reverse().map(w => `
      <a href="#/dossiers/${encodeURIComponent(w.case_id)}/donnees"><span class="qi">${icon("clock")}</span>
        <span><b>${esc(w.group_id || w.case_id)}</b><small>${esc((w.controls[0] || "un contrôle demande l'avis d'un valideur").replace(/^extraction : /, ""))}</small></span><span class="age">${ago(w.updated_at)}</span></a>`).join("")}</div>`
    : `<div class="empty" style="padding:28px 20px">${icon("check")}<p>Aucun dossier n'attend de décision.</p></div>`;

  const order = ["note_prete", "validee", "validation_humaine", "rejetee", "document_illisible", "erreur", "en_cours"];
  const maxS = Math.max(1, ...order.map(k => d.par_statut[k] || 0));
  $("#ov-status").innerHTML = order.filter(k => d.par_statut[k]).map(k => `<div class="row-bar">
      <span>${statusChip(k)}</span><span class="track"><span class="fill" style="display:block;width:${(d.par_statut[k] / maxS) * 100}%"></span></span>
      <span class="v">${d.par_statut[k]}</span></div>`).join("") || `<p class="cell-sub">Pas encore de dossier.</p>`;

  const srcs = Object.entries(d.par_source).sort((a, b) => b[1] - a[1]);
  const maxC = Math.max(1, ...srcs.map(x => x[1]));
  $("#ov-src").innerHTML = srcs.map(([k, v]) => `<div class="row-bar"><span>${esc(SOURCE_LABEL[k] || k)}</span>
      <span class="track"><span class="fill" style="display:block;width:${(v / maxC) * 100}%"></span></span><span class="v">${v}</span></div>`).join("") || `<p class="cell-sub">—</p>`;
  const delay = d.delai_median_validation_h;
  $("#ov-quality").innerHTML = [
    ["Validation humaine demandée", pct(d.taux_validation_humaine)],
    ["Délai médian de décision", delay == null ? "—" : delay >= 48 ? `${fr(delay / 24, 1)} jours` : `${fr(delay, 1)} h`],
    ["Groupes déficitaires dès l'origine", d.groupes_deficitaires],
    ["Appels au modèle par dossier", fr(d.appels_llm_moyens, 1)],
    ["Jetons consommés", compact(d.tokens_total)],
    ["Coût des modèles", `${fr(d.cout_total_usd, 2)} $`],
  ].map(([k, v]) => `<div><dt>${esc(k)}</dt><dd class="num">${esc(String(v))}</dd></div>`).join("");

  const h = state.health || await fetch("/health").then(r => r.json()).catch(() => null);
  $("#ov-health").innerHTML = h ? [
    ["API", `<span class="status ok">En ligne</span>`], ["Version", esc(h.version)],
    ["Modèle de langage", esc(h.llm_provider === "fake" ? "factice (tests)" : h.llm_provider)],
    ["Recherche dans la norme", esc(`${h.rag.mode}${h.rag.agent_langgraph ? " + agent LangGraph" : ""}`)],
    ["Base vectorielle", esc(h.rag.store || "—")],
    ["Vérificateur", h.rag.verificateur ? "actif" : "désactivé"],
  ].map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("")
    : `<div><dt>API</dt><dd><span class="status bad">Injoignable</span></dd></div>`;
  return () => unmount();
}
