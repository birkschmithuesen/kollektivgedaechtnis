"""Einmaliger Probelauf des Abholers auf dem Ausstellungsrechner.

Holt genau eine Runde ab und sagt, was passiert ist. Kein Dauerbetrieb --
dafuer ist `abholer-start.bat` da. Diese Datei belegt nur, dass die Kette
von DIESEM Rechner aus wirklich traegt: Token lesbar, Spiegel erreichbar,
Zielstation nimmt an.

Aufruf (im Fenster, mit dem venv der Station):
    C:\\Users\\birk\\kollektivgedaechtnis\\.venv\\Scripts\\python.exe pruefe-abholer.py [ziel-url]
"""

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\birk\kg-spiegel")

from mirror.abholer import Abholer  # noqa: E402

logging.basicConfig(level=logging.INFO, format="[abholer] %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> int:
    tokendatei = Path(os.environ["USERPROFILE"]) / ".kg-mirror-token"
    if not tokendatei.exists():
        print(f"FEHLER: {tokendatei} fehlt.")
        return 1

    token = tokendatei.read_text(encoding="utf-8").strip()
    spiegel = "https://kollektivgedaechtnis.flashclash.de"
    ziel = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8800"

    print(f"Spiegel:  {spiegel}")
    print(f"Station:  {ziel}")
    print()

    ab = Abholer(spiegel, token, ziel)

    try:
        wartend = ab._wartend()
    except Exception as fehler:
        print(f"FEHLER: Spiegel nicht erreichbar oder Token falsch: {fehler}")
        return 2

    print(f"Im Eingang: {len(wartend)} Foto(s)")
    if not wartend:
        print("Nichts abzuholen. (Am Handy ein Foto ueber den Spiegel schicken.)")
        return 0

    anzahl = ab.einmal()
    print()
    print(f"Zugestellt: {anzahl}")
    rest = ab._wartend()
    print(f"Rest im Eingang: {len(rest)}")
    if anzahl == 0 and rest:
        print("Nichts zugestellt -- laeuft die Station? (Kern auf 8800)")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
