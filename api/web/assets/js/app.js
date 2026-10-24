/* IFRS 17 Copilot — démarrage, connexion, mise en page, navigation, recherche. */
import { $, $$, esc, icon, state, saveSession, api, getJSON, canDo, me, on, emit, toast, modal,
  ROLE_LABEL, statusChip, setDevToken, devToken, debounce } from "./core.js";
import { medallion, band } from "./guilloche.js";

const ROUTES = [
  { re: /^\/?$/, nav: "overview", title: "Vue d'ensemble", load: () => import("./views/overview.js") },
  { re: /^\/dossiers\/([\w.-]+)(?:\/(\w+))?$/, nav: "cases", title: "Dossier", load: () => import("./views/case.js") },
  { re: /^\/dossiers$/, nav: "cases", title: "Dossiers", load: () => import("./views/cases.js") },
  { re: /^\/nouveau$/, nav: "intake", title: "Nouveau dossier", load: () => import("./views/intake.js"), role: "analyste" },
  { re: /^\/norme$/, nav: "norm", title: "Assistant normatif", load: () => import("./views/norm.js") },
  { re: /^\/simulateur$/, nav: "simulate", title: "Simulateur", load: () => import("./views/simulate.js") },
  { re: /^\/admin(?:\/(\w+))?$/, nav: "admin", title: "Administration", load: () => import("./views/admin.js"), role: "admin" },
];

/* ------------------------------------------------------------------ icônes déclarées dans le HTML */
function hydrateIcons(root = document) {
  $$("[data-icon]", root).forEach(el => { el.innerHTML = icon(el.dataset.icon); el.removeAttribute("data-icon"); });
}

/* ------------------------------------------------------------------ thème */
function applyThemeIcon() {
  const dark = document.documentElement.dataset.theme === "dark";
  $("#theme-btn").innerHTML = icon(dark ? "sun" : "moon");
  $("#theme-btn").setAttribute("aria-label", dark ? "Passer en thème clair" : "Passer en thème sombre");
}
$("#theme-btn").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("ifrs17.theme", next); } catch { /* stockage indisponible */ }
  applyThemeIcon();
  emit("theme", next);
});

/* ------------------------------------------------------------------ connexion */
function showLogin(message = "", tone = "bad") {
  $("#shell").hidden = true;
  $("#login").hidden = false;
  const err = $("#login-error");
  err.hidden = !message;
  err.className = `callout ${tone}`;
  err.innerHTML = message ? `${icon(tone === "bad" ? "alert" : "info")}<span>${esc(message)}</span>` : "";
  $("#login-dev").hidden = state.authRequired;
  const svg = $("#login-medallion");
  if (!svg.childElementCount) medallion(svg, { draw: true });
  document.body.classList.remove("booting");
  setTimeout(() => $("#login-user").focus(), 50);
}
$("#pw-toggle").innerHTML = icon("eye");
$("#pw-toggle").addEventListener("click", () => {
  const input = $("#login-pass");
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  $("#pw-toggle").setAttribute("aria-pressed", String(show));
  $("#pw-toggle").setAttribute("aria-label", show ? "Masquer le mot de passe" : "Afficher le mot de passe");
  $("#pw-toggle").innerHTML = icon(show ? "eyeOff" : "eye");
});
$("#login-form").addEventListener("submit", async e => {
  e.preventDefault();
  const user = $("#login-user"), pass = $("#login-pass");
  user.setAttribute("aria-invalid", String(!user.value.trim()));
  pass.setAttribute("aria-invalid", String(!pass.value));
  if (!user.value.trim() || !pass.value) { showLogin("Saisissez votre identifiant et votre mot de passe."); return; }
  const btn = $("#login-submit");
  btn.disabled = true; btn.innerHTML = `<span class="spin"></span>Connexion…`;
  try {
    const res = await fetch("/v1/auth/login", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: user.value.trim(), password: pass.value }) });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `Erreur ${res.status}`);
    saveSession({ token: body.token, user: body.user });
    pass.value = "";
    enterApp();
  } catch (err) {
    showLogin(err.message === "Failed to fetch" ? "Le serveur ne répond pas. Vérifiez que l'API est lancée." : err.message);
  } finally {
    btn.disabled = false; btn.textContent = "Se connecter";
  }
});
$("#dev-enter").addEventListener("click", () => enterApp());
on("auth:expired", msg => showLogin(msg, "info"));
on("auth:token", async () => {
  const r = await modal({ title: "Jeton de l'API", body: `<p class="modal-text">L'API refuse le jeton actuel. Saisissez la valeur d'API_TOKEN du fichier .env ; elle reste dans ce navigateur.</p>
    <label class="field">Jeton<input name="token" type="password" autocomplete="off" value="${esc(devToken())}"></label>`,
    actions: [{ label: "Annuler", value: "cancel" }, { label: "Enregistrer", value: "ok", tone: "primary", submit: true }] });
  if (r.value === "ok") { setDevToken(r.data.token.trim()); route(); }
});
$("#devbar-token").addEventListener("click", () => emit("auth:token"));

async function logout() {
  try { await api("/v1/auth/logout", { method: "POST" }); } catch { /* session déjà close */ }
  saveSession(null);
  location.hash = "#/";
  showLogin("Vous êtes déconnecté.", "info");
}
$("#logout-btn").addEventListener("click", logout);

/* ------------------------------------------------------------------ menu utilisateur */
const userBtn = $("#user-btn"), userMenu = $("#user-menu");
function toggleMenu(open = userMenu.hidden) {
  userMenu.hidden = !open;
  userBtn.setAttribute("aria-expanded", String(open));
  if (open) $("[role=menuitem]", userMenu).focus();
}
userBtn.addEventListener("click", () => toggleMenu());
document.addEventListener("click", e => { if (!e.target.closest(".usermenu")) toggleMenu(false); });
userMenu.addEventListener("keydown", e => {
  const items = $$("[role=menuitem]", userMenu);
  const i = items.indexOf(document.activeElement);
  if (e.key === "Escape") { toggleMenu(false); userBtn.focus(); }
  if (e.key === "ArrowDown") { e.preventDefault(); items[(i + 1) % items.length].focus(); }
  if (e.key === "ArrowUp") { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
});

function applyUser() {
  const u = me();
  const name = u ? (u.display_name || u.username) : "Développement";
  $("#user-name").textContent = name;
  $("#user-role").textContent = u ? ROLE_LABEL[u.role] || u.role : "sans compte";
  $("#user-initials").textContent = name.split(/\s+/).map(w => w[0]).slice(0, 2).join("").toUpperCase();
  $("#menu-name").textContent = name;
  $("#menu-login").textContent = u ? `${u.username} · ${ROLE_LABEL[u.role] || u.role}` : "mode développement";
  $("#logout-btn").hidden = !u;
  $$("[data-role]").forEach(el => { el.hidden = !canDo(el.dataset.role); });
  $("#devbar").hidden = !!u;
}

/* ------------------------------------------------------------------ état du service */
async function health() {
  const sys = $("#sys");
  try {
    const h = await (await fetch("/health")).json();
    state.health = h;
    sys.className = "sys ok";
    $("#sys-text").textContent = `Service opérationnel · v${h.version}`;
    sys.title = `Modèle : ${h.llm_provider === "fake" ? "factice (tests)" : h.llm_provider}`;
  } catch {
    sys.className = "sys bad";
    $("#sys-text").textContent = "API injoignable";
  }
}
$("#sys").addEventListener("click", () => { location.hash = canDo("admin") ? "#/admin/systeme" : "#/"; });

async function refreshWaiting() {
  if (!canDo("analyste")) return;
  try {
    const r = await getJSON("/v1/cases?status=validation_humaine&limit=1");
    const n = r.total;
    for (const el of [$("#bell-count"), $("#nav-waiting")]) { el.hidden = !n; el.textContent = n; }
    $("#bell").setAttribute("aria-label", n ? `${n} dossier(s) à valider` : "Aucun dossier à valider");
  } catch { /* indicateur facultatif */ }
}
on("cases:changed", refreshWaiting);

/* ------------------------------------------------------------------ navigation */
let cleanup = null;
let routeToken = 0;
on("crumbs", list => {
  $("#crumbs").innerHTML = list.map((c, i) => i < list.length - 1
    ? `<a href="${c.href}">${esc(c.label)}</a>${icon("chevronR")}` : `<span aria-current="page">${esc(c.label)}</span>`).join("");
});

async function route() {
  const raw = location.hash.replace(/^#/, "") || "/";
  const [path, qs] = raw.split("?");
  const query = new URLSearchParams(qs || "");
  let r = ROUTES.find(x => x.re.test(path));
  let params = r ? path.match(r.re).slice(1) : [];
  if (!r || (r.role && !canDo(r.role))) { r = ROUTES[0]; params = []; if (path !== "/") history.replaceState(null, "", "#/"); }
  $$("[data-nav]").forEach(a => (a.dataset.nav === r.nav ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  document.title = `${r.title} · IFRS 17 Copilot`;
  closeRail();
  const token = ++routeToken;
  if (cleanup) { try { cleanup(); } catch { /* vue déjà démontée */ } cleanup = null; }
  const main = $("#main");
  main.classList.remove("enter");
  main.innerHTML = `<div class="view-loading"><span class="spin"></span></div>`;
  emit("crumbs", [{ label: r.title }]);
  try {
    const mod = await r.load();
    if (token !== routeToken) return;
    main.innerHTML = "";
    cleanup = (await mod.render(main, params, query)) || null;
    hydrateIcons(main);
    void main.offsetWidth;
    main.classList.add("enter");
  } catch (err) {
    if (token !== routeToken) return;
    main.innerHTML = `<div class="page"><div class="callout bad">${icon("alert")}<div><b>Cette page n'a pas pu s'afficher.</b><p>${esc(err.message)}</p></div></div></div>`;
    console.error(err);
  }
  if (!main.contains(document.activeElement)) main.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);
export const go = hash => { if (location.hash === hash) route(); else location.hash = hash; };

/* menu latéral sur petit écran */
function closeRail() { document.body.classList.remove("rail-open"); $("#menu-btn").setAttribute("aria-expanded", "false"); }
$("#menu-btn").addEventListener("click", () => {
  const open = !document.body.classList.contains("rail-open");
  document.body.classList.toggle("rail-open", open);
  $("#menu-btn").setAttribute("aria-expanded", String(open));
});

/* ------------------------------------------------------------------ recherche (Ctrl K) */
const PAGES = [
  ["Vue d'ensemble", "#/", "overview"], ["Dossiers", "#/dossiers", "folder"], ["Nouveau dossier", "#/nouveau", "upload", "analyste"],
  ["Dossiers à valider", "#/dossiers?statut=validation_humaine", "bell"], ["Assistant normatif", "#/norme", "norm"],
  ["Simulateur (modèle général et PAA)", "#/simulateur", "chart"], ["Administration : comptes", "#/admin", "users", "admin"],
  ["Administration : piste d'audit", "#/admin/audit", "chain", "admin"], ["Administration : état du système", "#/admin/systeme", "activity", "admin"],
];
const palette = $("#palette"), pq = $("#palette-q"), plist = $("#palette-list");
let pItems = [], pIndex = 0;
function drawPalette() {
  plist.innerHTML = pItems.length ? pItems.map((it, i) => `<li role="option" aria-selected="${i === pIndex}" data-i="${i}">
      ${icon(it.icon)}<span class="p-main">${it.html}</span>${it.side ? `<span class="p-side">${it.side}</span>` : ""}</li>`).join("")
    : `<li class="p-empty">Aucun résultat. Essayez une référence de dossier ou un nom de groupe.</li>`;
}
const searchCases = debounce(async q => {
  const pages = PAGES.filter(p => (!p[3] || canDo(p[3])) && p[0].toLowerCase().includes(q.toLowerCase()))
    .map(p => ({ icon: p[2], html: esc(p[0]), href: p[1] }));
  let cases = [];
  if (q.trim().length >= 2) {
    try {
      const r = await getJSON(`/v1/cases?q=${encodeURIComponent(q.trim())}&limit=6`);
      cases = r.dossiers.map(c => ({ icon: "file", html: `<b>${esc(c.case_id)}</b> ${esc(c.group_id || c.filename || "")}`,
        side: statusChip(c.status), href: `#/dossiers/${encodeURIComponent(c.case_id)}` }));
    } catch { /* recherche facultative */ }
  }
  pItems = [...cases, ...pages]; pIndex = 0; drawPalette();
}, 160);
function openPalette() {
  pq.value = ""; pItems = PAGES.filter(p => !p[3] || canDo(p[3])).map(p => ({ icon: p[2], html: esc(p[0]), href: p[1] }));
  pIndex = 0; drawPalette(); palette.showModal(); pq.focus();
}
function pick(i) { const it = pItems[i]; if (!it) return; palette.close(); location.hash = it.href; }
$("#search-btn").addEventListener("click", openPalette);
pq.addEventListener("input", () => searchCases(pq.value));
pq.addEventListener("keydown", e => {
  if (e.key === "ArrowDown") { e.preventDefault(); pIndex = Math.min(pItems.length - 1, pIndex + 1); drawPalette(); }
  if (e.key === "ArrowUp") { e.preventDefault(); pIndex = Math.max(0, pIndex - 1); drawPalette(); }
  if (e.key === "Enter") { e.preventDefault(); pick(pIndex); }
});
plist.addEventListener("click", e => { const li = e.target.closest("[data-i]"); if (li) pick(+li.dataset.i); });
palette.addEventListener("click", e => { if (e.target === palette) palette.close(); });

async function shortcuts() {
  await modal({ title: "Raccourcis clavier", body: `<dl class="keys">
    <div><dt><kbd>Ctrl</kbd> <kbd>K</kbd></dt><dd>Rechercher un dossier ou une page</dd></div>
    <div><dt><kbd>N</kbd></dt><dd>Nouveau dossier</dd></div>
    <div><dt><kbd>G</kbd> puis <kbd>D</kbd></dt><dd>Aller aux dossiers</dd></div>
    <div><dt><kbd>G</kbd> puis <kbd>V</kbd></dt><dd>Aller à la vue d'ensemble</dd></div>
    <div><dt><kbd>?</kbd></dt><dd>Afficher cette aide</dd></div></dl>`, actions: [{ label: "Fermer", value: "ok", tone: "primary" }] });
}
$("#shortcut-btn").addEventListener("click", () => { toggleMenu(false); shortcuts(); });
let gPressed = 0;
document.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); if ($("#shell").hidden) return; openPalette(); return; }
  if (e.target.closest("input, textarea, select, [contenteditable], dialog") || e.ctrlKey || e.metaKey || e.altKey || $("#shell").hidden) return;
  const k = e.key.toLowerCase();
  if (k === "?") shortcuts();
  else if (k === "n" && canDo("analyste")) location.hash = "#/nouveau";
  else if (k === "g") gPressed = Date.now();
  else if (Date.now() - gPressed < 900 && k === "d") location.hash = "#/dossiers";
  else if (Date.now() - gPressed < 900 && k === "v") location.hash = "#/";
});

/* ------------------------------------------------------------------ démarrage */
function enterApp() {
  $("#login").hidden = true;
  $("#shell").hidden = false;
  document.body.classList.remove("booting");
  applyUser();
  refreshWaiting();
  route();
}

async function boot() {
  hydrateIcons();
  applyThemeIcon();
  $("#menu-btn").innerHTML = icon("menu");
  band($("#rail-band"), { width: 240, height: 70, waves: 9, lines: 6 });
  health();
  setInterval(health, 60000);
  setInterval(refreshWaiting, 60000);
  try {
    const st = await (await fetch("/v1/auth/status")).json();
    state.authRequired = !!st.comptes;
  } catch { state.authRequired = false; }
  if (state.session) {
    try { saveSession({ ...state.session, user: await getJSON("/v1/auth/me") }); }
    catch { saveSession(null); }
  }
  if (state.authRequired && !state.session) { showLogin(); return; }
  enterApp();
}
boot();
