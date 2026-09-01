#!/usr/bin/env bash
# Richtet den STT-Dienst (Spracherkennung) auf dem MacBook ein.
#
# 🔴 WARUM ES DIESE DATEI GIBT:
# Der Erkenner liegt NICHT in diesem Repo, sondern im fremden Repo
# `meredityman/fundusbot`. Auf dem Windows-Rechner startete ihn
# `kg-start\dienste\dienst-stt.bat`; fuer den Mac gab es dafuer nichts —
# und `start-mac.sh` startet ihn NICHT mit. Ohne ihn gibt es kein Interview.
#
# Aufruf (einmalig, danach nur noch start-stt-mac.sh):
#     ./scripts/einrichten-stt-mac.sh
#
# Was es NICHT tut: Schluessel setzen. Der Schluessel steht in der `.env` der
# STATION (dieses Repo) und wird von hier nur GELESEN, nicht kopiert.

set -euo pipefail

KG_REPO="$(cd "$(dirname "$0")/.." && pwd)"
FB="${KG_FUNDUSBOT:-$HOME/projekte/fundusbot}"
FB_REPO="https://github.com/meredityman/fundusbot.git"
# 🔴 Dieser Branch, nicht `win_fundusfantasma-dev-clean`: nachgesehen am
# 2026-09-02 mit `git ls-tree` — auf dem clean-Branch fehlt
# `infomaniak_whisper_backend.py` vollstaendig. `docs/stt-contract.md` nennt
# oben noch den clean-Branch; das gilt fuer den ElevenLabs-Vertrag.
FB_BRANCH="${KG_FUNDUSBOT_BRANCH:-eu-souveraen/infomaniak-whisper}"

schritt() { echo ""; echo "=== $* ==="; }
fehler()  { echo "FEHLER: $*" >&2; exit 1; }

schritt "1/6  Voraussetzungen"
command -v git >/dev/null 2>&1 || fehler "git fehlt. Erst scripts/einrichten-mac.sh laufen lassen."
command -v python3 >/dev/null 2>&1 || fehler "python3 fehlt."
echo "  git:     $(git --version)"
echo "  python3: $(python3 --version)"

# PortAudio ist eine C-Bibliothek und kommt NICHT mit dem pip-Paket
# `sounddevice` mit. Fehlt sie, laesst sich sounddevice zwar installieren,
# scheitert aber beim Import mit "PortAudio library not found" — ein
# Fehlerbild, das wie ein kaputtes Python aussieht, es aber nicht ist.
if ! brew list portaudio >/dev/null 2>&1; then
  echo "  portaudio: fehlt — wird installiert"
  brew install portaudio
else
  echo "  portaudio: da"
fi

schritt "2/6  fundusbot holen"
if [ -d "$FB/.git" ]; then
  echo "  liegt schon da: $FB"
  git -C "$FB" fetch --quiet origin || echo "  (fetch uebersprungen)"
else
  mkdir -p "$(dirname "$FB")"
  git clone "$FB_REPO" "$FB"
fi
git -C "$FB" checkout "$FB_BRANCH" 2>/dev/null || fehler \
  "Branch '$FB_BRANCH' nicht gefunden. Ohne ihn gibt es das Infomaniak-Backend nicht."
echo "  Branch: $(git -C "$FB" rev-parse --abbrev-ref HEAD)"
echo "  Stand:  $(git -C "$FB" log --oneline -1)"

# Beleg statt Vertrauen: liegt die Backend-Datei wirklich da?
[ -f "$FB/fundusapps/stt_server/backends/infomaniak_whisper_backend.py" ] || fehler \
  "infomaniak_whisper_backend.py fehlt in $FB — falscher Branch?"
echo "  Infomaniak-Backend: vorhanden"

schritt "3/6  Python-Umgebung fuer den Dienst"
# Eigene venv, NICHT die des Kollektivgedaechtnis-Repos: fundusbot bringt
# eigene Pins mit (numpy 1.26) und darf der Station nichts umbiegen.
if [ ! -d "$FB/venv" ]; then
  python3 -m venv "$FB/venv"
fi
PY="$FB/venv/bin/python"
"$PY" -m pip install --quiet --upgrade pip

# 🔴 NUR diese sieben Pakete — nicht `requirements/requirements.txt`.
# Die volle Liste zieht torch, TTS, faster-whisper und CUDA-Zeug (mehrere GB)
# und ist am Ausstellungstag ein Blocker. Ermittelt am 2026-09-02, indem jeder
# Import im STT-Pfad einzeln nachgesehen wurde (__main__, app, args, sr, vad,
# events, settings, botland_callbacks, backends/*, common/turnid).
#
# `vosk` steht hier, obwohl wir Infomaniak nutzen: `backends/__init__.py`
# importiert VoskBackend EAGER (Zeile 4), nicht lazy wie die anderen. Ohne das
# Paket scheitert schon `get_backend_class`.
#
# 🔴 Der Pin 0.3.44 ist Pflicht, kein Vorsichtsmass: die aktuelle vosk 0.3.45
# hat auf PyPI KEIN macOS-Wheel (nachgesehen: nur linux_armv7l, aarch64,
# x86_64, win_amd64). `pip install vosk` scheitert damit auf dem Mac. 0.3.44
# ist die letzte Version mit `macosx_10_6_universal2`.
schritt "4/6  Abhaengigkeiten (schlank — keine 3 GB Modelle)"
"$PY" -m pip install --quiet \
  "flask==3.1.0" \
  "python-dotenv==1.0.1" \
  "sounddevice==0.5.1" \
  "samplerate==0.2.4" \
  "numpy==1.26.4" \
  "requests==2.32.3" \
  "vosk==0.3.44"
echo "  installiert."

schritt "5/6  .env des Dienstes"
# 🔴 Diese Datei ist PFLICHT, nicht Komfort. `args.py` liest STT_HOST,
# STT_PORT, SST_AUDIO_DEVICES und STT_AUDIO_DEVICES_SR mit HARTEM
# Schluesselzugriff (config['STT_HOST']). Fehlt die .env, stirbt der Dienst
# beim IMPORT mit `KeyError: 'STT_HOST'` — nachgestellt am 2026-09-02.
# Beachte den Tippfehler im fremden Code: SST_AUDIO_DEVICES, nicht STT_.
if [ -f "$FB/.env" ]; then
  echo "  $FB/.env: da (wird nicht angefasst)"
else
  # Den Infomaniak-Schluessel aus der Station lesen. Er wird NICHT ausgegeben.
  KEY=""
  if [ -f "$KG_REPO/.env" ]; then
    KEY="$(sed -n 's/^HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY=//p' "$KG_REPO/.env" | head -1)"
  fi
  if [ -z "$KEY" ]; then
    echo "  🔴 Kein HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY in $KG_REPO/.env gefunden."
    echo "     Die .env wird trotzdem angelegt — Schluessel danach von Hand eintragen."
  fi
  cat > "$FB/.env" <<ENVDATEI
# Vom Kollektivgedaechtnis erzeugt (scripts/einrichten-stt-mac.sh).
# Diese vier Werte sind PFLICHT: args.py liest sie mit hartem Zugriff,
# ohne sie stirbt der Dienst beim Import mit KeyError.
STT_HOST=127.0.0.1
STT_PORT=5051

# ACHTUNG Tippfehler im fremden Code: SST_, nicht STT_.
# Der Wert ist ein SUBSTRING des Geraetenamens: get_audio_device_index matcht
# mit dem Python-Operator "in". KEINE Backticks in diesem Heredoc — sein
# Begrenzer ist unquotiert (das braucht \$KEY), also fuehrt die Shell alles
# zwischen Backticks als Kommando aus. Genau das passierte am 2026-09-01:
# "syntax error near unexpected token 'in'", und die Kommentarzeile landete
# verstuemmelt in der Datei. Die WERTE waren nicht betroffen.
# Mit start-stt-mac.sh --geraete die verfuegbaren Namen auflisten.
SST_AUDIO_DEVICES=MacBook
# Mac-Eingaenge laufen praktisch immer auf 48000, nicht 44100 wie die
# Fireface auf dem Windows-Rechner. Der Recognizer resampled selbst auf 16 k.
STT_AUDIO_DEVICES_SR=48000

# Vier Dinge an einem Schluessel: Analyse, Weckwort, Embeddings, Spracherkennung.
HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY=$KEY

# Wohin der Mikrofonschalter das Interviewsignal meldet. Leer = nirgendwohin.
KG_URL=http://127.0.0.1:8800
ENVDATEI
  chmod 600 "$FB/.env"
  echo "  $FB/.env angelegt (Rechte 600)."
fi

schritt "6/6  Probe: laesst sich der Dienst ueberhaupt laden?"
# Kein Netz, kein Mikrofon — nur die Frage, ob Importe und Argumente stehen.
# Genau die zwei Fehler, die sonst erst vor Publikum auffallen.
if ( cd "$FB" && "$PY" -c "
import sys
sys.argv = ['stt', 'infomaniak-whisper', '--language', 'de']
from fundusapps.stt_server.args import args
from fundusapps.stt_server.backends import get_backend_class
k = get_backend_class(args.backend)
print('  Backend geladen:', k.__name__)
print('  Adresse:', args.host, args.port)
import sounddevice as sd
print('  Audiogeraete sichtbar:', len(sd.query_devices()))
" 2>&1 | grep -v "^{" ); then
  echo ""
  echo "  ✅ Der Dienst ist startklar."
else
  echo ""
  echo "  🔴 Die Probe ist gescheitert — Meldung oben. NICHT ignorieren:"
  echo "     genau das waere sonst um 10:00 der Ausfall."
  exit 1
fi

cat <<HINWEIS

=========================================================
  Starten (in einem EIGENEN Terminalfenster, vor start-mac.sh):
      $KG_REPO/scripts/start-stt-mac.sh

  Mikrofon pruefen / Geraetenamen auflisten:
      $KG_REPO/scripts/start-stt-mac.sh --geraete

  Laeuft er? (im dritten Fenster)
      curl -s http://127.0.0.1:5051/status
=========================================================
HINWEIS
