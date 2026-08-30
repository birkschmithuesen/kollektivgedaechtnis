"""Eine Seite zum Durchklicken: Material, Satz, Bild und Graph je Zeitpunkt.

Birks Wunsch, 2026-08-30: „Ich will mir das Ganze direkt im Webbrowser
angucken, zusammen mit dem Graphen und dann auch mit dem Bild, und die
einzelnen Phasen nacheinander durchklicken."

Warum eine EIGENE Seite und nicht `/dream`: Screen B zeigt, was die Besucherin
sieht — ein Bild, ein Satz, sonst nichts. Diese Seite zeigt das Gegenteil,
nämlich alles, woraus das entstanden ist: die Begriffe mit ihren Nennungen, die
Bildbeschreibung, den benannten Widerspruch, mood und tension, den gesendeten
Prompt, und den Graphen zu genau diesem Zeitpunkt. Beides in eine Oberfläche zu
pressen würde die eine oder die andere verderben.

Sie erzeugt NICHTS. Sie liest, was `sim/probes/tagesverlauf.py` erzeugt hat
(Bild + `.md` je Zeitpunkt) und legt den Graphen daneben, den dieselbe
Personenzahl ergibt. Alles Teure ist damit schon bezahlt, und die Seite lässt
sich beliebig oft neu laden.

    uv run python sim/probes/durchklick.py out/<ordner> [--port 8899]

Dann http://127.0.0.1:8899 öffnen. Mit den Pfeiltasten oder den Knöpfen durch
die Zeitpunkte.
"""

from __future__ import annotations

import argparse
import http.server
import json
import re
import socketserver
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kg2.weighting import build_material  # noqa: E402
from sim.dream_calibrate import FIXTURE, prefix_graph  # noqa: E402

_FELD = {
    "satz": r"> \*\*(.*?)\*\*",
    "motiv": r"\*\*Motiv\*\* \(variabel\) \| (.*?) \|\n",
    "uebersetzung": r"\*\*Wörtliche Übersetzung\*\* \(nur Archiv\) \| (.*?) \|\n",
    "stimmung": r"\*\*Stimmung\*\* \(mood = \d\) \| (.*?) \|\n",
    "spannung": r"\*\*Spannung\*\* \(tension = \d\) \| (.*?) \|\n",
    "widerspruch": r"\*\*Widerspruch im Material\*\* \| (.*?) \|\n",
    "register": r"\*\*Register\*\*[^|]*\| (.*?) \|\n",
    "prompt": r"```\n(.*?)\n```\n</details>",
}


def _lies(md: Path) -> dict:
    text = md.read_text(encoding="utf-8")
    daten = {}
    for name, muster in _FELD.items():
        treffer = re.search(muster, text, re.DOTALL)
        daten[name] = treffer.group(1) if treffer else ""
    for name, muster in (("mood", r"mood = (\d)"), ("tension", r"tension = (\d)")):
        treffer = re.search(muster, text)
        daten[name] = int(treffer.group(1)) if treffer else 3
    treffer = re.search(r"# Traum \d+ — (.*)", text)
    daten["tageszeit"] = treffer.group(1) if treffer else ""
    return daten


def sammle(ordner: Path, graph_datei: Path) -> list[dict]:
    graph = json.loads(graph_datei.read_text(encoding="utf-8"))
    phasen = []
    for md in sorted(ordner.glob("*.md")):
        if md.name.startswith("_"):
            continue
        bild = next(
            (p for p in (md.with_suffix(".png"), md.with_suffix(".jpg")) if p.exists()),
            None,
        )
        if bild is None:
            continue
        treffer = re.search(r"(\d+)personen", md.stem)
        if not treffer:
            continue
        personen = int(treffer.group(1))

        material = build_material(prefix_graph(graph, personen))
        phasen.append(
            _lies(md)
            | {
                "bild": bild.name,
                "personen": personen,
                "begriffe": material.term_count,
                "geteilt": [
                    {"label": w.label, "mentions": w.mentions} for w in material.shared
                ],
                "einmal": [w.label for w in material.marginal],
            }
        )
    phasen.sort(key=lambda p: p["personen"])
    return phasen


_SEITE = """<!doctype html>
<meta charset="utf-8">
<title>Durchklick — {ordner}</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:#0d0d0f; color:#e8e8ea;
         font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
  header {{ position:sticky; top:0; z-index:9; background:#141418;
            border-bottom:1px solid #2a2a30; padding:.7rem 1.2rem;
            display:flex; align-items:center; gap:1rem; flex-wrap:wrap; }}
  header h1 {{ font-size:14px; font-weight:600; margin:0; color:#8a8a95; }}
  .tabs {{ display:flex; gap:.4rem; }}
  .tab {{ padding:.35rem .8rem; border:1px solid #2a2a30; border-radius:5px;
          background:#1a1a20; cursor:pointer; font-size:13px; }}
  .tab.on {{ background:#3a5f8a; border-color:#4a7fba; color:#fff; }}
  .hint {{ color:#5a5a65; font-size:12px; margin-left:auto; }}
  main {{ display:grid; grid-template-columns: 1.35fr 1fr; gap:1.2rem;
          padding:1.2rem; align-items:start; }}
  @media (max-width:1100px) {{ main {{ grid-template-columns:1fr; }} }}
  img.bild {{ width:100%; border-radius:6px; display:block; background:#000; }}
  .satz {{ font-size:1.45rem; line-height:1.35; margin:1rem 0 .3rem;
           font-weight:500; }}
  .meta {{ color:#7a7a85; font-size:12.5px; }}
  section {{ background:#141418; border:1px solid #24242a; border-radius:7px;
             padding:.85rem 1rem; margin-bottom:.9rem; }}
  section h2 {{ font-size:11px; text-transform:uppercase; letter-spacing:.07em;
                color:#6a6a75; margin:0 0 .5rem; font-weight:600; }}
  .werte {{ display:flex; gap:1.6rem; }}
  .wert b {{ font-size:1.6rem; font-weight:600; }}
  .skala {{ display:inline-block; width:6px; height:6px; border-radius:50%;
            background:#2e2e36; margin-right:2px; }}
  .skala.an {{ background:#4a7fba; }}
  .begriffe {{ max-height:15rem; overflow:auto; }}
  .b {{ display:flex; justify-content:space-between; padding:.12rem 0;
        border-bottom:1px solid #1e1e24; }}
  .b span:first-child {{ color:#c8c8d0; }}
  .b span:last-child {{ color:#5a5a65; font-variant-numeric:tabular-nums; }}
  .b.neu span:first-child {{ color:#7fc98a; }}
  .b.neu span:last-child::after {{ content:" neu"; color:#7fc98a; }}
  .rand {{ color:#5a5a65; font-size:12px; line-height:1.7; }}
  pre {{ white-space:pre-wrap; font-size:11.5px; color:#8a8a95;
         background:#0b0b0d; padding:.7rem; border-radius:5px; margin:0;
         max-height:20rem; overflow:auto; }}
  details summary {{ cursor:pointer; color:#6a6a75; font-size:12px; }}
</style>
<header>
  <h1>{ordner}</h1>
  <div class="tabs" id="tabs"></div>
  <span class="hint">← → blättern</span>
</header>
<main>
  <div>
    <img class="bild" id="bild">
    <div class="satz" id="satz"></div>
    <div class="meta" id="meta"></div>
    <section style="margin-top:1rem">
      <h2>Bildbeschreibung — das Motiv, das Stufe 2 bekommen hat</h2>
      <div id="motiv" style="color:#c8c8d0"></div>
    </section>
    <section>
      <h2>Benannter Widerspruch</h2>
      <div id="widerspruch" style="color:#c8c8d0"></div>
    </section>
    <details><summary>Vollständiger Bildprompt, wie gesendet</summary>
      <pre id="prompt" style="margin-top:.6rem"></pre></details>
  </div>
  <div>
    <section>
      <h2>Werte, vom Modell aus dem Material abgeleitet</h2>
      <div class="werte">
        <div class="wert">mood <b id="moodz"></b> <div id="moodp"></div>
          <div class="rand" id="moodt"></div></div>
        <div class="wert">tension <b id="tenz"></b> <div id="tenp"></div>
          <div class="rand" id="tent"></div></div>
      </div>
    </section>
    <section>
      <h2>Das Material zu diesem Zeitpunkt — geteilte Begriffe</h2>
      <div class="begriffe" id="geteilt"></div>
    </section>
    <section>
      <h2>Einmal genannt — Detail, nie Thema</h2>
      <div class="rand" id="einmal"></div>
    </section>
  </div>
</main>
<script>
const P = {daten};
let i = 0;
const tabs = document.getElementById('tabs');
P.forEach((p, n) => {{
  const b = document.createElement('button');
  b.className = 'tab'; b.textContent = p.personen + ' Personen';
  b.onclick = () => zeige(n); tabs.appendChild(b);
}});
function punkte(wert) {{
  let s = '';
  for (let k = 1; k <= 5; k++) s += `<span class="skala ${{k <= wert ? 'an' : ''}}"></span>`;
  return s;
}}
function zeige(n) {{
  i = n; const p = P[n];
  document.querySelectorAll('.tab').forEach((t, k) =>
    t.classList.toggle('on', k === n));
  document.getElementById('bild').src = p.bild;
  document.getElementById('satz').textContent = p.satz;
  document.getElementById('meta').textContent =
    `${{p.tageszeit}} · ${{p.personen}} Personen · ${{p.begriffe}} Begriffe`;
  document.getElementById('motiv').textContent = p.motiv;
  document.getElementById('widerspruch').textContent = p.widerspruch || '—';
  document.getElementById('prompt').textContent = p.prompt;
  document.getElementById('moodz').textContent = p.mood;
  document.getElementById('tenz').textContent = p.tension;
  document.getElementById('moodp').innerHTML = punkte(p.mood);
  document.getElementById('tenp').innerHTML = punkte(p.tension);
  document.getElementById('moodt').textContent = p.stimmung;
  document.getElementById('tent').textContent = p.spannung;
  // Was ist neu gegenüber dem vorigen Zeitpunkt? Das ist die Frage, an der
  // sich zeigt, ob die Station auf die letzten Interviews reagiert hat.
  const vorher = n > 0 ? new Set(P[n-1].geteilt.map(b => b.label)) : new Set();
  document.getElementById('geteilt').innerHTML = p.geteilt.map(b =>
    `<div class="b ${{n > 0 && !vorher.has(b.label) ? 'neu' : ''}}">
       <span>${{b.label}}</span><span>${{b.mentions}}×</span></div>`).join('')
    || '<div class="rand">noch keiner von zwei Menschen genannt</div>';
  document.getElementById('einmal').textContent = p.einmal.join(' · ') || '—';
}}
addEventListener('keydown', e => {{
  if (e.key === 'ArrowRight' && i < P.length - 1) zeige(i + 1);
  if (e.key === 'ArrowLeft' && i > 0) zeige(i - 1);
}});
zeige(0);
</script>
"""


def main() -> None:
    parser = argparse.ArgumentParser(prog="durchklick")
    parser.add_argument("ordner")
    parser.add_argument("--port", type=int, default=8899)
    parser.add_argument(
        "--graph",
        default=str(FIXTURE),
        help="Graph, aus dem das Material je Zeitpunkt gebildet wird.",
    )
    args = parser.parse_args()

    ordner = Path(args.ordner)
    phasen = sammle(ordner, Path(args.graph))
    if not phasen:
        print(f"keine Bild+md-Paare in {ordner}", file=sys.stderr)
        raise SystemExit(1)

    seite = _SEITE.format(
        ordner=ordner.name, daten=json.dumps(phasen, ensure_ascii=False)
    )
    (ordner / "_durchklick.html").write_text(seite, encoding="utf-8")

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(ordner), **kw)

        def do_GET(self):  # noqa: N802
            if self.path in ("/", "/index.html"):
                self.path = "/_durchklick.html"
            return super().do_GET()

        def log_message(self, format, *args):  # noqa: A002 — Ruhe im Terminal
            pass

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", args.port), Handler) as httpd:
        print(f"{len(phasen)} Zeitpunkte aus {ordner}")
        print(f"http://127.0.0.1:{args.port}   (Strg-C beendet)")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
