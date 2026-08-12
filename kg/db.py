"""SQLite schema and connection handling."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS counters (
    name  TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS person (
    id            TEXT PRIMARY KEY,
    started_at    REAL NOT NULL,
    stopped_at    REAL,
    stop_reason   TEXT,
    status        TEXT NOT NULL DEFAULT 'open',
    transcript    TEXT,
    photo_path    TEXT,
    portrait_path TEXT,
    hidden        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS term (
    id         TEXT PRIMARY KEY,
    label      TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL,
    hidden     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS term_alias (
    surface TEXT PRIMARY KEY,
    term_id TEXT NOT NULL REFERENCES term(id)
);

CREATE TABLE IF NOT EXISTS edge (
    id         TEXT PRIMARY KEY,
    person_id  TEXT NOT NULL REFERENCES person(id),
    term_id    TEXT NOT NULL REFERENCES term(id),
    created_at REAL NOT NULL,
    UNIQUE (person_id, term_id)
);

CREATE TABLE IF NOT EXISTS quote (
    id         TEXT PRIMARY KEY,
    person_id  TEXT NOT NULL REFERENCES person(id),
    text       TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS merge_decision (
    id         TEXT PRIMARY KEY,
    person_id  TEXT NOT NULL REFERENCES person(id),
    payload    TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS position (
    node_id TEXT PRIMARY KEY,
    x       REAL NOT NULL,
    y       REAL NOT NULL
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
