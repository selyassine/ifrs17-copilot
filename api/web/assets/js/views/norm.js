/* Assistant normatif : questions sur IFRS 17, réponses citées et relues, à l'écrit ou à l'oral. */
import { $, $$, esc, fr, icon, getJSON, toast, refLabel } from "../core.js";

const STARTERS = ["Comment la marge sur services contractuels est-elle libérée en résultat ?", "Quand un groupe de contrats est-il déficitaire dès l'origine ?",
  "À quelles conditions peut-on appliquer la méthode d'affectation des primes ?", "Comment l'ajustement pour risque est-il défini ?"];

/* D-091 : d'où vient le temps de réponse (le modèle agent par agent, l'attente du quota, la recherche) */
function timingHTML(d) {
  if (!d || !d.total_ms) return "";
  const sec = ms => `${fr(ms / 1000, 1)} s`;
  const agents = Object.entries(d.par_agent || {}).map(([k, v]) => `<li><span>${esc(k)}</span><span>${v.appels} appel${v.appels > 1 ? "s" : ""}, ${sec(v.ms)}</span></li>`).join("");
  return `<details class="tools timing"><summary>Temps de réponse : ${sec(d.total_ms)}, dont ${sec(d.modele_ms)} dans ${d.appels} appel${d.appels > 1 ? "s" : ""} au modèle</summary>
    <ul class="timing-list">${agents}
      ${d.attente_quota_s ? `<li class="warn"><span>dont attente du quota Groq (HTTP 429)</span><span>${fr(d.attente_quota_s, 1)} s</span></li>` : ""}
      ${d.secours ? `<li><span>appels passés au modèle de secours</span><span>${d.secours}</span></li>` : ""}
      ${d.index_ms > 500 ? `<li><span>chargement de l'index de la norme (premier appel)</span><span>${sec(d.index_ms)}</span></li>` : ""}
      <li><span>recherche des passages et contrôles du code</span><span>${sec(d.autre_ms)}</span></li></ul></details>`;
}

export async function render(main) {
  main.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>Assistant normatif</h1>
      <p>Les réponses s'appuient uniquement sur le règlement (UE) 2021/2036. Chaque paragraphe cité est vérifié par le code, puis chaque phrase est relue par un second modèle.</p></div></div>
    <div class="grid g-main">
      <section class="panel chat"><div class="thread" id="nm-thread" aria-live="polite">
        <div class="intro-card"><h3>Que voulez-vous savoir sur IFRS 17 ?</h3>
          <p>Posez votre question avec vos mots ; l'assistant cherche les paragraphes pertinents, répond en les citant, et refuse s'il ne trouve rien de solide.</p>
          <div class="chips">${STARTERS.map(t => `<button class="chip" type="button">${esc(t)}</button>`).join("")}</div></div></div>
        <form class="composer" id="nm-form"><label class="sr" for="nm-q">Question</label>
          <textarea class="input" id="nm-q" rows="1" placeholder="Votre question sur IFRS 17…" required></textarea>
          <button class="icon-btn mic" id="nm-mic" type="button" aria-label="Poser la question à l'oral">${icon("mic")}</button>
          <button class="btn primary" type="submit">${icon("send")}Envoyer</button></form></section>
      <aside class="stack">
        <section class="panel"><div class="panel-head"><h2>Paragraphe cité</h2></div><div class="panel-body" id="nm-cite">
          <p class="cell-sub" style="font-size:14px">Cliquez sur une référence dans une réponse, par exemple <span class="cite" style="cursor:default">§44</span>, pour lire ici le passage exact du règlement.</p></div></section>
        <section class="panel"><div class="panel-head"><h2>Garanties</h2></div><div class="panel-body"><ul class="controls-list">
          <li class="ok"><span class="ci">${icon("check")}</span><span>Une citation n'est acceptée que si la phrase recopiée figure dans le paragraphe.</span></li>
          <li class="ok"><span class="ci">${icon("check")}</span><span>Un second modèle juge chaque phrase : soutenue par son paragraphe, portée respectée.</span></li>
          <li class="ok"><span class="ci">${icon("check")}</span><span>Hors sujet ou sans passage pertinent : l'assistant refuse plutôt que d'inventer.</span></li>
          <li class="ok"><span class="ci">${icon("check")}</span><span>À l'oral, la transcription utilise le vocabulaire IFRS 17 (CSM, PAA, LRC…).</span></li></ul></div></section>
      </aside></div></div>`;

  const thread = $("#nm-thread");
  const add = html => { thread.insertAdjacentHTML("beforeend", html); thread.lastElementChild.scrollIntoView({ block: "nearest", behavior: "smooth" }); return thread.lastElementChild; };
  const thinking = text => add(`<div class="msg a thinking"><span class="who">${icon("norm")}</span><div class="body"><p class="text">${esc(text)}<span class="dots"><i></i><i></i><i></i></span></p></div></div>`);

  function answer(node, r) {
    node.classList.remove("thinking");
    const a = r.answer, body = $(".body", node);
    if (r.small_talk) { body.innerHTML = `<p class="text">${esc(a.refusal_reason)}</p>`; return; }
    if (a.refused) {
      const out = r.plan?.intent === "hors_perimetre";
      const seen = [...new Set((r.sources || []).flatMap(s => s.paragraph_ids || []))].slice(0, 6);
      body.innerHTML = `<p class="text">${esc(out ? a.refusal_reason : "Je n'ai trouvé aucun passage du règlement qui réponde solidement à cette question. Reformulez-la avec les termes de la norme (par exemple « marge sur services contractuels », « champ d'application »).")}</p>
        ${!out && seen.length ? `<p class="cell-sub" style="margin-top:6px">Passages consultés : ${seen.map(x => esc(refLabel(x))).join(", ")}</p>` : ""}
        <div class="meta"><span class="status warn">${out ? "Hors du périmètre d'IFRS 17" : "Pas de réponse"}</span></div>`;
      return;
    }
    const cites = Object.fromEntries((a.citations || []).map(c => [c.paragraph_id, c]));
    const html = esc(a.answer).replace(/\[([^[\]]{1,60})\]/g, (m, ref) => {
      const id = ref.replace("§", "").trim();
      return cites[id] ? `<button class="cite" type="button" data-ref="${esc(id)}" aria-expanded="false" title="${esc(refLabel(id, true))}">${esc(id.startsWith("def:") ? `définition « ${id.slice(4)} »` : ref)}</button>` : m;
    });
    const v = r.verdict;
    body.innerHTML = `<p class="text">${html}</p>
      <div class="meta">${!v ? "" : v.status === "ok" ? `<span class="status ok">Relue et validée</span>` : `<span class="status warn">À valider par un humain</span>`}
        <span>${(a.citations || []).length} paragraphe${(a.citations || []).length > 1 ? "s" : ""} cité${(a.citations || []).length > 1 ? "s" : ""}</span>
        ${r.rounds ? "<span>1 correction demandée par le vérificateur</span>" : ""}<span>${fr(r.latency_ms / 1000, 1)} s</span></div>
      ${timingHTML(r.duree)}`;
    node._cites = cites;
    const first = $(".cite", body);
    if (first) showCite(first, cites);
  }
  function showCite(btn, cites) {
    $$(".cite[aria-expanded]", thread).forEach(x => x.setAttribute("aria-expanded", "false"));
    btn.setAttribute("aria-expanded", "true");
    const c = cites[btn.dataset.ref];
    $("#nm-cite").innerHTML = `<div class="quote" style="margin-top:0"><b>${esc(refLabel(c.paragraph_id, true))} · règlement (UE) 2021/2036</b>« ${esc(c.quote)} »</div>`;
  }
  thread.addEventListener("click", e => {
    const chip = e.target.closest(".chip");
    if (chip) { ask(chip.textContent); return; }
    const b = e.target.closest(".cite[data-ref]");
    if (b) showCite(b, b.closest(".msg")._cites);
  });

  async function ask(q) {
    q = q.trim(); if (!q) return;
    $(".intro-card .chips", thread)?.remove();
    add(`<div class="msg q">${esc(q)}</div>`);
    const node = thinking("Recherche dans la norme, puis relecture par le vérificateur");
    try { answer(node, await getJSON("/v1/ask", { method: "POST", json: { question: q } })); }
    catch (err) { node.classList.remove("thinking"); $(".body", node).innerHTML = `<div class="callout bad">${icon("alert")}<span>${esc(err.message)}</span></div>`; }
  }
  const qa = $("#nm-q");
  qa.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#nm-form").requestSubmit(); } });
  qa.addEventListener("input", () => { qa.style.height = "auto"; qa.style.height = `${Math.min(160, qa.scrollHeight)}px`; });
  $("#nm-form").addEventListener("submit", e => { e.preventDefault(); const q = qa.value; qa.value = ""; qa.style.height = ""; ask(q); });

  /* question à l'oral : enregistrement dans le navigateur, puis Whisper (/v1/ask/audio) */
  let rec = null;
  const mic = $("#nm-mic");
  mic.addEventListener("click", async () => {
    if (rec?.state === "recording") { rec.stop(); return; }
    if (!navigator.mediaDevices?.getUserMedia) { toast("Ce navigateur ne permet pas d'enregistrer le micro.", "warn"); return; }
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); } catch { toast("Accès au micro refusé : autorisez-le dans le navigateur.", "warn"); return; }
    const chunks = [];
    rec = new MediaRecorder(stream);
    rec.ondataavailable = ev => chunks.push(ev.data);
    rec.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      mic.classList.remove("recording"); mic.setAttribute("aria-label", "Poser la question à l'oral");
      const type = rec.mimeType || "audio/webm";
      const ext = type.includes("ogg") ? "ogg" : type.includes("mp4") ? "m4a" : "webm";
      const form = new FormData();
      form.append("file", new File([new Blob(chunks, { type })], `question.${ext}`, { type }));
      const node = thinking("Transcription par Whisper, puis recherche dans la norme");
      try {
        const r = await getJSON("/v1/ask/audio", { method: "POST", form });
        node.insertAdjacentHTML("beforebegin", `<div class="msg q"><small>Question à l'oral, transcrite</small>${esc(r.transcription)}</div>`);
        answer(node, r);
      } catch (err) { node.classList.remove("thinking"); $(".body", node).innerHTML = `<div class="callout bad">${icon("alert")}<span>${esc(err.message)}</span></div>`; }
    };
    rec.start();
    mic.classList.add("recording"); mic.setAttribute("aria-label", "Arrêter et envoyer la question");
    toast("Enregistrement en cours : cliquez de nouveau sur le micro pour envoyer.", "info");
  });
  return () => { if (rec?.state === "recording") rec.stop(); };
}
