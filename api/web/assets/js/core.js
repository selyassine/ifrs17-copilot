/* IFRS 17 Copilot — noyau de l'application : appels à l'API, session, formats, icônes, messages. */

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
export function fr(x, d = 2) {
  if (x == null || Number.isNaN(Number(x))) return "—";
  return Number(x).toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });
}
export function compact(x) {
  const a = Math.abs(x);
  if (a >= 1e9) return `${fr(x / 1e9, 1)} Md`;
  if (a >= 1e6) return `${fr(x / 1e6, 1)} M`;
  if (a >= 1e4) return `${fr(x / 1e3, 0)} k`;
  return fr(x, a < 100 && a % 1 ? 1 : 0);
}
export const pct = (x, d = 0) => `${fr((x || 0) * 100, d)} %`;
export function when(iso, style = "short") {
  if (!iso) return "";
  const d = new Date(iso);
  return style === "date" ? d.toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" })
    : d.toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
export function ago(iso) {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "à l'instant";
  if (s < 3600) return `il y a ${Math.round(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.round(s / 3600)} h`;
  if (s < 86400 * 30) return `il y a ${Math.round(s / 86400)} j`;
  return when(iso, "date");
}
export const unitLabel = m => ({ 1: "unités", 1000: "milliers", 1000000: "millions" }[m] || "");

/* ------------------------------------------------------------------ libellés métier */
export const ROLE_LABEL = { analyste: "Analyste", valideur: "Valideur", admin: "Administrateur", systeme: "Système" };
export const ROLE_RANK = { analyste: 1, valideur: 2, admin: 3, systeme: 4 };
export const CASE_STATUS = {
  en_cours: ["En cours", "info"], note_prete: ["Note prête", "ok"], validation_humaine: ["À valider", "warn"],
  validee: ["Validée", "ok"], rejetee: ["Rejetée", "bad"], document_illisible: ["Illisible", "bad"], erreur: ["Erreur", "bad"],
};
export const SOURCE_LABEL = {
  site: "Espace de travail", "n8n-email": "E-mail", "n8n-formulaire": "Formulaire", "n8n-webhook": "Webhook n8n",
  api: "API", validation: "Validation",
};
export const ACTION_LABEL = {
  depot: "Dossier déposé", reprise: "Dossier repris", analyse: "Analyse terminée", echec: "Analyse en échec",
  validation_approuvee: "Données approuvées", analyse_apres_validation: "Note recalculée après validation",
  validation_rejetee: "Dossier rejeté", email_validation: "Demande de validation envoyée",
  email_note_envoyee: "Note envoyée par e-mail", transmis_validation: "Transmis au valideur",
  email_validation_envoye: "E-mail de validation envoyé", email_rejet_envoye: "Rejet notifié par e-mail",
  archive: "Dossier archivé", note_consultee: "Note consultée", question_copilot: "Question au Copilot",
  connexion: "Connexion", connexion_refusee: "Connexion refusée", deconnexion: "Déconnexion",
  compte_cree: "Compte créé", compte_modifie: "Compte modifié", copilot_rejoue: "Copilot rejoué depuis un point de reprise",
  copilot_memoire_effacee: "Mémoire du Copilot effacée",
};
export function statusChip(st, extra = "") {
  const [label, tone] = CASE_STATUS[st] || [st, "neutral"];
  return `<span class="status ${tone}${st === "en_cours" ? " running" : ""}${extra ? " " + extra : ""}">${esc(label)}</span>`;
}

/* ------------------------------------------------------------------ icônes (trait 1,7) */
const P = {
  overview: "M4 4h7v9H4zM13 4h7v5h-7zM13 11h7v9h-7zM4 15h7v5H4z",
  folder: "M3 7.5V18a1.5 1.5 0 001.5 1.5h15A1.5 1.5 0 0021 18V9a1.5 1.5 0 00-1.5-1.5H12L10 5H4.5A1.5 1.5 0 003 6.5z",
  plus: "M12 5v14M5 12h14",
  upload: "M12 15V4M7.5 8.5L12 4l4.5 4.5M5 15v3.5A1.5 1.5 0 006.5 20h11a1.5 1.5 0 001.5-1.5V15",
  norm: "M12 4v16M5 8h14M7 8l-3 7a3.5 3.5 0 006 0zM17 8l-3 7a3.5 3.5 0 006 0zM8 20h8",
  chart: "M4 20h16M6 16l4-5 3 3 6-8M15 6h4v4",
  shield: "M12 3l7.5 3v5.5c0 4.6-3.2 8.2-7.5 9.5-4.3-1.3-7.5-4.9-7.5-9.5V6z",
  search: "M10.5 17a6.5 6.5 0 110-13 6.5 6.5 0 010 13zM20 20l-4.8-4.8",
  bell: "M6 16V11a6 6 0 0112 0v5l1.5 2h-15zM10 20.5a2 2 0 004 0",
  sun: "M12 16.5a4.5 4.5 0 110-9 4.5 4.5 0 010 9zM12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4L6 18M18 6l1.4-1.4",
  moon: "M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z",
  logout: "M15 4h3.5A1.5 1.5 0 0120 5.5v13a1.5 1.5 0 01-1.5 1.5H15M10 16l4-4-4-4M14 12H4",
  user: "M12 12a4 4 0 100-8 4 4 0 000 8zM4.5 20c1-3.7 4-5.5 7.5-5.5s6.5 1.8 7.5 5.5",
  users: "M9 11a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM3 19.5c.8-3.3 3.2-5 6-5s5.2 1.7 6 5M16 4.3a3.5 3.5 0 010 6.4M18 14.8c1.6.6 2.6 2.1 3 4.7",
  check: "M5 12.5l4.5 4.5L19 7.5",
  x: "M6 6l12 12M18 6L6 18",
  alert: "M12 3.5L2.5 20h19zM12 10v4.5M12 17.3v.2",
  info: "M12 21a9 9 0 110-18 9 9 0 010 18zM12 11v5.5M12 7.8v.2",
  clock: "M12 21a9 9 0 110-18 9 9 0 010 18zM12 7.5V12l3 2",
  file: "M6.5 3h7.5L19 8v11.5A1.5 1.5 0 0117.5 21h-11A1.5 1.5 0 015 19.5v-15A1.5 1.5 0 016.5 3zM14 3v5h5M8.5 13h7M8.5 16.5h5",
  mail: "M3.5 6.5h17v11h-17zM3.5 7l8.5 6.5L20.5 7",
  form: "M5 4h14v16H5zM8 8.5h8M8 12h8M8 15.5h4",
  api: "M8 8l-4 4 4 4M16 8l4 4-4 4M13.5 5l-3 14",
  arrow: "M5 12h14M13 6l6 6-6 6",
  back: "M19 12H5M11 18l-6-6 6-6",
  chevronL: "M15 6l-6 6 6 6",
  chevronR: "M9 6l6 6-6 6",
  chevronD: "M6 9l6 6 6-6",
  print: "M7 9V3.5h10V9M7 17.5H4.5V10h15v7.5H17M7 14h10v6.5H7z",
  download: "M12 4v11M7.5 10.5L12 15l4.5-4.5M5 19.5h14",
  volume: "M4 9.5h3.5L12 6v12l-4.5-3.5H4zM15.5 9.2a4 4 0 010 5.6M18.2 6.6a7.6 7.6 0 010 10.8",
  spark: "M12 3l1.8 5.4L19 10l-5.2 1.6L12 17l-1.8-5.4L5 10l5.2-1.6zM18.5 16l.7 2 2 .8-2 .7-.7 2-.7-2-2-.7 2-.8z",
  lock: "M6.5 11h11v9.5h-11zM8.5 11V8a3.5 3.5 0 017 0v3",
  chain: "M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1",
  refresh: "M20 11.5A8 8 0 006.3 6.3L4 8.5M4 4v4.5h4.5M4 12.5a8 8 0 0013.7 5.2l2.3-2.2M20 20v-4.5h-4.5",
  send: "M4 12l16-8-6 16-2.5-6.5z",
  mic: "M12 15a3 3 0 003-3V6a3 3 0 00-6 0v6a3 3 0 003 3zM5.5 11a6.5 6.5 0 0013 0M12 17.5V21",
  cpu: "M7 7h10v10H7zM10 10h4v4h-4zM9.5 3v4M14.5 3v4M9.5 17v4M14.5 17v4M3 9.5h4M3 14.5h4M17 9.5h4M17 14.5h4",
  activity: "M3 12h4l2.5-6 5 12 2.5-6H21",
  seal: "M12 3l2 1.6 2.5-.3.9 2.4 2.3 1.1-.4 2.5 1.4 2.1-1.9 1.7.1 2.5-2.5.6-1.2 2.3-2.4-.8-2.2 1.2-1.6-2-2.5-.4.1-2.5L4.1 15l1.2-2.2L4.2 10.5l2.1-1.4.2-2.5 2.5-.2z",
  eye: "M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12zM12 15a3 3 0 100-6 3 3 0 000 6z",
  eyeOff: "M3 3l18 18M10.6 6A9.6 9.6 0 0112 5.5c6 0 9.5 6.5 9.5 6.5a16 16 0 01-2.9 3.6M6.5 7.1C4 8.8 2.5 12 2.5 12S6 18.5 12 18.5c1.6 0 3-.4 4.2-1M9.9 9.9a3 3 0 004.2 4.2",
  edit: "M4 20h4L19 9a2.8 2.8 0 00-4-4L4 16zM13.5 6.5l4 4",
  external: "M14 4h6v6M20 4l-9 9M18 14v5.5a.5.5 0 01-.5.5h-13a.5.5 0 01-.5-.5v-13a.5.5 0 01.5-.5H10",
  menu: "M4 7h16M4 12h16M4 17h16",
  keyboard: "M3 6.5h18v11H3zM6.5 10h1M10 10h1M13.5 10h1M17 10h.5M7 14h10",
  layers: "M12 4l8.5 4.5L12 13 3.5 8.5zM3.5 12.5L12 17l8.5-4.5M3.5 16.5L12 21l8.5-4.5",
  database: "M12 8c4.4 0 8-1.3 8-3s-3.6-3-8-3-8 1.3-8 3 3.6 3 8 3zM4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
};
export const icon = (name, cls = "i") => `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${P[name] || ""}"/></svg>`;

/* ------------------------------------------------------------------ session et API */
const SESSION_KEY = "ifrs17.session";
const TOKEN_KEY = "ifrs17.token";
export const state = { session: null, authRequired: false, health: null };
try { state.session = JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null"); } catch { state.session = null; }

export function saveSession(s) {
  state.session = s;
  try { if (s) sessionStorage.setItem(SESSION_KEY, JSON.stringify(s)); else sessionStorage.removeItem(SESSION_KEY); } catch { /* stockage indisponible */ }
}
export function devToken() { try { return localStorage.getItem(TOKEN_KEY) || "change-moi"; } catch { return "change-moi"; } }
export function setDevToken(t) { try { localStorage.setItem(TOKEN_KEY, t); } catch { /* stockage indisponible */ } }
export const me = () => state.session?.user || null;
export function canDo(role) {
  if (!state.session) return !state.authRequired;
  return (ROLE_RANK[state.session.user.role] || 0) >= ROLE_RANK[role];
}

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}
const listeners = {};
export const on = (ev, fn) => { (listeners[ev] ||= []).push(fn); };
export const emit = (ev, data) => (listeners[ev] || []).forEach(fn => fn(data));

export async function api(path, { method = "GET", json, form, signal } = {}) {
  const headers = state.session ? { Authorization: `Bearer ${state.session.token}` } : { "X-API-Token": devToken() };
  let body;
  if (json !== undefined) { headers["Content-Type"] = "application/json; charset=utf-8"; body = JSON.stringify(json); }
  if (form) body = form;
  let res;
  try { res = await fetch(path, { method, headers, body, signal }); }
  catch (e) {
    if (e.name === "AbortError") throw e;
    throw new ApiError("Le serveur ne répond pas. Vérifiez que l'API est lancée.", 0);
  }
  if (res.status === 401) {
    if (state.session || state.authRequired) {
      saveSession(null);
      emit("auth:expired", "Votre session a expiré. Reconnectez-vous pour continuer.");
      throw new ApiError("Session expirée.", 401);
    }
    emit("auth:token", null);
    throw new ApiError("Le jeton de l'API est refusé.", 401);
  }
  if (!res.ok) {
    let detail = `Erreur ${res.status}`;
    try { const j = await res.json(); detail = j.detail || detail; } catch { /* réponse non JSON */ }
    if (Array.isArray(detail)) detail = detail.map(d => `${(d.loc || []).slice(1).join(".")} : ${d.msg}`).join(" ; ");
    throw new ApiError(typeof detail === "string" ? detail : JSON.stringify(detail), res.status);
  }
  return res;
}
export const getJSON = async (path, opts) => (await api(path, opts)).json();

/* ------------------------------------------------------------------ messages éphémères */
export function toast(message, tone = "ok", { action, timeout = 4200 } = {}) {
  let host = $("#toasts");
  if (!host) { host = document.createElement("div"); host.id = "toasts"; host.setAttribute("aria-live", "polite"); document.body.append(host); }
  const el = document.createElement("div");
  el.className = `toast ${tone}`;
  el.innerHTML = `${icon(tone === "bad" ? "alert" : tone === "warn" ? "alert" : tone === "info" ? "info" : "check")}<span>${esc(message)}</span>`;
  if (action) {
    const b = document.createElement("button");
    b.className = "link-btn"; b.type = "button"; b.textContent = action.label;
    b.addEventListener("click", () => { action.run(); el.remove(); });
    el.append(b);
  }
  host.append(el);
  requestAnimationFrame(() => el.classList.add("in"));
  setTimeout(() => { el.classList.remove("in"); setTimeout(() => el.remove(), 300); }, timeout);
}

/* ------------------------------------------------------------------ fenêtre modale */
export function modal({ title, body = "", actions = [], size = "" }) {
  return new Promise(resolve => {
    const dlg = document.createElement("dialog");
    dlg.className = `modal ${size}`;
    dlg.innerHTML = `<form method="dialog" class="modal-card">
      <header><h2>${esc(title)}</h2><button class="icon-btn" value="" aria-label="Fermer">${icon("x")}</button></header>
      <div class="modal-body">${body}</div>
      <footer>${actions.map(a => `<button class="btn ${a.tone || ""}" value="${esc(a.value)}" ${a.submit ? "" : 'formnovalidate'}>${esc(a.label)}</button>`).join("")}</footer>
    </form>`;
    document.body.append(dlg);
    const form = $("form", dlg);
    dlg.addEventListener("close", () => {
      const data = Object.fromEntries(new FormData(form).entries());
      resolve({ value: dlg.returnValue, data });
      setTimeout(() => dlg.remove(), 200);
    });
    dlg.showModal();
    const first = $("input, textarea, select", $(".modal-body", dlg));
    (first || $("footer .btn:last-child", dlg))?.focus();
  });
}
export async function confirmAction(title, text, label = "Confirmer", tone = "primary") {
  const r = await modal({ title, body: `<p class="modal-text">${esc(text)}</p>`,
    actions: [{ label: "Annuler", value: "cancel" }, { label, value: "ok", tone, submit: true }] });
  return r.value === "ok";
}

/* Animation d'un nombre jusqu'à sa valeur (une seule fois, au premier affichage). */
export function countUp(el, to, format = x => fr(x, 0), ms = 700) {
  if (reduceMotion() || !Number.isFinite(to)) { el.textContent = format(to); return; }
  const t0 = performance.now();
  const step = t => {
    const k = Math.min(1, (t - t0) / ms);
    el.textContent = format(to * (1 - Math.pow(1 - k, 3)));
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/* Lecture d'un flux SSE renvoyé par fetch (POST /v1/case/stream). */
export async function readStream(res, onEvent) {
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

/* Nom lisible d'un identifiant de paragraphe : 44, B119, C5, art-2, cons-3, def:… */
export function refLabel(id, long = false) {
  id = String(id);
  let m;
  if ((m = id.match(/^art-(\d+)$/))) return `Article ${m[1]}`;
  if ((m = id.match(/^cons-(\d+)$/))) return long ? `Modification d'autres normes, point ${m[1]}` : `modif. ${m[1]}`;
  if (id.startsWith("def:")) return long ? `Définition « ${id.slice(4)} » (annexe A)` : `définition « ${id.slice(4)} »`;
  if (/^[BC]\d/.test(id)) return long ? `Paragraphe ${id} (annexe ${id[0]})` : id;
  return long ? `Paragraphe ${id}` : `§${id}`;
}

/* Imprimer une note HTML dans une nouvelle fenêtre (la note a sa feuille d'impression A4). */
export function printHTML(html) {
  const w = window.open("", "_blank");
  if (!w) { toast("Autorisez les fenêtres surgissantes pour imprimer la note.", "warn"); return; }
  w.document.write(html); w.document.close(); w.focus();
  setTimeout(() => w.print(), 400);
}
export function downloadText(text, name, type = "text/html") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
export const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
