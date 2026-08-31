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
    hidden        INTEGER NOT NULL DEFAULT 0,
    -- Der selbstgenannte Name aus dem Interview (kg.extraction), NULL wenn
    -- sich niemand vorgestellt hat. Steht bewusst am Ende der Tabelle: so
    -- sieht eine frisch angelegte Datenbank genauso aus wie eine, die die
    -- Spalte über `_nachruesten` unten angehängt bekommen hat.
    name          TEXT
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


#: Spalten, die erst nach dem ersten Betrieb dazugekommen sind — Tabelle,
#: Spaltenname, SQL-Typ. Das ist absichtlich kein Migrationsframework: es gibt
#: keine Versionsnummer, keine Reihenfolge und keinen Rückweg, nur „fehlt sie,
#: dann häng sie an". Mehr braucht eine Station, die nichts umbenennt und
#: nichts löscht, und weniger würde die eine Datenbank vergessen, auf die es
#: ankommt.
_NACHGEREICHTE_SPALTEN = (("person", "name", "TEXT"),)


def _nachruesten(conn: sqlite3.Connection) -> None:
    """Fehlende Spalten an eine bestehende Datenbank anfügen.

    `CREATE TABLE IF NOT EXISTS` fasst eine Tabelle, die es schon gibt, nicht
    mehr an. Eine neue Spalte in `SCHEMA` erreicht deshalb ausgerechnet die
    Arbeitsdatenbank mit den echten Interviews nie — dort schlüge dann jede
    Abfrage darauf fehl, während sie in jedem Test grün ist, weil der auf einer
    frisch angelegten Datei läuft. Bestehende Zeilen behalten NULL, was hier
    genau das Richtige heißt: von den vor der Änderung befragten Personen
    kennen wir den Namen tatsächlich nicht.
    """
    for tabelle, spalte, typ in _NACHGEREICHTE_SPALTEN:
        vorhanden = {row["name"] for row in conn.execute(f"PRAGMA table_info({tabelle})")}
        if spalte not in vorhanden:
            conn.execute(f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {typ}")


def connect(path: Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _nachruesten(conn)
    conn.commit()
    return conn
