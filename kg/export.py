"""Complete graph.json after every change — no delta mechanism (spec 11).

This file is also the read-only interface for Tool 2 („Kollektivtraum"), so it
carries the full state including quotes and flags; consumers filter.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


def build_graph(store) -> dict:
    positions = store.get_positions()
    nodes: list[dict] = []

    for person in store.list_persons():
        x, y = positions.get(person.id, (None, None))
        nodes.append(
            {
                "id": person.id,
                "type": "person",
                "portrait": _portrait_url(person.portrait_path),
                "created_at": person.started_at,
                "hidden": person.hidden,
                "x": x,
                "y": y,
            }
        )

    for term in store.list_terms():
        x, y = positions.get(term.id, (None, None))
        nodes.append(
            {
                "id": term.id,
                "type": "term",
                "label": term.label,
                "mentions": store.mention_count(term.id),
                "created_at": term.created_at,
                "hidden": term.hidden,
                "x": x,
                "y": y,
            }
        )

    edges = [
        {"id": e.id, "source": e.person_id, "target": e.term_id} for e in store.list_edges()
    ]

    # Welche Begriffe der Traum gerade benutzt (Birk, 2026-08-30): „Der Graph
    # soll die Begriffe hervorheben, die gerade zur Bildgenerierung genutzt
    # werden." Berechnet, NICHT von Tool 2 gemeldet — Tool 1 darf Tool 2 nicht
    # kennen (spec §9, die Kopplung geht nur in eine Richtung: Tool 2 pollt
    # diese Datei). Möglich ist das nur, weil die Auswahl seit 2026-08-30
    # mechanisch aus zwei Zahlen folgt (`kg2.weighting.select_required`):
    # dieselben Eingaben ergeben hier dieselbe Liste wie dort, ohne dass ein
    # Wert hin und her laufen müsste.
    #
    # Der Import steht bewusst hier unten und nicht oben: Er ist die EINZIGE
    # Stelle, an der Tool 1 etwas aus `kg2` liest, und ein Fehlschlag darf den
    # Export nicht kosten — ohne Tool 2 im Pfad bleibt `in_dream` schlicht
    # überall False und die Wand sieht aus wie vorher.
    dream_labels: set[str] = set()
    try:
        from kg2.weighting import build_material, select_required

        material = build_material({"nodes": nodes, "edges": edges})
        dream_labels = {w.label for w in select_required(material)}
    except Exception:  # noqa: BLE001 — die Wand darf daran nicht scheitern
        dream_labels = set()
    for node in nodes:
        if node["type"] == "term":
            node["in_dream"] = node.get("label") in dream_labels

    return {
        "version": 1,
        "generated_at": time.time(),
        "max_terms": int(store.get_setting("max_terms", "1")),
        "nodes": nodes,
        "edges": edges,
        "quotes": _quotes(store),
    }


def _quotes(store) -> list[dict]:
    """At most one quote per person.

    The pipeline never writes more than one these days, but older stores
    (never migrated — deletions are Birk's call, not this code's) can still
    hold several per person. `store.list_quotes()` is ordered by created_at,
    so keeping the first person_id we see keeps the oldest — the deliberate
    compromise for that leftover data.
    """
    seen: set[str] = set()
    quotes = []
    for q in store.list_quotes():
        if q.person_id in seen:
            continue
        seen.add(q.person_id)
        quotes.append({"id": q.id, "person_id": q.person_id, "text": q.text})
    return quotes


def write_graph_json(store, path: Path) -> dict:
    graph = build_graph(store)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return graph


def _portrait_url(portrait_path: str | None) -> str | None:
    if not portrait_path:
        return None
    return f"/media/portraits/{Path(portrait_path).name}"
