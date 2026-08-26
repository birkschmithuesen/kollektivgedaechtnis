"""Walk a finished simulation into a live graph, one interview at a time.

Built for reading the wall's construction rather than watching it: after step
N the graph holds EXACTLY the first N interviews — their people, the terms they
brought, the edges and quotes — and nothing from interview N+1. That is what
makes a single step legible: every node that appears, appears because of the
one interview just added.

Deliberately NOT `sim.replay`: that one runs the real pipeline (LLM extraction
plus embeddings) and costs money and minutes per interview. Here the extraction
has already happened — `out/<run>/sim.db` IS its result — so this replays the
OUTCOME. Same graph, no model calls, instant steps. The price of that shortcut
is honesty about what it does not test: nothing here exercises extraction or
merging, and a step that looks right proves only that the recorded result was
copied correctly.

Terms are carried over BY LABEL, not by id. In the source database a term id is
whatever the merge judge happened to create; re-resolving through
`get_or_create_term` means the second person to say "Drohnen am Bau" lands on
the node the first person created, which is precisely the growth the wall is
supposed to show.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Interview:
    """One recorded interview, resolved into everything needed to replay it."""

    person_id: str
    index: int
    started_at: float
    stopped_at: float
    stop_reason: str
    transcript: str
    terms: tuple[str, ...]
    quotes: tuple[str, ...]


class InterviewStepper:
    """Reads a finished run; hands out its interviews in recorded order.

    `check_same_thread=False` plus an explicit lock: FastAPI runs synchronous
    endpoints in a worker threadpool, so `/step` is not guaranteed to land on
    the thread that opened this connection — and SQLite refuses cross-thread
    use by default. The lock is what actually makes that safe; the flag only
    stops sqlite3 from rejecting it outright.
    """

    def __init__(self, source_db: Path) -> None:
        self.conn = sqlite3.connect(str(source_db), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._ids = [
            row["id"]
            for row in self.conn.execute("SELECT id FROM person ORDER BY started_at, id")
        ]

    @property
    def total(self) -> int:
        return len(self._ids)

    def interview(self, index: int) -> Interview:
        """The 1-based `index`-th interview of the run."""
        if not 1 <= index <= self.total:
            raise IndexError(f"interview {index} outside 1..{self.total}")
        person_id = self._ids[index - 1]
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM person WHERE id = ?", (person_id,)
            ).fetchone()
            terms = [
                r["label"]
                for r in self.conn.execute(
                    """
                    SELECT t.label FROM edge e
                    JOIN term t ON t.id = e.term_id
                    WHERE e.person_id = ?
                    ORDER BY e.created_at, e.id
                    """,
                    (person_id,),
                )
            ]
            quotes = [
                r["text"]
                for r in self.conn.execute(
                    "SELECT text FROM quote WHERE person_id = ? ORDER BY created_at, id",
                    (person_id,),
                )
            ]
        return Interview(
            person_id=person_id,
            index=index,
            started_at=row["started_at"],
            stopped_at=row["stopped_at"] or row["started_at"],
            stop_reason=row["stop_reason"] or "text",
            transcript=row["transcript"] or "",
            terms=tuple(terms),
            quotes=tuple(quotes),
        )

    def close(self) -> None:
        self.conn.close()


def apply_interview(store, interview: Interview, portrait_path: str | None = None) -> dict:
    """Write one interview into a live store; report what it changed.

    The report distinguishes terms that were NEW from terms that merely gained
    another voice, because on the wall those are two different events: one adds
    a node, the other thickens a connection that was already there.
    """
    person = store.create_person(
        started_at=interview.started_at,
        photo_path=portrait_path,
        portrait_path=portrait_path,
    )
    store.close_person(
        person.id, stopped_at=interview.stopped_at, reason=interview.stop_reason
    )
    store.set_person_transcript(person.id, interview.transcript)

    new_terms: list[str] = []
    joined_terms: list[str] = []
    for label in interview.terms:
        existed = store.get_term_by_label(label) is not None
        term = store.get_or_create_term(label, created_at=interview.stopped_at)
        store.add_edge(person.id, term.id, created_at=interview.stopped_at)
        (joined_terms if existed else new_terms).append(label)

    for text in interview.quotes:
        store.add_quote(person.id, text, created_at=interview.stopped_at)

    return {
        "person_id": person.id,
        "index": interview.index,
        "new_terms": new_terms,
        "joined_terms": joined_terms,
        "quotes": len(interview.quotes),
        "transcript": interview.transcript,
    }
