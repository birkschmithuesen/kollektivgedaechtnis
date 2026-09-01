#!/usr/bin/env bash
# Startet die Spracherkennung auf dem MacBook (Port 5051).
#
# Das Gegenstueck zu `kg-start\dienste\dienst-stt.bat` vom Windows-Rechner.
# `start-mac.sh` startet diesen Dienst NICHT mit — er laeuft in einem eigenen
# Fenster, damit man seine Ausgabe sieht und ihn getrennt neu starten kann.
#
# Aufruf:
#     ./scripts/start-stt-mac.sh
#     ./scripts/start-stt-mac.sh --geraete     # nur Mikrofone auflisten
#
# Beenden: Strg-C in diesem Fenster.

set -u

KG_REPO="$(cd "$(dirname "$0")/.." && pwd)"
FB="${KG_FUNDUSBOT:-$HOME/projekte/fundusbot}"
PY="$FB/venv/bin/python"

if [ ! -x "$PY" ]; then
  echo "FEHLER: $PY fehlt." >&2
  echo "        Erst einrichten:  $KG_REPO/scripts/einrichten-stt-mac.sh" >&2
  exit 1
fi
if [ ! -f "$FB/.env" ]; then
  echo "FEHLER: $FB/.env fehlt — der Dienst stirbt sonst beim Start mit" >&2
  echo "        KeyError: 'STT_HOST'. Erst einrichten-stt-mac.sh laufen lassen." >&2
  exit 1
fi

cd "$FB" || exit 1

# --- Nur die Geraete zeigen --------------------------------------------------
# `get_audio_device_index` matcht den .env-Wert als SUBSTRING gegen den Namen.
# Wer hier den falschen Namen eintraegt, bekommt einen ValueError beim Start —
# laut und frueh, aber nur wenn man weiss, wo man nachsieht.
if [ "${1:-}" = "--geraete" ]; then
  "$PY" - <<'PYCODE'
import sounddevice as sd
print("Eingaenge (nur die zaehlen):")
for i, d in enumerate(sd.query_devices()):
    if d["max_input_channels"] > 0:
        print(f"  [{i}] {d['name']}  ({d['max_input_channels']} Kanaele, "
              f"{int(d['default_samplerate'])} Hz)")
print("\nDen passenden NAMEN (oder ein eindeutiges Stueck davon) in")
print("~/projekte/fundusbot/.env unter SST_AUDIO_DEVICES eintragen,")
print("und die Rate daneben unter STT_AUDIO_DEVICES_SR.")
PYCODE
  exit 0
fi

mkdir -p "$HOME/kg-logs"
LOG="$HOME/kg-logs/stt.log"

echo "Spracherkennung — Infomaniak Whisper (Schweiz), Port 5051"
echo "  fundusbot: $(git -C "$FB" rev-parse --abbrev-ref HEAD) @ $(git -C "$FB" log --oneline -1 | cut -c1-40)"
echo "  Log:       $LOG"
echo ""

# 🔴 KEIN `--channels regie`. Der Windows-Befehl hat es, hier waere es falsch.
# Belegt im Quelltext (fundusapps/stt_server/sr.py):
#   * `_CHANNEL_IDX = {'left':0,'right':1,'regie':0,'audience':1}` — `regie`
#     ist nur ein NAME fuer Kanal 0 eines STEREO-Stroms.
#   * In `__enter__` erzwingt jedes bekannte Kanallabel `num_channels = 2`.
# Auf dem Windows-Rechner haengt eine Fireface UFX III mit zwei Kanaelen
# (13/14 ueber ASIO) daran. Das eingebaute MacBook-Mikrofon ist MONO — die
# Anforderung von zwei Kanaelen scheitert im PortAudio-Stream.
# Ohne `--channels` laeuft genau ein Recognizer mit `recognizer_id="0"`.
#
# Fuer den Core ist das folgenlos, nachgesehen statt vermutet:
# `kg/stt_client.py::_dispatch` verzweigt allein auf `type == "final"` und
# liest `recognizer_id` nie; `kg/transcript.py::from_dict` nimmt jeden Wert
# entgegen. Ein Interview ueber ein Mono-Mikrofon kommt also vollstaendig an.
#
# Ein externes Stereo-Interface am Mac? Dann `--channels regie audience`
# ANHAENGEN (zwei Werte, sonst wieder Mono-Konflikt).
# Kein `exec ... | tee`: eine Pipeline laeuft in einer Subshell, `exec` ersetzt
# dann nicht diese Shell, und der Exit-Code waere der von `tee` (immer 0) —
# ein abgestuerzter Dienst saehe aus wie ein sauberes Ende.
set -o pipefail
"$PY" -m fundusapps.stt_server \
    --language de \
    infomaniak-whisper \
    --api-key-env HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY \
    "$@" 2>&1 | tee -a "$LOG"
CODE=${PIPESTATUS[0]}

echo ""
if [ "$CODE" -ne 0 ]; then
  echo "🔴 Die Spracherkennung ist mit Code $CODE beendet." >&2
  echo "   Ohne sie gibt es kein Interview. Log: $LOG" >&2
else
  echo "Spracherkennung beendet."
fi
exit "$CODE"
