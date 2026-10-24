/* IFRS 17 Copilot — page de présentation : médaillon, agents, visite du produit, apparitions au défilement. */
import { medallion, band } from "./guilloche.js";
import { icon, esc } from "./core.js";

const $ = s => document.querySelector(s);
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

medallion($("#hero-medallion"), { size: 1150, draw: !reduce });
band($("#night-band"), { width: 1600, height: 90, waves: 22, lines: 7 });
band($("#cta-band"), { width: 1600, height: 120, waves: 16, lines: 8 });

/* barre de navigation : transparente sur le héros, pleine ensuite */
const nav = $("#nav");
const onScroll = () => nav.classList.toggle("solid", scrollY > 40);
addEventListener("scroll", onScroll, { passive: true });
onScroll();

/* ------------------------------------------------------------------ agents */
const AGENTS = [
  { k: "routeur", n: "Routeur", ic: "layers", s: "oriente chaque demande",
    role: "Classe la demande : question sur la norme, document à analyser, calcul, ou hors sujet. Une salutation reçoit une réponse sans appel au modèle.",
    model: "gpt-oss-20b, ou règles", guard: "Hors sujet : refus immédiat, sans recherche", m: ["20/20", "demandes bien orientées sur le jeu de test"] },
  { k: "extracteur", n: "Extracteur", ic: "file", s: "lit PDF, scans et photos",
    role: "Remplit les données du groupe de contrats à partir du document : primes, sinistres et frais, unités de couverture, taux, monnaie et unité des montants.",
    model: "gpt-oss-120b (texte), Gemini Flash (image)", guard: "Chaque chiffre est retrouvé dans le document ; une image est lue deux fois", m: ["15/15", "documents lus sans erreur, dans les trois modes"] },
  { k: "calculateur", n: "Calculateur", ic: "chart", s: "calcule, sans modèle de langage",
    role: "Valeurs actuelles, ajustement pour risque et son niveau de confiance, marge sur services contractuels, composante de perte, écoulement période par période et sensibilités.",
    model: "Aucun : moteur Python", guard: "Testé contre des calculs faits à la main et les exemples d'un cours", m: ["À l'euro près", "sur les exemples chiffrés d'un cours IFRS 17"] },
  { k: "chercheur", n: "Chercheur", ic: "norm", s: "retrouve et cite le règlement",
    role: "Un agent LangGraph raisonne sur le mécanisme en jeu, cherche dans les 397 paragraphes du règlement, note les passages trouvés et relance une recherche si nécessaire.",
    model: "BGE-M3 + BM25, Qdrant, gpt-oss-120b", guard: "Citation acceptée seulement si la phrase figure dans le paragraphe", m: ["0,517 → 0,750", "bon paragraphe dans les 5 premiers, cas pratiques"] },
  { k: "verificateur", n: "Vérificateur", ic: "shield", s: "relit chaque phrase",
    role: "Un second modèle juge chaque phrase de la réponse : soutenue par le paragraphe cité, portée respectée. Il demande une correction au plus, puis passe la main à un humain.",
    model: "gpt-oss-120b", guard: "Sa preuve doit être recopiée du paragraphe cité", m: ["5 sur 7", "erreurs volontairement glissées repérées"] },
  { k: "redacteur", n: "Rédacteur", ic: "edit", s: "rédige la note actuarielle",
    role: "Produit la note de dix sections : données, hypothèses, évaluation, écoulement, projection, sensibilités, fondements cités, contrôles et bloc de validation.",
    model: "gpt-oss-120b pour la synthèse seulement", guard: "Tout le chiffré est écrit par le code ; un nombre inventé fait réécrire la synthèse", m: ["9/9", "synthèses acceptées par le contrôle"] },
];
const list = $("#agent-list"), card = $("#agent-card");
list.innerHTML = AGENTS.map((a, i) => `<button role="tab" id="ag-${a.k}" aria-selected="${i === 0}" data-i="${i}"><span class="ai">${icon(a.ic)}</span><span>${esc(a.n)}<small>${esc(a.s)}</small></span></button>`).join("");
let agentTimer = null, agentIdx = 0;
function showAgent(i, user = false) {
  agentIdx = i;
  const a = AGENTS[i];
  list.querySelectorAll("button").forEach((b, j) => b.setAttribute("aria-selected", String(j === i)));
  card.setAttribute("aria-labelledby", `ag-${a.k}`);
  card.classList.remove("swap"); void card.offsetWidth; card.classList.add("swap");
  card.innerHTML = `<h3>${esc(a.n)}</h3><p class="role">${esc(a.role)}</p>
    <dl><div><dt>Modèle</dt><dd>${esc(a.model)}</dd></div><div><dt>Garde-fou</dt><dd>${esc(a.guard)}</dd></div><div><dt>Rôle dans la chaîne</dt><dd>étape ${i + 1} sur ${AGENTS.length}</dd></div></dl>
    <div class="measure"><b>${esc(a.m[0])}</b><span>${esc(a.m[1])}</span></div>`;
  if (user) clearInterval(agentTimer);
}
list.addEventListener("click", e => { const b = e.target.closest("button"); if (b) showAgent(+b.dataset.i, true); });
list.addEventListener("keydown", e => {
  if (!["ArrowDown", "ArrowUp", "ArrowRight", "ArrowLeft"].includes(e.key)) return;
  e.preventDefault();
  const n = (agentIdx + (["ArrowDown", "ArrowRight"].includes(e.key) ? 1 : -1) + AGENTS.length) % AGENTS.length;
  showAgent(n, true); list.querySelectorAll("button")[n].focus();
});
showAgent(0);

/* ------------------------------------------------------------------ visite du produit */
const TOUR = [
  ["vue-ensemble", "Vue d'ensemble", "app / vue d'ensemble", "Ce qui attend chacun : dossiers à valider, activité des 30 derniers jours, qualité, coût des modèles et état du service."],
  ["fiche-dossier", "Fiche dossier", "app / dossiers / PREV-2023-A", "Le cycle de vie du dossier, l'évaluation à l'origine expliquée en cascade et l'écoulement de la marge, recalculés par le moteur à l'ouverture."],
  ["validation", "Validation", "app / dossiers / EMP-2024-J / données", "Le valideur compare les données extraites au document, corrige les cellules, puis approuve : la note définitive est recalculée et tracée."],
  ["note", "Note actuarielle", "app / dossiers / PREV-2023-A / note", "La note complète, scellée lorsque tous les contrôles sont passés, imprimable en PDF A4 ou téléchargeable."],
  ["assistant-normatif", "Assistant normatif", "app / norme", "Une question en langage courant, une réponse qui cite le règlement : le paragraphe exact s'affiche à côté."],
  ["copilot", "Copilot", "app / dossiers / PREV-2023-A / copilot", "« Et si les sinistres augmentaient de 15 % ? » L'agent choisit ses outils de calcul ; chaque chiffre de sa réponse est vérifié."],
  ["piste-audit", "Piste d'audit", "app / dossiers / EMP-2024-J / audit", "Dépôt, analyse, e-mails, décisions : chaque événement est horodaté, attribué et chaîné par son empreinte."],
];
const tabs = $("#tour-tabs"), img = $("#tour-img");
tabs.innerHTML = TOUR.map((t, i) => `<button role="tab" aria-selected="${i === 0}" data-i="${i}">${esc(t[1])}</button>`).join("");
TOUR.slice(1).forEach(t => { const im = new Image(); im.src = `/app/assets/img/produit/${t[0]}.webp`; });
function showTour(i) {
  const t = TOUR[i];
  tabs.querySelectorAll("button").forEach((b, j) => b.setAttribute("aria-selected", String(j === i)));
  img.classList.add("fade");
  setTimeout(() => {
    img.src = `/app/assets/img/produit/${t[0]}.webp`;
    img.alt = `Capture de l'espace de travail : ${t[1]}`;
    $("#tour-url").textContent = t[2];
    $("#tour-cap").textContent = t[3];
    img.onload = () => img.classList.remove("fade");
    if (img.complete) img.classList.remove("fade");
  }, reduce ? 0 : 180);
}
tabs.addEventListener("click", e => { const b = e.target.closest("button"); if (b) showTour(+b.dataset.i); });
showTour(0);

/* ------------------------------------------------------------------ chaîne d'empreintes (illustration) */
const EVENTS = [["Dossier déposé", "9f3c1a…"], ["Analyse terminée", "4b80e2…"], ["Validation demandée", "c21d97…"], ["Données approuvées", "77ae05…"], ["Note envoyée", "e0b6f4…"]];
$("#hashchain").innerHTML = EVENTS.map((e, k) => `<div class="hc" style="--k:${k}"><span class="dot"></span><b>${e[0]}</b><code>${e[1]}</code></div>`).join("");

/* ------------------------------------------------------------------ apparitions au défilement */
document.querySelectorAll("#journey li").forEach((li, k) => li.style.setProperty("--k", k));
const io = new IntersectionObserver(entries => entries.forEach(en => {
  if (en.isIntersecting) { en.target.classList.add("on"); io.unobserve(en.target); }
}), { threshold: 0.35 });
["#journey", "#hashchain", ".reveal"].forEach(sel => document.querySelectorAll(sel).forEach(el => io.observe(el)));

/* Les agents défilent seuls tant que le visiteur n'a pas choisi. */
if (!reduce) {
  const agio = new IntersectionObserver(([en]) => {
    clearInterval(agentTimer);
    if (en.isIntersecting) agentTimer = setInterval(() => showAgent((agentIdx + 1) % AGENTS.length), 4200);
  }, { threshold: 0.5 });
  agio.observe($("#agents"));
  list.addEventListener("click", () => agio.disconnect(), { once: true });
}
