/* Réponses du Copilot en graphes, tableaux, fichiers et audio (D-089).
   Le graphe vient des résultats des outils (donc du moteur), jamais du texte du modèle : il est juste par
   construction et ne coûte aucun appel au modèle. Le site choisit le graphe d'après l'outil appelé. */
import { $, esc, fr, icon, toast, downloadText } from "./core.js";
import { mount, columns, lines, waterfall, legend } from "./charts.js";

/** Barres horizontales signées (ici plutôt que dans charts.js : ce module ne dépend que de fonctions
    présentes depuis la v0.7, ce qui évite l'erreur « export introuvable » avec un charts.js en cache).
    Barres horizontales signées (chocs, comparaisons) : libellé à gauche, valeur au bout de la barre.
    `items` : [{ label, value, tip?, tone? }] ; tone "base" = barre neutre (référence). */
function hbars(items, { format = v => fr(v, 0) } = {}) {
  return (W, H) => {
    const lw = Math.min(190, Math.max(90, W * 0.34));
    const pad = { l: lw, r: 64, t: 6, b: 6 };
    const lo = Math.min(0, ...items.map(i => i.value)), hi = Math.max(0, ...items.map(i => i.value));
    const span = hi - lo || 1;
    const iw = W - pad.l - pad.r - (lo < 0 ? 56 : 0);
    const x0 = pad.l + (lo < 0 ? 56 : 0);
    const x = v => x0 + ((v - lo) / span) * iw;
    const rowH = (H - pad.t - pad.b) / items.length;
    const bh = Math.min(18, rowH * 0.6);
    const rows = items.map((it, i) => {
      const yc = pad.t + rowH * i + rowH / 2;
      const a = x(Math.min(0, it.value)), b = x(Math.max(0, it.value));
      const cls = it.tone === "base" ? "c-total" : it.value >= 0 ? "c-up" : "c-down";
      const vx = it.value >= 0 ? b + 6 : a - 6;
      return `<text x="${pad.l - 10}" y="${yc + 4}" class="tk lbl" text-anchor="end">${esc(it.label)}</text>
        <rect x="${a}" y="${yc - bh / 2}" width="${Math.max(1.5, b - a)}" height="${bh}" rx="3" class="mk ${cls}" data-g="${i}"/>
        <text x="${vx}" y="${yc + 4}" class="val" text-anchor="${it.value >= 0 ? "start" : "end"}">${format(it.value)}</text>
        <rect x="0" y="${pad.t + rowH * i}" width="${W}" height="${rowH}" class="hit" data-k="${i}"
          data-tip="${esc(`<b>${esc(it.label)}</b><span>${format(it.value)}</span>${it.tip ? `<small>${esc(it.tip)}</small>` : ""}`)}"/>`;
    }).join("");
    return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" class="chart" role="img">
      <line x1="${x(0)}" x2="${x(0)}" y1="${pad.t}" y2="${H - pad.b}" class="axis"/>${rows}</svg>`;
  };
}

/** "1 234,56" | "+310,25" | "12,4 %" | "-5" → nombre ; null si ce n'est pas un nombre. */
export function num(v) {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v !== "string") return null;
  const s = v.replace(/[\s  ]/g, "").replace(/[−–]/g, "-").replace(/%$/, "").replace(",", ".");
  return /^[+-]?\d+(\.\d+)?$/.test(s) ? parseFloat(s) : null;
}

const HEAD = {
  survenance: "Survenance", dernier_cumul: "Dernier cumul", facteur_restant: "Facteur restant",
  deja_paye_en_pourcentage_de_l_ultime: "Déjà payé / ultime", ultime: "Ultime", provision: "Provision",
  erreur_de_mack: "Erreur de Mack", part_de_la_provision: "Part de la provision", s_p_ultime: "S/P ultime",
  annee: "Année", paiements: "Paiements", taux_spot: "Taux spot", valeur_actuelle: "Valeur actuelle",
  choc: "Choc", bel: "BEL", lic: "LIC", variation_du_lic: "Variation du LIC", niveau: "Niveau",
  ajustement_risque: "Ajustement pour risque", csm: "CSM", perte: "Perte", statut: "Statut", bascule: "Bascule",
  variation_du_resultat_a_l_origine: "Variation du résultat à l'origine", periode: "Période", produits: "Produits",
  resultat_des_services: "Résultat des services", charges_financieres: "Charges financières",
  niveau_demande: "Niveau demandé", ajustement_risque_exige: "Ajustement pour risque exigé",
  ajustement_risque_exige_en_pourcentage_des_sorties: "Exigé, en % des sorties", csm_initiale: "CSM initiale",
  perte_initiale: "Perte à l'origine", csm_centrale: "CSM centrale", perte_centrale: "Perte centrale",
  ajustement_risque_retenu: "Ajustement pour risque retenu", niveau_de_confiance_retenu: "Niveau de confiance retenu",
  hypothese: "Hypothèse", lic_central: "LIC central", meilleure_estimation_bel: "Meilleure estimation (BEL)",
  provision_non_actualisee: "Provision non actualisée", effet_actualisation: "Effet de l'actualisation",
  coefficient_de_variation: "Coefficient de variation", niveau_de_confiance: "Niveau de confiance",
  duration_annees: "Duration (années)", calcul_du_lic: "Calcul du LIC", calcul_de_la_csm: "Calcul de la CSM",
  valeur_actuelle_primes: "Valeur actuelle des primes", valeur_actuelle_sorties: "Valeur actuelle des sorties",
  valeur_actuelle_recouvrements: "Valeur actuelle des recouvrements", frais_d_acquisition: "Frais d'acquisition",
  flux_execution: "Flux de trésorerie d'exécution", liberation_csm_premiere_periode: "CSM libérée en période 1",
  ajustement_risque_pourcentage: "Ajustement pour risque (%)", volatilite_registre: "Volatilité (registre)",
  statut_central: "Statut central", annees_de_survenance: "Années de survenance", date_de_cloture: "Date de clôture",
};
const head = k => HEAD[k] || k.replace(/_/g, " ").replace(/^./, c => c.toUpperCase());
const yes = v => (v === true ? "oui" : v === false ? "non" : v ?? "");

/** Tableau à partir d'une liste d'objets (mêmes clés). */
function tableOf(list) {
  const cols = Object.keys(list[0] || {});
  return { cols: cols.map(head), rows: list.map(o => cols.map(k => yes(o[k]))) };
}
/** Tableau « libellé / valeur » à partir d'un objet plat (sous-objets aplatis). */
function pairs(obj, skip = []) {
  const rows = [];
  const walk = (o, prefix = "") => Object.entries(o).forEach(([k, v]) => {
    if (skip.includes(k) || Array.isArray(v)) return;
    if (v && typeof v === "object") walk(v, `${prefix}${head(k)} : `);
    else rows.push([`${prefix}${head(k)}`, yes(v)]);
  });
  walk(obj);
  return { cols: ["Élément", "Valeur"], rows };
}
const rowsH = n => Math.max(90, n * 34 + 12);
const sign = v => (v > 0 ? "+" : "") + fr(v, 2);
const maxBy = (arr, f) => arr.reduce((a, b) => (f(b) > f(a) ? b : a), arr[0]);

/** Visuels d'une réponse : [{ id, title, draw?, height?, legend?, note, table, file }] — un par outil utile.
    `note` : la lecture du graphe, écrite par le code avec les chiffres de l'outil. */
export function visuals(tools, { lic = false, unit = "" } = {}) {
  const out = [];
  const u = unit ? ` (${unit})` : "";
  (tools || []).forEach((t, n) => {
    const r = t.resultat;
    if (!r || typeof r !== "object" || r.erreur || r.refus) return;
    const add = v => out.push({ id: `${t.outil}-${n}`, file: t.outil, ...v });
    switch (t.outil) {
      case "par_survenance": {
        const rows = r.par_survenance || [];
        if (rows.length > 1) {
          const top = maxBy(rows, x => num(x.provision) || 0);
          const done = rows.filter(x => (num(x.provision) || 0) === 0).map(x => x.survenance);
          add({ title: `Provision par année de survenance${u}`, table: tableOf(rows),
            draw: columns(rows.map(x => ({ label: x.survenance, value: num(x.provision) || 0,
              tip: `${x.survenance} : ${x.part_de_la_provision} de la provision` })), { format: v => fr(v, 0) }),
            note: `Chaque colonne est ce qui reste à payer pour une année de survenance. ${top.survenance} pèse le plus : ${top.provision}, soit ${top.part_de_la_provision} de la provision totale (${r.provision_totale}). Les années récentes portent l'essentiel de la provision, car leurs sinistres sont encore peu payés${done.length ? ` ; ${done.join(", ")} ${done.length > 1 ? "sont" : "est"} entièrement payée${done.length > 1 ? "s" : ""}` : ""}.` });
        } else if (rows.length === 1) add({ title: `Survenance ${rows[0].survenance}${u}`, table: tableOf(rows), note: "" });
        break;
      }
      case "paiements_futurs": {
        const rows = r.par_annee || [];
        const series = [{ name: "Paiements attendus", values: rows.map(x => num(x.paiements) || 0) },
          { name: "Valeur actuelle", values: rows.map(x => num(x.valeur_actuelle) || 0) }];
        add({ title: `Paiements futurs par année calendaire${u}`, table: tableOf(rows),
          ...(rows.length > 1 ? { draw: lines(rows.map(x => `+${x.annee}`), series, { area: 0 }), legend: legend(series) } : {}),
          note: `La courbe montre quand les sinistres déjà survenus seront payés, année après année ; l'écart entre les deux courbes est l'effet de l'actualisation. Total attendu ${r.total_paiements}, valeur actuelle ${r.total_valeur_actuelle} (duration ${r.duration_annees} ans).` });
        break;
      }
      case "sensibilites": {
        const chocs = r.chocs || [];
        const key = lic ? "variation_du_lic" : "variation_du_resultat_a_l_origine";
        const big = chocs.length ? maxBy(chocs, x => Math.abs(num(x[key]) || 0)) : null;
        const flips = chocs.filter(x => x.bascule).map(x => x.choc);
        add({ title: lic ? `Effet des chocs sur le LIC${u}` : `Effet des chocs sur le résultat à l'origine${u}`,
          table: tableOf(chocs), height: rowsH(chocs.length),
          draw: hbars(chocs.map(x => ({ label: x.choc, value: num(x[key]) || 0,
            tip: lic ? `LIC ${x.lic}` : `${x.statut}${x.bascule ? ", bascule" : ""}` })), { format: v => (v > 0 ? "+" : "") + fr(v, 0) }),
          note: big ? (lic
            ? `Chaque barre est la variation du LIC après un choc : vers la droite, le passif augmente. Le choc le plus fort est « ${big.choc} » (${big[key]}).`
            : `Chaque barre est la variation du résultat à l'origine (CSM moins perte) après un choc : vers la gauche, la marge baisse. Le choc le plus fort est « ${big.choc} » (${big[key]})${flips.length ? ` ; le groupe bascule avec : ${flips.join(", ")}` : " ; aucun choc ne fait basculer le groupe"}.`) : "" });
        const lv = r.niveaux_de_confiance || [];
        if (lv.length > 1) {
          // colonnes : les niveaux (65 %, 75 %… 99,5 %) ne sont pas régulièrement espacés, une courbe les déformerait
          add({ id: `${t.outil}-${n}-niveaux`, title: `Ajustement pour risque selon le niveau de confiance${u}`,
            table: tableOf(lv), draw: columns(lv.map(x => ({ label: x.niveau, value: num(x.ajustement_risque) || 0,
              tip: `Niveau ${x.niveau} : LIC ${x.lic}` })), { format: v => fr(v, 0) }),
            note: `Plus le niveau de confiance est élevé, plus l'ajustement pour risque est grand : de ${lv[0].ajustement_risque} à ${lv[0].niveau} jusqu'à ${lv[lv.length - 1].ajustement_risque} à ${lv[lv.length - 1].niveau}.` });
        }
        break;
      }
      case "evaluer_scenario": {
        const items = lic
          ? [{ label: "LIC central", value: num(r.lic_central), tone: "base" }, { label: "LIC du scénario", value: num(r.lic) }]
          : [{ label: "Central", value: (num(r.csm_centrale) || 0) - (num(r.perte_centrale) || 0), tone: "base", tip: "CSM moins perte" },
            { label: "Scénario", value: (num(r.csm_initiale) || 0) - (num(r.perte_initiale) || 0), tip: r.statut }];
        if (items.every(i => i.value != null))
          add({ title: lic ? `LIC : central et scénario${u}` : `Résultat à l'origine, CSM moins perte${u}`, height: rowsH(2),
            draw: hbars(items, { format: v => fr(v, 0) }), table: pairs(r),
            note: lic ? `La barre foncée est le LIC du dossier, la barre verte celui du scénario : écart ${r.variation_du_lic}.`
              : `La barre foncée est le scénario central, l'autre le scénario demandé : le résultat à l'origine varie de ${r.variation_du_resultat_a_l_origine} et le groupe est ${r.statut}${r.statut !== r.statut_central ? ` (il était ${r.statut_central})` : ""}.` });
        break;
      }
      case "niveau_de_confiance": {
        const items = [{ label: `Retenu (${r.niveau_de_confiance_retenu})`, value: num(r.ajustement_risque_retenu), tone: "base" },
          { label: `Exigé à ${r.niveau_demande}`, value: num(r.ajustement_risque_exige) }];
        if (items.every(i => i.value != null)) {
          const effect = lic ? (r.variation_du_lic ? ` Le LIC passerait de ${r.lic_central} à ${r.lic} (${r.variation_du_lic}).` : "")
            : r.csm_centrale ? ` La CSM passerait de ${r.csm_centrale} à ${r.csm_initiale} (${r.variation_du_resultat_a_l_origine}) ; le groupe resterait ${r.statut}.` : "";
          add({ title: `Ajustement pour risque${u}`, height: rowsH(2), draw: hbars(items, { format: v => fr(v, 0) }), table: pairs(r),
            note: `La barre foncée est l'ajustement retenu dans le dossier (niveau de confiance ${r.niveau_de_confiance_retenu}), l'autre celui qu'exige ${r.niveau_demande}.${effect}` });
        }
        break;
      }
      case "projection_resultat": {
        const rows = r.par_periode || [];
        const series = [{ name: "Produits", values: rows.map(x => num(x.produits) || 0) },
          { name: "Résultat des services", values: rows.map(x => num(x.resultat_des_services) || 0) },
          { name: "Charges financières", values: rows.map(x => num(x.charges_financieres) || 0) }];
        add({ title: `Compte de résultat attendu par période${u}`, table: tableOf(rows),
          ...(rows.length > 1 ? { draw: lines(rows.map(x => `P${x.periode}`), series, { area: -1 }), legend: legend(series) } : {}),
          note: `Chaque point est une période du groupe dans le scénario central. Totaux : produits ${r.total_produits}, résultat des services ${r.total_resultat_des_services}, charges financières ${r.total_charges_financieres}.` });
        if (rows.length > 1 && rows.every(x => x.csm_fin_de_periode != null))
          add({ id: `${t.outil}-${n}-csm`, title: `CSM restante en fin de période${u}`,
            table: tableOf(rows.map(x => ({ periode: x.periode, csm_fin_de_periode: x.csm_fin_de_periode }))),
            draw: columns(rows.map(x => ({ label: `P${x.periode}`, value: num(x.csm_fin_de_periode) || 0,
              tip: `Fin de la période ${x.periode}` })), { format: v => fr(v, 0) }),
            note: `La CSM est le profit pas encore gagné : chaque période, elle porte intérêt puis une part est libérée en résultat selon les unités de couverture fournies. Elle passe de ${rows[0].csm_fin_de_periode} en fin de première période à ${rows[rows.length - 1].csm_fin_de_periode} à la fin.` });
        break;
      }
      case "donnees_du_dossier": {
        if (lic && num(r.meilleure_estimation_bel) != null && num(r.ajustement_risque) != null && num(r.lic) != null)
          add({ title: `Composition du LIC${u}`, height: 230, table: pairs(r),
            draw: waterfall([{ label: "Meilleure estimation (BEL)", short: "BEL", value: num(r.meilleure_estimation_bel) },
              { label: "Ajustement pour risque", short: "RA", value: num(r.ajustement_risque) },
              { label: "LIC", value: num(r.lic), total: true }]),
            note: `Le LIC est la somme de la meilleure estimation actualisée des paiements futurs (BEL) et de l'ajustement pour risque : ${r.calcul_du_lic || `${r.meilleure_estimation_bel} + ${r.ajustement_risque} = ${r.lic}`}.` });
        else if (!lic && num(r.valeur_actuelle_primes) != null && num(r.valeur_actuelle_sorties) != null) {
          const steps = [{ label: "Primes", value: num(r.valeur_actuelle_primes) },
            ...(num(r.valeur_actuelle_recouvrements) ? [{ label: "Recouvrements", short: "Recouv.", value: num(r.valeur_actuelle_recouvrements) }] : []),
            { label: "Sorties", value: -num(r.valeur_actuelle_sorties) },
            ...(num(r.frais_d_acquisition) ? [{ label: "Frais d'acquisition", short: "Frais", value: -num(r.frais_d_acquisition) }] : []),
            { label: "Ajustement pour risque", short: "RA", value: -(num(r.ajustement_risque) || 0) }];
          const total = steps.reduce((a, s) => a + s.value, 0);
          steps.push({ label: total >= 0 ? "CSM" : "Perte", value: total, total: true });
          add({ title: `Calcul de la CSM à l'origine${u}`, height: 240, table: pairs(r), draw: waterfall(steps),
            note: `On part des primes actualisées, on retire les sorties, les frais et l'ajustement pour risque : ce qui reste est la CSM (profit non encore gagné). Si le reste est négatif, la CSM est nulle et le groupe est déficitaire.${r.calcul_de_la_csm ? ` Pour ce dossier : ${r.calcul_de_la_csm}.` : ""}` });
        } else add({ title: "Données du dossier", table: pairs(r), note: "" });
        break;
      }
      default: break;      // rechercher_norme, memoire_du_dossier : du texte, déjà dans la réponse
    }
  });
  return out;
}

/** Texte d'une réponse en HTML sûr : paragraphes, listes à puces, gras, références lisibles ; aucun caractère
    de mise en forme (**, #, `) ni nom de champ technique n'est affiché tel quel. */
export function richText(text) {
  let t = String(text || "").replace(/\r/g, "")
    .replace(/\[def:\s*([^\]]+)\]/g, "(définition : $1)")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/\b([a-z]+(?:_[a-z]+){1,6})\b/g, w => (HEAD[w] ? HEAD[w].replace(/^[A-Z](?![A-Z])/, c => c.toLowerCase()) : w.replace(/_/g, " ")));
  const blocks = t.split(/\n{2,}/).map(b => b.trim()).filter(Boolean);
  const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/__(.+?)__/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])\*(?!\s)([^*]+?)\*(?=[\s).,;:!?]|$)/g, "$1<em>$2</em>");
  const bullet = /^(?:[-•*]|\d+[.)])\s+/;
  return blocks.map(b => {
    // lignes à puces consécutives → une liste ; les autres lignes → paragraphes (avant, entre ou après les listes)
    const out = [];
    let list = null, para = [];
    const flushPara = () => { if (para.length) out.push(`<p>${para.map(inline).join("<br>")}</p>`); para = []; };
    const flushList = () => { if (list) out.push(`<${list.tag}>${list.items.map(x => `<li>${inline(x)}</li>`).join("")}</${list.tag}>`); list = null; };
    b.split("\n").map(l => l.trim()).filter(Boolean).forEach(l => {
      if (bullet.test(l)) {
        flushPara();
        const tag = /^\d/.test(l) ? "ol" : "ul";
        if (list && list.tag !== tag) flushList();
        (list ||= { tag, items: [] }).items.push(l.replace(bullet, ""));
      } else { flushList(); para.push(l); }
    });
    flushList(); flushPara();
    return out.join("");
  }).join("");
}

/** CSV lisible par Excel (France) : séparateur « ; », virgule décimale, BOM UTF-8. */
export function toCSV(table) {
  const cell = v => {
    const n = num(v);
    const s = n != null && !/%$/.test(String(v).trim()) ? String(n).replace(".", ",") : String(v ?? "");
    return /[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return "﻿" + [table.cols, ...table.rows].map(r => r.map(cell).join(";")).join("\r\n");
}

function tableHTML(t) {
  return `<div class="cp-table"><table><thead><tr>${t.cols.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${t.rows.map(r => `<tr>${r.map((v, i) => `<td${i && num(v) != null ? ' class="n"' : ""}>${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

/** Place les visuels sous une réponse ; renvoie le nombre de visuels montés. */
export function mountMedia(host, r, opts = {}) {
  const vs = visuals(r.tools, opts);
  if (!vs.length) return 0;
  // un graphe identique à un graphe déjà montré dans ce fil est replié (« toujours le même graphe », F-036)
  vs.forEach(v => {
    const sig = `${v.title}|${JSON.stringify(v.table.rows)}`;
    v.repeat = !!opts.seen?.has(sig);
    opts.seen?.add(sig);
  });
  const box = document.createElement("div");
  box.className = "cp-media";
  box.innerHTML = vs.map((v, i) => v.repeat
    ? `<details class="cp-fig cp-repeat" data-i="${i}"><summary>${icon("chart")}Même graphe que plus haut : ${esc(v.title)}</summary>
        <div class="chart-box" data-chart="${i}"></div></details>`
    : `<figure class="cp-fig" data-i="${i}">
      <figcaption><span>${icon("chart")}${esc(v.title)}</span>
        <button class="btn sm ghost" type="button" data-csv="${i}" title="Tableau au format CSV, ouvrable dans Excel">${icon("download")}Excel (CSV)</button></figcaption>
      ${v.legend || ""}${v.draw ? `<div class="chart-box" data-chart="${i}"></div>` : tableHTML(v.table)}
      ${v.note ? `<p class="cp-note">${esc(v.note)}</p>` : ""}
      ${v.draw ? `<details class="cp-data"><summary>Voir le tableau</summary>${tableHTML(v.table)}</details>` : ""}</figure>`).join("");
  host.append(box);
  vs.forEach((v, i) => {
    const el = $(`[data-chart="${i}"]`, box);
    if (!v.draw || !el) return;
    if (v.repeat) {        // dessiné à l'ouverture (largeur connue seulement quand le bloc est visible)
      el.closest("details").addEventListener("toggle", () => { if (!el.childElementCount) mount(el, v.draw, v.height || 220); }, { once: true });
    } else mount(el, v.draw, v.height || 220);
  });
  box.addEventListener("click", e => {
    const b = e.target.closest("[data-csv]");
    if (!b) return;
    const v = vs[+b.dataset.csv];
    downloadText(toCSV(v.table), `${opts.caseId ? `${opts.caseId}_` : ""}${v.file}.csv`, "text/csv;charset=utf-8");
    toast("Tableau téléchargé (CSV, ouvrable dans Excel).");
  });
  return vs.length;
}

/* ------------------------------------------------------------------ audio : lecture de la réponse */
/** Texte prononçable : sans markdown, unités et références dites en toutes lettres. */
export function speakable(text) {
  return String(text || "")
    .replace(/\*\*|__|`|#+\s/g, "")
    .replace(/\[(?:def:)?([^\]]+)\]/g, (_, ref) => (/^§/.test(ref) ? `paragraphe ${ref.slice(1)}` : ""))
    .replace(/§\s?(\d+)/g, "paragraphe $1")
    .replace(/(\d)\s?pb\b/g, "$1 points de base")
    .replace(/\bLIC\b/g, "L I C").replace(/\bCSM\b/g, "C S M").replace(/\bBEL\b/g, "B E L").replace(/\bRA\b/g, "R A")
    .replace(/(\d)[ \u00a0\u202f](?=\d{3}\b)/g, "$1")
    .replace(/\s+/g, " ").trim();
}

let speaking = null;
export const canSpeak = () => "speechSynthesis" in window && typeof SpeechSynthesisUtterance !== "undefined";
/** Lit `text` en français ; un second clic sur le même bouton arrête la lecture. */
export function speak(text, btn) {
  if (!canSpeak()) { toast("Ce navigateur ne sait pas lire le texte à voix haute.", "warn"); return; }
  const synth = window.speechSynthesis;
  const was = speaking;
  synth.cancel();
  document.querySelectorAll(".speaking").forEach(b => { b.classList.remove("speaking"); b.setAttribute("aria-pressed", "false"); });
  speaking = null;
  if (was === btn) return;
  const u = new SpeechSynthesisUtterance(speakable(text));
  u.lang = "fr-FR";
  const voice = synth.getVoices().find(v => /^fr(-|_)FR/i.test(v.lang)) || synth.getVoices().find(v => /^fr/i.test(v.lang));
  if (voice) u.voice = voice;
  u.rate = 1.02;
  u.onend = u.onerror = () => { btn?.classList.remove("speaking"); btn?.setAttribute("aria-pressed", "false"); if (speaking === btn) speaking = null; };
  btn?.classList.add("speaking"); btn?.setAttribute("aria-pressed", "true");
  speaking = btn;
  synth.speak(u);
}
export const stopSpeaking = () => { if (canSpeak()) window.speechSynthesis.cancel(); speaking = null; };
