"""The only module that reads from or writes to Tool 2's SQLite.

Same discipline as `kg.store`, and for the same reason: FastAPI runs sync route
handlers in a threadpool while the watcher loop and the dream cycle write from
their own threads, and Python's `sqlite3` does not serialise statements against
a shared connection by itself. Every public method goes through one re-entrant
lock.

Smaller than Tool 1's store on purpose — there is one table with one row per
dream and no merging, no positions, no aliases.
"""

from __future__ import annotations

import functools
import json
import sqlite3
import threading
from pathlib import Path

from kg2.db import connect
from kg2.models import Dream


def _locked(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


def _row(row: sqlite3.Row) -> Dream:
    return Dream(
        id=row["id"],
        created_at=row["created_at"],
        graph_generated_at=row["graph_generated_at"],
        person_count=row["person_count"],
        term_count=row["term_count"],
        edge_count=row["edge_count"],
        contradiction=bool(row["contradiction"]),
        guiding_question=row["guiding_question"],
        absorbed_persons=json.loads(row["absorbed_persons"]),
        stage1_prompt=row["stage1_prompt"],
        sentence=row["sentence"],
        stage2_prompt=row["stage2_prompt"],
        condense_model=row["condense_model"],
        image_model=row["image_model"],
        image_path=row["image_path"],
        status=row["status"],
        error=row["error"],
        discarded=bool(row["discarded"]),
    )


class DreamStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        # kg2.db.connect opens the connection with check_same_thread=False so
        # a single connection (and this DreamStore) can be shared across
        # threads: FastAPI runs sync route handlers in a threadpool
        # (kg2/server.py), and the watcher loop and the dream cycle write
        # through the same DreamStore instance from their own threads.
        # Python's sqlite3 module does not serialise statements against a
        # shared connection by itself — two threads issuing statements at
        # once can interleave mid-transaction, or interleave between an
        # UPSERT and the following SELECT in `_next_id` and read the same
        # counter value, minting a duplicate id.
        #
        # This RLock serialises every public method below (via the
        # `@_locked` decorator) — reads included, since a read racing a
        # write on one shared connection is exactly as unsafe as two writes
        # racing. It must be re-entrant, not a plain Lock: `_next_id` is
        # called from inside `create_dream`, another locked method on the
        # same thread, and a plain Lock would deadlock the instant that
        # happened.
        self._lock = threading.RLock()

    @classmethod
    def open(cls, path: Path) -> "DreamStore":
        return cls(connect(Path(path)))

    @_locked
    def close(self) -> None:
        self.conn.close()

    def _next_id(self) -> str:
        # The upsert-then-read below is made atomic with self._lock (see the
        # rationale in __init__): its only caller, create_dream, is itself a
        # @_locked public method, so this lock is always re-entrant here —
        # but it is taken explicitly anyway so _next_id stays correct even if
        # ever called some other way.
        with self._lock:
            self.conn.execute(
                "INSERT INTO counters(name, value) VALUES ('dream', 1) "
                "ON CONFLICT(name) DO UPDATE SET value = value + 1"
            )
            row = self.conn.execute(
                "SELECT value FROM counters WHERE name='dream'"
            ).fetchone()
            return f"d{row[0]}"

    # -- writing ------------------------------------------------------------

    @_locked
    def create_dream(
        self,
        *,
        created_at: float,
        graph_generated_at: float | None,
        person_count: int,
        term_count: int,
        edge_count: int,
        contradiction: bool,
        guiding_question: str,
        absorbed_persons: list[str],
    ) -> Dream:
        """Insert the row BEFORE the first cloud call.

        A crash or a kill between here and `finish_dream` then leaves a row
        stuck at `running` — visibly incomplete, which is the honest record —
        rather than leaving no trace that a dream was ever attempted.
        """
        dream_id = self._next_id()
        self.conn.execute(
            "INSERT INTO dream(id, created_at, graph_generated_at, person_count,"
            " term_count, edge_count, contradiction, guiding_question,"
            " absorbed_persons, status)"
            " VALUES (?,?,?,?,?,?,?,?,?, 'running')",
            (
                dream_id,
                created_at,
                graph_generated_at,
                person_count,
                term_count,
                edge_count,
                int(contradiction),
                guiding_question,
                json.dumps(sorted(absorbed_persons)),
            ),
        )
        self.conn.commit()
        return self.get_dream(dream_id)

    @_locked
    def set_stage1(self, dream_id: str, *, prompt: str, sentence: str, model: str) -> None:
        self.conn.execute(
            "UPDATE dream SET stage1_prompt=?, sentence=?, condense_model=? WHERE id=?",
            (prompt, sentence, model, dream_id),
        )
        self.conn.commit()

    @_locked
    def set_stage2_prompt(self, dream_id: str, *, prompt: str, model: str) -> None:
        """Recorded BEFORE the render, so a failed render still leaves the
        prompt that failed — which is the one worth reading (spec §5.3)."""
        self.conn.execute(
            "UPDATE dream SET stage2_prompt=?, image_model=? WHERE id=?",
            (prompt, model, dream_id),
        )
        self.conn.commit()

    @_locked
    def finish_dream(self, dream_id: str, *, image_path: str) -> None:
        self.conn.execute(
            "UPDATE dream SET image_path=?, status='done', error=NULL WHERE id=?",
            (image_path, dream_id),
        )
        self.conn.commit()

    @_locked
    def fail_dream(self, dream_id: str, error: str) -> None:
        self.conn.execute(
            "UPDATE dream SET status='failed', error=? WHERE id=?", (error, dream_id)
        )
        self.conn.commit()

    @_locked
    def set_discarded(self, dream_id: str, discarded: bool) -> None:
        """The row is never deleted (spec §7) — the record stays honest and the
        display filters. Reversible, like Tool 1's hide flag."""
        self.conn.execute(
            "UPDATE dream SET discarded=? WHERE id=?", (int(discarded), dream_id)
        )
        self.conn.commit()

    # -- reading ------------------------------------------------------------

    @_locked
    def get_dream(self, dream_id: str) -> Dream | None:
        row = self.conn.execute("SELECT * FROM dream WHERE id=?", (dream_id,)).fetchone()
        return _row(row) if row else None

    @_locked
    def all_dreams(self) -> list[Dream]:
        """Every row, whatever its status. The record, not the display."""
        # Tiebreak on rowid, not id: id is TEXT ("d1", "d2", ... "d10"), so on
        # a created_at tie sorting by id would go lexicographic (d1, d10, d2,
        # ...) instead of insertion order. SQLite's implicit rowid is
        # monotonic with insertion order and immune to that, and to any float
        # collision in created_at.
        rows = self.conn.execute("SELECT * FROM dream ORDER BY created_at, rowid").fetchall()
        return [_row(row) for row in rows]

    @_locked
    def visible_dreams(self) -> list[Dream]:
        """What screen B shows, oldest to newest: finished and not discarded.

        A `running` dream is not here — the screen keeps the previous image
        until the new one exists, which is what makes a 60 s generation
        invisible and a failure look like nothing at all (spec §8).
        """
        # See all_dreams() for why the tiebreak is rowid, not id.
        rows = self.conn.execute(
            "SELECT * FROM dream WHERE status='done' AND discarded=0 "
            "ORDER BY created_at, rowid"
        ).fetchall()
        return [_row(row) for row in rows]

    @_locked
    def current_dream(self) -> Dream | None:
        visible = self.visible_dreams()
        return visible[-1] if visible else None

    @_locked
    def history(self) -> list[Dream]:
        """The strip: every earlier dream, oldest first (spec §6)."""
        return self.visible_dreams()[:-1]

    @_locked
    def last_started_at(self) -> float | None:
        """The floor's reference point (spec §4.1: since the last dream STARTED).

        Spans every row, including `failed` and `discarded`: a failure that did
        not move the floor would be retried on the very next poll, which is the
        retry storm spec §8 forbids.
        """
        row = self.conn.execute("SELECT MAX(created_at) FROM dream").fetchone()
        return row[0]

    # -- settings -----------------------------------------------------------

    @_locked
    def get_setting(self, key: str, default: str) -> str:
        row = self.conn.execute("SELECT value FROM setting WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    @_locked
    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO setting(key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        self.conn.commit()

    @_locked
    def consume_flag(self, key: str) -> bool:
        """Read a boolean setting and clear it back to "0", as one operation
        under the single lock rather than two separately-locked calls.

        Each of get_setting/set_setting is individually safe, but the pair is
        not fused: an operator press landing in the gap between the read and
        the clear would be silently overwritten back to "0" and lost — with
        the operator's only feedback being that nothing happened. `_lock` is
        an RLock (see __init__), so calling the two locked methods from here
        is safely re-entrant.
        """
        was_set = self.get_setting(key, "0") == "1"
        if was_set:
            self.set_setting(key, "0")
        return was_set

    @_locked
    def set_setting_default(self, key: str, value: str) -> None:
        """Seed a setting only if it has never been set — so a restart restores
        the operator's value, not config2.toml's start value."""
        self.conn.execute(
            "INSERT OR IGNORE INTO setting(key, value) VALUES (?,?)", (key, str(value))
        )
        self.conn.commit()
