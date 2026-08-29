"""How many term labels stay legible on the wall — measured, not guessed.

Written 2026-08-29 for the Tool 1 display-dial rebuild: the dial being
replaced is `min_mentions` ("show terms said by at least N people"), an
indirect proxy for the real constraint. The real constraint is how many
labels fit on a 1920x1080 projection before they collide or shrink below
reading size — which is what `max_terms`, the cap this probe's numbers argue
for, targets directly.

Reuses `sim.prerender`'s own server + projection helpers so this measures the
REAL frontend, not a mock. No LLM, no image generation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kg.export import write_graph_json  # noqa: E402
from sim.prerender import _launch_chromium, _open_projection, _served  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

CAPS = (20, 26, 32, 40, 49, 60)


def _apply_cap(store, cap: int) -> None:
    """Hide all but the `cap` strongest terms — the rule the new dial would use.

    Strongest = most mentions, ties broken by newest first (the recency axis
    Tool 2 already uses). Hiding, not deleting: the wall is a display filter,
    the data stays.
    """
    counts = {}
    for edge in store.list_edges():
        counts[edge.term_id] = counts.get(edge.term_id, 0) + 1
    terms = list(store.list_terms())
    ranked = sorted(
        terms, key=lambda t: (-counts.get(t.id, 0), -t.created_at, t.label)
    )
    keep = {t.id for t in ranked[:cap]}
    for t in terms:
        want_hidden = t.id not in keep
        if t.hidden != want_hidden:
            store.set_hidden(f"term:{t.id}", want_hidden)

MEASURE_JS = """
() => {
  const view = window.kgView;
  const cy = view.cy;
  const terms = cy.nodes('.term');
  const boxes = terms.map(n => n.boundingBox({ includeLabels: true, includeNodes: false }));
  const fonts = terms.map(n => parseFloat(n.renderedStyle('font-size'))).sort((a, b) => a - b);
  const zoom = cy.zoom();
  const area = boxes.reduce((s, b) => s + (b.w * b.h), 0) * zoom * zoom;
  const ov = (a, b) => a.x1 < b.x2 && a.x2 > b.x1 && a.y1 < b.y2 && a.y2 > b.y1;
  let labelPairs = 0;
  for (let i = 0; i < boxes.length; i++)
    for (let j = i + 1; j < boxes.length; j++)
      if (ov(boxes[i], boxes[j])) labelPairs++;
  const pboxes = cy.nodes('.person').map(n => n.boundingBox({ includeNodes: true, includeLabels: false }));
  let onPersons = 0;
  boxes.forEach(b => pboxes.forEach(pb => { if (ov(b, pb)) onPersons++; }));
  const stats = { labelPairs, labelsOnPersons: onPersons, personPairs: 0 };
  return {
    terms: terms.length,
    persons: cy.nodes('.person').length,
    font_rendered: fonts.length ? +(fonts[Math.floor(fonts.length / 2)] * zoom).toFixed(1) : null,
    zoom: +zoom.toFixed(3),
    label_pairs: stats.labelPairs,
    labels_on_persons: stats.labelsOnPersons,
    person_pairs: stats.personPairs,
    area_pct: +(100 * area / (window.innerWidth * window.innerHeight)).toFixed(1),
  };
}
"""


def _settle(page) -> None:
    """Wait for the wall's OWN done-signal, never a fixed sleep.

    The first version of this probe waited 4000 ms after each push. That is
    long enough most of the time and not long enough some of the time: an
    fcose relayout plus the camera glide was measured at up to ~3000 ms, and a
    reading taken mid-animation reports the PREVIOUS frame's zoom. That is how
    the spec ended up claiming that fewer terms produce smaller type — a
    frozen camera view from the previous step, not a real measurement.

    `layoutPending === false` is the wall's own statement that it has settled.
    """
    page.wait_for_function(
        "() => window.kgView && window.kgView.layoutPending === false", timeout=60000
    )
    # The flag drops when the layout is done; the glide runs after it. One
    # short settle covers the animation without going back to guessing.
    page.wait_for_timeout(1500)


def main() -> None:
    from playwright.sync_api import sync_playwright

    db = REPO / "out" / "sim19c" / "sim.db"
    if not db.exists():
        print(f"FEHLT: {db}", file=sys.stderr)
        raise SystemExit(1)

    rows = []
    # A scratch copy, not the fixture in place: this probe hides terms by
    # writing `hidden` flags straight into the database, and a bare
    # `_served(db)` would leave that mutation behind in `out/sim19c/sim.db`
    # for the next thing that reads it. Found the hard way (2026-08-29): two
    # probe runs over the same un-copied file produced an impossible-looking
    # "identical zoom at two different term counts" result that was actually
    # the second run reading the first run's leftover state.
    with _served(db, scratch=REPO / "out" / "_wall_legibility_scratch") as served:
        with sync_playwright() as p:
            browser = _launch_chromium(p)
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            _open_projection(page, served.base_url, "dark")
            _settle(page)

            for cap in CAPS:
                with served.store.transaction():
                    # A large cap, never a small threshold: the exported
                    # graph's own `max_terms` field is what the client applies
                    # on every plain graph push (no explicit dial value here),
                    # so it must not fight the `hidden`-flag capping below.
                    served.store.set_setting("max_terms", "999")
                    _apply_cap(served.store, cap)
                served.publish(
                    {
                        "type": "graph",
                        "graph": write_graph_json(
                            served.store, served.cfg.graph_json_path
                        ),
                    }
                )
                _settle(page)
                r = page.evaluate(MEASURE_JS)
                r["cap"] = cap
                rows.append(r)
                print(json.dumps(r, ensure_ascii=False), flush=True)
            browser.close()

    print("\n=== 60 Personen, 1920x1080, echtes Frontend ===")
    hdr = f"{'cap':>5} {'Begriffe':>9} {'Font px':>8} {'Label-Kollis':>13} {'auf Person':>11} {'Flaeche%':>9}"
    print(hdr)
    for r in rows:
        print(
            f"{r['cap']:>5} {r['terms']:>9} {str(r['font_rendered']):>8} "
            f"{r['label_pairs']:>13} {r['labels_on_persons']:>11} {r['area_pct']:>9}"
        )


if __name__ == "__main__":
    main()
