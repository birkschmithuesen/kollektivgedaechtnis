"""Nachgereichte Spalten auf einer Bestandsdatenbank (kg/db.py).

Der Grund steht bei `_nachruesten`: `CREATE TABLE IF NOT EXISTS` fasst eine
Tabelle, die es schon gibt, nicht mehr an. Eine neue Spalte in `SCHEMA`
erreicht damit ausgerechnet die eine Datenbank nie, auf die es ankommt — die
mit den echten Interviews (`out/sim20.db`, sechzig Stück). Jeder andere Test in
diesem Verzeichnis läuft auf einer frisch angelegten Datei und wäre grün,
während die Station beim ersten Zugriff auf die Spalte abbricht. Deshalb dieser
hier, der ausdrücklich mit dem alten Stand anfängt.
"""

import sqlite3

import pytest

from kg.db import connect
from kg.store import Store

# Die `person`-Tabelle, wie sie vor der Namensspalte aussah. Absichtlich
# ausgeschrieben statt aus kg.db importiert: Der Test muss den ALTEN Stand
# herstellen können — und kann das nicht, wenn er sich aus derselben Quelle
# bedient, deren Weiterentwicklung er prüft.
ALTES_PERSON_SCHEMA = """
CREATE TABLE person (
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
"""


@pytest.fixture()
def bestandsdatenbank(tmp_path):
    """Eine Datei mit dem alten Schema und einem bereits geführten Interview."""
    path = tmp_path / "bestand.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(ALTES_PERSON_SCHEMA)
    conn.execute(
        "INSERT INTO person(id, started_at, status, transcript) VALUES (?,?,?,?)",
        ("p1", 100.0, "done", "wir bauen viel zu viel neu"),
    )
    conn.commit()
    conn.close()
    return path


def _spalten(conn) -> set[str]:
    # Über den Index, nicht über den Namen: eine rohe sqlite3-Verbindung hat
    # die `Row`-Factory nicht, die kg.db.connect setzt.
    return {row[1] for row in conn.execute("PRAGMA table_info(person)")}


def test_eine_bestandsdatenbank_bekommt_die_namensspalte(bestandsdatenbank):
    assert "name" not in _spalten(sqlite3.connect(str(bestandsdatenbank)))  # Ausgangslage

    conn = connect(bestandsdatenbank)
    try:
        assert "name" in _spalten(conn)
    finally:
        conn.close()


def test_die_alten_interviews_bleiben_vollstaendig_und_namenlos(bestandsdatenbank):
    """Nachrüsten heißt anfügen, nicht neu anlegen.

    Die sechzig bereits geführten Interviews müssen die Änderung unverändert
    überstehen — und ohne Namen dastehen, denn das ist die Wahrheit: Von ihnen
    wurde keiner erhoben.
    """
    store = Store(connect(bestandsdatenbank))
    try:
        person = store.get_person("p1")
        assert person.transcript == "wir bauen viel zu viel neu"
        assert person.name is None
    finally:
        store.close()


def test_die_nachruestung_laeuft_bei_jedem_start_erneut_ohne_zu_stolpern(bestandsdatenbank):
    """`connect()` läuft bei jedem Start der Station, nicht einmalig.

    Es gibt keine Versionsnummer, die einen zweiten Durchlauf verhindern würde,
    also muss der zweite Durchlauf schlicht nichts tun — ein zweites `ALTER
    TABLE` wäre ein Fehler und nähme die Station beim Hochfahren mit.
    """
    for _ in range(3):
        conn = connect(bestandsdatenbank)
        conn.close()

    store = Store(connect(bestandsdatenbank))
    try:
        assert store.get_person("p1").name is None
    finally:
        store.close()


def test_eine_neu_angelegte_datenbank_bringt_die_spalte_schon_mit(tmp_path):
    """Frisch und nachgerüstet müssen dasselbe ergeben, sonst hängt das
    Verhalten der Station davon ab, wie alt ihre Datei ist."""
    store = Store.open(tmp_path / "neu.db")
    try:
        person = store.create_person(started_at=1.0)
        assert person.name is None
        store.set_person_name(person.id, "Frau Kirchner")
        assert store.get_person(person.id).name == "Frau Kirchner"
    finally:
        store.close()
