/* Fiche d'un dossier : synthèse chiffrée, note, données (corrigées et approuvées par un valideur),
   Copilot, piste d'audit. Un seul endroit pour suivre et décider. */
import { $, $$, esc, fr, pct, when, ago, icon, canDo, me, api, getJSON, statusChip, emit, toast, modal, confirmAction,
  SOURCE_LABEL, ACTION_LABEL, ROLE_LABEL, unitLabel, printHTML, downloadText, refLabel, state } from "../core.js";
import { mount, waterfall, lines, legend } from "../charts.js";

const SEAL = `<svg viewBox="0 0 48 48" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-width="1.3">
  <circle cx="24" cy="24" r="21"/><circle cx="24" cy="24" r="16.5"/>
  ${Array.from({ length: 24 }, (_, i) => { const a = (i / 24) * Math.PI * 2; return `<path d="M${24 + 17.5 * Math.cos(a)} ${24 + 17.5 * Math.sin(a)}L${24 + 20 * Math.cos(a)} ${24 + 20 * Math.sin(a)}"/>`; }).join("")}
  <path d="M16.5 24.5l5 5 10-11" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></g></svg>`;

const TABS = [["synthese", "Synthèse"], ["note", "Note"], ["donnees", "Données"], ["copilot", "Copilot"], ["audit", "Piste d'audit"]];
const ACTION_TONE = {
  depot: ["upload", "info"], analyse: ["cpu", ""], analyse_apres_validation: ["cpu", "ok"], echec: ["alert", "bad"],
  validation_approuvee: ["check", "ok"], validation_rejetee: ["x", "bad"], email_validation: ["mail", "warn"],
  email_note_envoyee: ["mail", "ok"], transmis_validation: ["mail", "warn"], note_consultee: ["file", ""],
  question_copilot: ["spark", ""], reprise: ["refresh", "info"],
};

function lifecycle(c) {
  const analysed = !["en_cours", "erreur", "document_illisible"].includes(c.status);
  const failed = ["erreur", "document_illisible"].includes(c.status);
  const steps = [
    { b: "Déposé", s: `${when(c.created_at)} · ${SOURCE_LABEL[c.source] || c.source}`, k: "done" },
    { b: "Analysé", s: failed ? "document inexploitable" : analysed ? `${c.llm_calls} appel(s) au modèle, ${fr((c.duration_ms || 0) / 1000, 0)} s` : "en cours",
      k: failed ? "stop" : analysed ? "done" : "now" },
    { b: "Validation humaine", k: "todo", s: "" },
    { b: "Note diffusable", k: ["note_prete", "validee"].includes(c.status) ? "done" : c.status === "rejetee" ? "stop" : "todo",
      s: c.status === "validee" ? "note recalculée et validée" : c.status === "note_prete" ? "tous les contrôles passés" : c.status === "rejetee" ? "aucune note diffusée" : "en attente" },
  ];
  const v = steps[2];
  if (c.status === "validation_humaine") Object.assign(v, { k: "now", s: "attend la décision d'un valideur" });
  else if (c.status === "validee") Object.assign(v, { k: "done", s: `approuvé par ${c.validated_by} ${ago(c.validated_at)}` });
  else if (c.status === "rejetee") Object.assign(v, { k: "stop", s: `rejeté par ${c.validated_by || "un valideur"}` });
  else if (c.status === "note_prete") Object.assign(v, { k: "done", s: c.ever_human ? "décidée" : "non requise : contrôles passés" });
  const mark = { done: icon("check"), now: icon("clock"), stop: icon("x"), todo: "" };
  return `<ol class="lifecycle">${steps.map(s => `<li class="${s.k}"><span class="lc-mark">${mark[s.k]}</span><b>${s.b}</b><small>${esc(s.s)}</small></li>`).join("")}</ol>`;
}

function eventItem(e) {
  const d = e.detail || {};
  const bits = [];
  if (d.statut) bits.push(`statut : ${({ note_prete: "note prête", validation_humaine: "à valider", validee: "validée", rejetee: "rejetée", document_illisible: "illisible", erreur: "erreur" })[d.statut] || d.statut}`);
  if (d.csm != null && d.statut) bits.push(d.perte ? `perte ${fr(d.perte)}` : `CSM ${fr(d.csm)}`);
  if (d.document) bits.push(d.document);
  if (d.valideur) bits.push(`valideur ${d.valideur}`);
  if (d.commentaire) bits.push(`« ${d.commentaire} »`);
  if (d.question) bits.push(`« ${d.question} »`);
  if (d.envoyee !== undefined) bits.push(d.envoyee ? "e-mail envoyé" : `e-mail non envoyé : ${d.detail || ""}`);
  if (d.controles?.length) bits.push(d.controles.join(" ; "));
  if (d.a) bits.push(`destinataire ${d.a}`);
  const [ic, tone] = ACTION_TONE[e.action] || ["activity", ""];
  return `<li><span class="tmark ${tone}">${icon(ic)}</span><div>
    <div class="thead"><b>${esc(ACTION_LABEL[e.action] || e.action)}</b><span class="twho">${esc(when(e.at))}</span></div>
    <span class="twho">par ${esc(e.actor)}</span>${bits.length ? `<p>${esc(bits.join(" · "))}</p>` : ""}
    <span class="hash" title="Empreinte SHA-256 chaînée à l'événement précédent">${icon("chain")}${esc(e.hash.slice(0, 16))}</span></div></li>`;
}

export async function render(main, params) {
  const id = decodeURIComponent(params[0]);
  let tab = TABS.some(t => t[0] === params[1]) ? params[1] : "synthese";
  emit("crumbs", [{ label: "Dossiers", href: "#/dossiers" }, { label: id }]);
  const c = await getJSON(`/v1/cases/${encodeURIComponent(id)}`);
  const p = c.portfolio;
  const isLic = p?.kind === "lic";          // dossier de sinistres survenus : triangle, Chain Ladder et Mack (D-083)
  const unmounts = [];
  let noteHTML = null;
  let csm = null;
  if (p && !isLic) { try { csm = await getJSON("/v1/csm/compute", { method: "POST", json: p }); } catch { csm = null; } }
  emit("crumbs", [{ label: "Dossiers", href: "#/dossiers" }, { label: c.group_id || id }]);

  const canDecide = canDo("valideur") && c.status === "validation_humaine" && !!p && !isLic;
  const canApproveLic = canDo("valideur") && c.status === "validation_humaine" && isLic && !!p.triangle_data;
  const canReject = canDo("valideur") && ["validation_humaine", "note_prete"].includes(c.status);
  const unit = p ? `${p.currency}, ${unitLabel(p.unit_multiplier)}` : c.currency;

  main.innerHTML = `<div class="page">
    <div class="case-head"><div class="case-title">
      <div class="eyebrow">Dossier <span class="mono">${esc(c.case_id)}</span></div>
      <h1>${esc(c.group_id || "Groupe non identifié")} ${statusChip(c.status)}</h1>
      <div class="case-sub">
        <span>${icon(c.source === "n8n-email" ? "mail" : c.source === "n8n-formulaire" ? "form" : c.source === "api" ? "api" : "user")}${esc(c.submitter || SOURCE_LABEL[c.source] || c.source)}</span>
        ${c.filename ? `<span>${icon("file")}${esc(c.filename)}</span>` : ""}
        <span>${icon("clock")}déposé ${esc(ago(c.created_at))}</span></div></div>
      <div class="case-actions">
        ${c.has_note ? `<button class="btn" id="cd-print">${icon("print")}Imprimer ou PDF</button>` : ""}
        ${canReject ? `<button class="btn danger" id="cd-reject">${icon("x")}Rejeter</button>` : ""}
        ${canDecide || canApproveLic ? `<button class="btn primary" id="cd-review">${icon("check")}Vérifier et approuver</button>` : ""}
      </div></div>
    ${lifecycle(c)}
    ${c.status === "validation_humaine" && !canDo("valideur") ? `<div class="callout info" style="margin-bottom:18px">${icon("info")}<span>Ce dossier attend la décision d'un <b>valideur</b>. Votre rôle (${esc(ROLE_LABEL[me()?.role] || "")}) permet de le consulter.</span></div>` : ""}
    <div class="tabs" role="tablist">${TABS.map(([k, l]) => `<button role="tab" data-tab="${k}" aria-selected="${k === tab}">${l}${k === "audit" ? `<span class="count">${c.evenements.length}</span>` : ""}</button>`).join("")}</div>
    <div id="cd-panel"></div></div>`;

  /* ---------------------------------------------------------------- synthèse */
  function synthese(el) {
    const controls = c.controls || [];
    const failing = ["validation_humaine", "rejetee", "erreur", "document_illisible"].includes(c.status) || (c.ever_human && controls.length);
    const norm = state.runs?.[c.case_id]?.norm || [];
    el.innerHTML = `<div class="grid g-main"><div class="stack">
      ${failing && controls.length ? `<div class="callout ${c.status === "validation_humaine" ? "warn" : "bad"}">${icon("alert")}<div><b>${c.status === "validation_humaine" ? "Contrôles à revoir avant diffusion" : "Contrôles non passés"}</b><ul>${controls.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div></div>` : ""}
      ${c.decision_comment ? `<div class="callout info">${icon("info")}<div><b>Commentaire du valideur</b><p>${esc(c.decision_comment)}</p></div></div>` : ""}
      ${isLic ? licPanel() : csm ? `<section class="panel"><div class="panel-head"><h2>Évaluation à la comptabilisation initiale</h2><span class="meta">${esc(unit)}</span></div>
        <div class="panel-body"><dl class="figs">
          <div class="hero ${csm.onerous ? "loss" : ""}"><dt>${csm.onerous ? "Perte à l'origine (§47)" : "Marge sur services contractuels"}</dt><dd class="num">${fr(csm.onerous ? csm.initial_loss_component : csm.initial_csm)}</dd></div>
          <div><dt>Flux d'exécution</dt><dd class="num">${fr(csm.fulfilment_cash_flows)}</dd></div>
          <div><dt>Ajustement pour risque</dt><dd class="num">${fr(csm.risk_adjustment)}</dd></div>
          <div><dt>Périodes de couverture</dt><dd class="num">${p.premiums.length}</dd></div></dl></div></section>
      <section class="panel"><div class="panel-head"><h2>De la valeur actuelle des flux à la marge</h2><span class="meta">§32, §38, §47</span></div>
        <div class="panel-body"><ul class="legend"><li><i class="sw box c1"></i>augmente la marge</li><li><i class="sw box c2"></i>la diminue</li><li><i class="sw box total"></i>résultat</li></ul>
        <div class="chart-box" id="cd-wf" style="height:270px"></div></div></section>
      <section class="panel"><div class="panel-head"><h2>Écoulement de la marge par période</h2><span class="meta">§44, B119</span></div>
        <div class="panel-body">${legend([{ name: "Marge de clôture" }, { name: "Libérée en résultat" }])}<div class="chart-box" id="cd-rf" style="height:240px"></div></div></section>`
      : `<div class="callout bad">${icon("alert")}<div><b>Pas de calcul pour ce dossier</b><p>Les données du portefeuille n'ont pas pu être lues : aucun montant n'est calculé.</p></div></div>`}
      ${norm.length ? `<section class="panel"><div class="panel-head"><h2>Fondements dans la norme</h2><span class="meta">réponses vérifiées pendant l'analyse</span></div>
        <div class="panel-body stack">${norm.map(n => `<div><b>${esc(n.question)}</b><p class="cell-sub" style="font-size:14px;color:var(--ink-2);margin-top:4px">${esc(n.answer.answer || n.answer.refusal_reason || "")}</p>
          ${(n.answer.citations || []).slice(0, 2).map(q => `<div class="quote"><b>${esc(refLabel(q.paragraph_id, true))}</b>« ${esc(q.quote)} »</div>`).join("")}</div>`).join("")}</div></section>` : ""}
      </div>
      <div class="stack">
        <section class="panel"><div class="panel-head"><h2>Dossier</h2></div><div class="panel-body"><dl class="kv">
          ${[["Référence", `<span class="mono">${esc(c.case_id)}</span>`], ["Canal", esc(SOURCE_LABEL[c.source] || c.source)],
            ["Déposant", esc(c.submitter || "—")], ["Document", esc(c.filename || "—")],
            ["Empreinte du document", c.sha256 ? `<span class="mono" title="${esc(c.sha256)}">${esc(c.sha256.slice(0, 20))}…</span>` : "—"],
            ["Monnaie et unité", esc(unit || "—")],
            ["Taux d'actualisation", p && !isLic ? (Array.isArray(p.discount_rates) ? `courbe, ${pct(p.discount_rates[0], 2)} à ${pct(p.discount_rates.at(-1), 2)}` : pct(p.discount_rates, 2)) : "—"],
            ["Ajustement pour risque", isLic && p.lic ? `quantile ${pct(p.lic.level, 0)}, CV ${pct(p.lic.cv, 1)}` : p ? `${pct(p.risk_adjustment_pct, 1)} des sorties` : "—"],
            ["Durée d'analyse", c.duration_ms ? `${fr(c.duration_ms / 1000, 1)} s` : "—"],
            ["Appels au modèle", `${c.llm_calls}${c.tokens ? ` · ${fr(c.tokens, 0)} jetons` : ""}`],
            ["Décision", c.validated_by ? `${esc(c.validated_by)}, ${esc(when(c.validated_at))}` : "—"],
          ].map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("")}</dl></div></section>
        <section class="panel"><div class="panel-head"><h2>Contrôles par le code</h2></div><div class="panel-body"><ul class="controls-list">
          ${checks().map(([ok, t]) => `<li class="${ok ? "ok" : "warn"}"><span class="ci">${icon(ok ? "check" : "alert")}</span><span>${esc(t)}</span></li>`).join("")}</ul></div></section>
      </div></div>`;
    if (csm) {
      const neg = csm.onerous;
      unmounts.push(mount($("#cd-wf", el), waterfall([
        { label: "Primes", sub: "valeur actuelle", value: csm.pv_inflows, note: "entrées de trésorerie actualisées" },
        { label: "Sinistres et frais", short: "Sorties", sub: "valeur actuelle", value: -csm.pv_outflows, note: "sorties de trésorerie actualisées" },
        { label: "Ajustement", short: "RA", sub: "pour risque", value: -csm.risk_adjustment, note: "risque non financier (§37)" },
        { label: neg ? "Perte" : "Marge", sub: neg ? "en résultat" : "à l'origine", value: neg ? -csm.initial_loss_component : csm.initial_csm, total: true,
          note: neg ? "comptabilisée immédiatement (§47)" : "différée, libérée avec le service (§38)" },
      ]), 270));
      const rf = csm.rollforward || [];
      if (!rf.some(r => Math.abs(r.closing) > 0.005 || Math.abs(r.release) > 0.005)) {
        $("#cd-rf", el).closest(".panel-body").innerHTML = `<div class="callout info">${icon("info")}<span>Groupe déficitaire : il n'y a pas de marge à libérer. La perte est comptabilisée dès l'origine et suivie dans la composante de perte (§47 à §52) ; la note détaille sa reprise période par période.</span></div>`;
      } else if (rf.length) unmounts.push(mount($("#cd-rf", el), lines(rf.map(r => `P${r.period}`), [
        { name: "Marge de clôture", values: rf.map(r => r.closing) }, { name: "Libérée en résultat", values: rf.map(r => r.release) }]), 240));
    }
  }
  function licPanel() {
    const l = p.lic;
    if (!l) return `<div class="callout bad">${icon("alert")}<div><b>Pas de calcul pour ce dossier</b><p>Le triangle n'a pas pu être évalué.</p></div></div>`;
    return `<section class="panel"><div class="panel-head"><h2>Passif pour sinistres survenus</h2><span class="meta">${esc(unit)} · §40(b), §37, §119</span></div>
      <div class="panel-body"><dl class="figs">
        <div class="hero"><dt>Passif pour sinistres survenus (LIC)</dt><dd class="num">${fr(l.lic)}</dd></div>
        <div><dt>Meilleure estimation actualisée</dt><dd class="num">${fr(l.bel)}</dd></div>
        <div><dt>Ajustement pour risque (${pct(l.level, 0)})</dt><dd class="num">${fr(l.risk_adjustment)}</dd></div>
        <div><dt>Provision non actualisée</dt><dd class="num">${fr(l.reserve)}</dd></div></dl>
        <p class="cell-sub" style="font-size:14px;margin-top:12px">Chain Ladder sur ${p.triangle_data.origin_years.length} années de survenance ; erreur de prédiction de Mack ${fr(l.mack_se)} (coefficient de variation ${pct(l.cv, 1)}). La note détaille le triangle, les facteurs, les paiements futurs et les niveaux de confiance.</p></div></section>`;
  }
  function checks() {
    const human = c.status === "validation_humaine" || c.ever_human;
    if (isLic) {
      const out = [[true, "Triangle lu et chaque montant retrouvé dans le document"],
        [!!p.lic, "Passif calculé par le moteur Python (Chain Ladder, Mack), sans modèle de langage"],
        [c.has_note, c.has_note ? "Note écrite par le code, sans modèle de langage" : "Pas de note produite"]];
      if (human) out.push([c.status === "validee", c.status === "validee" ? "Triangle approuvé par un valideur" : "Validation humaine requise"]);
      return out;
    }
    const out = [
      [!!p, p ? "Données du portefeuille lues et retrouvées dans le document" : "Données du portefeuille non lues"],
      [!!csm, "Marge calculée par le moteur Python, sans modèle de langage"],
      [c.has_note, c.has_note ? "Note produite : chiffres et citations vérifiés" : "Pas de note produite"],
    ];
    if (human) out.push([c.status === "validee", c.status === "validee" ? "Données approuvées par un valideur" : "Validation humaine requise"]);
    return out;
  }

  /* ---------------------------------------------------------------- note */
  async function note(el) {
    if (!c.has_note) { el.innerHTML = `<div class="panel"><div class="empty">${icon("file")}<h3>Pas de note pour ce dossier</h3><p>La note est produite dès que les données du portefeuille sont lisibles.</p></div></div>`; return; }
    const sealed = ["note_prete", "validee"].includes(c.status);
    el.innerHTML = `<section class="panel"><div class="note-bar"><div class="seal-line">${sealed ? `<span class="seal">${SEAL}</span>` : icon("alert")}
        <span>${sealed ? `<b>Note ${c.status === "validee" ? "validée" : "prête"}</b> · contrôles passés${c.validated_by ? `, approuvée par ${esc(c.validated_by)}` : ""}` : "<b>Note provisoire</b> · à ne pas diffuser avant la décision d'un valideur"}</span></div>
        <div class="case-actions"><button class="btn sm" id="nt-dl">${icon("download")}Télécharger (HTML)</button><button class="btn sm" id="nt-print">${icon("print")}Imprimer ou PDF</button></div></div>
      <iframe class="note-frame" id="nt-frame" title="Note IFRS 17 du dossier ${esc(c.case_id)}" sandbox="allow-same-origin allow-modals"></iframe></section>`;
    noteHTML ??= await (await api(`/v1/cases/${encodeURIComponent(c.case_id)}/note`)).text();
    const fr_ = $("#nt-frame", el);
    fr_.addEventListener("load", () => { try { fr_.style.height = `${fr_.contentDocument.documentElement.scrollHeight + 20}px`; } catch { /* hauteur par défaut */ } });
    fr_.srcdoc = noteHTML;
    $("#nt-print", el).addEventListener("click", () => printHTML(noteHTML));
    $("#nt-dl", el).addEventListener("click", () => downloadText(noteHTML, `note-ifrs17-${c.group_id || c.case_id}.html`));
  }

  /* ---------------------------------------------------------------- données */
  function donneesLic(el) {
    const t = p.triangle_data;
    const n = t.origin_years.length;
    const cum = t.triangle;
    el.innerHTML = `<section class="panel"><div class="panel-head"><h2>Triangle lu dans le document</h2><span class="meta">${esc(unit)} · ${t.cumulative ? "paiements cumulés" : "paiements de l'année"}</span></div>
      <div class="panel-body"><div class="table-wrap"><table class="data-grid"><thead><tr><th>Survenance</th>${t.premiums ? "<th>Prime</th>" : ""}${Array.from({ length: n }, (_, k) => `<th>Ret. ${k + 1}</th>`).join("")}</tr></thead>
        <tbody>${cum.map((row, i) => `<tr><td>${esc(t.origin_years[i])}</td>${t.premiums ? `<td class="num">${fr(t.premiums[i], 0)}</td>` : ""}${row.map(v => `<td class="num">${fr(v, 0)}</td>`).join("")}${"<td></td>".repeat(i)}</tr>`).join("")}</tbody></table></div>
        <dl class="kv" style="margin-top:16px"><div><dt>Taux d'actualisation</dt><dd>${Array.isArray(t.discount_rates) ? t.discount_rates.map(x => pct(x, 2)).join(" ; ") : pct(t.discount_rates, 2)}</dd></div>
          <div><dt>Niveau de confiance</dt><dd>${t.confidence_level ? pct(t.confidence_level, 0) : "non indiqué (niveau cible du registre)"}</dd></div>
          <div><dt>Facteur de queue</dt><dd>${t.tail_factor === 1 ? "aucun" : fr(t.tail_factor, 4)}</dd></div></dl>
        ${canApproveLic ? `<form id="lic-form"><label class="field" style="margin-top:18px">Commentaire de validation<textarea name="comment" rows="2" placeholder="Ex. : triangle comparé au document, taux vérifiés."></textarea><small>Inscrit dans la piste d'audit. Pour corriger une cellule, rejetez le dossier ou transmettez le triangle corrigé par l'API (/v1/case/validated).</small></label>
          <div class="decision"><p>Vous approuvez en tant que <b>${esc(me()?.display_name || me()?.username || "valideur")}</b>.</p>
          <div class="case-actions"><button class="btn danger" type="button" id="lic-reject">Rejeter le dossier</button><button class="btn primary" type="submit" id="lic-ok">${icon("check")}Approuver et produire la note</button></div></div></form>` : ""}
      </div></section>`;
    if (!canApproveLic) return;
    $("#lic-reject", el).addEventListener("click", reject);
    $("#lic-form", el).addEventListener("submit", async e => {
      e.preventDefault();
      const btn = $("#lic-ok", el);
      btn.disabled = true; btn.innerHTML = `<span class="spin"></span>Calcul et rédaction de la note…`;
      try {
        const r = await getJSON("/v1/case/validated", { method: "POST", json: { triangle: t, case_id: c.case_id, comment: new FormData(e.target).get("comment") || null } });
        emit("cases:changed");
        toast(r.status === "note_prete" ? "Dossier approuvé : la note définitive est prête." : "Dossier approuvé, des points restent à revoir.", r.status === "note_prete" ? "ok" : "warn");
        location.hash = `#/dossiers/${encodeURIComponent(c.case_id)}/note`;
      } catch (err) {
        btn.disabled = false; btn.innerHTML = `${icon("check")}Approuver et produire la note`;
        toast(`Approbation impossible : ${err.message}`, "bad", { timeout: 7000 });
      }
    });
  }

  function donnees(el) {
    if (isLic) { donneesLic(el); return; }
    if (!p) { el.innerHTML = `<div class="panel"><div class="empty">${icon("database")}<h3>Aucune donnée exploitable</h3><p>${esc((c.controls || []).join(" ; ") || "Le document n'a pas pu être lu.")}</p></div></div>`; return; }
    const edit = canDecide;
    const rates = Array.isArray(p.discount_rates) ? p.discount_rates : null;
    const cell = (k, i, v, d = 2) => edit ? `<input name="${k}.${i}" value="${String(v).replace(".", ",")}" inputmode="decimal" aria-label="${k} période ${i + 1}" data-orig="${v}">` : fr(v, d);
    const sum = a => a.reduce((x, y) => x + y, 0);
    el.innerHTML = `<form class="panel" id="dt-form">
      <div class="panel-head"><h2>${edit ? "Vérifier et corriger les données extraites" : "Données extraites du document"}</h2><span class="meta">${esc(unit)}</span></div>
      <div class="panel-body">
        ${edit ? `<p class="cell-sub" style="font-size:14px;margin-bottom:16px">Comparez avec le document source. Les cellules modifiées sont surlignées ; l'approbation recalcule la marge, interroge la norme et produit la note définitive.</p>` : ""}
        <div class="meta-grid">
          ${edit ? `<label class="field">Groupe de contrats<input name="group_id" value="${esc(p.group_id)}" required></label>
            <label class="field">Monnaie<input name="currency" value="${esc(p.currency)}" maxlength="3" required></label>
            <label class="field">Unité des montants<select name="unit_multiplier">${[1, 1000, 1000000].map(u => `<option value="${u}" ${u === p.unit_multiplier ? "selected" : ""}>${unitLabel(u)}</option>`).join("")}</select></label>
            ${rates ? "" : `<label class="field">Taux d'actualisation<input name="discount_rate" value="${String(p.discount_rates).replace(".", ",")}" inputmode="decimal"><small>décimal : 0,03 pour 3 %</small></label>`}
            <label class="field">Ajustement pour risque<input name="risk_adjustment_pct" value="${String(p.risk_adjustment_pct).replace(".", ",")}" inputmode="decimal"><small>part des sorties, décimal</small></label>`
          : `<dl class="kv" style="grid-column:1/-1"><div><dt>Groupe de contrats</dt><dd>${esc(p.group_id)}</dd></div><div><dt>Taux d'actualisation</dt><dd>${rates ? "courbe par période (ci-dessous)" : pct(p.discount_rates, 2)}</dd></div><div><dt>Ajustement pour risque</dt><dd>${pct(p.risk_adjustment_pct, 1)} des sorties</dd></div></dl>`}
        </div>
        <div class="table-wrap"><table class="data-grid"><thead><tr><th>Période</th><th>Primes</th><th>Sinistres et frais</th><th>Unités de couverture</th>${rates ? "<th>Taux</th>" : ""}</tr></thead>
          <tbody>${p.premiums.map((_, i) => `<tr><td>Période ${i + 1}</td><td>${cell("premiums", i, p.premiums[i])}</td><td>${cell("outflows", i, p.outflows[i])}</td>
            <td>${cell("coverage_units", i, p.coverage_units[i], 0)}</td>${rates ? `<td>${edit ? cell("discount_rates", i, rates[i]) : pct(rates[i], 2)}</td>` : ""}</tr>`).join("")}</tbody>
          <tfoot><tr><td>Total</td><td class="num">${fr(sum(p.premiums))}</td><td class="num">${fr(sum(p.outflows))}</td><td class="num">${fr(sum(p.coverage_units), 0)}</td>${rates ? "<td></td>" : ""}</tr></tfoot></table></div>
        ${edit ? `<label class="field" style="margin-top:18px">Commentaire de validation<textarea name="comment" rows="2" placeholder="Ex. : groupe PREV-2023-A retenu, taux de la période 4 vérifié dans l'annexe."></textarea><small>Inscrit dans la piste d'audit.</small></label>` : ""}
      </div>
      ${edit ? `<div class="decision"><p>Vous approuvez en tant que <b>${esc(me()?.display_name || me()?.username || "valideur")}</b>.</p>
        <div class="case-actions"><button class="btn danger" type="button" id="dt-reject">Rejeter le dossier</button><button class="btn primary" type="submit" id="dt-ok">${icon("check")}Approuver et produire la note</button></div></div>` : ""}
    </form>`;
    if (!edit) return;
    $$("input[data-orig]", el).forEach(inp => inp.addEventListener("input", () => {
      inp.classList.toggle("changed", Number(inp.value.replace(/\s/g, "").replace(",", ".")) !== Number(inp.dataset.orig));
    }));
    $("#dt-reject", el).addEventListener("click", reject);
    $("#dt-form", el).addEventListener("submit", async e => {
      e.preventDefault();
      const f = new FormData(e.target);
      const num = (v, name) => { const x = Number(String(v).replace(/\s/g, "").replace(",", ".")); if (!Number.isFinite(x)) throw new Error(`${name} : « ${v} » n'est pas un nombre`); return x; };
      let q;
      try {
        q = structuredClone(p);
        for (const k of ["premiums", "outflows", "coverage_units"]) q[k] = q[k].map((_, i) => num(f.get(`${k}.${i}`), `${k} période ${i + 1}`));
        if (rates) q.discount_rates = rates.map((_, i) => num(f.get(`discount_rates.${i}`), `taux période ${i + 1}`));
        else q.discount_rates = num(f.get("discount_rate"), "taux");
        q.group_id = String(f.get("group_id")).trim(); q.currency = String(f.get("currency")).trim().toUpperCase();
        q.unit_multiplier = Number(f.get("unit_multiplier")); q.risk_adjustment_pct = num(f.get("risk_adjustment_pct"), "ajustement pour risque");
      } catch (err) { toast(err.message, "bad"); return; }
      const btn = $("#dt-ok", el);
      btn.disabled = true; btn.innerHTML = `<span class="spin"></span>Calcul et rédaction de la note…`;
      try {
        const r = await getJSON("/v1/case/validated", { method: "POST", json: { portfolio: q, case_id: c.case_id, comment: f.get("comment") || null } });
        state.runs = { ...(state.runs || {}), [c.case_id]: { norm: r.norm } };
        emit("cases:changed");
        toast(r.status === "note_prete" ? "Dossier approuvé : la note définitive est prête." : "Dossier approuvé, mais un contrôle de la norme reste à revoir.", r.status === "note_prete" ? "ok" : "warn");
        location.hash = `#/dossiers/${encodeURIComponent(c.case_id)}/note`;
      } catch (err) {
        btn.disabled = false; btn.innerHTML = `${icon("check")}Approuver et produire la note`;
        toast(`Approbation impossible : ${err.message}`, "bad", { timeout: 7000 });
      }
    });
  }

  async function reject() {
    const r = await modal({ title: "Rejeter le dossier", body: `<p class="modal-text">Aucune note ne sera diffusée. Le motif est inscrit dans la piste d'audit et communiqué au déposant par n8n.</p>
      <label class="field">Motif du rejet<textarea name="reason" rows="3" minlength="3" required placeholder="Ex. : document incomplet, deux groupes de contrats mélangés."></textarea></label>`,
    actions: [{ label: "Annuler", value: "cancel" }, { label: "Rejeter le dossier", value: "ok", tone: "danger solid", submit: true }] });
    if (r.value !== "ok") return;
    try {
      await api(`/v1/cases/${encodeURIComponent(c.case_id)}/reject`, { method: "POST", json: { comment: r.data.reason.trim() } });
      emit("cases:changed"); toast("Dossier rejeté."); location.hash = `#/dossiers/${encodeURIComponent(c.case_id)}/audit`;
    } catch (err) { toast(`Rejet impossible : ${err.message}`, "bad"); }
  }

  /* ---------------------------------------------------------------- Copilot (D-057, mémoire et trajectoire D-061) */
  const TOOL_LABEL = { donnees_du_dossier: "Données du dossier", evaluer_scenario: "Scénario", sensibilites: "Sensibilités",
    niveau_de_confiance: "Niveau de confiance", projection_resultat: "Projection du résultat", rechercher_norme: "Recherche dans la norme",
    memoire_du_dossier: "Mémoire du dossier" };
  const NODE_LABEL = { decider: "décider", agir: "agir", verifier: "vérifier" };
  const args = a => Object.entries(a || {}).map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`).join(", ");
  function trajectoryHTML(r) {
    const steps = (r.steps || []).map(st => {
      if (st.noeud === "decider") return `<li><b>Décider</b> ${st.action === "outil" ? `→ ${esc(TOOL_LABEL[st.outil] || st.outil)}` : st.action === "repondre" ? "→ répondre" : esc(st.action || "")}${st.pensee ? `<small>${esc(st.pensee)}</small>` : ""}</li>`;
      if (st.noeud === "agir") return `<li><b>Agir</b> ${esc(TOOL_LABEL[st.outil] || st.outil)}${Object.keys(st.arguments || {}).length ? ` (${esc(args(st.arguments))})` : ""}${st.erreur ? `<small class="neg">${esc(st.erreur)}</small>` : ""}</li>`;
      return `<li><b>Vérifier</b> ${st.problemes?.length ? `<small class="neg">${esc(st.problemes.join(" ; "))}</small>` : "<small>chiffres et citations fondés</small>"}</li>`;
    }).join("");
    const cps = (r.trajectory || []).filter(cp => cp.prochaine.length);
    return `<ol class="traj">${steps}</ol>${cps.length ? `<p class="traj-h">Points de reprise sauvegardés</p><ul class="cps">${cps.map((cp, i) =>
      `<li><span>n° ${i + 1} · avant « ${esc(NODE_LABEL[cp.prochaine[0]] || cp.prochaine[0])} »</span>${canDo("valideur") ? `<button class="btn sm ghost" data-replay="${esc(cp.checkpoint_id)}">${icon("refresh")}Rejouer d'ici</button>` : ""}</li>`).join("")}</ul>` : ""}`;
  }
  function answerHTML(r, label = "") {
    return `${label ? `<span class="status info" style="margin-bottom:8px">${esc(label)}</span>` : ""}<p class="text">${esc(r.answer)}</p>
      <details class="tools"><summary>Trajectoire : ${r.tools.length} outil${r.tools.length > 1 ? "s" : ""}, ${r.llm_calls} appel${r.llm_calls > 1 ? "s" : ""} au modèle</summary>${trajectoryHTML(r)}</details>
      <div class="meta">${r.source === "llm" ? `<span class="status ok">Chiffres vérifiés</span>` : `<span class="status warn">Réponse construite par le code</span>`}
        ${r.memory_used ? `<span>${icon("layers")} ${r.memory_used} échange${r.memory_used > 1 ? "s" : ""} en mémoire</span>` : ""}<span>${fr(r.latency_ms / 1000, 1)} s</span><span>${esc(r.engine)}</span></div>`;
  }
  async function copilot(el) {
    if (!p) { el.innerHTML = `<div class="panel"><div class="empty">${icon("spark")}<h3>Copilot indisponible</h3><p>Il a besoin des données du portefeuille.</p></div></div>`; return; }
    const chips = isLic
      ? ["Que devient le LIC si les taux baissent de 100 points de base ?", "Quelle année de survenance pèse le plus dans la provision ?",
        "Quel ajustement pour risque à 90 % de confiance ?", "Que dit la norme sur le passif pour sinistres survenus ?"]
      : ["Le groupe reste-t-il bénéficiaire si les sinistres augmentent de 15 % ?", "Quelle hypothèse est la plus sensible ?",
        "Quel ajustement pour risque à 90 % de confiance, et quel effet sur la marge ?", "Que dit la norme si le groupe devient déficitaire ?"];
    const data = isLic ? { triangle: p.triangle_data } : { portfolio: p };
    let hist = { echanges: [], points_de_reprise: [], checkpointer: null };
    try { hist = await getJSON(`/v1/copilot/${encodeURIComponent(c.case_id)}`); } catch { /* historique facultatif */ }
    el.innerHTML = `<div class="grid g-main"><section class="panel chat"><div class="thread" id="cp-thread" aria-live="polite">
        <div class="intro-card"><h3>Explorer le dossier ${esc(p.group_id)}</h3>
          <p>Posez une question « et si… ». L'agent choisit ses outils (${isLic ? "scénario sur les taux, la queue ou le niveau de confiance, sensibilités, détail par survenance, paiements futurs" : "scénario, sensibilités, niveau de confiance, projection"}, norme, mémoire du dossier) ; chaque chiffre de sa réponse est vérifié contre les résultats du moteur. Il se souvient des échanges précédents sur ce dossier.</p>
          ${hist.echanges.length ? "" : `<div class="chips">${chips.map(t => `<button class="chip" type="button">${esc(t)}</button>`).join("")}</div>`}</div>
        ${hist.echanges.map(m => `<div class="msg q">${esc(m.question)}</div><div class="msg a"><span class="who">${icon("spark")}</span><div class="body">
          <p class="text">${esc(m.answer)}</p><div class="meta"><span class="status">En mémoire</span><span>${esc(m.actor)}, ${esc(when(m.at))}</span></div></div></div>`).join("")}</div>
      <form class="composer" id="cp-form"><label class="sr" for="cp-q">Question</label>
        <textarea class="input" id="cp-q" rows="1" placeholder="Votre question sur ce dossier, ou une suite : « et à 20 % ? »" required></textarea>
        <span></span><button class="btn primary" type="submit">${icon("send")}Demander</button></form></section>
      <aside class="stack">
        <section class="panel"><div class="panel-head"><h2>Mémoire du dossier</h2><span class="meta" id="cp-mem-n">${hist.echanges.length} échange${hist.echanges.length > 1 ? "s" : ""}</span></div>
          <div class="panel-body stack" style="gap:12px;font-size:14px;color:var(--ink-2)">
            <p>Les trois derniers échanges et les décisions du valideur sont placés dans le contexte ; les plus anciens sont retrouvés par l'outil « mémoire du dossier ». Seules les réponses contrôlées sont gardées.</p>
            ${canDo("valideur") ? `<button class="btn sm" id="cp-forget" ${hist.echanges.length ? "" : "disabled"}>${icon("x")}Effacer la mémoire</button>` : ""}</div></section>
        <section class="panel"><div class="panel-head"><h2>État sauvegardé</h2></div><div class="panel-body" style="font-size:14px;color:var(--ink-2)">
          <p>${hist.checkpointer ? `Après chaque étape, le graphe LangGraph enregistre son état (${esc(hist.checkpointer)}) : <b>${hist.points_de_reprise.length}</b> points de reprise pour ce dossier. Ouvrez la trajectoire d'une réponse pour la rejouer depuis l'un d'eux.` : "LangGraph n'est pas installé : le Copilot tourne sans sauvegarde d'état."}</p></div></section>
      </aside></div>`;
    const thread = $("#cp-thread", el);
    thread.scrollTop = thread.scrollHeight;
    const pending = text => {
      const a = document.createElement("div");
      a.className = "msg a thinking";
      a.innerHTML = `<span class="who">${icon("spark")}</span><div class="body"><p class="text">${esc(text)}<span class="dots"><i></i><i></i><i></i></span></p></div>`;
      thread.append(a); a.scrollIntoView({ block: "nearest", behavior: "smooth" });
      return a;
    };
    const fill = (a, r, label) => { a.classList.remove("thinking"); $(".body", a).innerHTML = answerHTML(r, label); };
    const fail = (a, err) => { a.classList.remove("thinking"); $(".body", a).innerHTML = `<div class="callout bad">${icon("alert")}<span>${esc(err.message)}</span></div>`; };
    async function ask(q) {
      if (!q.trim()) return;
      $(".intro-card .chips", el)?.remove();
      thread.insertAdjacentHTML("beforeend", `<div class="msg q">${esc(q)}</div>`);
      const a = pending("L'agent choisit ses outils");
      try {
        fill(a, await getJSON("/v1/copilot", { method: "POST", json: { question: q, ...data, case_id: c.case_id } }));
        const n = $("#cp-mem-n", el); n.textContent = `${(parseInt(n.textContent, 10) || 0) + 1} échanges`;
        $("#cp-forget", el)?.removeAttribute("disabled");
      } catch (err) { fail(a, err); }
    }
    el.addEventListener("click", async e => {
      const chip = e.target.closest(".chip");
      if (chip) { ask(chip.textContent); return; }
      const rb = e.target.closest("[data-replay]");
      if (rb) {
        rb.disabled = true;
        const a = pending("Rejeu depuis le point de reprise");
        try { fill(a, await getJSON(`/v1/copilot/${encodeURIComponent(c.case_id)}/rejouer`, { method: "POST", json: { checkpoint_id: rb.dataset.replay, ...data } }), "Rejeu depuis un point de reprise"); }
        catch (err) { fail(a, err); }
        rb.disabled = false;
      }
    });
    $("#cp-forget", el)?.addEventListener("click", async () => {
      if (!await confirmAction("Effacer la mémoire du Copilot", "Les échanges gardés pour ce dossier seront supprimés ; l'action est inscrite dans la piste d'audit.", "Effacer", "danger solid")) return;
      try { await api(`/v1/copilot/${encodeURIComponent(c.case_id)}/memoire`, { method: "DELETE" }); toast("Mémoire effacée."); show("copilot"); }
      catch (err) { toast(err.message, "bad"); }
    });
    const qa = $("#cp-q", el);
    qa.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#cp-form", el).requestSubmit(); } });
    $("#cp-form", el).addEventListener("submit", e => { e.preventDefault(); const q = qa.value; qa.value = ""; ask(q); });
  }

  /* ---------------------------------------------------------------- audit */
  function audit(el) {
    el.innerHTML = `<div class="grid g-main"><section class="panel"><div class="panel-head"><h2>Piste d'audit du dossier</h2><span class="meta">${c.evenements.length} événement${c.evenements.length > 1 ? "s" : ""}</span></div>
      <div class="panel-body"><ol class="timeline">${c.evenements.slice().reverse().map(eventItem).join("")}</ol></div></section>
      <section class="panel"><div class="panel-head"><h2>Comment lire cette piste</h2></div><div class="panel-body stack" style="gap:12px;font-size:14px;color:var(--ink-2)">
        <p>Chaque événement porte une empreinte SHA-256 calculée sur son contenu et sur l'empreinte de l'événement précédent.</p>
        <p>Modifier ou supprimer un événement après coup casse la chaîne : la vérification d'intégrité (administration) désigne le premier événement altéré.</p>
        ${canDo("admin") ? `<a class="btn" href="#/admin/audit">${icon("shield")}Vérifier l'intégrité</a>` : ""}</div></section></div>`;
  }

  const PANELS = { synthese, note, donnees, copilot, audit };
  async function show(name) {
    tab = name;
    $$(".tabs [role=tab]", main).forEach(b => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
    unmounts.splice(0).forEach(u => u());
    const el = $("#cd-panel", main);
    el.innerHTML = "";
    const fresh = document.createElement("div");
    el.append(fresh);
    try { await PANELS[name](fresh); } catch (err) { fresh.innerHTML = `<div class="callout bad">${icon("alert")}<span>${esc(err.message)}</span></div>`; }
    history.replaceState(null, "", `#/dossiers/${encodeURIComponent(c.case_id)}${name === "synthese" ? "" : "/" + name}`);
  }
  $$(".tabs [role=tab]", main).forEach(b => b.addEventListener("click", () => show(b.dataset.tab)));
  $(".tabs", main).addEventListener("keydown", e => {
    const i = TABS.findIndex(t => t[0] === tab);
    if (e.key === "ArrowRight") { show(TABS[(i + 1) % TABS.length][0]); $(`[data-tab="${tab}"]`, main).focus(); }
    if (e.key === "ArrowLeft") { show(TABS[(i - 1 + TABS.length) % TABS.length][0]); $(`[data-tab="${tab}"]`, main).focus(); }
  });
  $("#cd-print", main)?.addEventListener("click", async () => { noteHTML ??= await (await api(`/v1/cases/${encodeURIComponent(c.case_id)}/note`)).text(); printHTML(noteHTML); });
  $("#cd-reject", main)?.addEventListener("click", reject);
  $("#cd-review", main)?.addEventListener("click", () => show("donnees"));
  await show(tab);
  return () => unmounts.forEach(u => u());
}
