"""Ein bereits gefuehrtes Interview noch einmal auswerten.

🔴 WARUM ES DIESE DATEI GIBT (Birk, 2026-09-02): „ich habe bisher ein
Interview gemacht zum Test. das will ich jetzt neu analysieren lassen -- also
Begriffe und Bild." In der Nacht davor sind der Extraktions- und der
Traum-Prompt umgebaut worden; die schon ausgewertete Person traegt aber noch
das Ergebnis der alten Fassung. Einen Weg, das zu wiederholen, gab es nicht --
weder eine Route im Kern noch ein Skript.

WAS ES TUT: Es wirft die ALTE Auswertung dieser Person weg (Kanten, Zitat,
Name, verwaiste Begriffe) und laesst dann `kg.pipeline.process_interview`
laufen -- also GENAU den Weg, den ein frisches Interview auch geht. Es baut
die Auswertung nicht nach: eine zweite Fassung waere eine zweite Stelle, an
der es falsch werden kann, und sie wuerde beim naechsten Umbau vergessen.

WAS ES NICHT ANFASST: Foto und Portrait. Sie haengen an der Person, nicht an
der Auswertung -- ein neuer Zuschnitt waere eine andere Aufgabe
(kg/photos.py).

🔴 Vorher die Station beenden. Der laufende Kern haelt `kg.db` offen, und ein
Umschreiben mitten im Betrieb hinterlaesst einen Halbzustand. Das Skript
prueft es selbst -- dieselbe Wache wie in `dichte-umschalten.py`.

Aufruf:
    uv run python scripts/neu-analysieren.py --person p6
    uv run python scripts/neu-analysieren.py --letzte
    uv run python scripts/neu-analysieren.py --letzte --probe   # nur zeigen
"""

import argparse
import shutil
import socket
import sqlite3
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def dienste_laufen() -> bool:
    for port in (8800, 8810):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
    return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--person", help="Personen-Id, z. B. p6")
    p.add_argument("--letzte", action="store_true", help="die zuletzt befragte Person")
    p.add_argument("--probe", action="store_true",
                   help="nur anzeigen, was jetzt dasteht -- nichts aendern")
    p.add_argument("--trotzdem", action="store_true",
                   help="auch bei laufender Station (nicht empfohlen)")
    args = p.parse_args()
    if not args.person and not args.letzte:
        p.error("--person oder --letzte angeben")

    from kg.config import load_config
    from kg.db import connect
    from kg.embeddings import build_embedder
    from kg.export import write_graph_json
    from kg.llm import build_llm
    from kg.pipeline import process_interview
    from kg.store import Store
    from kg.transcript import TranscriptLog

    cfg = load_config(REPO / "config.toml")
    db = Path(cfg.data_dir) / "kg.db"
    if not db.exists():
        print(f"FEHLER: {db} gibt es nicht."); return 1

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    if args.letzte:
        zeile = con.execute(
            "SELECT id, started_at, stopped_at, name FROM person "
            "WHERE started_at IS NOT NULL ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    else:
        zeile = con.execute(
            "SELECT id, started_at, stopped_at, name FROM person WHERE id=?",
            (args.person,),
        ).fetchone()
    if not zeile:
        print("FEHLER: keine solche Person."); return 1
    pid, started_at, stopped_at, name = zeile
    if started_at is None or stopped_at is None:
        print(f"FEHLER: {pid} hat keine Interviewzeiten -- nichts zum Auswerten."); return 1

    alte_begriffe = [r[0] for r in con.execute(
        "SELECT t.label FROM term t JOIN edge e ON e.term_id=t.id WHERE e.person_id=? "
        "ORDER BY t.label", (pid,))]
    alte_zitate = [r[0] for r in con.execute(
        "SELECT text FROM quote WHERE person_id=?", (pid,))]
    con.close()

    print(f"\n  Person {pid}" + (f" ({name})" if name else " (ohne Namen)"))
    print(f"  Interview: {time.strftime('%H:%M:%S', time.localtime(started_at))}"
          f" bis {time.strftime('%H:%M:%S', time.localtime(stopped_at))}")
    print(f"  BISHER  Begriffe: {alte_begriffe or '—'}")
    print(f"          Zitat:    {alte_zitate[0][:90] + '…' if alte_zitate else '—'}")

    if args.probe:
        print("\n  (--probe: nichts geaendert)")
        return 0

    if dienste_laufen() and not args.trotzdem:
        print("\n>>> Die Station laeuft (Port 8800/8810 lauscht).")
        print("    Erst beenden: Strg-C im Startfenster oder ./scripts/stop-station.sh")
        return 1

    # Sicherung, bevor irgendetwas verschwindet. Eine Auswertung laesst sich
    # wiederholen, ein geloeschtes Zitat nicht.
    marke = time.strftime("%Y%m%d-%H%M%S")
    sicherung = db.with_name(f"kg.db.vor-neuanalyse-{marke}")
    shutil.copy2(db, sicherung)
    print(f"\n  Sicherung: {sicherung.name}")

    # Die alte Auswertung wegraeumen. Der Store hat dafuer keine Methoden --
    # Loeschen ist im Betrieb nie vorgesehen, und das soll auch so bleiben.
    con = sqlite3.connect(db)
    con.execute("DELETE FROM edge WHERE person_id=?", (pid,))
    con.execute("DELETE FROM quote WHERE person_id=?", (pid,))
    # Begriffe, die danach niemand mehr gesagt hat, sind Ueberbleibsel: Sie
    # stuenden weiter an der Wand, ohne dass jemand sie genannt haette.
    verwaist = con.execute(
        "DELETE FROM term WHERE id NOT IN (SELECT term_id FROM edge)"
    ).rowcount
    con.execute("UPDATE person SET name=NULL WHERE id=?", (pid,))
    con.commit()
    con.close()
    print(f"  alte Auswertung entfernt ({verwaist} Begriffe waren danach verwaist)")

    # Und jetzt der ECHTE Weg -- derselbe, den ein frisches Interview geht.
    # `Store` nimmt eine VERBINDUNG, keinen Pfad -- `kg.db.connect` oeffnet sie
    # so, wie der Kern es tut (row_factory, Schema, Nachruestungen).
    store = Store(connect(db))
    ergebnis = process_interview(
        store,
        cfg,
        build_llm(cfg),
        build_embedder(cfg),
        TranscriptLog(Path(cfg.data_dir) / "transcript.jsonl"),
        pid,
        started_at,
        stopped_at,
    )
    write_graph_json(store, cfg.graph_json_path)

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    neu = [r[0] for r in con.execute(
        "SELECT t.label FROM term t JOIN edge e ON e.term_id=t.id WHERE e.person_id=? "
        "ORDER BY t.label", (pid,))]
    zitat = con.execute("SELECT text FROM quote WHERE person_id=?", (pid,)).fetchone()
    neuer_name = con.execute("SELECT name FROM person WHERE id=?", (pid,)).fetchone()[0]
    con.close()

    print(f"\n  JETZT   Status:   {ergebnis.status}")
    print(f"          Begriffe: {neu or '— KEINE —'}")
    print(f"          Zitat:    {zitat[0] if zitat else '—'}")
    print(f"          Name:     {neuer_name or '—'}")
    print("\n  -> Station starten. Der Traum zieht sich den neuen Graphen selbst.")
    if not neu:
        print("  🔴 Keine Begriffe: die Person erscheint als leere Scheibe an der Wand.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
