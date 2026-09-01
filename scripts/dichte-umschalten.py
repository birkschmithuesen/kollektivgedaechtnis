"""Schaltet die Station zwischen Dichtestufen um -- fuer das Einrichten vor Ort.

Birk, 2026-09-01, in der Halle: die Groessen (Portrait, Anzeige, Begriffe)
muessen am Regler eingestellt werden, und zwar so, dass es bei EINER Person
genauso funktioniert wie bei sechzig. Dafuer braucht es Graphen in mehreren
Dichten -- schnell umschaltbar, ohne auf echte Interviews zu warten.

Die Stufen sind mit `sim/seed_graph.py` erzeugt: echte Portraits, echte
Begriffslaengen aus dem Konferenzthema, KEIN LLM und keine Kosten. Das ist so
nah an der Realitaet wie es ohne echte Besucher geht.

🔴 KOPIEREN, NICHT VERSCHIEBEN. Die erste Fassung verschob `data/` nach
`data-echt/` und scheiterte mitten drin an `PermissionError: WinError 32` --
die laufende Station haelt `embeddings.sqlite3` offen. Zurueck blieb ein
Halbzustand: Datenbank in beiden Ordnern, Bilder nur in einem. Deshalb jetzt:
die echte Datenbank wird EINMAL kopiert (nie verschoben, nie geloescht), und
alles Weitere passiert nur noch an `data/`.

🔴 Vorher die Dienste beenden. Ein laufender Kern haelt Dateien offen; das
Umschalten scheitert sonst genau in dem Moment, in dem es schon halb passiert
ist.

Aufruf auf der Station:
    C:\\Users\\birk\\kollektivgedaechtnis\\.venv\\Scripts\\python.exe ^
        dichte-umschalten.py --stufe 40
    ... --stufe echt      (zurueck auf den Ausstellungsbetrieb)
    ... --stufe status    (was liegt gerade?)

Danach die Station starten (START-Verknuepfung).
"""

import argparse
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

BASIS = Path(r"C:\Users\birk\kollektivgedaechtnis")
AKTIV = BASIS / "data"
ECHT = BASIS / "data-echt"          # Sicherungskopie, wird NIE angetastet
STUFEN = BASIS / "data-dichte"      # data-dichte/1, /10, /40, /60
MARKE = AKTIV / ".dichte-stufe"


def zaehle(db: Path) -> str:
    if not db.exists():
        return "keine Datenbank"
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        p = con.execute("SELECT COUNT(*) FROM person").fetchone()[0]
        t = con.execute("SELECT COUNT(*) FROM term").fetchone()[0]
        e = con.execute("SELECT COUNT(*) FROM edge").fetchone()[0]
        con.close()
        return f"{p} Personen, {t} Begriffe, {e} Kanten"
    except sqlite3.Error as fehler:
        return f"nicht lesbar ({fehler})"


def bilder(ordner: Path) -> str:
    p = len(list((ordner / "photos").glob("*"))) if (ordner / "photos").is_dir() else 0
    q = len(list((ordner / "portraits").glob("*"))) if (ordner / "portraits").is_dir() else 0
    return f"{p} Fotos, {q} Portraits"


def status() -> None:
    stufe = MARKE.read_text().strip() if MARKE.exists() else "echt"
    print(f"AKTIV (data/):  Stufe {stufe}")
    print(f"                {zaehle(AKTIV / 'kg.db')}, {bilder(AKTIV)}")
    print()
    if ECHT.exists():
        print(f"Sicherung (data-echt/): {zaehle(ECHT / 'kg.db')}, {bilder(ECHT)}")
    else:
        print("Sicherung (data-echt/): noch keine -- entsteht beim ersten Umschalten")
    print()
    print("Verfuegbare Stufen:")
    if STUFEN.exists():
        for d in sorted((x for x in STUFEN.iterdir() if x.is_dir()),
                        key=lambda p: int(p.name) if p.name.isdigit() else 0):
            print(f"  {d.name:>4}: {zaehle(d / 'kg.db')}")
    else:
        print("  (keine)")


def dienste_laufen() -> bool:
    """Laeuft noch etwas, das Dateien in data/ offen haelt?"""
    try:
        aus = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-NetTCPConnection -State Listen -EA SilentlyContinue | "
             "Where-Object {$_.LocalPort -in 8800,8810} | Measure-Object).Count"],
            capture_output=True, text=True, timeout=30)
        return aus.stdout.strip() not in ("0", "")
    except Exception:
        return False   # im Zweifel weitermachen, der Kopiervorgang meldet sich selbst


def ersetze_inhalt(quelle: Path, ziel: Path) -> None:
    """Ersetzt den INHALT von ziel durch den von quelle -- ohne ziel zu loeschen.

    Den Ordner selbst stehen zu lassen ist der Punkt: Windows verweigert das
    Loeschen eines Ordners, in dem noch eine Datei offen ist, und dann steht
    man mit einem halb umgezogenen Zustand da (erlebt 2026-09-01).
    """
    ziel.mkdir(parents=True, exist_ok=True)
    for eintrag in ziel.iterdir():
        if eintrag.name == ".dichte-stufe":
            continue
        try:
            shutil.rmtree(eintrag) if eintrag.is_dir() else eintrag.unlink()
        except PermissionError as fehler:
            raise SystemExit(
                f"\nFEHLER: {eintrag.name} ist gesperrt ({fehler}).\n"
                "Die Station laeuft noch. Erst beenden (STOP-Verknuepfung oder\n"
                "station-stop.ps1), dann erneut umschalten. Es wurde nichts\n"
                "Unwiederbringliches getan -- data-echt/ ist unberuehrt.")
    for eintrag in quelle.iterdir():
        shutil.copytree(eintrag, ziel / eintrag.name) if eintrag.is_dir() \
            else shutil.copy2(eintrag, ziel / eintrag.name)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--stufe", required=True, help="1, 10, 40, 60, 'echt' oder 'status'")
    p.add_argument("--trotzdem", action="store_true",
                   help="auch umschalten, wenn Dienste laufen (nicht empfohlen)")
    args = p.parse_args()

    if args.stufe == "status":
        status()
        return 0

    if dienste_laufen() and not args.trotzdem:
        print(">>> Die Station laeuft (Port 8800/8810 lauscht).")
        print("Erst beenden -- sonst sind die Dateien gesperrt und das")
        print("Umschalten bricht mitten drin ab.")
        print("\n  STOP-Verknuepfung auf dem Desktop, oder:")
        print("  powershell -File C:\\Users\\SF-Tracking\\kg-start\\station-stop.ps1")
        return 1

    # Sicherung der echten Datenbank -- einmalig, per KOPIE.
    if not ECHT.exists():
        if MARKE.exists():
            print("FEHLER: data/ ist eine Stufe, aber data-echt/ fehlt. Abbruch.")
            return 1
        print("Sichere die echte Datenbank nach data-echt/ ...")
        shutil.copytree(AKTIV, ECHT)
        print(f"  gesichert: {zaehle(ECHT / 'kg.db')}, {bilder(ECHT)}")

    quelle = ECHT if args.stufe == "echt" else STUFEN / args.stufe
    if not (quelle / "kg.db").exists():
        print(f"Gibt es nicht: {quelle}")
        status()
        return 1

    ersetze_inhalt(quelle, AKTIV)
    if args.stufe == "echt":
        MARKE.unlink(missing_ok=True)
    else:
        MARKE.write_text(args.stufe, encoding="utf-8")

    print(f"\nAktiv: Stufe {args.stufe}")
    status()
    print("\n-> Station starten (START-Verknuepfung), dann am Regler einstellen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
