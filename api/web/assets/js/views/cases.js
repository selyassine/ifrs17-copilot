/* Registre des dossiers : filtres par statut et canal, recherche, pagination. */
import { $, $$, esc, fr, ago, when, icon, canDo, getJSON, statusChip, emit, SOURCE_LABEL, debounce } from "../core.js";

const PAGE = 20;
const TABS = [["", "Tous"], ["validation_humaine", "À valider"], ["note_prete", "Note prête"], ["validee", "Validés"],
  ["rejetee", "Rejetés"], ["document_illisible", "Illisibles"], ["erreur", "Erreurs"]];

export async function render(main, _params, query) {
  const st = { status: query.get("statut") || "", source: query.get("canal") || "", q: query.get("q") || "", page: 0 };
  emit("crumbs", [{ label: "Dossiers" }]);
  main.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>Dossiers</h1>
      <p>Tous les dossiers, qu'ils viennent de l'espace de travail, d'un e-mail ou du formulaire de dépôt. Chaque action y est tracée.</p></div>
</div>
    <section class="panel">
      <div class="toolbar"><div class="seg" role="group" aria-label="Statut" id="cs-tabs"></div></div>
      <div class="toolbar">
        <label class="search-in grow">${icon("search")}<span class="sr">Rechercher</span>
          <input class="input" id="cs-q" placeholder="Référence, groupe de contrats, déposant, fichier…" value="${esc(st.q)}"></label>
        <label><span class="sr">Canal</span><select class="input" id="cs-src">
          <option value="">Tous les canaux</option>${Object.entries(SOURCE_LABEL).filter(([k]) => k !== "validation")
            .map(([k, v]) => `<option value="${k}" ${k === st.source ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
      </div>
      <div id="cs-body" aria-live="polite"></div>
    </section></div>`;

  let counts = {};
  try { counts = (await getJSON("/v1/dashboard")).par_statut; } catch { /* compteurs facultatifs */ }
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const drawTabs = () => {
    $("#cs-tabs").innerHTML = TABS.map(([k, label]) => `<button type="button" data-s="${k}" aria-pressed="${k === st.status}">${label}
      <span class="n">${k ? counts[k] || 0 : total}</span></button>`).join("");
  };
  drawTabs();

  const sync = () => {
    const p = new URLSearchParams();
    if (st.status) p.set("statut", st.status);
    if (st.source) p.set("canal", st.source);
    if (st.q) p.set("q", st.q);
    history.replaceState(null, "", `#/dossiers${p.toString() ? "?" + p : ""}`);
  };

  async function load() {
    const body = $("#cs-body");
    const qs = new URLSearchParams({ status: st.status, source: st.source, q: st.q, limit: PAGE, offset: st.page * PAGE });
    body.style.opacity = ".55";
    try {
      const r = await getJSON(`/v1/cases?${qs}`);
      body.style.opacity = "";
      if (!r.total) {
        body.innerHTML = `<div class="empty">${icon("search")}<h3>Aucun dossier</h3><p>${st.q || st.status || st.source
          ? "Aucun dossier ne correspond à ces critères." : "Le registre est vide : déposez un premier dossier."}</p>
          ${st.q || st.status || st.source ? `<button class="btn" id="cs-reset">Effacer les filtres</button>` : ""}</div>`;
        $("#cs-reset")?.addEventListener("click", () => { Object.assign(st, { status: "", source: "", q: "", page: 0 }); $("#cs-q").value = ""; $("#cs-src").value = ""; drawTabs(); sync(); load(); });
        return;
      }
      const pages = Math.ceil(r.total / PAGE);
      body.innerHTML = `<div class="table-wrap"><table class="table"><thead><tr>
          <th>Dossier</th><th>Statut</th><th class="r">CSM ou perte à l'origine</th><th class="hide-sm">Déposant</th>
          <th class="hide-sm">Document</th><th class="r">Mis à jour</th></tr></thead><tbody>
        ${r.dossiers.map(c => `<tr class="click" data-href="#/dossiers/${encodeURIComponent(c.case_id)}">
          <td><a class="ref" href="#/dossiers/${encodeURIComponent(c.case_id)}">${esc(c.group_id || "Groupe non lu")}</a><small class="mono">${esc(c.case_id)}</small></td>
          <td>${statusChip(c.status)}</td>
          <td class="r num">${c.csm == null ? "—" : c.onerous ? `<span class="neg">perte ${fr(c.loss)}</span>` : fr(c.csm)}
            ${c.currency ? `<small>${esc(c.currency)}${c.unit ? `, ${esc(c.unit)}` : ""}</small>` : ""}</td>
          <td class="hide-sm">${esc(c.submitter || "—")}<small>${esc(SOURCE_LABEL[c.source] || c.source)}</small></td>
          <td class="hide-sm">${esc(c.filename || "—")}</td>
          <td class="r" title="${esc(when(c.updated_at))}">${ago(c.updated_at)}</td></tr>`).join("")}
        </tbody></table></div>
        <div class="pager" ${pages > 1 ? "" : "hidden"}><span>${r.total} dossier${r.total > 1 ? "s" : ""}${pages > 1 ? `, page ${st.page + 1} sur ${pages}` : ""}</span>
          <span class="btns"><button class="btn sm" id="cs-prev" ${st.page ? "" : "disabled"}>${icon("chevronL")}Précédents</button>
          <button class="btn sm" id="cs-next" ${st.page + 1 < pages ? "" : "disabled"}>Suivants${icon("chevronR")}</button></span></div>`;
      $("#cs-prev").addEventListener("click", () => { st.page -= 1; load(); });
      $("#cs-next").addEventListener("click", () => { st.page += 1; load(); });
      $$("tr[data-href]", body).forEach(tr => tr.addEventListener("click", e => { if (!e.target.closest("a")) location.hash = tr.dataset.href; }));
    } catch (err) {
      body.style.opacity = "";
      body.innerHTML = `<div class="panel-body"><div class="callout bad">${icon("alert")}<span>${esc(err.message)}</span></div></div>`;
    }
  }

  $("#cs-tabs").addEventListener("click", e => {
    const b = e.target.closest("[data-s]");
    if (!b) return;
    st.status = b.dataset.s; st.page = 0; drawTabs(); sync(); load();
  });
  $("#cs-src").addEventListener("change", e => { st.source = e.target.value; st.page = 0; sync(); load(); });
  $("#cs-q").addEventListener("input", debounce(e => { st.q = e.target.value.trim(); st.page = 0; sync(); load(); }, 280));
  await load();
}
