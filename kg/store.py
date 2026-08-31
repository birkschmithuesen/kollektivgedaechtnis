"""The only module that reads from or writes to SQLite."""

from __future__ import annotations

import contextlib
import functools
import json
import sqlite3
import threading
from pathlib import Path

from kg.db import connect
from kg.models import Edge, Person, Quote, Term

_PREFIXES = {"person": "p", "term": "t", "edge": "e", "quote": "q", "merge": "m"}


def _locked(method):
    """Serialise one public `Store` method call through the store-wide lock.

    See the rationale on `Store._lock` in `__init__`. Plain wrapper (not
    itself a `@contextlib.contextmanager`-style method) so it is safe to
    stack on `transaction()`-adjacent methods too: it just acquires
    `self._lock`, runs the wrapped call, and releases it — re-entrant on the
    same thread because `self._lock` is an `RLock`.
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class Store:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        # kg.db.connect opens the connection with check_same_thread=False so
        # a single connection (and this Store) can be shared across threads:
        # FastAPI runs sync route handlers in a threadpool (kg/server.py),
        # and the Core loop and the per-interview pipeline write through the
        # same Store instance from their own threads. Python's sqlite3
        # module does not serialise statements against a shared connection
        # by itself — two threads issuing statements at once can interleave
        # mid-transaction (each sees "no transaction active" and both issue
        # BEGIN, the second raising "cannot start a transaction within a
        # transaction"), or interleave between an UPSERT and the following
        # SELECT in `_next_id` and read the same counter value, minting a
        # duplicate id.
        #
        # This RLock serialises every public method below (via the
        # `@_locked` decorator) — reads included, since a read racing a
        # write on one shared connection is exactly as unsafe as two writes
        # racing. It must be re-entrant, not a plain Lock: `_next_id` is
        # called from inside other locked methods (create_person,
        # get_or_create_term, add_edge, add_quote, record_merge_decision),
        # and `transaction()` below holds this same lock for an entire
        # multi-call block while calling other `@_locked` public methods
        # within that block. A plain Lock would deadlock the instant any of
        # that happened on the thread already holding it.
        self._lock = threading.RLock()
        self._tx_depth = 0

    @classmethod
    def open(cls, path: Path) -> "Store":
        return cls(connect(Path(path)))

    @_locked
    def close(self) -> None:
        self.conn.close()

    @contextlib.contextmanager
    def transaction(self):
        """An all-or-nothing block spanning multiple `Store` calls.

        Every public method below commits its own write individually via
        `_commit`. Inside an open `transaction()`, those per-method commits
        are suppressed; the block commits once, as a whole, on clean exit, or
        rolls back everything on exception. Re-entrant: nesting a
        `transaction()` inside an already-open one only tracks depth — the
        outermost block is the one that actually commits or rolls back — so a
        helper method that opens its own `transaction()` still works
        correctly when called from within a caller's larger one.

        Holds `self._lock` (see `__init__`) for the entire block: the `with
        self._lock:` below wraps everything, including the `yield`, so the
        lock stays held from before the first statement inside the caller's
        `with store.transaction():` body runs until after the last one
        finishes — another thread can never commit, or even interleave a
        statement, inside this open transaction. `self._lock` is an RLock
        precisely so the `@_locked` public methods called inside the block
        (and a nested `transaction()`) can re-acquire it on the same thread
        without deadlocking.
        """
        with self._lock:
            self._tx_depth += 1
            try:
                yield
            except BaseException:
                # Not `except Exception`: a BaseException raised inside the
                # block (KeyboardInterrupt when the operator stops the
                # station, a thread's SystemExit) must roll back too, or
                # `finally` below drops `_tx_depth` back to 0 and releases
                # the lock while `conn` is left sitting in an uncommitted
                # implicit transaction — the next unrelated write's own
                # `_commit()` would then commit this partial write right
                # along with it, permanently persisting a half-applied
                # change (e.g. a `fold_term` with its loser deleted but the
                # loser's edges not yet moved).
                if self._tx_depth == 1:
                    self.conn.rollback()
                raise
            else:
                if self._tx_depth == 1:
                    self.conn.commit()
            finally:
                self._tx_depth -= 1

    def _commit(self) -> None:
        """Commit now, unless an enclosing `transaction()` will do it instead."""
        with self._lock:
            if self._tx_depth == 0:
                self.conn.commit()

    # -- ids ---------------------------------------------------------------

    def _next_id(self, kind: str) -> str:
        # No RETURNING clause: the target SQLite (3.34) predates 3.35's support
        # for it, so this is an upsert followed by a separate read. The two
        # statements are made atomic with `self._lock` (see the rationale in
        # `__init__`): every caller of `_next_id` is itself a `@_locked`
        # public method, so this lock is always re-entrant, but it is taken
        # explicitly here too so `_next_id` stays correct even if ever called
        # some other way.
        with self._lock:
            self.conn.execute(
                "INSERT INTO counters(name, value) VALUES (?, 1) "
                "ON CONFLICT(name) DO UPDATE SET value = value + 1",
                (kind,),
            )
            row = self.conn.execute(
                "SELECT value FROM counters WHERE name=?", (kind,)
            ).fetchone()
        return f"{_PREFIXES[kind]}{row['value']}"

    # -- person ------------------------------------------------------------

    @_locked
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
        self._commit()
        return self.get_person(person_id)

    @_locked
    def close_person(self, person_id: str, stopped_at: float, reason: str) -> None:
        self.conn.execute(
            "UPDATE person SET stopped_at=?, stop_reason=?, status='closed' WHERE id=?",
            (stopped_at, reason, person_id),
        )
        self._commit()

    @_locked
    def set_person_transcript(self, person_id: str, text: str) -> None:
        self.conn.execute("UPDATE person SET transcript=? WHERE id=?", (text, person_id))
        self._commit()

    @_locked
    def set_person_name(self, person_id: str, name: str | None) -> None:
        """Der Name der befragten Person — aus der Extraktion oder vom Operator.

        Leer heißt NULL, nicht Leerstring: Die Spracherkennung verhört Namen,
        also muss der Operator ein falsch verstandenes Feld leeren können, und
        das Ergebnis davon ist derselbe Zustand wie bei einer Person, die sich
        nie vorgestellt hat — nicht ein zweiter, leerer Name, den die Anzeige
        dann als eigene Zeile über dem Zitat mitschleppen würde.
        """
        self.conn.execute(
            "UPDATE person SET name=? WHERE id=?", ((name or "").strip() or None, person_id)
        )
        self._commit()

    @_locked
    def set_person_status(self, person_id: str, status: str) -> None:
        self.conn.execute("UPDATE person SET status=? WHERE id=?", (status, person_id))
        self._commit()

    @_locked
    def set_person_portrait(self, person_id: str, photo_path: str, portrait_path: str) -> None:
        self.conn.execute(
            "UPDATE person SET photo_path=?, portrait_path=? WHERE id=?",
            (photo_path, portrait_path, person_id),
        )
        self._commit()

    @_locked
    def get_person(self, person_id: str) -> Person | None:
        row = self.conn.execute("SELECT * FROM person WHERE id=?", (person_id,)).fetchone()
        return _person(row) if row else None

    @_locked
    def open_person(self) -> Person | None:
        row = self.conn.execute(
            "SELECT * FROM person WHERE stopped_at IS NULL ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return _person(row) if row else None

    @_locked
    def list_persons(self) -> list[Person]:
        rows = self.conn.execute("SELECT * FROM person ORDER BY started_at").fetchall()
        return [_person(r) for r in rows]

    # -- term --------------------------------------------------------------

    @_locked
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
        self._commit()
        return self.get_term(term_id)

    @_locked
    def get_term(self, term_id: str) -> Term | None:
        row = self.conn.execute("SELECT * FROM term WHERE id=?", (term_id,)).fetchone()
        return _term(row) if row else None

    @_locked
    def get_term_by_label(self, label: str) -> Term | None:
        row = self.conn.execute("SELECT * FROM term WHERE label=?", (label,)).fetchone()
        return _term(row) if row else None

    @_locked
    def rename_term(
        self, term_id: str, new_label: str, *, mentions_before_merge: int | None = None
    ) -> bool:
        """Rename a term, unless two people already share it. Returns whether
        the label changed.

        D5 (Birk, 2026-08-19): **a term's label is frozen from the moment a
        second distinct person has mentioned it.** While a term belongs to one
        person an unlucky first name may still be corrected; after that the
        name is public property — it is on the wall, and it is also the text
        the embedder sees for this node, so a bad rename both misrepresents
        the node and stops it attracting the very concept it was built from
        (run 19b, `.superpowers/sdd/task-19-report.md`).

        The gate sits here, next to the write, so no caller can bypass it; a
        refusal is silent and writes nothing at all — not even an alias for
        the rejected name, or the node would start answering to it.
        `mention_count` counts DISTINCT persons, which is exactly the notion
        the rule is stated in: how many people have said this.

        `mentions_before_merge` selects WHICH count the rule is judged
        against, never whether it is judged: `kg.merging.apply_merges` passes
        the winner's count from before it folded the group's losers in,
        because the merge and the naming of its result are one decision. It is
        the only legitimate caller; everyone else gets the live count.
        """
        old = self.get_term(term_id)
        if old is None or old.label == new_label:
            return False
        mentions = (
            self.mention_count(term_id)
            if mentions_before_merge is None
            else mentions_before_merge
        )
        if mentions >= 2:
            return False
        self.conn.execute("UPDATE term SET label=? WHERE id=?", (new_label, term_id))
        # Keep the old label reachable: a decision once made is never re-derived.
        for surface in (old.label, new_label):
            self.conn.execute(
                "INSERT OR REPLACE INTO term_alias(surface, term_id) VALUES (?,?)",
                (surface, term_id),
            )
        self._commit()
        return True

    @_locked
    def add_alias(self, term_id: str, surface: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO term_alias(surface, term_id) VALUES (?,?)",
            (surface, term_id),
        )
        self._commit()

    @_locked
    def fold_term(self, loser_id: str, winner_id: str) -> None:
        """Merge `loser_id` into `winner_id` (spec 6.2, 7): a merge is the
        finding that more people meant the same thing, so the winner must
        come out at least as strong as either term was alone — every alias
        and edge the loser carried moves onto the winner, mention counts
        combine, and the loser term itself is deleted so it cannot linger as
        an unreachable second node on the wall.

        Edges are folded through `add_edge`, which is idempotent per
        (person_id, term_id): a person who mentioned both terms ends up with
        exactly one edge to the winner, never two (edge has
        UNIQUE(person_id, term_id)).
        """
        if loser_id == winner_id:
            return
        loser = self.get_term(loser_id)
        if loser is None:
            return
        with self.transaction():
            # Point every alias the loser owned at the winner instead. The
            # loser's own label must stay reachable too — a decision, once
            # made, is never re-derived.
            self.conn.execute(
                "UPDATE term_alias SET term_id=? WHERE term_id=?", (winner_id, loser_id)
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO term_alias(surface, term_id) VALUES (?,?)",
                (loser.label, winner_id),
            )
            loser_edges = self.conn.execute(
                "SELECT person_id, created_at FROM edge WHERE term_id=?", (loser_id,)
            ).fetchall()
            for row in loser_edges:
                self.add_edge(row["person_id"], winner_id, created_at=row["created_at"])
            self.conn.execute("DELETE FROM edge WHERE term_id=?", (loser_id,))
            # The loser's position row would otherwise point at a deleted node.
            self.conn.execute("DELETE FROM position WHERE node_id=?", (f"term:{loser_id}",))
            self.conn.execute("DELETE FROM term WHERE id=?", (loser_id,))

    @_locked
    def find_term_by_alias(self, surface: str) -> Term | None:
        row = self.conn.execute(
            "SELECT t.* FROM term_alias a JOIN term t ON t.id = a.term_id WHERE a.surface=?",
            (surface,),
        ).fetchone()
        return _term(row) if row else None

    @_locked
    def list_terms(self) -> list[Term]:
        rows = self.conn.execute("SELECT * FROM term ORDER BY created_at, id").fetchall()
        return [_term(r) for r in rows]

    # -- edges / quotes ----------------------------------------------------

    @_locked
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
        self._commit()
        row = self.conn.execute("SELECT * FROM edge WHERE id=?", (edge_id,)).fetchone()
        return _edge(row)

    @_locked
    def list_edges(self) -> list[Edge]:
        rows = self.conn.execute("SELECT * FROM edge ORDER BY created_at, id").fetchall()
        return [_edge(r) for r in rows]

    @_locked
    def mention_count(self, term_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(DISTINCT person_id) AS n FROM edge WHERE term_id=?", (term_id,)
        ).fetchone()
        return int(row["n"])

    @_locked
    def add_quote(self, person_id: str, text: str, created_at: float) -> Quote:
        quote_id = self._next_id("quote")
        self.conn.execute(
            "INSERT INTO quote(id, person_id, text, created_at) VALUES (?,?,?,?)",
            (quote_id, person_id, text, created_at),
        )
        self._commit()
        row = self.conn.execute("SELECT * FROM quote WHERE id=?", (quote_id,)).fetchone()
        return Quote(row["id"], row["person_id"], row["text"], row["created_at"])

    @_locked
    def list_quotes(self) -> list[Quote]:
        rows = self.conn.execute("SELECT * FROM quote ORDER BY created_at, id").fetchall()
        return [Quote(r["id"], r["person_id"], r["text"], r["created_at"]) for r in rows]

    # -- flags, positions, decisions, settings ------------------------------

    @_locked
    def set_hidden(self, node_id: str, hidden: bool) -> None:
        kind, _, ident = node_id.partition(":")
        if kind not in ("person", "term") or not ident:
            raise ValueError(f"unknown node id: {node_id!r}")
        self.conn.execute(f"UPDATE {kind} SET hidden=? WHERE id=?", (1 if hidden else 0, ident))
        self._commit()

    @_locked
    def save_positions(self, positions: dict[str, tuple[float, float]]) -> None:
        self.conn.executemany(
            "INSERT INTO position(node_id, x, y) VALUES (?,?,?) "
            "ON CONFLICT(node_id) DO UPDATE SET x=excluded.x, y=excluded.y",
            [(node_id, float(x), float(y)) for node_id, (x, y) in positions.items()],
        )
        self._commit()

    @_locked
    def get_positions(self) -> dict[str, tuple[float, float]]:
        rows = self.conn.execute("SELECT node_id, x, y FROM position").fetchall()
        return {r["node_id"]: (r["x"], r["y"]) for r in rows}

    @_locked
    def record_merge_decision(self, person_id: str, payload: dict, created_at: float) -> None:
        self.conn.execute(
            "INSERT INTO merge_decision(id, person_id, payload, created_at) VALUES (?,?,?,?)",
            (self._next_id("merge"), person_id, json.dumps(payload, ensure_ascii=False), created_at),
        )
        self._commit()

    @_locked
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

    @_locked
    def get_setting(self, key: str, default: str) -> str:
        row = self.conn.execute("SELECT value FROM setting WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    @_locked
    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO setting(key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        self._commit()

    @_locked
    def set_setting_default(self, key: str, value: str) -> None:
        """Seed a setting only if it has never been set.

        Startup uses this to apply the calibrated `default_max_terms` without
        overwriting a dial the operator turned before the crash (spec 7, 10.5).
        """
        self.conn.execute(
            "INSERT OR IGNORE INTO setting(key, value) VALUES (?,?)", (key, str(value))
        )
        self._commit()


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
        name=row["name"],
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
