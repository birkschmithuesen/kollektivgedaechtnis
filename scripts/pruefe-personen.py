"""Trennt echte Interviews von Testleichen in der laufenden Datenbank.

Anlass (Birk, 2026-09-01): Frage nach Testdatenbank gegen reale Datenbank.
Befund: es gibt nur EINE Datenbank (`data/kg.db`), und in der stehen neben
sechs echten Interviews acht Personen, die heute durch Foto-Tests entstanden
sind -- jedes eingeworfene Foto eroeffnet eine Person.

Dieses Skript sagt je Person, ob sie Inhalt hat (Begriffe, Zitat, Name) oder
leer ist. Eine leere Person erscheint an der Wand als Scheibe ohne alles.

🔴 Zeigt KEINE Namen, KEINE Zitate, KEIN Transkript -- nur Zaehlungen und
Zeitstempel. Die Begriffe (`label`) sind oeffentlich (sie stehen an der Wand)
und werden je Person genannt, damit Birk Testmuell zuordnen kann.

Aufruf auf der Station:
    C:\\Users\\birk\\kollektivgedaechtnis\\.venv\\Scripts\\python.exe ^
        pruefe-personen.py
"""

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

DB = Path(r"C:\Users\birk\kollektivgedaechtnis\data\kg.db")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DB))
    args = p.parse_args()

    con = sqlite3.connect(f"file:{Path(args.db)}?mode=ro", uri=True)

    # Welche Spalte verbindet Begriff und Person? Struktur erst lesen,
    # nicht raten -- die Tabellen heissen hier im Singular, und schon das
    # hatte ich beim ersten Versuch falsch.
    pos_spalten = [r[1] for r in con.execute("PRAGMA table_info(position)")]
    edge_spalten = [r[1] for r in con.execute("PRAGMA table_info(edge)")]
    quote_spalten = [r[1] for r in con.execute("PRAGMA table_info(quote)")]
    print(f"position: {pos_spalten}")
    print(f"edge:     {edge_spalten}")
    print(f"quote:    {quote_spalten}")
    print("=" * 92)

    personen = list(con.execute(
        "SELECT id, started_at, status, stop_reason, hidden, "
        "       CASE WHEN name IS NULL OR name='' THEN 0 ELSE 1 END,"
        "       CASE WHEN transcript IS NULL OR transcript='' THEN 0 ELSE LENGTH(transcript) END,"
        "       CASE WHEN portrait_path IS NULL OR portrait_path='' THEN 0 ELSE 1 END "
        "FROM person ORDER BY started_at"))

    print(f"{'Person':<8}{'Beginn':<14}{'Status':<12}{'Transkr.':>9}"
          f"{'Begriffe':>9}{'Zitat':>7}{'Name':>6}{'Foto':>6}  Bewertung")

    leer, echt = [], []
    for pid, start, status, grund, hidden, hat_name, tlen, hat_foto in personen:
        try:
            wann = datetime.fromtimestamp(float(start)).strftime("%m-%d %H:%M")
        except (TypeError, ValueError):
            wann = str(start)

        # Begriffe dieser Person ueber die Verknuepfungstabelle
        n_begriffe = 0
        labels = []
        for tabelle, spalte in (("position", "person_id"), ("edge", "person_id")):
            spalten = pos_spalten if tabelle == "position" else edge_spalten
            if spalte not in spalten:
                continue
            try:
                zeilen = list(con.execute(
                    f"SELECT t.label FROM {tabelle} x JOIN term t ON t.id = x.term_id "
                    f"WHERE x.{spalte} = ?", (pid,)))
                if zeilen:
                    labels = [z[0] for z in zeilen]
                    n_begriffe = len(labels)
                    break
            except sqlite3.Error:
                continue

        n_zitate = 0
        if "person_id" in quote_spalten:
            n_zitate = con.execute(
                "SELECT COUNT(*) FROM quote WHERE person_id=?", (pid,)).fetchone()[0]

        # Bewertung: eine Person ohne Begriff UND ohne Zitat ist an der Wand
        # eine leere Scheibe -- unabhaengig davon, warum.
        if n_begriffe == 0 and n_zitate == 0:
            urteil = "LEER -> leere Scheibe an der Wand"
            leer.append((pid, wann, tlen))
        else:
            urteil = "hat Inhalt"
            echt.append((pid, wann, n_begriffe))

        print(f"{str(pid):<8}{wann:<14}{str(status):<12}{tlen:>9}"
              f"{n_begriffe:>9}{n_zitate:>7}{hat_name:>6}{hat_foto:>6}  {urteil}")
        if labels:
            print(f"         Begriffe: {labels}")

    print("=" * 92)
    print(f"Mit Inhalt: {len(echt)}   LEER: {len(leer)}")
    if leer:
        print("\nLeere Personen (Kandidaten zum Ausblenden vor der Ausstellung):")
        for pid, wann, tlen in leer:
            print(f"  {pid:<6} {wann}  Transkript {tlen} Zeichen")
        print("\nAusblenden statt loeschen: UPDATE person SET hidden=1 WHERE id=...")
        print("Das entscheidet Birk -- dieses Skript aendert NICHTS (read-only).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
