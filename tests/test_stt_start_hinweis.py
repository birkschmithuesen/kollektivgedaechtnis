"""Ein fehlendes Mikrofon soll sagen, was zu tun ist.

🔴 WARUM (2026-09-02, beim Abschluss der Nacht): Birk hatte das ZOOM AMS-24
zum Entwickeln abgesteckt. `start-station.sh` meldete daraufhin korrekt und
laut, dass die Spracherkennung gestorben ist -- mit einem Python-Traceback und
der Zeile

    ValueError: Audio device 'ZOOM AMS-24' not found. Available devices: [...]

Das ist die richtige Diagnose und die falsche Hilfe. Wer um 09:00 vor der
Station steht, braucht keinen Stacktrace, sondern die zwei Wege: Geraet
anstecken, oder auf das eingebaute Mikrofon umstellen.

Der Test prueft den HINWEIS, nicht den Wortlaut der fremden Fehlermeldung --
die steht in `meredityman/fundusbot` und gehoert uns nicht.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKRIPT = REPO / "scripts" / "start-stt-mac.sh"


def test_das_skript_ist_gueltig():
    fertig = subprocess.run(["bash", "-n", str(SKRIPT)], capture_output=True, text=True)
    assert fertig.returncode == 0, fertig.stderr


def test_bei_fehlendem_geraet_nennt_es_beide_wege():
    text = SKRIPT.read_text(encoding="utf-8")
    # Der Zweig, der auf die fremde Fehlermeldung reagiert.
    assert "not found" in text, "das Skript erkennt den Fall gar nicht"
    # Weg 1: das Geraet auflisten, um zu sehen, was wirklich da ist.
    assert "--geraete" in text
    # Weg 2: umstellen, und zwar mit dem Ort, an dem es steht.
    assert "SST_AUDIO_DEVICES" in text
    assert ".env" in text


def test_es_verrät_dabei_keinen_schluessel():
    """Der Zweig druckt Umgebung — der Infomaniak-Schluessel darf nie dabei
    sein. Der Dienst selbst maskiert ihn; unser Hinweis darf ihn nicht wieder
    hervorholen."""
    text = SKRIPT.read_text(encoding="utf-8")
    assert "$HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY" not in text
    assert "cat \"$FB/.env\"" not in text
