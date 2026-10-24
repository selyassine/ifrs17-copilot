/* Administration : comptes et rôles, piste d'audit et vérification d'intégrité, état du système. */
import { $, $$, esc, when, ago, icon, me, api, getJSON, emit, toast, modal, ROLE_LABEL, ACTION_LABEL } from "../core.js";

const TABS = [["comptes", "Comptes"], ["audit", "Piste d'audit"], ["systeme", "État du système"]];
const SEAL = `<svg viewBox="0 0 48 48" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="24" cy="24" r="21"/><circle cx="24" cy="24" r="16.5"/>
  ${Array.from({ length: 24 }, (_, i) => { const a = (i / 24) * Math.PI * 2; return `<path d="M${24 + 17.5 * Math.cos(a)} ${24 + 17.5 * Math.sin(a)}L${24 + 20 * Math.cos(a)} ${24 + 20 * Math.sin(a)}"/>`; }).join("")}</g>
  <path d="M17 24.5l5 5 9.5-10.5" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

export async function render(main, params) {
  let tab = TABS.some(t => t[0] === params[0]) ? params[0] : "comptes";
  main.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>Administration</h1><p>Comptes de l'équipe, piste d'audit infalsifiable et configuration du service.</p></div></div>
    <div class="tabs" role="tablist">${TABS.map(([k, l]) => `<button role="tab" data-tab="${k}" aria-selected="${k === tab}">${l}</button>`).join("")}</div>
    <div id="ad-body"></div></div>`;

  /* ---------------------------------------------------------------- comptes */
  async function comptes(el) {
    const users = await getJSON("/v1/users");
    const self = me()?.username;
    el.innerHTML = `<div class="admin-cols"><section class="panel flush">
      <div class="panel-head"><h2>Comptes</h2><button class="btn primary sm" id="u-new">${icon("plus")}Nouveau compte</button></div>
      <div class="panel-body table-wrap"><table class="table"><thead><tr><th>Utilisateur</th><th>Rôle</th><th>État</th><th class="hide-sm">Dernière connexion</th><th class="r">Actions</th></tr></thead><tbody>
      ${users.map(u => `<tr data-u="${esc(u.username)}"><td><b>${esc(u.display_name || u.username)}</b><small>${esc(u.username)}${u.username === self ? " · vous" : ""}</small></td>
        <td><select class="role-select" aria-label="Rôle de ${esc(u.username)}" ${u.username === self ? "disabled" : ""}>
          ${["analyste", "valideur", "admin"].map(r => `<option value="${r}" ${r === u.role ? "selected" : ""}>${ROLE_LABEL[r]}</option>`).join("")}</select></td>
        <td>${u.active ? `<span class="status ok">Actif</span>` : `<span class="status bad">Désactivé</span>`}</td>
        <td class="hide-sm" title="${esc(when(u.last_login))}">${u.last_login ? ago(u.last_login) : "jamais"}</td>
        <td class="r">${u.username === self ? "" : `<button class="btn sm ghost" data-act="pwd">Mot de passe</button>
          <button class="btn sm ${u.active ? "danger" : ""}" data-act="toggle">${u.active ? "Désactiver" : "Réactiver"}</button>`}</td></tr>`).join("")}
      </tbody></table></div></section>
      <section class="panel"><div class="panel-head"><h2>Rôles</h2></div><div class="panel-body"><dl class="kv">
        <div><dt>Analyste</dt><dd>Dépose et analyse des dossiers, interroge la norme et le Copilot, consulte le registre.</dd></div>
        <div><dt>Valideur</dt><dd>En plus : corrige les données extraites, approuve ou rejette un dossier en validation humaine.</dd></div>
        <div><dt>Administrateur</dt><dd>En plus : gère les comptes, consulte et vérifie la piste d'audit complète.</dd></div>
        <div><dt>Sécurité</dt><dd>Mots de passe PBKDF2-SHA256 (200 000 itérations), blocage 5 minutes après 5 échecs, sessions de 8 heures.</dd></div></dl></div></section></div>`;
    const patch = async (name, body, okMsg) => {
      try { await api(`/v1/users/${encodeURIComponent(name)}`, { method: "PATCH", json: body }); toast(okMsg); }
      catch (err) { toast(err.message, "bad"); }
      show("comptes");
    };
    $$("tr[data-u]", el).forEach(tr => {
      const name = tr.dataset.u, u = users.find(x => x.username === name);
      $(".role-select", tr).addEventListener("change", e => patch(name, { role: e.target.value }, `Rôle de ${name} : ${ROLE_LABEL[e.target.value]}.`));
      $('[data-act="toggle"]', tr)?.addEventListener("click", async () => {
        if (u.active) {
          const r = await modal({ title: `Désactiver ${u.display_name || name}`, body: `<p class="modal-text">Le compte ne pourra plus se connecter. Son historique reste dans la piste d'audit ; vous pourrez le réactiver.</p>`,
            actions: [{ label: "Annuler", value: "c" }, { label: "Désactiver", value: "ok", tone: "danger solid", submit: true }] });
          if (r.value !== "ok") return;
        }
        patch(name, { active: !u.active }, u.active ? `${name} est désactivé.` : `${name} est réactivé.`);
      });
      $('[data-act="pwd"]', tr)?.addEventListener("click", async () => {
        const r = await modal({ title: `Nouveau mot de passe pour ${name}`, body: `<p class="modal-text">Communiquez-le par un autre canal que l'e-mail du dossier.</p>
          <label class="field">Mot de passe provisoire<input name="password" type="password" minlength="8" required autocomplete="new-password"><small>8 caractères au moins</small></label>`,
        actions: [{ label: "Annuler", value: "c" }, { label: "Enregistrer", value: "ok", tone: "primary", submit: true }] });
        if (r.value === "ok") patch(name, { password: r.data.password }, `Mot de passe de ${name} remplacé.`);
      });
    });
    $("#u-new", el).addEventListener("click", async () => {
      const r = await modal({ title: "Nouveau compte", body: `
        <label class="field">Nom affiché<input name="display_name" autocomplete="off" placeholder="Prénom Nom"></label>
        <label class="field">Identifiant<input name="username" required autocomplete="off" pattern="[A-Za-z0-9._-]{2,40}"><small>lettres, chiffres, point, tiret</small></label>
        <label class="field">Rôle<select name="role"><option value="analyste">Analyste</option><option value="valideur">Valideur</option><option value="admin">Administrateur</option></select></label>
        <label class="field">Mot de passe provisoire<input name="password" type="password" minlength="8" required autocomplete="new-password"></label>`,
      actions: [{ label: "Annuler", value: "c" }, { label: "Créer le compte", value: "ok", tone: "primary", submit: true }] });
      if (r.value !== "ok") return;
      try { await api("/v1/users", { method: "POST", json: r.data }); toast(`Compte ${r.data.username} créé.`); }
      catch (err) { toast(err.message, "bad"); }
      show("comptes");
    });
  }

  /* ---------------------------------------------------------------- audit */
  async function audit(el) {
    const { evenements } = await getJSON("/v1/audit?limit=300");
    const recent = evenements.slice(-10);
    el.innerHTML = `<div class="stack">
      <section class="panel"><div class="integrity" id="au-state"><span class="seal">${SEAL}</span><div><b>Intégrité de la piste d'audit</b>
        <p>${evenements.length} événements récents. La vérification recalcule l'empreinte de chaque événement depuis le premier.</p></div></div>
        <div class="chain" id="au-chain">${recent.map((e, k) => `${k ? '<span class="lnk"></span>' : ""}<div class="blk" style="--k:${k}"><b>${esc(ACTION_LABEL[e.action] || e.action)}</b><code>${esc(e.hash.slice(0, 12))}</code></div>`).join("")}</div>
        <div class="decision"><p>Toute modification ou suppression d'un événement après coup rompt la chaîne et est signalée ici.</p><button class="btn primary" id="au-verify">${icon("shield")}Vérifier l'intégrité</button></div></section>
      <section class="panel flush"><div class="panel-head"><h2>Journal</h2><label class="search-in" style="width:min(320px,100%)">${icon("search")}<span class="sr">Filtrer</span><input class="input" id="au-q" placeholder="Filtrer : action, acteur, dossier…"></label></div>
        <div class="panel-body table-wrap"><table class="table"><thead><tr><th>Date</th><th>Action</th><th>Acteur</th><th class="hide-sm">Dossier</th><th class="hide-sm">Empreinte</th></tr></thead><tbody id="au-rows"></tbody></table></div>
        <div class="pager"><span></span><button class="btn sm" id="au-more">Afficher 50 événements de plus</button></div></section></div>`;
    let shown = 50;
    const draw = q => {
      q = q.toLowerCase();
      const rows = evenements.slice().reverse().filter(e => !q || [e.action, ACTION_LABEL[e.action], e.actor, e.case_id].join(" ").toLowerCase().includes(q));
      $("#au-more", el).hidden = rows.length <= shown;
      $("#au-rows", el).innerHTML = rows.slice(0, shown).map(e => `<tr><td class="num" title="${esc(e.at)}">${esc(when(e.at))}</td><td>${esc(ACTION_LABEL[e.action] || e.action)}</td>
        <td>${esc(e.actor)}</td><td class="hide-sm">${e.case_id && !e.case_id.startsWith("_") ? `<a href="#/dossiers/${encodeURIComponent(e.case_id)}">${esc(e.case_id)}</a>` : `<span class="cell-sub" style="display:inline">${esc(e.case_id || "—")}</span>`}</td>
        <td class="hide-sm"><span class="mono" style="font-size:12px;color:var(--ink-3)">${esc(e.hash.slice(0, 16))}</span></td></tr>`).join("")
        || `<tr><td colspan="5" class="cell-sub">Aucun événement.</td></tr>`;
    };
    draw("");
    $("#au-more", el).addEventListener("click", () => { shown += 50; draw($("#au-q", el).value); });
    $("#au-q", el).addEventListener("input", e => draw(e.target.value));
    $("#au-verify", el).addEventListener("click", async () => {
      const btn = $("#au-verify", el); btn.disabled = true; btn.innerHTML = `<span class="spin"></span>Vérification…`;
      try {
        const r = await getJSON("/v1/audit/verify");
        const box = $("#au-state", el);
        box.className = `integrity ${r.intacte ? "ok" : "bad"}`;
        box.querySelector("div").innerHTML = r.intacte
          ? `<b>Chaîne intacte</b><p>${r.evenements} événements vérifiés un à un. Dernière empreinte <span class="mono">${esc((r.derniere_empreinte || "").slice(0, 24))}…</span></p>`
          : `<b>Chaîne rompue</b><p>L'événement n° ${r.premier_evenement_altere} a été modifié ou supprimé après son inscription.</p>`;
        const ch = $("#au-chain", el); ch.classList.remove("verified"); void ch.offsetWidth; ch.classList.add("verified");
        toast(r.intacte ? "Piste d'audit intacte." : "Piste d'audit altérée !", r.intacte ? "ok" : "bad");
      } catch (err) { toast(err.message, "bad"); }
      btn.disabled = false; btn.innerHTML = `${icon("shield")}Vérifier de nouveau`;
    });
  }

  /* ---------------------------------------------------------------- système */
  async function systeme(el) {
    const h = await (await fetch("/health")).json();
    const yes = v => v ? `<span class="status ok">activé</span>` : `<span class="status">désactivé</span>`;
    el.innerHTML = `<div class="grid g-2">
      <section class="panel"><div class="panel-head"><h2>Service</h2><span class="status ok">En ligne</span></div><div class="panel-body"><dl class="kv">
        <div><dt>Version</dt><dd>${esc(h.version)}</dd></div>
        <div><dt>Modèle de langage</dt><dd>${esc(h.llm_provider === "fake" ? "factice (tests)" : h.llm_provider)}</dd></div>
        <div><dt>Routeur des demandes</dt><dd>${esc(h.router_mode)}</dd></div>
        <div><dt>Comptes</dt><dd>${h.registre?.comptes ? "connexion obligatoire" : "aucun compte : mode développement"}</dd></div>
        <div><dt>Documentation</dt><dd><a href="/docs" target="_blank" rel="noopener">API interactive (OpenAPI)</a></dd></div></dl></div></section>
      <section class="panel"><div class="panel-head"><h2>Recherche dans la norme</h2></div><div class="panel-body"><dl class="kv">
        <div><dt>Mode</dt><dd>${esc(h.rag.mode)} · découpage ${esc(h.rag.chunking)}</dd></div>
        <div><dt>Modèle d'embedding</dt><dd>${esc(h.rag.embedding || "—")}</dd></div>
        <div><dt>Base vectorielle</dt><dd>${esc(h.rag.store)}</dd></div>
        <div><dt>Agent LangGraph</dt><dd>${yes(h.rag.agent_langgraph)}</dd></div>
        <div><dt>Glossaire des sigles</dt><dd>${yes(h.rag.glossaire)}</dd></div>
        <div><dt>Index des questions</dt><dd>${yes(h.rag.index_questions)}</dd></div>
        <div><dt>Graphe des renvois</dt><dd>${yes(h.rag.graphe_renvois)}</dd></div>
        <div><dt>Reranker</dt><dd>${esc(h.rag.reranker || "aucun")}</dd></div>
        <div><dt>Vérificateur</dt><dd>${yes(h.rag.verificateur)}</dd></div></dl>
        ${h.rag.avertissements?.length ? `<div class="callout warn" style="margin-top:14px">${icon("alert")}<div><b>Configuration à revoir</b><ul>${h.rag.avertissements.map(w => `<li>${esc(w)}</li>`).join("")}</ul></div></div>` : ""}
      </div></section></div>`;
  }

  const PANELS = { comptes, audit, systeme };
  async function show(name) {
    tab = name;
    emit("crumbs", [{ label: "Administration", href: "#/admin" }, { label: TABS.find(t => t[0] === name)[1] }]);
    $$(".tabs [role=tab]", main).forEach(b => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
    history.replaceState(null, "", `#/admin${name === "comptes" ? "" : "/" + name}`);
    const el = $("#ad-body", main);
    el.innerHTML = `<div class="view-loading" style="min-height:200px"><span class="spin"></span></div>`;
    try { await PANELS[name](el); } catch (err) { el.innerHTML = `<div class="callout bad">${icon("alert")}<span>${esc(err.message)}</span></div>`; }
  }
  $$(".tabs [role=tab]", main).forEach(b => b.addEventListener("click", () => show(b.dataset.tab)));
  await show(tab);
}
