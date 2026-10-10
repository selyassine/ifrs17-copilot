/* IFRS 17 Copilot — interface web (JavaScript sans dépendance : fonctionne hors ligne). */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const TOKEN_KEY = "ifrs17.token";
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function fr(x, d = 2) {
  return Number(x).toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });
}
function token() {
  try { return localStorage.getItem(TOKEN_KEY) ?? "change-moi"; } catch { return "change-moi"; }
}

async function api(path, { method = "GET", json, form } = {}) {
  const headers = { "X-API-Token": token() };
  let body;
  if (json !== undefined) { headers["Content-Type"] = "application/json; charset=utf-8"; body = JSON.stringify(json); }
  if (form) body = form;
  const res = await fetch(path, { method, headers, body });
  if (res.status === 401) { openSettings("Le jeton de l'API est refusé : saisissez la valeur d'API_TOKEN du fichier .env."); throw new Error("Jeton refusé."); }
  if (!res.ok) {
    let detail = `Erreur ${res.status}`;
    try { const j = await res.json(); detail = j.detail || detail; } catch { /* réponse non JSON */ }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res;
}

/* ------------------------------------------------------------------ navigation */
const VIEWS = ["accueil", "analyser", "norme", "simuler", "resultats", "fonctionnement"];
function route() {
  const name = (location.hash.replace("#/", "") || "accueil").split("?")[0];
  const view = VIEWS.includes(name) ? name : "accueil";
  $$("[data-view]").forEach(s => { s.hidden = s.dataset.view !== view; });
  $$("[data-nav]").forEach(a => {
    if (a.dataset.nav === view) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  document.title = `${$(`[data-nav="${view}"]`).textContent.trim()} · IFRS 17 Copilot`;
  if (view === "resultats") loadMetrics();
  if (view === "analyser") loadSamples();
  $("#view").focus({ preventScroll: true });
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);

/* ------------------------------------------------------------------ état du service */
async function health() {
  const box = $("#status");
  try {
    const r = await fetch("/health");
    const h = await r.json();
    const llm = h.llm_provider === "fake" ? "LLM factice (tests)" : "LLM connecté";
    box.className = "status ok";
    $("#status-text").textContent = `API en ligne, ${llm}`;
    box.title = `Version ${h.version}, routeur ${h.router_mode}`;
  } catch {
    box.className = "status bad";
    $("#status-text").textContent = "API injoignable";
    box.title = "Lancer l'API : .\\make.ps1 serve";
  }
}

/* ------------------------------------------------------------------ réglages */
function openSettings(message) {
  const dlg = $("#settings");
  $("#token").value = token();
  const hint = $(".settings .hint");
  hint.textContent = message || "Gardé dans ce navigateur uniquement.";
  if (!dlg.open) dlg.showModal();
}
$("#open-settings").addEventListener("click", () => openSettings());
$("#settings").addEventListener("close", () => {
  if ($("#settings").returnValue === "save") {
    try { localStorage.setItem(TOKEN_KEY, $("#token").value.trim()); } catch { /* stockage indisponible */ }
  }
});

/* ------------------------------------------------------------------ chaîne de contrôle */
const AGENTS = {
  "extracteur": ["Extracteur", "lit le document"],
  "calculateur": ["Calculateur", "calcule la marge en Python, sans LLM"],
  "chercheur_rag+verificateur": ["Chercheur et vérificateur", "cherche la norme, puis relit la réponse"],
  "chercheur_rag": ["Chercheur", "réponse de référence déjà vérifiée"],
  "redacteur": ["Rédacteur", "rédige la note"],
};
const ICON = {
  ok: '<svg viewBox="0 0 16 16"><path d="M3 8.5l3 3 7-7"/></svg>',
  warn: '<svg viewBox="0 0 16 16"><path d="M8 3.5v5.5M8 12.2v.3"/></svg>',
  bad: '<svg viewBox="0 0 16 16"><path d="M4 4l8 8M12 4l-8 8"/></svg>',
  ref: '<svg viewBox="0 0 16 16"><path d="M3 8.5l3 3 7-7"/></svg>',
};
function stepClass(status) {
  if (status === "en cours") return "running";
  if (["ok", "note_prete"].includes(status)) return "ok";
  if (["reference", "saute"].includes(status)) return "ref";
  if (["echec", "erreur"].includes(status)) return "bad";
  if (status === "pending") return "pending";
  return "warn";
}
const STATUS_LABEL = {
  "ok": "vérifié", "reference": "référence", "saute": "données validées", "a_verifier": "à vérifier",
  "validation_humaine": "à valider", "echec": "échec", "erreur": "erreur", "repli": "synthèse du code",
  "refus": "pas de réponse", "en cours": "en cours", "pending": "",
};
function stepHTML(st) {
  const cls = stepClass(st.status);
  const [name, desc] = AGENTS[st.agent] || [st.agent, ""];
  const detail = st.detail ? esc(st.detail) : esc(desc);
  const time = st.status === "en cours" || st.status === "pending" ? "" : `${(st.ms / 1000).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} s`;
  return `<li class="${cls}"><span class="mark">${ICON[cls] || ""}</span>
    <div><div class="who">${esc(name)} <span class="what">${esc(STATUS_LABEL[st.status] ?? st.status)}</span></div>
    <div class="what">${detail}</div></div><span class="ms num">${time}</span></li>`;
}

/* Rejeu d'un dossier réel sur l'accueil (une seule animation, au chargement). */
const REPLAY = [
  { agent: "extracteur", status: "ok", detail: "PDF lu par sa couche texte, chiffres retrouvés dans le document", ms: 9100 },
  { agent: "calculateur", status: "ok", detail: "groupe bénéficiaire, CSM initiale 397,89", ms: 4 },
  { agent: "chercheur_rag+verificateur", status: "ok", detail: "Comment la CSM est-elle déterminée à l'origine ? Réponse citant le §38", ms: 23800 },
  { agent: "chercheur_rag+verificateur", status: "ok", detail: "Comment la CSM est-elle libérée ? Réponse citant B119 et §43", ms: 21400 },
  { agent: "redacteur", status: "ok", detail: "synthèse du LLM : chaque nombre et chaque paragraphe vérifiés", ms: 6200 },
];
let replayTimer;
function replay() {
  clearTimeout(replayTimer);
  const list = $("#hero-chain");
  const result = $("#hero-result");
  result.hidden = true;
  if (reduceMotion) { list.innerHTML = REPLAY.map(stepHTML).join(""); result.hidden = false; return; }
  list.innerHTML = REPLAY.map(s => stepHTML({ ...s, status: "pending" })).join("");
  let i = 0;
  const tick = () => {
    const rows = $$("li", list);
    rows[i].outerHTML = stepHTML({ ...REPLAY[i], status: "en cours" });
    replayTimer = setTimeout(() => {
      $$("li", list)[i].outerHTML = stepHTML(REPLAY[i]);
      i += 1;
      if (i < REPLAY.length) replayTimer = setTimeout(tick, 120);
      else result.hidden = false;
    }, 650);
  };
  replayTimer = setTimeout(tick, 350);
}
$("#replay").addEventListener("click", replay);

/* ------------------------------------------------------------------ analyser un dossier */
const LAYOUT = { lignes: "tableau en lignes", colonnes: "tableau en colonnes", recit: "texte et tableau" };
let samples = null;
let chosenFile = null;
let lastResult = null;

async function loadSamples() {
  if (samples) return;
  const sel = $("#sample");
  try {
    samples = await (await fetch("/v1/samples")).json();
  } catch { samples = []; }
  const groups = { simple: "Documents simples", piege: "Documents piégés" };
  for (const [kind, label] of Object.entries(groups)) {
    const og = document.createElement("optgroup");
    og.label = label;
    samples.filter(s => s.kind === kind).forEach(s => {
      const o = document.createElement("option");
      o.value = s.id;
      o.disabled = !s.available;
      const what = s.kind === "piege" ? s.piege : `${LAYOUT[s.layout] || s.layout}${s.scan ? ", version scannée disponible" : ""}`;
      o.textContent = `${s.id}, ${what}${s.available ? "" : " (à générer)"}`;
      og.append(o);
    });
    if (og.children.length) sel.append(og);
  }
  if (!samples.some(s => s.available)) $("#sample-hint").textContent = "Aucun document d'exemple : lancez python -m multimodal.synth puis python -m multimodal.synth_hard.";
}

function setFile(file) {
  chosenFile = file;
  const tag = $("#drop-file");
  tag.hidden = !file;
  tag.textContent = file ? `${file.name} (${Math.round(file.size / 1024)} Ko)` : "";
  if (file) $("#sample").value = "";
  updateRun();
}
function updateRun() { $("#run").disabled = !(chosenFile || $("#sample").value); }

$("#file").addEventListener("change", e => setFile(e.target.files[0] || null));
const drop = $("#drop");
["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, () => drop.classList.remove("over")));
drop.addEventListener("drop", e => { e.preventDefault(); if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); });
$("#sample").addEventListener("change", () => {
  const s = (samples || []).find(x => x.id === $("#sample").value);
  if (s) { chosenFile = null; $("#drop-file").hidden = true; $("#file").value = ""; }
  const img = $('input[name="fmt"][value="image"]');
  img.disabled = !s || !s.has_image;
  if (img.disabled) $('input[name="fmt"][value="pdf"]').checked = true;
  $("#sample-hint").textContent = !s ? "" : s.attendu === "alerte"
    ? "Attendu : le dossier doit partir en validation humaine, une information manque ou est ambiguë."
    : s.kind === "piege" ? "Attendu : piège déjoué, note prête et CSM juste." : "Attendu : note prête et CSM juste.";
  updateRun();
});

let clock;
$("#intake").addEventListener("submit", async e => {
  e.preventDefault();
  const run = $("#run");
  run.disabled = true;
  run.textContent = "Analyse en cours…";
  $("#result").hidden = true;
  $("#outcome").innerHTML = "";
  const chain = $("#live-chain");
  chain.innerHTML = "";
  const t0 = performance.now();
  clearInterval(clock);
  clock = setInterval(() => { $("#run-time").textContent = `${((performance.now() - t0) / 1000).toFixed(0)} s`; }, 500);
  try {
    let file = chosenFile;
    if (!file) {
      const id = $("#sample").value;
      const fmt = $('input[name="fmt"]:checked').value;
      const blob = await (await api(`/v1/samples/${id}?format=${fmt}`)).blob();
      file = new File([blob], fmt === "image" ? `${id}.jpg` : `${id}.pdf`, { type: blob.type });
    }
    const form = new FormData();
    form.append("file", file);
    const res = await api("/v1/case/stream", { method: "POST", form });
    await readStream(res, ev => {
      if (ev.type === "step") {
        const html = stepHTML(ev);
        const rows = $$("li", chain);
        if (rows[ev.index]) rows[ev.index].outerHTML = html; else chain.insertAdjacentHTML("beforeend", html);
      } else if (ev.type === "notification") {
        $("#outcome").innerHTML = `<p class="mail">Validation humaine demandée : envoi de l'e-mail au valideur…</p>`;
      } else if (ev.type === "result") {
        showResult(ev.data);
      } else if (ev.type === "error") {
        $("#outcome").innerHTML = `<div class="outcome bad"><h3>Analyse interrompue</h3><p>${esc(ev.detail)}</p></div>`;
      }
    });
  } catch (err) {
    $("#outcome").innerHTML = `<div class="outcome bad"><h3>Analyse impossible</h3><p>${esc(err.message)}</p></div>`;
  } finally {
    clearInterval(clock);
    run.textContent = "Lancer l'analyse";
    updateRun();
  }
});

async function readStream(res, onEvent) {
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let cut;
    while ((cut = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, cut);
      buf = buf.slice(cut + 2);
      const line = chunk.split("\n").find(l => l.startsWith("data: "));
      if (line) onEvent(JSON.parse(line.slice(6)));
    }
  }
}

function showResult(r) {
  lastResult = r;
  const box = $("#outcome");
  const csm = r.csm;
  const figures = csm ? `<dl class="figures">
      <div><dt>${csm.onerous ? "Perte immédiate" : "CSM initiale"}</dt><dd class="num">${fr(csm.onerous ? csm.initial_loss_component : csm.initial_csm)}</dd></div>
      <div><dt>Flux de trésorerie d'exécution</dt><dd class="num">${fr(csm.fulfilment_cash_flows)}</dd></div>
      <div><dt>Ajustement pour risque</dt><dd class="num">${fr(csm.risk_adjustment)}</dd></div>
    </dl>` : "";
  if (r.status === "note_prete") {
    box.innerHTML = `<div class="outcome ok"><span class="stamp ok">Note prête</span><h3 style="margin-top:10px">Tous les contrôles sont passés</h3>${figures}</div>`;
  } else if (r.status === "validation_humaine") {
    box.innerHTML = `<div class="outcome warn"><span class="stamp warn">À valider par un humain</span>
      <h3 style="margin-top:10px">Un contrôle n'est pas passé : la note reste provisoire</h3>
      <ul>${r.controls.map(c => `<li>${esc(c)}</li>`).join("")}</ul>
      ${mailLine(r.notification)}
      <p style="margin-top:10px">Vérifiez les données extraites dans l'onglet « Données extraites », corrigez-les si besoin, puis validez.</p>${figures}</div>`;
  } else {
    box.innerHTML = `<div class="outcome bad"><span class="stamp bad">Document inexploitable</span>
      <h3 style="margin-top:10px">Les données nécessaires au calcul n'ont pas pu être lues</h3>
      <ul>${r.controls.map(c => `<li>${esc(c)}</li>`).join("")}</ul></div>`;
  }
  renderTabs(r);
}

/* Validation humaine : l'API a transmis le dossier à n8n, qui envoie l'e-mail au valideur (D-041). */
function mailLine(n) {
  if (!n) return "";
  return n.envoyee
    ? `<p class="mail sent"><b>E-mail envoyé au valideur.</b> Il a reçu la note provisoire et un formulaire pré-rempli : il peut valider depuis sa boîte mail, ou vous pouvez valider ici.</p>`
    : `<p class="mail"><b>E-mail non envoyé.</b> ${esc(n.detail)}. Vous pouvez valider ici.</p>`;
}

function renderTabs(r) {
  const result = $("#result");
  result.hidden = !(r.note_html || r.portfolio);
  $("#note-frame").srcdoc = r.note_html || "<p style='font-family:sans-serif'>Pas de note pour ce dossier.</p>";
  $('[data-panel="data"]').innerHTML = dataPanel(r);
  $('[data-panel="norm"]').innerHTML = (r.norm || []).map(n => `<div class="a" style="margin-bottom:26px">
      <h3>${esc(n.question)}</h3>
      <p class="text" style="margin-top:8px">${esc(n.answer.answer || n.answer.refusal_reason || "")}</p>
      ${(n.answer.citations || []).map(c => `<div class="quote"><b>§${esc(c.paragraph_id)}</b>« ${esc(c.quote)} »</div>`).join("")}
      <div class="meta"><span class="stamp ${n.verdict === "ok" ? "ok" : "warn"}">${n.verdict === "ok" ? "Relue et validée" : "À valider"}</span></div>
    </div>`).join("") || "<p>Aucune question posée à la norme pour ce dossier.</p>";
  const form = $("#validate-form");
  if (form) form.addEventListener("submit", submitValidation);
  selectTab(r.status === "validation_humaine" ? "data" : "note");
}

function dataPanel(r) {
  const p = r.portfolio;
  if (!p) return "<p>Aucune donnée exploitable.</p>";
  const edit = r.status === "validation_humaine";
  const rates = Array.isArray(p.discount_rates) ? p.discount_rates : null;
  const cell = (name, k, v) => edit ? `<input name="${name}.${k}" value="${v}" inputmode="decimal" aria-label="${name} période ${k + 1}">` : fr(v, name === "coverage_units" ? 0 : 2);
  const rows = p.premiums.map((_, k) => `<tr><th scope="row">Période ${k + 1}</th>
      <td>${cell("premiums", k, p.premiums[k])}</td><td>${cell("outflows", k, p.outflows[k])}</td>
      <td>${cell("coverage_units", k, p.coverage_units[k])}</td>${rates ? `<td>${cell("discount_rates", k, rates[k])}</td>` : ""}</tr>`).join("");
  const meta = edit ? `<div class="meta-fields">
      <label>Groupe<input name="group_id" value="${esc(p.group_id)}"></label>
      <label>Devise<input name="currency" value="${esc(p.currency)}" maxlength="3"></label>
      <label>Unité des montants<input name="unit_multiplier" value="${p.unit_multiplier}" inputmode="numeric"></label>
      ${rates ? "" : `<label>Taux d'actualisation (décimal)<input name="discount_rate" value="${p.discount_rates}" inputmode="decimal"></label>`}
      <label>Ajustement pour risque (décimal)<input name="risk_adjustment_pct" value="${p.risk_adjustment_pct}" inputmode="decimal"></label>
    </div>` : `<p style="margin-bottom:12px">Groupe <b>${esc(p.group_id)}</b>, ${esc(p.currency)}, montants ×${p.unit_multiplier.toLocaleString("fr-FR")}, ajustement pour risque ${fr(p.risk_adjustment_pct * 100)} %${rates ? "" : `, taux ${fr(p.discount_rates * 100)} %`}.</p>`;
  const table = `<table class="datagrid"><thead><tr><th>Période</th><th>Primes</th><th>Sorties</th><th>Unités de couverture</th>${rates ? "<th>Taux spot</th>" : ""}</tr></thead><tbody>${rows}</tbody></table>`;
  if (!edit) return meta + table;
  return `<form id="validate-form">${meta}${table}
    <div class="actions" style="margin-top:16px"><button class="btn primary" type="submit">Valider ces données et produire la note</button></div></form>`;
}

async function submitValidation(e) {
  e.preventDefault();
  const f = new FormData(e.target);
  const p = structuredClone(lastResult.portfolio);
  const num = v => Number(String(v).replace(/\s/g, "").replace(",", "."));
  for (const key of ["premiums", "outflows", "coverage_units"]) p[key] = p[key].map((_, k) => num(f.get(`${key}.${k}`)));
  if (Array.isArray(p.discount_rates)) p.discount_rates = p.discount_rates.map((_, k) => num(f.get(`discount_rates.${k}`)));
  else p.discount_rates = num(f.get("discount_rate"));
  p.group_id = f.get("group_id"); p.currency = f.get("currency");
  p.unit_multiplier = num(f.get("unit_multiplier")); p.risk_adjustment_pct = num(f.get("risk_adjustment_pct"));
  const btn = e.submitter; btn.disabled = true; btn.textContent = "Production de la note…";
  try {
    const r = await (await api("/v1/case/validated", { method: "POST", json: { portfolio: p, case_id: lastResult.case_id } })).json();
    $("#live-chain").innerHTML = r.steps.map(stepHTML).join("");
    showResult(r);
  } catch (err) {
    btn.disabled = false; btn.textContent = "Valider ces données et produire la note";
    alert(`Validation impossible : ${err.message}`);
  }
}

function selectTab(name) {
  $$(".tabs [role=tab]").forEach(b => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
  $$(".tabpanel").forEach(p => { p.hidden = p.dataset.panel !== name; });
}
$$(".tabs [role=tab]").forEach(b => b.addEventListener("click", () => selectTab(b.dataset.tab)));
$("#download").addEventListener("click", () => {
  if (!lastResult?.note_html) return;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([lastResult.note_html], { type: "text/html" }));
  a.download = `note-ifrs17-${lastResult.portfolio?.group_id || lastResult.case_id}.html`;
  a.click();
});

/* ------------------------------------------------------------------ interroger la norme */
const thread = $("#thread");
$$(".chip").forEach(c => c.addEventListener("click", () => { $("#question").value = c.textContent; $("#composer").requestSubmit(); }));
$("#question").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#composer").requestSubmit(); } });

$("#composer").addEventListener("submit", async e => {
  e.preventDefault();
  const q = $("#question").value.trim();
  if (!q) return;
  $("#question").value = "";
  addQuestion(q);
  const wait = addWaiting();
  try {
    const r = await (await api("/v1/ask", { method: "POST", json: { question: q } })).json();
    wait.replaceWith(answerNode(r));
  } catch (err) {
    wait.innerHTML = `<p class="text">${esc(err.message)}</p>`;
  }
});

function addQuestion(text, oral = false) {
  $(".suggest:not(.inline)")?.remove();
  thread.insertAdjacentHTML("beforeend", `<div class="q">${oral ? "<small>Question à l'oral, transcrite</small>" : ""}${esc(text)}</div>`);
}
function addWaiting(text = "Recherche dans la norme, puis relecture par le vérificateur…") {
  const d = document.createElement("div");
  d.className = "a typing";
  d.textContent = text;
  thread.append(d);
  d.scrollIntoView({ block: "nearest", behavior: reduceMotion ? "auto" : "smooth" });
  return d;
}
/* Nom lisible d'un identifiant de paragraphe : 44, B119, C5, art-2, cons-3, def:… */
function refLabel(id, long = false) {
  id = String(id);
  let m;
  if ((m = id.match(/^art-(\d+)$/))) return `Article ${m[1]}`;
  if ((m = id.match(/^cons-(\d+)$/))) return long ? `Modification d'autres normes, point ${m[1]}` : `modif. ${m[1]}`;
  if (id.startsWith("def:")) return long ? `Définition « ${id.slice(4)} » (annexe A)` : `définition « ${id.slice(4)} »`;
  if (/^[BC]\d/.test(id)) return long ? `Paragraphe ${id} (annexe ${id[0]})` : id;
  return long ? `Paragraphe ${id}` : `§${id}`;
}
function suggestions() {
  const box = document.createElement("div");
  box.className = "suggest inline";
  ["Quel est l'objectif d'IFRS 17 ?", "Comment la CSM est-elle libérée en résultat ?", "Quand un contrat est-il déficitaire dès l'origine ?"]
    .forEach(t => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "chip"; b.textContent = t;
      b.addEventListener("click", () => { $("#question").value = t; $("#composer").requestSubmit(); });
      box.append(b);
    });
  return box;
}
function answerNode(r) {
  const a = r.answer;
  const div = document.createElement("div");
  if (r.small_talk) {
    div.className = "a";
    div.innerHTML = `<p class="text">${esc(a.refusal_reason)}</p>`;
    div.append(suggestions());
    return div;
  }
  if (a.refused) {
    const outOfScope = r.plan.intent === "hors_perimetre";
    const seen = [...new Set((r.sources || []).flatMap(s => s.paragraph_ids || []))].slice(0, 6);
    div.className = "a refused";
    div.innerHTML = `<p class="text">${esc(outOfScope ? a.refusal_reason : "Je n'ai trouvé aucun passage de la norme qui réponde à cette question. Reformulez-la avec les termes du règlement (par exemple « objectif de la norme », « champ d'application », « marge sur services contractuels »).")}</p>
      ${!outOfScope && seen.length ? `<p class="hint">Passages consultés : ${seen.map(refLabel).map(esc).join(", ")}</p>` : ""}
      <div class="meta"><span class="stamp warn">Pas de réponse</span><span>${outOfScope ? "Question hors du périmètre d'IFRS 17" : "Aucun passage de la norme ne permet de répondre"}</span></div>`;
    return div;
  }
  const cites = Object.fromEntries((a.citations || []).map(c => [c.paragraph_id, c]));
  const html = esc(a.answer).replace(/\[([^\[\]]{1,60})\]/g, (m, ref) => {
    const id = ref.replace("§", "").trim();
    return cites[id] ? `<button class="cite" type="button" data-ref="${esc(id)}" aria-expanded="false" title="${esc(refLabel(id, true))}">${esc(ref)}</button>` : m;
  });
  const v = r.verdict;
  const verdict = !v ? "" : v.status === "ok" ? '<span class="stamp ok">Relue et validée</span>' : '<span class="stamp warn">À valider par un humain</span>';
  div.className = "a";
  div.innerHTML = `<p class="text">${html}</p><div class="quotes"></div>
    <div class="meta">${verdict}<span>${(a.citations || []).length} paragraphe(s) cité(s), vérifiés par le code</span>${r.rounds ? "<span>1 correction demandée par le vérificateur</span>" : ""}<span class="num">${(r.latency_ms / 1000).toFixed(1)} s</span></div>`;
  div.addEventListener("click", ev => {
    const b = ev.target.closest(".cite");
    if (!b) return;
    const open = b.getAttribute("aria-expanded") === "true";
    $$(".cite", div).forEach(x => x.setAttribute("aria-expanded", "false"));
    const box = $(".quotes", div);
    box.innerHTML = "";
    if (!open) {
      const c = cites[b.dataset.ref];
      b.setAttribute("aria-expanded", "true");
      box.innerHTML = `<div class="quote"><b>${esc(refLabel(c.paragraph_id, true))}, règlement (UE) 2021/2036</b>« ${esc(c.quote)} »</div>`;
    }
  });
  return div;
}

/* Question à l'oral : enregistrement dans le navigateur, puis /v1/ask/audio (Whisper). */
let recorder = null;
$("#mic").addEventListener("click", async () => {
  const mic = $("#mic");
  if (recorder && recorder.state === "recording") { recorder.stop(); return; }
  if (!navigator.mediaDevices?.getUserMedia) { alert("Ce navigateur ne permet pas d'enregistrer le micro."); return; }
  let stream;
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
  catch { alert("Accès au micro refusé : autorisez-le dans le navigateur."); return; }
  const chunks = [];
  recorder = new MediaRecorder(stream);
  recorder.ondataavailable = ev => chunks.push(ev.data);
  recorder.onstop = async () => {
    stream.getTracks().forEach(t => t.stop());
    mic.classList.remove("recording");
    mic.setAttribute("aria-label", "Poser la question à l'oral");
    const type = recorder.mimeType || "audio/webm";
    const ext = type.includes("ogg") ? "ogg" : type.includes("mp4") ? "m4a" : "webm";
    const form = new FormData();
    form.append("file", new File([new Blob(chunks, { type })], `question.${ext}`, { type }));
    const wait = addWaiting("Transcription par Whisper, puis recherche dans la norme…");
    try {
      const r = await (await api("/v1/ask/audio", { method: "POST", form })).json();
      wait.remove();
      addQuestion(r.transcription, true);
      thread.append(answerNode(r));
    } catch (err) {
      wait.innerHTML = `<p class="text">${esc(err.message)}</p>`;
    }
  };
  recorder.start();
  mic.classList.add("recording");
  mic.setAttribute("aria-label", "Arrêter l'enregistrement et envoyer");
});

/* ------------------------------------------------------------------ résultats mesurés */
let metricsLoaded = false;
async function loadMetrics() {
  if (metricsLoaded) return;
  metricsLoaded = true;
  const m = await (await fetch("data/metrics.json")).json();
  const r = m.retrieval;
  const bars = r.items.map(it => `<div class="bar${it.chosen ? " chosen" : ""}"><span>${esc(it.label)}</span>
      <div class="track"><div class="fill" style="width:${it.value * 100}%"></div></div><span class="num">${fr(it.value, 3)}</span></div>`).join("");
  const pairs = m.iterations.items.map(it => {
    const w = v => `${(v / it.total) * 100}%`;
    return `<div><div class="pair-label">${esc(it.label)}</div>
      <div class="pair"><span>avant</span><div class="track"><div class="fill before" style="width:${w(it.before)}"></div></div><span class="num">${it.before}/${it.total}</span></div>
      <div class="pair"><span>après</span><div class="track"><div class="fill after" style="width:${w(it.after)}"></div></div><span class="num">${it.after}/${it.total}</span></div></div>`;
  }).join("");
  const facts = list => `<dl class="facts">${list.map(it => `<div><dd class="num">${esc(it.value)}</dd><dt>${esc(it.label)}</dt></div>`).join("")}</dl>`;
  const ex = m.extraction;
  $("#metrics").innerHTML = `
    <section class="metric"><div><h2>${esc(r.title)}</h2><p class="take">${esc(r.takeaway)}</p><p class="unit">${esc(r.metric)}</p></div><div class="bars">${bars}</div></section>
    <section class="metric"><div><h2>${esc(m.iterations.title)}</h2><p class="take">Une version ne change qu'une chose ; elle est gardée si la mesure progresse sur le même jeu de test.</p></div><div class="pairs">${pairs}</div></section>
    <section class="metric"><div><h2>${esc(ex.title)}</h2><p class="take">${esc(ex.takeaway)}</p></div>
      <table class="ledger"><thead><tr><th>Mode</th><th>15 documents simples</th><th>10 documents piégés</th><th>Durée</th></tr></thead>
      <tbody>${ex.rows.map(x => `<tr><th scope="row">${esc(x.mode)}</th><td class="num nowrap">${esc(x.simple)}</td><td class="num">${esc(x.pieges)}</td><td class="num nowrap">${esc(x.duree)}</td></tr>`).join("")}</tbody></table></section>
    <section class="metric"><div><h2>${esc(m.safety.title)}</h2><p class="take">Une erreur grave, c'est une donnée fausse qui part au calcul sans contrôle humain. Elle est mesurée à part.</p></div>${facts(m.safety.items)}</section>
    <section class="metric"><div><h2>${esc(m.endtoend.title)}</h2><p class="take">Les six agents enchaînés sur dix documents piégés, avec les offres gratuites de Groq et de Gemini.</p></div>${facts(m.endtoend.items)}</section>
    <p class="hint">${esc(m.source)}</p>`;
}

/* ------------------------------------------------------------------ démarrage */
health();
route();
replay();


/* ------------------------------------------------------------------ simuler un groupe (D-042, D-043) */
const numList = (s, pct = false) => String(s || "").split(";").map(x => x.trim()).filter(Boolean)
  .map(x => { const v = Number(x.replace(/\s/g, "").replace(",", ".")); if (!Number.isFinite(v)) throw new Error(`« ${x} » n'est pas un nombre`); return pct ? v / 100 : v; });
const numOf = s => numList(s)[0] ?? 0;
$$("#sim-tabs [data-sim]").forEach(b => b.addEventListener("click", () => {
  $$("#sim-tabs [data-sim]").forEach(x => x.setAttribute("aria-selected", String(x === b)));
  $$("[data-simpanel]").forEach(p => { p.hidden = p.dataset.simpanel !== b.dataset.sim; });
}));

function bbaExample() {
  $("#b-premium").value = "1000000"; $("#b-expected").value = "200000 ; 200000 ; 200000 ; 200000";
  $("#b-actual").value = "200000 ; 220000 ; 220000 ; 220000"; $("#b-rates").value = "4,2 ; 4,3 ; 4,4 ; 3,5 ; 3,0";
  $("#b-ra").value = "50000"; $("#b-rachg").value = "0 ; 5000 ; 0 ; 0";
  $("#b-rev").value = "3 : 200000 ; 200000 ; 200000 ; 220000"; $("#b-cu").value = "100 ; 100 ; 100 ; 100"; $("#b-option").value = "OCI";
}
$("#b-example").addEventListener("click", bbaExample);
bbaExample();

const money = v => { const x = Math.abs(v) < 0.5 ? 0 : v; return `<td class="${x < 0 ? "neg" : ""}">${fr(x, 0)}</td>`; };
$("#bba-form").addEventListener("submit", async e => {
  e.preventDefault();
  const out = $("#bba-out");
  try {
    const rev = $("#b-rev").value.trim();
    let revisions = [];
    if (rev) {
      const [y, list] = rev.split(":");
      revisions = [{ at_end_of_year: Number(y), expected_claims: numList(list) }];
    }
    const body = {
      group_id: "SIMULATION", single_premium: numOf($("#b-premium").value), expected_claims: numList($("#b-expected").value),
      actual_claims: $("#b-actual").value.trim() ? numList($("#b-actual").value) : null, rates: numList($("#b-rates").value, true),
      ra_initial: numOf($("#b-ra").value), ra_changes: $("#b-rachg").value.trim() ? numList($("#b-rachg").value) : null,
      claim_revisions: revisions, coverage_units: $("#b-cu").value.trim() ? numList($("#b-cu").value) : null, finance_option: $("#b-option").value,
    };
    out.innerHTML = `<p class="mail">Calcul en cours…</p>`;
    const r = await (await api("/v1/csm/rollforward", { method: "POST", json: body })).json();
    const ys = r.years, head = ys.map(y => `<th>Année ${y.year}</th>`).join("");
    const line = (label, f) => `<tr><td>${label}</td>${ys.map(y => money(f(y))).join("")}</tr>`;
    const group = t => `<tr class="group"><td colspan="${ys.length + 1}">${t}</td></tr>`;
    out.innerHTML = `<div class="simsum">
        <div><span>BEL à l'origine</span><b>${fr(r.bel_initial, 0)}</b></div>
        <div><span>${r.loss_initial > 0 ? "Perte à l'origine" : "CSM à l'origine"}</span><b>${fr(r.loss_initial > 0 ? r.loss_initial : r.csm_initial, 0)}</b></div>
        <div><span>Résultat total</span><b>${fr(r.total_profit, 0)}</b></div>
        <div><span>OCI cumulé</span><b>${fr(r.total_oci, 0)}</b></div></div>
      <div class="simtable-wrap"><table class="simtable"><thead><tr><th>Montants en unités monétaires</th>${head}</tr></thead><tbody>
      ${group("Meilleure estimation (BEL)")}
      <tr><td>Taux d'ouverture → clôture</td>${ys.map(y => `<td>${fr(y.rate_open * 100, 1)} % → ${fr(y.rate_close * 100, 1)} %</td>`).join("")}</tr>
      ${line("BEL d'ouverture", y => y.bel_open)}${line("Intérêts (taux d'ouverture)", y => y.bel_interest)}${line("Sinistres attendus de l'année", y => y.bel_claims_expected)}
      ${line("Révision des sinistres futurs", y => y.bel_estimate_change)}${line("Effet du changement de taux", y => y.bel_rate_effect)}
      <tr class="total"><td>BEL de clôture</td>${ys.map(y => money(y.bel_close)).join("")}</tr>
      ${group("Ajustement pour risque (RA)")}
      ${line("RA d'ouverture", y => y.ra_open)}${line("Variation (services futurs)", y => y.ra_future_change)}${line("Libération (unités de couverture)", y => -y.ra_release)}
      <tr class="total"><td>RA de clôture</td>${ys.map(y => money(y.ra_close)).join("")}</tr>
      ${group("Marge sur services contractuels (CSM)")}
      ${line("CSM d'ouverture", y => y.csm_open)}${line("Capitalisation (taux bloqué)", y => y.csm_accretion)}${line("Ajustement (services futurs)", y => y.csm_adjustment)}
      <tr><td>Part libérée (unités de couverture)</td>${ys.map(y => `<td>${fr(y.coverage_ratio * 100, 0)} %</td>`).join("")}</tr>
      ${line("Libération en résultat", y => -y.csm_release)}
      <tr class="total"><td>CSM de clôture</td>${ys.map(y => money(y.csm_close)).join("")}</tr>
      ${line("Composante de perte (clôture)", y => y.loss_component_close)}
      ${group("Compte de résultat IFRS 17")}
      ${line("Produits des activités d'assurance", y => y.insurance_revenue)}${line("Charges des activités d'assurance", y => -y.insurance_service_expenses)}
      ${line("dont écart d'expérience", y => -y.experience_adjustment)}
      <tr class="total"><td>Résultat des activités d'assurance</td>${ys.map(y => money(y.insurance_service_result)).join("")}</tr>
      ${line("Charges financières d'assurance", y => y.insurance_finance_expense)}
      <tr class="total"><td>Résultat</td>${ys.map(y => money(y.profit)).join("")}</tr>
      ${line("Autres éléments du résultat global (OCI)", y => y.oci)}
      </tbody></table></div>`;
  } catch (err) {
    out.innerHTML = `<div class="outcome bad"><h3>Calcul impossible</h3><p>${esc(err.message)}</p></div>`;
  }
});

function paaExample() {
  $("#p-premium").value = "1000"; $("#p-start").value = "2025-07-01"; $("#p-months").value = "12"; $("#p-acq").value = "30"; $("#p-option").value = "1";
  $("#p-occ").value = "2026-05-15"; $("#p-est").value = "750"; $("#p-ra").value = "50"; $("#p-paidon").value = "2026-10-15"; $("#p-paid").value = "900";
  $("#p-dates").value = "2025-12-31 ; 2026-06-30 ; 2026-12-31";
}
$("#p-example").addEventListener("click", paaExample);
paaExample();
$("#paa-form").addEventListener("submit", async e => {
  e.preventDefault();
  const out = $("#paa-out");
  try {
    const claims = $("#p-occ").value ? [{ occurred: $("#p-occ").value, estimate: numOf($("#p-est").value), risk_adjustment: numOf($("#p-ra").value),
      paid_on: $("#p-paidon").value || null, paid_amount: $("#p-paidon").value ? numOf($("#p-paid").value) : null }] : [];
    const body = { contract: { group_id: "PAA", premium: numOf($("#p-premium").value), coverage_start: $("#p-start").value, coverage_months: Number($("#p-months").value),
      acquisition_costs: numOf($("#p-acq").value), expense_acquisition_costs: $("#p-option").value === "1", claims },
      at: $("#p-dates").value.split(";").map(x => x.trim()).filter(Boolean) };
    const rows = await (await api("/v1/paa/position", { method: "POST", json: body })).json();
    const line = (label, f) => `<tr><td>${label}</td>${rows.map(p => money(f(p))).join("")}</tr>`;
    out.innerHTML = `<div class="simtable-wrap"><table class="simtable"><thead><tr><th>Au</th>${rows.map(p => `<th>${esc(p.at)}</th>`).join("")}</tr></thead><tbody>
      <tr><td>Mois de couverture écoulés</td>${rows.map(p => `<td>${p.months_elapsed}</td>`).join("")}</tr>
      ${line("Passif pour couverture restante (LRC)", p => p.lrc)}${line("Passif pour sinistres survenus (LIC)", p => p.lic)}
      <tr class="group"><td colspan="${rows.length + 1}">Résultat cumulé</td></tr>
      ${line("Produits des activités d'assurance", p => p.revenue_to_date)}${line("Frais d'acquisition en charge", p => -p.acquisition_expense_to_date)}
      ${line("Sinistres et ajustement pour risque", p => -p.claims_expense_to_date)}
      <tr class="total"><td>Résultat cumulé</td>${rows.map(p => money(p.result_to_date)).join("")}</tr></tbody></table></div>`;
  } catch (err) {
    out.innerHTML = `<div class="outcome bad"><h3>Calcul impossible</h3><p>${esc(err.message)}</p></div>`;
  }
});
