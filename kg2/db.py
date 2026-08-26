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
    contradiction      INTEGER NOT NULL DEFAULT 0,
    guiding_question   TEXT NOT NULL DEFAULT '',
    absorbed_persons   TEXT NOT NULL DEFAULT '[]',
    stage1_prompt      TEXT,
    sentence           TEXT,
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
