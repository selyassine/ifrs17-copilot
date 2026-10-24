/* Nouveau dossier : dépôt d'un document, suivi des agents en direct, puis ouverture de la fiche. */
import { $, $$, esc, fr, icon, me, api, statusChip, emit, toast, readStream, state } from "../core.js";

const AGENTS = {
  extracteur: ["Extracteur", "Lit le document et retrouve chaque chiffre dans sa source", "file"],
  calculateur: ["Calculateur", "Calcule la marge en Python, sans modèle de langage", "chart"],
  "chercheur_rag+verificateur": ["Chercheur et vérificateur", "Cherche la norme, puis relit la réponse phrase par phrase", "norm"],
  chercheur_rag: ["Chercheur", "Réponse de référence déjà vérifiée et relue", "norm"],
  redacteur: ["Rédacteur", "Rédige la note : le code écrit les chiffres, le modèle la synthèse", "edit"],
};
const PLAN = ["extracteur", "calculateur", "chercheur_rag+verificateur", "redacteur"];
const LABEL = { ok: "vérifié", reference: "référence", saute: "données validées", a_verifier: "à vérifier", validation_humaine: "à valider",
  echec: "échec", erreur: "erreur", repli: "synthèse du code", refus: "pas de réponse", "en cours": "en cours" };
const LAYOUT = { lignes: "tableau en lignes", colonnes: "tableau en colonnes", recit: "texte et tableau" };

function cls(status) {
  if (status === "en cours") return "running";
  if (["ok", "note_prete"].includes(status)) return "ok";
  if (["reference", "saute"].includes(status)) return "ref";
  if (["echec", "erreur"].includes(status)) return "bad";
  if (status === "pending") return "";
  return "warn";
}
function agentHTML(st) {
  const [name, desc, ic] = AGENTS[st.agent] || [st.agent, "", "cpu"];
  const c = cls(st.status);
  const t = st.status === "en cours" || st.status === "pending" || st.ms == null ? "" : `${fr(st.ms / 1000, 1)} s`;
  return `<li class="agent ${c}"><span class="node">${icon(c === "ok" ? "check" : c === "bad" ? "x" : c === "warn" ? "alert" : ic)}</span>
    <div><b>${esc(name)}${LABEL[st.status] ? `<span class="st">${esc(LABEL[st.status])}</span>` : ""}</b><p>${esc(st.detail || desc)}</p></div><span class="t">${t}</span></li>`;
}

export async function render(main) {
  let file = null, sample = null, samples = [], running = false;
  main.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>Nouveau dossier</h1>
      <p>Déposez l'état d'un portefeuille (PDF, scan ou photo). Les agents s'enchaînent sous vos yeux ; le dossier est inscrit au registre dès le dépôt.</p></div></div>
    <div class="intake">
      <section class="panel"><div class="panel-head"><h2>Document</h2></div><div class="panel-body">
        <label class="drop" id="in-drop"><input type="file" id="in-file" accept="application/pdf,image/png,image/jpeg,.xlsx,.csv" hidden>
          <span class="di">${icon("upload")}</span><b>Glissez un document ici</b><small>ou cliquez pour parcourir · PDF, PNG, JPEG, Excel ou CSV, 10 Mo au plus</small></label>
        <div id="in-picked" style="margin-top:14px" hidden></div>
        <div class="or">ou un document d'exemple</div>
        <div class="samples" id="in-samples"><p class="cell-sub">Chargement des exemples…</p></div>
        <div class="fmt" id="in-fmt" hidden><span>Format :</span><div class="seg" role="group" aria-label="Format">
          <button type="button" data-f="pdf" aria-pressed="true">PDF</button><button type="button" data-f="image" aria-pressed="false">Image scannée</button></div></div>
        <div style="margin-top:20px;display:grid;gap:10px">
          <button class="btn primary lg wide" id="in-run" disabled>${icon("cpu")}Lancer l'analyse</button>
          <p class="cell-sub" style="text-align:center">Documents fictifs uniquement : les offres gratuites des modèles peuvent conserver les données.</p></div>
      </div></section>
      <section class="panel"><div class="panel-head"><h2>Chaîne des agents</h2><span class="run-clock" id="in-clock"></span></div>
        <div class="panel-body"><ol class="pipeline" id="in-pipe">${PLAN.map(a => agentHTML({ agent: a, status: "pending" })).join("")}</ol>
        <div class="outcome" id="in-out"></div></div></section>
    </div></div>`;

  const run = $("#in-run");
  const update = () => { run.disabled = running || !(file || sample); };
  function pickFile(f) {
    if (!f) return;
    if (!["application/pdf", "image/png", "image/jpeg"].includes(f.type) && !/\.(xlsx|csv)$/i.test(f.name)) {
      toast("Format non pris en charge : PDF, PNG, JPEG, Excel (.xlsx) ou CSV.", "bad"); return; }
    if (f.size > 10 * 1024 * 1024) { toast("Fichier trop lourd : 10 Mo au plus.", "bad"); return; }
    file = f; sample = null;
    $$(".sample", main).forEach(b => b.setAttribute("aria-pressed", "false"));
    $("#in-fmt").hidden = true;
    $("#in-picked").hidden = false;
    $("#in-picked").innerHTML = `<div class="file-pill"><span class="fi">${icon("file")}</span><div><b>${esc(f.name)}</b><small>${fr(f.size / 1024, 0)} Ko</small></div>
      <button class="icon-btn" type="button" id="in-clear" aria-label="Retirer le document">${icon("x")}</button></div>`;
    $("#in-clear").addEventListener("click", () => { file = null; $("#in-picked").hidden = true; $("#in-file").value = ""; update(); });
    update();
  }
  $("#in-file").addEventListener("change", e => pickFile(e.target.files[0]));
  const drop = $("#in-drop");
  ["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, () => drop.classList.remove("over")));
  drop.addEventListener("drop", e => { e.preventDefault(); pickFile(e.dataTransfer.files[0]); });

  try { samples = await (await fetch("/v1/samples")).json(); } catch { samples = []; }
  const avail = samples.filter(s => s.available);
  $("#in-samples").innerHTML = avail.length ? avail.map(s => `<button type="button" class="sample" data-id="${esc(s.id)}" aria-pressed="false">
      <span class="sid">${esc(s.id)}</span><span>${esc(s.kind === "piege" ? s.piege : LAYOUT[s.layout] || s.layout)}
        <small>${s.attendu === "alerte" ? "attendu : validation humaine" : s.kind === "piege" ? "attendu : piège déjoué, note prête" : "attendu : note prête"}</small></span>
      <span class="tag ${s.kind === "piege" ? "trap" : ""}">${s.kind === "piege" ? "piégé" : "simple"}</span></button>`).join("")
    : `<p class="cell-sub">Aucun document d'exemple : lancez <code>python -m multimodal.synth</code>.</p>`;
  let fmt = "pdf";
  $("#in-samples").addEventListener("click", e => {
    const b = e.target.closest(".sample"); if (!b) return;
    sample = samples.find(s => s.id === b.dataset.id); file = null; $("#in-picked").hidden = true;
    $$(".sample", main).forEach(x => x.setAttribute("aria-pressed", String(x === b)));
    $("#in-fmt").hidden = !sample.has_image;
    if (!sample.has_image) fmt = "pdf";
    $$("#in-fmt [data-f]").forEach(x => x.setAttribute("aria-pressed", String(x.dataset.f === fmt)));
    update();
  });
  $("#in-fmt").addEventListener("click", e => { const b = e.target.closest("[data-f]"); if (!b) return; fmt = b.dataset.f; $$("#in-fmt [data-f]").forEach(x => x.setAttribute("aria-pressed", String(x === b))); });

  let clock = null;
  run.addEventListener("click", async () => {
    running = true; update();
    run.innerHTML = `<span class="spin"></span>Analyse en cours…`;
    const pipe = $("#in-pipe"), out = $("#in-out");
    pipe.innerHTML = PLAN.map(a => agentHTML({ agent: a, status: "pending" })).join("");
    out.innerHTML = "";
    const t0 = performance.now();
    clock = setInterval(() => { $("#in-clock").textContent = `${fr((performance.now() - t0) / 1000, 0)} s`; }, 250);
    let caseId = null;
    const steps = [];
    const draw = (final = false) => {
      const seen = new Set(steps.filter(Boolean).map(x => x.agent));
      const pending = final ? [] : PLAN.filter(a => !seen.has(a) && !(a === "chercheur_rag+verificateur" && seen.has("chercheur_rag")))
        .map(a => ({ agent: a, status: "pending" }));
      pipe.innerHTML = [...steps.filter(Boolean), ...pending].map(agentHTML).join("");
    };
    try {
      let f = file;
      if (!f) {
        const blob = await (await api(`/v1/samples/${sample.id}?format=${fmt}`)).blob();
        f = new File([blob], fmt === "image" ? `${sample.id}.jpg` : `${sample.id}.pdf`, { type: blob.type });
      }
      const form = new FormData();
      form.append("file", f); form.append("source", "site");
      if (me()) form.append("submitter", me().display_name || me().username);
      const res = await api("/v1/case/stream", { method: "POST", form });
      await readStream(res, ev => {
        if (ev.type === "start") { caseId = ev.case_id; emit("cases:changed"); }
        if (ev.type === "step") { steps[ev.index] = ev; draw(); }
        if (ev.type === "notification") out.innerHTML = `<div class="callout info">${icon("mail")}<span>Validation humaine demandée : envoi de l'e-mail au valideur…</span></div>`;
        if (ev.type === "result") done(ev.data);
        if (ev.type === "error") out.innerHTML = `<div class="callout bad">${icon("alert")}<div><b>Analyse interrompue</b><p>${esc(ev.detail)}</p></div></div>
          ${caseId ? `<a class="btn" href="#/dossiers/${encodeURIComponent(caseId)}">Voir le dossier au registre</a>` : ""}`;
      });
    } catch (err) {
      out.innerHTML = `<div class="callout bad">${icon("alert")}<div><b>Analyse impossible</b><p>${esc(err.message)}</p></div></div>`;
    } finally {
      clearInterval(clock); running = false; update();
      run.innerHTML = `${icon("cpu")}Lancer une autre analyse`;
      emit("cases:changed");
    }
    function done(r) {
      if (r.steps?.length) { steps.splice(0, steps.length, ...r.steps); }
      draw(true);
      state.runs = { ...(state.runs || {}), [r.case_id]: { norm: r.norm } };
      const csm = r.csm;
      const n = r.notification;
      out.innerHTML = `<div class="callout ${r.status === "note_prete" ? "ok" : r.status === "validation_humaine" ? "warn" : "bad"}">${icon(r.status === "note_prete" ? "check" : "alert")}<div>
          <b>${r.status === "note_prete" ? "Tous les contrôles sont passés : la note est prête" : r.status === "validation_humaine" ? "Un contrôle demande l'avis d'un valideur" : "Document inexploitable"}</b>
          ${r.controls.length ? `<ul>${r.controls.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
          ${n ? `<p style="margin-top:6px">${n.envoyee ? "E-mail envoyé au valideur avec la note provisoire et le formulaire pré-rempli." : `E-mail non envoyé : ${esc(n.detail)}.`}</p>` : ""}</div></div>
        ${r.lic ? `<dl class="figs" style="margin:6px 0 4px"><div class="hero"><dt>Passif pour sinistres survenus</dt><dd class="num">${fr(r.lic.lic)}</dd></div>
          <div><dt>Meilleure estimation</dt><dd class="num">${fr(r.lic.bel)}</dd></div><div><dt>Ajustement pour risque</dt><dd class="num">${fr(r.lic.risk_adjustment)}</dd></div>
          <div><dt>Statut</dt><dd style="font-size:15px;padding-top:6px">${statusChip(r.status)}</dd></div></dl>` : ""}
        ${csm ? `<dl class="figs" style="margin:6px 0 4px"><div class="hero ${csm.onerous ? "loss" : ""}"><dt>${csm.onerous ? "Perte à l'origine" : "Marge à l'origine"}</dt><dd class="num">${fr(csm.onerous ? csm.initial_loss_component : csm.initial_csm)}</dd></div>
          <div><dt>Flux d'exécution</dt><dd class="num">${fr(csm.fulfilment_cash_flows)}</dd></div><div><dt>Ajustement pour risque</dt><dd class="num">${fr(csm.risk_adjustment)}</dd></div>
          <div><dt>Statut</dt><dd style="font-size:15px;padding-top:6px">${statusChip(r.status)}</dd></div></dl>` : ""}
        <a class="btn primary" href="#/dossiers/${encodeURIComponent(r.case_id)}${r.status === "validation_humaine" ? "/donnees" : r.note_html ? "/note" : ""}">${icon("arrow")}Ouvrir le dossier</a>`;
    }
  });
  return () => clearInterval(clock);
}
