// Tafelmasse und Kantenboegen fuer theme-f (Schwarzplan, Entwurf 2026-08-30).
//
// Warum das hier und nicht in projection.js steht: Beides sind reine
// Berechnungen ohne Cytoscape-Bezug, die `toCytoscape()` in graph-model.js
// braucht, BEVOR ein Knoten existiert. Die Tafelgroesse muss vor dem Layout
// feststehen, sonst rechnet fcose mit einer anderen Flaeche als die, die
// spaeter gezeichnet wird.
//
// Der Punkt am Begriff faellt in theme-f weg: ein Begriff IST eine
// beschriftete Flaeche. Der Punkt trug nie Bedeutung (er war Kanten- und
// Label-Anker) und verschwand ohnehin hinter Portraits — genau deshalb stand
// im Bestandscode der Hinweis, dass Punkt UND Schrift die Farbe tragen
// muessen. Mit der Flaeche enden Kanten ausserdem an der Tafelkante statt
// unter der Schrift.

function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name);
  return (value && value.trim()) || fallback;
}


/* --- 1. Textmetrik: die Fläche muss ihre Beschriftung kennen ---------------
   Cytoscape kann einen Knoten NICHT auf seine Labelgröße wachsen lassen
   (kein 'width: label'). Die Box wird darum vorher gemessen und als
   data(boxW/boxH) mitgegeben. Ein 2D-Context ohne DOM, gecacht. */

const _measureCtx = document.createElement('canvas').getContext('2d');
let _measureFont = '';
const _measureCache = new Map();

function measureLabel(text, fontPx, fontFamily, maxWidthPx) {
  const key = `${text}|${fontPx}|${maxWidthPx}`;
  const hit = _measureCache.get(key);
  if (hit) return hit;

  const font = `${fontPx}px ${fontFamily}`;
  if (_measureFont !== font) { _measureCtx.font = font; _measureFont = font; }

  // Dieselbe Umbruchregel wie Cytoscapes text-wrap: wrap.
  const lines = [];
  let cur = '';
  for (const word of String(text).split(/\s+/)) {
    const probe = cur ? `${cur} ${word}` : word;
    if (_measureCtx.measureText(probe).width <= maxWidthPx || !cur) {
      cur = probe;
    } else {
      lines.push(cur);
      cur = word;
    }
  }
  if (cur) lines.push(cur);

  let widest = 0;
  for (const line of lines) {
    widest = Math.max(widest, _measureCtx.measureText(line).width);
  }
  const out = {
    w: Math.ceil(widest),
    h: Math.ceil(lines.length * fontPx * LINE_HEIGHT),
    lines: lines.length,
  };
  _measureCache.set(key, out);
  return out;
}

// Exportiert, weil BEIDE Seiten denselben Wert brauchen: termBox() rechnet die
// Tafelhoehe damit aus, und der Stil in projection.js setzt line-height auf
// denselben Wert. Zwei getrennte Konstanten wuerden die Tafel frueher oder
// spaeter kleiner machen als die Schrift darin.
export const LINE_HEIGHT = 1.12;

/** Box eines Begriffs-Knotens inkl. Tafelrand. An toCytoscape() hängen:
 *  data.boxW / data.boxH je Begriff setzen, wenn das Label feststeht. */
export function termBox(label, schriftPx) {
  const pad = parseFloat(cssVar('--plate-pad', '10'));
  // 🔴 Die Groesse kommt seit dem 2026-09-03 von aussen (Birk: „ändere die
  // hervorhebung von oft genannten begriffen zu größe der schrift"). Ohne das
  // masse die Tafel weiter mit 26 px, waehrend der Text darin groesser steht —
  // und ragte hinaus. Ohne Angabe gilt weiter der Wert aus dem Theme.
  const fs = schriftPx || parseFloat(cssVar('--label-size', '26'));
  const ff = cssVar('--label-font', 'Georgia, serif');
  const maxw = parseFloat(cssVar('--label-max-width', '220px'));
  const m = measureLabel(label, fs, ff, maxw);
  return { w: m.w + 2 * pad, h: m.h + 2 * pad };
}

/* --- 2. Kantenkrümmung: deterministisch aus der Kanten-ID ------------------
   Jede Kante bekommt ihren eigenen, aber ÜBER DIE ZEIT KONSTANTEN Bogen.
   Zufall pro Frame würde bei jedem Re-Layout zappeln; ein Hash der ID ist
   stabil über die ganzen acht Stunden. Zwei Kontrollpunkte mit
   gegenläufigem Vorzeichen ergeben die flache S-Kurve statt eines Bogens. */

function hash32(str) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h >>> 0;
}

/** {cpd, cpw} für eine Kante. An toCytoscape() hängen: als data mitgeben. */
export function edgeCurve(edgeId) {
  const h = hash32(edgeId);
  const sign = (h & 1) ? 1 : -1;
  const amp1 = 18 + ((h >>> 1) % 22);   // 18..39 model units
  const amp2 = 10 + ((h >>> 6) % 16);   // 10..25, Gegenschwung
  return {
    cpd: `${sign * amp1} ${-sign * amp2}`,
    cpw: '0.35 0.72',
  };
}

