"""Zeigt, WAS in der laufenden Datenbank der Station steht -- ohne Inhalte.

Anlass (Birk, 2026-09-01): „Hast du eine Testdatenbank mit dem ganzen
synthetischen Zeug in Begriffen und die gerade laufende reale Datenbank?"

Die Frage ist berechtigt: waehrend der Tests heute sind mehrere Fotos
eingeworfen worden, jedes eroeffnet eine Person. Wenn dabei synthetische oder
Test-Begriffe in die ECHTE Ausstellungsdatenbank gelangt sind, stehen die
morgen an der Wand.

🔴 Gibt nur Struktur und Zaehlungen aus. Begriffe (`label`) sind das, was
ohnehin oeffentlich an der Wand steht -- die werden gezeigt, damit Birk
Testmuell erkennen kann. Zitate, Namen und Transkripte NICHT.

Aufruf auf der Station:
    C:\\Users\\birk\\kollektivgedaechtnis\\.venv\\Scripts\\python.exe ^
        zeige-datenbank.py
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

    pfad = Path(args.db)
    print(f"Datenbank: {pfad}")
    print(f"Groesse: {pfad.stat().st_size} Bytes")
    print("=" * 78)

    # read-only oeffnen: die Station laeuft, nichts darf veraendert werden.
    con = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)

    tabellen = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print("Tabellen:", ", ".join(tabellen))
    print()

    for t in tabellen:
        try:
            n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except sqlite3.Error as fehler:
            print(f"  {t:<24} FEHLER: {fehler}")
            continue
        print(f"  {t:<24} {n:>6} Zeilen")

    # --- Personen: wann sind sie entstanden? ---
    print()
    if "person" in tabellen:
        spalten = [r[1] for r in con.execute("PRAGMA table_info(person)")]
        zeit = next((s for s in spalten if s in
                     ("created_at", "at", "timestamp", "started_at")), None)
        print(f"Personen-Spalten: {spalten}")
        if zeit:
            print("\nPersonen nach Zeit (nur Zeitstempel, keine Namen):")
            for pid, ts in con.execute(
                    f"SELECT id, {zeit} FROM person ORDER BY {zeit}"):
                try:
                    lesbar = datetime.fromtimestamp(float(ts)).strftime("%m-%d %H:%M")
                except (TypeError, ValueError):
                    lesbar = str(ts)
                print(f"  {str(pid)[:8]:<10} {lesbar}")

    # --- Begriffe: die stehen an der Wand, also darf man sie sehen ---
    if "term" in tabellen:
        print()
        spalten = [r[1] for r in con.execute("PRAGMA table_info(term)")]
        print(f"Begriffs-Spalten: {spalten}")
        label = "label" if "label" in spalten else spalten[1]
        print(f"\nAlle Begriffe im Graphen ({label}):")
        for i, (lab,) in enumerate(
                con.execute(f"SELECT {label} FROM term ORDER BY {label}"), 1):
            print(f"  {i:>3}. {lab}")

    con.close()
    print()
    print("=" * 78)
    print("Zu pruefen: stehen hier Begriffe drin, die aus TESTFOTOS stammen")
    print("(Kaffeemaschine, Testmuster, Aufbau-Gespraech)? Die gehoeren nicht")
    print("an die Wand. Loeschen entscheidet Birk.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
