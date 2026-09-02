"""`token-verteilen.sh datei` muss auch auf dem Mac durchlaufen.

🔴 WARUM (2026-09-02): Der `datei`-Zweig meldet am Ende Rechte und Groesse der
geschriebenen Datei — mit `stat -c '%a'`. Das ist die GNU-Form; macOS bringt
BSD-`stat` mit und antwortet darauf

    stat: illegal option -- c

Wegen `set -euo pipefail` bricht das Skript daran ab. Die Datei ist zu diesem
Zeitpunkt schon geschrieben, der Aufrufer sieht aber einen Fehler und weiss
nicht, ob das Token nun liegt oder nicht — die schlechteste aller Auskuenfte
bei einem Geheimnis.

Dieselbe Klasse Fehler wie in `dichte-umschalten.py` (feste Windows-Pfade) und
`pruefe-leere-extraktion.py`: auf dem Rechner unbrauchbar, auf dem es gebraucht
wird.

Der Test faehrt den Zweig ECHT, gegen eine Attrappe von `ssh` — das Token
verlaesst dabei nichts und keine Verbindung wird aufgebaut.
"""

from __future__ import annotations

import os
import stat as stat_modul
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKRIPT = REPO / "scripts" / "token-verteilen.sh"


def test_das_skript_ist_gueltig():
    fertig = subprocess.run(["bash", "-n", str(SKRIPT)], capture_output=True, text=True)
    assert fertig.returncode == 0, fertig.stderr


def test_der_datei_zweig_laeuft_durch_und_schreibt_600(tmp_path):
    # Eine ssh-Attrappe, die das „Token" liefert, ohne dass etwas nach draussen geht.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "ssh").write_text(
        "#!/bin/sh\nprintf 'attrappen-token-abcdef\\n'\n", encoding="utf-8"
    )
    (bin_dir / "ssh").chmod(0o755)

    ziel = tmp_path / "kg-mirror-token"
    fertig = subprocess.run(
        [str(SKRIPT), "datei", str(ziel)],
        capture_output=True, text=True, cwd=REPO,
        env={**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/local/bin"},
    )

    assert fertig.returncode == 0, (
        f"der Zweig bricht ab:\nSTDOUT {fertig.stdout}\nSTDERR {fertig.stderr}"
    )
    assert ziel.exists(), "die Datei wurde nicht geschrieben"
    rechte = stat_modul.S_IMODE(ziel.stat().st_mode)
    assert rechte == 0o600, f"Rechte {oct(rechte)} statt 0o600 — ein Geheimnis"
    inhalt = ziel.read_text(encoding="utf-8")
    assert inhalt.startswith("KG_MIRROR_TOKEN="), inhalt[:40]
    # Und er sagt WAS er getan hat, ohne Fehlerrauschen. Die erste Fassung
    # dieses Tests prueft nur den Rueckgabecode — und war damit blind: `set -e`
    # greift bei einem `stat` in einer Kommandosubstitution nicht, das Skript
    # lief durch und meldete „geschrieben: … (,  39 Bytes)" mit einer
    # stat-Fehlermeldung davor. Bei einem Geheimnis ist das die schlechteste
    # Auskunft: die Datei liegt, und der Aufrufer glaubt es nicht.
    assert "geschrieben" in fertig.stdout
    assert "600" in fertig.stdout, f"die Rechte fehlen in der Meldung: {fertig.stdout!r}"
    assert "illegal option" not in fertig.stderr, fertig.stderr
    assert "usage: stat" not in fertig.stderr, fertig.stderr
