/* Graphiques SVG sans dépendance : colonnes, cascade, courbes. Traits fins, grille discrète,
   info-bulle au survol, redessinés à la largeur réelle du conteneur. */
import { esc, fr, compact } from "./core.js";

const NS = "http://www.w3.org/2000/svg";

/** Monte un graphique : `draw(width)` renvoie le SVG ; redessiné quand le conteneur change de taille. */
export function mount(el, draw, height = 220) {
  let last = 0;
  const render = () => {
    const w = Math.max(280, Math.round(el.clientWidth));
    if (w === last) return;
    last = w;
    el.innerHTML = draw(w, height);
    wireTips(el);
  };
  render();
  const ro = new ResizeObserver(render);
  ro.observe(el);
  return () => ro.disconnect();
}

function niceMax(v) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}
function ticks(min, max, count = 4, int = false) {
  const span = int ? Math.max(1, niceMax((max - min) / count)) : niceMax((max - min) / count);
  const out = [];
  let v = Math.floor(min / span) * span;
  out.push(+v.toFixed(10));
  while (v < max - span * 1e-6) { v += span; out.push(+v.toFixed(10)); }
  return out;
}
/* chemin d'une barre arrondie (4 px) du côté de la valeur, carrée côté ligne de base */
function bar(x, y0, y1, w, r = 4) {
  const up = y1 < y0;
  const h = Math.abs(y1 - y0);
  r = Math.min(r, h, w / 2);
  if (h < 0.5) return "";
  return up
    ? `M${x} ${y0}V${y1 + r}Q${x} ${y1} ${x + r} ${y1}H${x + w - r}Q${x + w} ${y1} ${x + w} ${y1 + r}V${y0}Z`
    : `M${x} ${y0}V${y1 - r}Q${x} ${y1} ${x + r} ${y1}H${x + w - r}Q${x + w} ${y1} ${x + w} ${y1 - r}V${y0}Z`;
}

function wireTips(el) {
  let tip = el.querySelector(".chart-tip");
  if (!tip) { tip = document.createElement("div"); tip.className = "chart-tip"; tip.hidden = true; el.append(tip); }
  const svg = el.querySelector("svg");
  if (!svg) return;
  const show = (t, ev) => {
    tip.innerHTML = t.dataset.tip;
    tip.hidden = false;
    const box = el.getBoundingClientRect();
    const tb = tip.getBoundingClientRect();
    let x = ev.clientX - box.left + 14;
    if (x + tb.width > box.width) x = ev.clientX - box.left - tb.width - 14;
    tip.style.transform = `translate(${Math.max(0, x)}px, ${Math.max(0, ev.clientY - box.top - tb.height - 10)}px)`;
    svg.querySelectorAll(".hot").forEach(n => n.classList.remove("hot"));
    const k = t.dataset.k;
    if (k != null) svg.querySelectorAll(`[data-g="${k}"]`).forEach(n => n.classList.add("hot"));
  };
  svg.addEventListener("pointermove", ev => {
    const t = ev.target.closest("[data-tip]");
    if (t) show(t, ev); else { tip.hidden = true; svg.querySelectorAll(".hot").forEach(n => n.classList.remove("hot")); }
  });
  svg.addEventListener("pointerleave", () => { tip.hidden = true; svg.querySelectorAll(".hot").forEach(n => n.classList.remove("hot")); });
}

/** Colonnes d'une seule série (ex. dossiers déposés par jour). */
export function columns(items, { format = v => fr(v, 0), label = i => i.label, tickEvery = 1, unit = "" } = {}) {
  return (W, H) => {
    const pad = { l: 34, r: 8, t: 12, b: 26 };
    const tks = ticks(0, Math.max(1, ...items.map(i => i.value)), 4, true);
    const max = tks[tks.length - 1];
    const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
    const slot = iw / items.length;
    const bw = Math.min(24, Math.max(3, slot - 2));
    const y = v => pad.t + ih - (v / max) * ih;
    const grid = tks.map(v => `<line x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}" class="gl"/>
      <text x="${pad.l - 8}" y="${y(v) + 4}" class="tk" text-anchor="end">${compact(v)}</text>`).join("");
    const bars = items.map((it, i) => {
      const x = pad.l + i * slot + (slot - bw) / 2;
      const tick = i % tickEvery === 0 || (i === items.length - 1 && i % tickEvery >= tickEvery / 2)
        ? `<text x="${x + bw / 2}" y="${H - 6}" class="tk" text-anchor="middle">${esc(label(it))}</text>` : "";
      return `<path d="${bar(x, y(0), y(it.value), bw)}" class="mk c1" data-g="${i}"/>${tick}
        <rect x="${pad.l + i * slot}" y="${pad.t}" width="${slot}" height="${ih}" class="hit" data-k="${i}"
          data-tip="${esc(`<b>${esc(it.tip || it.label)}</b><span>${format(it.value)}${unit}</span>`)}"/>`;
    }).join("");
    return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" class="chart" role="img">${grid}
      <line x1="${pad.l}" x2="${W - pad.r}" y1="${y(0)}" y2="${y(0)}" class="axis"/>${bars}</svg>`;
  };
}

/** Cascade : étapes signées puis total (comptabilisation initiale d'un groupe). */
export function waterfall(steps, { format = v => fr(v, 0) } = {}) {
  return (W, H) => {
    const pad = { l: 52, r: 12, t: 24, b: 46 };
    let run = 0;
    const segs = steps.map(s => {
      if (s.total) return { ...s, a: 0, b: s.value };
      const a = run; run += s.value; return { ...s, a, b: run };
    });
    const lo = Math.min(0, ...segs.map(s => Math.min(s.a, s.b)));
    const hi = Math.max(0, ...segs.map(s => Math.max(s.a, s.b)));
    const tk = ticks(lo, hi, 4);
    const min = Math.min(lo, tk[0]), max = Math.max(hi, tk[tk.length - 1]);
    const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
    const y = v => pad.t + ih - ((v - min) / (max - min || 1)) * ih;
    const slot = iw / segs.length;
    const bw = Math.min(56, slot * 0.52);
    const grid = tk.map(v => `<line x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}" class="gl"/>
      <text x="${pad.l - 8}" y="${y(v) + 4}" class="tk" text-anchor="end">${compact(v)}</text>`).join("");
    const body = segs.map((s, i) => {
      const x = pad.l + i * slot + (slot - bw) / 2;
      const cls = s.total ? (s.value < 0 ? "c-neg-total" : "c-total") : s.value >= 0 ? "c-up" : "c-down";
      const top = Math.min(y(s.a), y(s.b)), h = Math.max(1.5, Math.abs(y(s.a) - y(s.b)));
      const link = i < segs.length - 1 && !segs[i + 1].total
        ? `<line x1="${x + bw}" x2="${x + slot}" y1="${y(s.b)}" y2="${y(s.b)}" class="link"/>` : "";
      const vy = s.value >= 0 ? top - 7 : top + h + 15;
      return `<rect x="${x}" y="${top}" width="${bw}" height="${h}" rx="3" class="mk ${cls}" data-g="${i}"/>${link}
        <text x="${x + bw / 2}" y="${vy}" class="val" text-anchor="middle">${format(s.value)}</text>
        <text x="${x + bw / 2}" y="${H - 26}" class="tk lbl" text-anchor="middle">${esc(slot < 100 && s.short ? s.short : s.label)}</text>
        ${s.sub && slot >= 100 ? `<text x="${x + bw / 2}" y="${H - 11}" class="tk sub" text-anchor="middle">${esc(s.sub)}</text>` : ""}
        <rect x="${pad.l + i * slot}" y="${pad.t}" width="${slot}" height="${ih}" class="hit" data-k="${i}"
          data-tip="${esc(`<b>${esc(s.label)}</b><span>${format(s.value)}</span>${s.note ? `<small>${esc(s.note)}</small>` : ""}`)}"/>`;
    }).join("");
    return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" class="chart" role="img">${grid}
      <line x1="${pad.l}" x2="${W - pad.r}" y1="${y(0)}" y2="${y(0)}" class="axis"/>${body}</svg>`;
  };
}

/** Courbes (une à trois séries, même unité) avec réticule au survol. */
export function lines(labels, series, { format = v => fr(v, 0), area = 0 } = {}) {
  return (W, H) => {
    const pad = { l: 52, r: 16, t: 14, b: 28 };
    const all = series.flatMap(s => s.values);
    const tk = ticks(Math.min(0, ...all), Math.max(...all, 1), 4);
    const min = tk[0], max = tk[tk.length - 1];
    const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
    const x = i => pad.l + (labels.length === 1 ? iw / 2 : (i / (labels.length - 1)) * iw);
    const y = v => pad.t + ih - ((v - min) / (max - min || 1)) * ih;
    const grid = tk.map(v => `<line x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}" class="gl"/>
      <text x="${pad.l - 8}" y="${y(v) + 4}" class="tk" text-anchor="end">${compact(v)}</text>`).join("");
    const xt = labels.map((l, i) => `<text x="${x(i)}" y="${H - 8}" class="tk" text-anchor="middle">${esc(l)}</text>`).join("");
    const paths = series.map((s, k) => {
      const d = s.values.map((v, i) => `${i ? "L" : "M"}${x(i)} ${y(v)}`).join("");
      const fill = k === area ? `<path d="${d}L${x(s.values.length - 1)} ${y(Math.max(min, 0))}L${x(0)} ${y(Math.max(min, 0))}Z" class="area c${k + 1}"/>` : "";
      const dots = s.values.map((v, i) => `<circle cx="${x(i)}" cy="${y(v)}" r="4" class="dot c${k + 1}" data-g="${i}"/>`).join("");
      return `${fill}<path d="${d}" class="ln c${k + 1}"/>${dots}`;
    }).join("");
    const step = labels.length > 1 ? iw / (labels.length - 1) : iw;
    const hits = labels.map((l, i) => `<rect x="${x(i) - step / 2}" y="${pad.t}" width="${step}" height="${ih}" class="hit" data-k="${i}"
      data-tip="${esc(`<b>${esc(l)}</b>${series.map((s, k) => `<span><i class="sw c${k + 1}"></i>${esc(s.name)} ${format(s.values[i])}</span>`).join("")}`)}"/>
      <line x1="${x(i)}" x2="${x(i)}" y1="${pad.t}" y2="${pad.t + ih}" class="cross" data-g="${i}"/>`).join("");
    return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" class="chart" role="img">${grid}
      <line x1="${pad.l}" x2="${W - pad.r}" y1="${y(Math.max(min, 0))}" y2="${y(Math.max(min, 0))}" class="axis"/>${hits}${paths}${xt}</svg>`;
  };
}

export const legend = series => `<ul class="legend">${series.map((s, k) =>
  `<li><i class="sw c${k + 1}${s.dash ? " dash" : ""}"></i>${esc(s.name)}</li>`).join("")}</ul>`;
export { NS };
