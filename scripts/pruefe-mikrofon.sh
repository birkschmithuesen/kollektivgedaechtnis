#!/usr/bin/env bash
# Misst das EINGETRAGENE Mikrofon und sagt, ob es die VAD-Schwelle erreicht.
#
# 🔴 WARUM ES DIESE DATEI GIBT (2026-09-01, am Geraet):
# Ein Mikrofon, das nichts liefert, sieht im STT-Dienst aus wie eines, das
# funktioniert. Der Stream oeffnet sich fehlerfrei, `/status` sagt 200,
# `signal` sagt `true` -- und der Pegel liegt trotzdem unter der Schwelle, ab
# der die Spracherkennung ueberhaupt anspringt. Dann laeuft die Station den
# ganzen Tag und nimmt kein einziges Interview auf, ohne eine einzige
# Fehlermeldung.
#
# Real gemessen an diesem Abend:
#   MacBook Pro Microphone   RMS 0,027    -> ueber der Schwelle, erkennt
#   ZOOM AMS-24 Driver       RMS 0,00034  -> 30x DARUNTER, erkennt nie
# Beide meldeten `signal: true`.
#
# Aufruf (der STT-Dienst darf dabei NICHT laufen, er haelt das Geraet):
#     ./scripts/pruefe-mikrofon.sh
#     ./scripts/pruefe-mikrofon.sh 8      # 8 Sekunden statt 4
#
# Waehrend der Messung SPRECHEN -- gemessen wird, was ankommt, nicht was
# ankommen sollte.

set -u

KG_REPO="$(cd "$(dirname "$0")/.." && pwd)"
FB="${KG_FUNDUSBOT:-$HOME/projekte/fundusbot}"
PY="$FB/venv/bin/python"
SEKUNDEN="${1:-4}"

if [ ! -x "$PY" ]; then
  echo "FEHLER: $PY fehlt. Erst: $KG_REPO/scripts/einrichten-stt-mac.sh" >&2
  exit 1
fi

# Laeuft der Dienst noch, haelt er das Geraet und diese Messung misst nichts
# oder scheitert. Lieber frueh und deutlich abbrechen.
if curl -s -m 2 -o /dev/null "http://127.0.0.1:5051/status" 2>/dev/null; then
  echo "FEHLER: Der STT-Dienst laeuft (Port 5051) und haelt das Mikrofon." >&2
  echo "        Erst dort Strg-C, dann diese Probe." >&2
  exit 1
fi

exec "$PY" - "$FB" "$SEKUNDEN" <<'PYCODE'
import sys
from pathlib import Path

fb, sekunden = Path(sys.argv[1]), float(sys.argv[2])

# Denselben Wert lesen, den der Dienst liest -- nicht einen zweiten Ort
# pflegen. Der Tippfehler SST_ statt STT_ steht im fremden Code und ist hier
# absichtlich nachgebildet.
werte = {}
for zeile in (fb / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in zeile and not zeile.lstrip().startswith("#"):
        k, _, v = zeile.partition("=")
        werte[k.strip()] = v.strip()
gesucht = werte.get("SST_AUDIO_DEVICES", "")
rate = int(werte.get("STT_AUDIO_DEVICES_SR", "48000"))

import numpy as np
import sounddevice as sd

# `get_audio_device_index` im Dienst matcht als SUBSTRING. Hier genauso, sonst
# misst die Probe ein anderes Geraet als der Betrieb.
treffer = [(i, d) for i, d in enumerate(sd.query_devices())
           if d["max_input_channels"] > 0 and gesucht in d["name"]]
if not treffer:
    print(f"🔴 KEIN Eingang enthaelt {gesucht!r} (aus {fb}/.env).")
    print("   Verfuegbar:")
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            print(f"     [{i}] {d['name']}")
    raise SystemExit(1)

index, dev = treffer[0]
if len(treffer) > 1:
    print(f"⚠️  {gesucht!r} passt auf {len(treffer)} Eingaenge; der Dienst nimmt den ersten.")
print(f"Geraet:  [{index}] {dev['name']}  ({dev['max_input_channels']} Kanaele, {rate} Hz)")
print(f"Messe {sekunden:.0f} s — JETZT SPRECHEN …")

kanaele = min(2, dev["max_input_channels"])
roh = sd.rec(int(sekunden * rate), samplerate=rate, channels=kanaele,
             device=index, dtype="float32")
sd.wait()

# 0,01 ist `vad_energy_threshold`, die Vorgabe des Dienstes. Darunter springt
# die Erkennung nicht an -- das ist die Zahl, auf die es ankommt.
SCHWELLE = 0.01
print()
werte_pro_kanal = []
for k in range(kanaele):
    ch = roh[:, k]
    rms = float(np.sqrt((ch ** 2).mean()))
    spitze = float(np.abs(ch).max())
    werte_pro_kanal.append(rms)
    name = {0: "Kanal 0 (links / 'regie')", 1: "Kanal 1 (rechts / 'audience')"}[k]
    print(f"  {name:32}  RMS={rms:.5f}   Spitze={spitze:.5f}")

best = max(werte_pro_kanal)
print()
print(f"  VAD-Schwelle des Dienstes:        {SCHWELLE:.5f}")
print()
if best >= SCHWELLE:
    print(f"✅ Der Pegel traegt ({best / SCHWELLE:.1f}x ueber der Schwelle).")
    raise SystemExit(0)
print(f"🔴 ZU LEISE — {SCHWELLE / max(best, 1e-9):.0f}x UNTER der Schwelle.")
print("   Die Station wuerde laufen und NIE ein Interview aufnehmen.")
print("   Zu pruefen, in dieser Reihenfolge:")
print("     * Steckt das Mikrofon im richtigen Eingang?")
print("     * Gain am Geraet aufgedreht?")
print("     * Phantomspeisung (+48 V) an, falls Kondensatormikrofon?")
print("     * Kommt das Signal ueberhaupt in den USB-Weg (Direct/Mix am Geraet)?")
raise SystemExit(1)
PYCODE
