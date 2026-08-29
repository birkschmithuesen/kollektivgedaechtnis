"""SQLite schema and connection handling for Tool 2's own store.

Deliberately a separate database file from Tool 1's (`dreams.sqlite3` next to
`kg.db`, and on a different machine entirely): spec §2 — Tool 2 never writes to
Tool 1's SQLite, and the surest way to keep that true is never to open it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS counters (
    name  TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS dream (
    id                 TEXT PRIMARY KEY,
    created_at         REAL NOT NULL,
    graph_generated_at REAL,
    person_count       INTEGER NOT NULL DEFAULT 0,
    term_count         INTEGER NOT NULL DEFAULT 0,
    edge_count         INTEGER NOT NULL DEFAULT 0,
    -- Altbestand, keine Migration: die Widerspruchs-Klausel selbst ist am
    -- 2026-08-28 ersatzlos entfallen (kg2/condense.py), aber die Spalte zu
    -- entfernen bräuchte eine Migration, die kein bestehender Datensatz
    -- rechtfertigt. kg2/store.py::create_dream schreibt hier künftig immer 0.
    contradiction      INTEGER NOT NULL DEFAULT 0,
    guiding_question   TEXT NOT NULL DEFAULT '',
    absorbed_persons   TEXT NOT NULL DEFAULT '[]',
    stage1_prompt      TEXT,
    sentence           TEXT,
    -- Literal English translation of `sentence` — the honest English
    -- counterpart of what stood on the wall. NULL for rows written before
    -- 2026-08-28; readers must treat that the same as "no translation
    -- available". Since 2026-08-29 it is no longer stage 2's motif on its
    -- own, only the fallback for `image_description` below.
    sentence_en        TEXT,
    -- The motif actually fed to stage 2 (kg2/imagegen.py): 3-4 sentences of
    -- English prose about the same scene as `sentence`, at length. Added
    -- 2026-08-29, additively and WITHOUT a migration — the same treatment
    -- sentence_en/mood/tension got on 2026-08-28. NULL for every row written
    -- before that date, and legitimately NULL for a dream whose stage 1
    -- returned nothing usable here; readers treat NULL as "not available"
    -- and fall back, never as an error.
    image_description  TEXT,
    -- One short English clause naming which two things in the material
    -- contradict each other. NULL like the column above for old rows — and
    -- legitimately empty even on a brand-new row: material without a real
    -- contradiction must not have one invented for it (kg2/condense.py).
    tension_source     TEXT,
    -- 1-5, both from the same stage-1 call as `sentence` (kg2/condense.py).
    -- NULL for rows written before 2026-08-28.
    mood               INTEGER,
    tension            INTEGER,
    stage2_prompt      TEXT,
    condense_model     TEXT,
    image_model        TEXT,
    image_path         TEXT,
    status             TEXT NOT NULL DEFAULT 'running',
    error              TEXT,
    discarded          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS setting (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
