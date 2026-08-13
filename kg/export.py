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

    return {
        "version": 1,
        "generated_at": time.time(),
        "min_mentions": int(store.get_setting("min_mentions", "1")),
        "nodes": nodes,
        "edges": [
            {"id": e.id, "source": e.person_id, "target": e.term_id} for e in store.list_edges()
        ],
        "quotes": [
            {"id": q.id, "person_id": q.person_id, "text": q.text} for q in store.list_quotes()
        ],
    }


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
