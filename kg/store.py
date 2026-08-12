"""The only module that reads from or writes to SQLite."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from kg.db import connect
from kg.models import Edge, Person, Quote, Term

_PREFIXES = {"person": "p", "term": "t", "edge": "e", "quote": "q", "merge": "m"}


class Store:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    @classmethod
    def open(cls, path: Path) -> "Store":
        return cls(connect(Path(path)))

    def close(self) -> None:
        self.conn.close()

    # -- ids ---------------------------------------------------------------

    def _next_id(self, kind: str) -> str:
        # No RETURNING clause: the target SQLite (3.34) predates 3.35's support
        # for it. Single-writer process, so the upsert-then-read is not racy.
        self.conn.execute(
            "INSERT INTO counters(name, value) VALUES (?, 1) "
            "ON CONFLICT(name) DO UPDATE SET value = value + 1",
            (kind,),
        )
        row = self.conn.execute("SELECT value FROM counters WHERE name=?", (kind,)).fetchone()
        return f"{_PREFIXES[kind]}{row['value']}"

    # -- person ------------------------------------------------------------

    def create_person(
        self,
        started_at: float,
        photo_path: str | None = None,
        portrait_path: str | None = None,
    ) -> Person:
        person_id = self._next_id("person")
        self.conn.execute(
            "INSERT INTO person(id, started_at, photo_path, portrait_path) VALUES (?,?,?,?)",
            (person_id, started_at, photo_path, portrait_path),
        )
        self.conn.commit()
        return self.get_person(person_id)

    def close_person(self, person_id: str, stopped_at: float, reason: str) -> None:
        self.conn.execute(
            "UPDATE person SET stopped_at=?, stop_reason=?, status='closed' WHERE id=?",
            (stopped_at, reason, person_id),
        )
        self.conn.commit()

    def set_person_transcript(self, person_id: str, text: str) -> None:
        self.conn.execute("UPDATE person SET transcript=? WHERE id=?", (text, person_id))
        self.conn.commit()

    def set_person_status(self, person_id: str, status: str) -> None:
        self.conn.execute("UPDATE person SET status=? WHERE id=?", (status, person_id))
        self.conn.commit()

    def set_person_portrait(self, person_id: str, photo_path: str, portrait_path: str) -> None:
        self.conn.execute(
            "UPDATE person SET photo_path=?, portrait_path=? WHERE id=?",
            (photo_path, portrait_path, person_id),
        )
        self.conn.commit()

    def get_person(self, person_id: str) -> Person | None:
        row = self.conn.execute("SELECT * FROM person WHERE id=?", (person_id,)).fetchone()
        return _person(row) if row else None

    def open_person(self) -> Person | None:
        row = self.conn.execute(
            "SELECT * FROM person WHERE stopped_at IS NULL ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return _person(row) if row else None

    def list_persons(self) -> list[Person]:
        rows = self.conn.execute("SELECT * FROM person ORDER BY started_at").fetchall()
        return [_person(r) for r in rows]

    # -- term --------------------------------------------------------------

    def get_or_create_term(self, label: str, created_at: float) -> Term:
        existing = self.get_term_by_label(label)
        if existing:
            return existing
        term_id = self._next_id("term")
        self.conn.execute(
            "INSERT INTO term(id, label, created_at) VALUES (?,?,?)",
            (term_id, label, created_at),
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO term_alias(surface, term_id) VALUES (?,?)",
            (label, term_id),
        )
        self.conn.commit()
        return self.get_term(term_id)

    def get_term(self, term_id: str) -> Term | None:
        row = self.conn.execute("SELECT * FROM term WHERE id=?", (term_id,)).fetchone()
        return _term(row) if row else None

    def get_term_by_label(self, label: str) -> Term | None:
        row = self.conn.execute("SELECT * FROM term WHERE label=?", (label,)).fetchone()
        return _term(row) if row else None

    def rename_term(self, term_id: str, new_label: str) -> None:
        old = self.get_term(term_id)
        if old is None or old.label == new_label:
            return
        self.conn.execute("UPDATE term SET label=? WHERE id=?", (new_label, term_id))
        # Keep the old label reachable: a decision once made is never re-derived.
        for surface in (old.label, new_label):
            self.conn.execute(
                "INSERT OR REPLACE INTO term_alias(surface, term_id) VALUES (?,?)",
                (surface, term_id),
            )
        self.conn.commit()

    def add_alias(self, term_id: str, surface: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO term_alias(surface, term_id) VALUES (?,?)",
            (surface, term_id),
        )
        self.conn.commit()

    def find_term_by_alias(self, surface: str) -> Term | None:
        row = self.conn.execute(
            "SELECT t.* FROM term_alias a JOIN term t ON t.id = a.term_id WHERE a.surface=?",
            (surface,),
        ).fetchone()
        return _term(row) if row else None

    def list_terms(self) -> list[Term]:
        rows = self.conn.execute("SELECT * FROM term ORDER BY created_at, id").fetchall()
        return [_term(r) for r in rows]

    # -- edges / quotes ----------------------------------------------------

    def add_edge(self, person_id: str, term_id: str, created_at: float) -> Edge:
        row = self.conn.execute(
            "SELECT * FROM edge WHERE person_id=? AND term_id=?", (person_id, term_id)
        ).fetchone()
        if row:
            return _edge(row)
        edge_id = self._next_id("edge")
        self.conn.execute(
            "INSERT INTO edge(id, person_id, term_id, created_at) VALUES (?,?,?,?)",
            (edge_id, person_id, term_id, created_at),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM edge WHERE id=?", (edge_id,)).fetchone()
        return _edge(row)

    def list_edges(self) -> list[Edge]:
        rows = self.conn.execute("SELECT * FROM edge ORDER BY created_at, id").fetchall()
        return [_edge(r) for r in rows]

    def mention_count(self, term_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(DISTINCT person_id) AS n FROM edge WHERE term_id=?", (term_id,)
        ).fetchone()
        return int(row["n"])

    def add_quote(self, person_id: str, text: str, created_at: float) -> Quote:
        quote_id = self._next_id("quote")
        self.conn.execute(
            "INSERT INTO quote(id, person_id, text, created_at) VALUES (?,?,?,?)",
            (quote_id, person_id, text, created_at),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM quote WHERE id=?", (quote_id,)).fetchone()
        return Quote(row["id"], row["person_id"], row["text"], row["created_at"])

    def list_quotes(self) -> list[Quote]:
        rows = self.conn.execute("SELECT * FROM quote ORDER BY created_at, id").fetchall()
        return [Quote(r["id"], r["person_id"], r["text"], r["created_at"]) for r in rows]

    # -- flags, positions, decisions, settings ------------------------------

    def set_hidden(self, node_id: str, hidden: bool) -> None:
        kind, _, ident = node_id.partition(":")
        if kind not in ("person", "term") or not ident:
            raise ValueError(f"unknown node id: {node_id!r}")
        self.conn.execute(f"UPDATE {kind} SET hidden=? WHERE id=?", (1 if hidden else 0, ident))
        self.conn.commit()

    def save_positions(self, positions: dict[str, tuple[float, float]]) -> None:
        self.conn.executemany(
            "INSERT INTO position(node_id, x, y) VALUES (?,?,?) "
            "ON CONFLICT(node_id) DO UPDATE SET x=excluded.x, y=excluded.y",
            [(node_id, float(x), float(y)) for node_id, (x, y) in positions.items()],
        )
        self.conn.commit()

    def get_positions(self) -> dict[str, tuple[float, float]]:
        rows = self.conn.execute("SELECT node_id, x, y FROM position").fetchall()
        return {r["node_id"]: (r["x"], r["y"]) for r in rows}

    def record_merge_decision(self, person_id: str, payload: dict, created_at: float) -> None:
        self.conn.execute(
            "INSERT INTO merge_decision(id, person_id, payload, created_at) VALUES (?,?,?,?)",
            (self._next_id("merge"), person_id, json.dumps(payload, ensure_ascii=False), created_at),
        )
        self.conn.commit()

    def list_merge_decisions(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM merge_decision ORDER BY created_at, id"
        ).fetchall()
        return [
            {
                "id": r["id"],
                "person_id": r["person_id"],
                "payload": json.loads(r["payload"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def get_setting(self, key: str, default: str) -> str:
        row = self.conn.execute("SELECT value FROM setting WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO setting(key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        self.conn.commit()

    def set_setting_default(self, key: str, value: str) -> None:
        """Seed a setting only if it has never been set.

        Startup uses this to apply the calibrated `default_min_mentions` without
        overwriting a dial the operator turned before the crash (spec 7, 10.5).
        """
        self.conn.execute(
            "INSERT OR IGNORE INTO setting(key, value) VALUES (?,?)", (key, str(value))
        )
        self.conn.commit()


def _person(row: sqlite3.Row) -> Person:
    return Person(
        id=row["id"],
        started_at=row["started_at"],
        stopped_at=row["stopped_at"],
        stop_reason=row["stop_reason"],
        status=row["status"],
        transcript=row["transcript"],
        photo_path=row["photo_path"],
        portrait_path=row["portrait_path"],
        hidden=bool(row["hidden"]),
    )


def _term(row: sqlite3.Row) -> Term:
    return Term(
        id=row["id"], label=row["label"], created_at=row["created_at"], hidden=bool(row["hidden"])
    )


def _edge(row: sqlite3.Row) -> Edge:
    return Edge(
        id=row["id"],
        person_id=row["person_id"],
        term_id=row["term_id"],
        created_at=row["created_at"],
    )
