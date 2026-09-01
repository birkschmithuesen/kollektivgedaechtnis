"""Findet die realen Interviews im Transkript -- OHNE Inhalte auszugeben.

Das Transkript enthaelt echte Aussagen realer Personen (Namen, Aussagen,
Kontext). Es gehoert damit NICHT in den Sitzungskontext eines Agenten. Dieses
Skript gibt deshalb ausschliesslich STRUKTUR aus: wann, wie lange, wie viele
Zeichen, wie viele Sprecherwechsel -- keine einzige Textzeile.

Zweck: die Sitzungen finden, an denen sich der Analyse-Prompt real erproben
laesst (Birk, 2026-09-01: „kannst du das Interview reinholen, was wir gestern
gemacht haben, das war mit einer realen Person").

Aufruf auf der Station:
    C:\\Users\\birk\\kollektivgedaechtnis\\.venv\\Scripts\\python.exe ^
        finde-interviews.py
"""

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

PFAD = Path(r"C:\Users\birk\kollektivgedaechtnis\data\transcript.jsonl")

# Eine Pause laenger als das gilt als Grenze zwischen zwei Sitzungen.
# 180 s ist bewusst grosszuegig: lieber zwei Interviews zusammen zeigen als
# eines mitten im Nachdenken zerschneiden.
PAUSE = 180.0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pfad", default=str(PFAD))
    p.add_argument("--pause", type=float, default=PAUSE)
    args = p.parse_args()

    zeilen = []
    with open(args.pfad, encoding="utf-8") as f:
        for zeile in f:
            zeile = zeile.strip()
            if not zeile:
                continue
            try:
                d = json.loads(zeile)
            except json.JSONDecodeError:
                continue
            if d.get("type") != "final":
                continue
            zeilen.append(d)

    zeilen.sort(key=lambda d: float(d.get("timestamp", 0)))
    print(f"Finale Segmente insgesamt: {len(zeilen)}")
    if not zeilen:
        return 0

    # In Sitzungen zerlegen
    gruppen = []
    aktuell = [zeilen[0]]
    for vorher, jetzt in zip(zeilen, zeilen[1:]):
        if float(jetzt["timestamp"]) - float(vorher["timestamp"]) > args.pause:
            gruppen.append(aktuell)
            aktuell = [jetzt]
        else:
            aktuell.append(jetzt)
    gruppen.append(aktuell)

    print(f"Sitzungen (Pause > {args.pause:.0f} s): {len(gruppen)}")
    print("=" * 88)
    print(f"{'#':>3} {'Beginn':<17}{'Dauer':>8}{'Segm.':>7}{'Zeichen':>9}"
          f"{'Erkenner':>10}  Wechsel")

    for i, g in enumerate(gruppen, 1):
        beginn = datetime.fromtimestamp(float(g[0]["timestamp"]))
        dauer = float(g[-1]["timestamp"]) - float(g[0]["timestamp"])
        zeichen = sum(len(d.get("text", "")) for d in g)

        # Sprecherwechsel: die Station laeuft mit --channels regie, also nur
        # EIN Erkenner -- eine Trennung nach Sprecher gibt es im Log nicht.
        # Gezaehlt wird deshalb, wie oft der recognizer_id wechselt; steht dort
        # nur ein Wert, ist auch das eine Aussage: die Fragen der fragenden
        # Person stehen im selben Kanal wie die Antworten.
        erkenner = Counter(d.get("recognizer_id", "") or "-" for d in g)
        wechsel = sum(
            1 for a, b in zip(g, g[1:])
            if (a.get("recognizer_id") or "") != (b.get("recognizer_id") or "")
        )
        print(f"{i:>3} {beginn:%Y-%m-%d %H:%M}{dauer:>7.0f}s{len(g):>7}"
              f"{zeichen:>9}{len(erkenner):>10}  {wechsel}")

    print("=" * 88)
    print("Erkenner je Sitzung > 1 hiesse getrennte Kanaele fuer Frage und Antwort.")
    print("Steht dort ueberall 1, laufen beide Stimmen durch denselben Kanal --")
    print("dann MUSS der Analyse-Prompt die Trennung leisten, nicht die Technik.")
    print()
    print("Fuer den Prompt-Test die Nummer einer laengeren Sitzung waehlen und")
    print("`pruefe-analyse-prompt.py --sitzung <n>` aufrufen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
