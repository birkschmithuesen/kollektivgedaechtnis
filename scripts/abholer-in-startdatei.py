"""Reiht den Abholer als Schritt 5 in kollektivtraum.bat ein.

Idempotent: laeuft die Datei schon mit Abholer, passiert nichts. Das ist
wichtig, weil die Startdatei am Ausstellungstag mehrfach angefasst werden
koennte und ein zweiter Lauf sonst zwei Abholer eintruege.

Die Nummerierung [n/5] wird zu [n/6] -- sie ist keine Zierde, sondern das,
woran man beim Zusehen erkennt, ob noch etwas kommt.
"""

import re
import sys
from pathlib import Path

PFAD = Path(r"C:\Users\SF-Tracking\kg-start\kollektivtraum.bat")

BLOCK = """
rem ---------------------------------------------------------------------
rem  5. Der Abholer. Holt Fotos, die von Handys OHNE Tailnet-Zugang beim
rem     oeffentlichen Spiegel eingeworfen wurden, und reicht sie an den
rem     Kern weiter. Handys IM Tailnet brauchen ihn nicht.
rem
rem     Wie der Spiegel darueber: faellt er aus, laeuft die Wand weiter,
rem     nur Fotos von aussen bleiben liegen. Deshalb steht er hier hinten.
rem ---------------------------------------------------------------------
if exist "%SPIEGEL%\\mirror\\abholer-start.bat" (
  if exist "%USERPROFILE%\\.kg-mirror-token" (
    echo   [5/6] Foto-Abholer  ^(Handys ohne Tailnet^)
    call :starte "Abholer" "%SPIEGEL%\\mirror\\abholer-start.bat" abholer
  ) else (
    echo   [5/6] Abholer UEBERSPRUNGEN: .kg-mirror-token fehlt.
  )
) else (
  echo   [5/6] Abholer UEBERSPRUNGEN: abholer-start.bat nicht vorhanden.
)

"""


def main() -> int:
    if not PFAD.exists():
        print(f"FEHLER: {PFAD} nicht gefunden", file=sys.stderr)
        return 1

    text = PFAD.read_text(encoding="cp1252", errors="replace")

    if "abholer-start.bat" in text:
        print("Abholer steht bereits in der Startdatei - nichts zu tun.")
        return 0

    # Anker: der Kommentarblock von Schritt 5 (den Anzeigen). Davor kommt
    # der neue Block. Bewusst am Kommentar und nicht an "[5/5]": der
    # Kommentar steht genau einmal, die Nummer mehrfach.
    anker = "rem ---------------------------------------------------------------------\nrem  5. Die Anzeigen."
    if anker not in text:
        print("FEHLER: Ankerstelle nicht gefunden - Datei von Hand pruefen.", file=sys.stderr)
        return 2

    neu = text.replace(anker, BLOCK.lstrip("\n") + anker.replace("5. Die Anzeigen.", "6. Die Anzeigen."), 1)

    # Nummerierung nachziehen: alles, was noch [n/5] heisst, wird [n/6].
    # Der neue Block ist schon [5/6] und bleibt unberuehrt.
    neu = re.sub(r"\[(\d)/5\]", lambda m: f"[{m.group(1)}/6]", neu)
    # Die Anzeigen waren [5/5] -> nach der Regel oben [5/6], muessen aber
    # [6/6] sein, weil der Abholer sich davor geschoben hat. Nur die
    # Fenster-Zeilen treffen, nicht den neuen Block.
    neu = neu.replace("[5/6] Fenster", "[6/6] Fenster")

    PFAD.write_text(neu, encoding="cp1252", errors="replace")
    print("Abholer als Schritt 5 eingetragen, Nummerierung auf /6 gesetzt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
