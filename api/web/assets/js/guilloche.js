/* Guilloché : les motifs de sécurité des certificats et des polices d'assurance, générés en SVG.
   Une couronne = plusieurs lignes ondulées entrelacées autour d'un cercle ; une rosace = une courbe
   de spirographe (hypotrochoïde). Aucune image : tout est calculé, net à toutes les tailles. */

const TAU = Math.PI * 2;
const f = x => Math.round(x * 10) / 10;

function pathOf(points) {
  let d = `M${f(points[0][0])} ${f(points[0][1])}`;
  for (let i = 1; i < points.length; i++) d += `L${f(points[i][0])} ${f(points[i][1])}`;
  return d + "Z";
}

/** Couronne : `lines` ondes de `waves` crêtes, décalées entre elles, entre R-amp et R+amp. */
export function ring({ cx = 0, cy = 0, R = 100, amp = 10, waves = 24, lines = 8, beat = 3, steps = 900 } = {}) {
  const out = [];
  for (let j = 0; j < lines; j++) {
    const ph = (j / lines) * TAU / waves;
    const pts = [];
    for (let s = 0; s <= steps; s++) {
      const t = (s / steps) * TAU;
      const r = R + amp * Math.sin(waves * t + ph * waves) * (0.9 + 0.1 * Math.cos(beat * t));
      pts.push([cx + r * Math.cos(t), cy + r * Math.sin(t)]);
    }
    out.push(pathOf(pts));
  }
  return out;
}

/** Rosace : hypotrochoïde fermée (R et r entiers), répétée avec une légère rotation. */
export function rosette({ cx = 0, cy = 0, R = 90, r = 33, d = 60, copies = 3, scale = 1, steps = 1600 } = {}) {
  const g = (a, b) => (b ? g(b, a % b) : a);
  const turns = r / g(R, r);
  const out = [];
  for (let c = 0; c < copies; c++) {
    const rot = (c / copies) * TAU / (R / g(R, r));
    const k = scale * (1 - c * 0.06);
    const pts = [];
    for (let s = 0; s <= steps; s++) {
      const t = (s / steps) * TAU * turns;
      const x = (R - r) * Math.cos(t) + d * Math.cos(((R - r) / r) * t);
      const y = (R - r) * Math.sin(t) - d * Math.sin(((R - r) / r) * t);
      pts.push([cx + k * (x * Math.cos(rot) - y * Math.sin(rot)), cy + k * (x * Math.sin(rot) + y * Math.cos(rot))]);
    }
    out.push(pathOf(pts));
  }
  return out;
}

/** Remplit un <svg> avec un médaillon complet (rosace + couronnes). `draw` anime le tracé. */
export function medallion(svg, { size = 600, draw = false, density = 1 } = {}) {
  const c = size / 2;
  const s = size / 600;
  const layers = [
    { cls: "g-outer", paths: ring({ cx: c, cy: c, R: 268 * s, amp: 16 * s, waves: 48, lines: Math.max(3, Math.round(6 * density)), beat: 6 }) },
    { cls: "g-mid", paths: ring({ cx: c, cy: c, R: 210 * s, amp: 26 * s, waves: 30, lines: Math.max(3, Math.round(7 * density)), beat: 5 }) },
    { cls: "g-inner", paths: ring({ cx: c, cy: c, R: 156 * s, amp: 13 * s, waves: 36, lines: Math.max(3, Math.round(5 * density)), beat: 4 }) },
    { cls: "g-rose", paths: [...rosette({ cx: c, cy: c, R: 144, r: 54, d: 74, copies: 5, scale: s * 1.1 }),
                             ...rosette({ cx: c, cy: c, R: 120, r: 45, d: 30, copies: 3, scale: s * 0.9 })] },
  ];
  svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
  svg.innerHTML = layers.map((l, li) => `<g class="${l.cls}">${l.paths.map((d, i) =>
    `<path d="${d}" pathLength="1" style="--i:${i};--l:${li}"/>`).join("")}</g>`).join("");
  if (draw) svg.classList.add("drawing");
  return svg;
}

/** Bande horizontale de guilloché (bordure de certificat). */
export function band(svg, { width = 1200, height = 60, waves = 40, lines = 7 } = {}) {
  const out = [];
  const steps = 1400;
  for (let j = 0; j < lines; j++) {
    const ph = (j / lines) * TAU;
    const pts = [];
    for (let s = 0; s <= steps; s++) {
      const x = (s / steps) * width;
      const t = (s / steps) * TAU * waves;
      const y = height / 2 + (height * 0.36) * Math.sin(t + ph / 3) * Math.cos((s / steps) * TAU * 3 + ph / 8);
      pts.push([x, y]);
    }
    out.push(pts.map((p, i) => `${i ? "L" : "M"}${f(p[0])} ${f(p[1])}`).join(""));
  }
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("preserveAspectRatio", "none");
  svg.innerHTML = out.map(d => `<path d="${d}"/>`).join("");
  return svg;
}
