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

# --- Schluessel aus der .env des Projekts -----------------------------------
# Vor dem `cd`, denn danach ist das Arbeitsverzeichnis das FREMDE Repo.
# `--api-key-env NAME` liest den Schluessel aus der UMGEBUNG, nicht aus einer
# Datei -- ohne dieses Laden findet der Dienst ihn nur, wenn ihn jemand vorher
# von Hand exportiert hat (beim Sammelstart tut das `start-station.sh`, beim
# Einzelstart aus einem frischen Fenster niemand).
if [ -f "$KG_REPO/.env" ]; then
  # shellcheck disable=SC1091
  set -a; . "$KG_REPO/.env"; set +a
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

# --- Mikrofonschalter (Birk, 2026-09-01: „muss mit dem Mikrofongate starten")
# Mit dem Schalter entscheidet der EINGANGSPEGEL, ob erkannt wird: unter der
# Schwelle pausiert die Erkennung und es geht ein Interview-STOPP an den Kern,
# darueber laeuft sie und es geht ein START. Das ist der Bedienweg am Mikrofon
# selbst -- niemand muss ans Bedienpult.
#
# Der Empfaenger ist `KG_URL` aus der .env des Dienstes (dort auf
# http://127.0.0.1:8800). Fehlt der Wert, schaltet das Gate weiterhin die
# Erkennung und zeigt seinen Zustand an, nur meldet es niemandem etwas --
# `args.py` sagt das beim Start selbst.
#
# Die drei Schwellen (`--mic-gate-threshold` 0,002, Hysterese 0,5, Entprellung
# 1500 ms) werden BEWUSST nicht mitgegeben: sie werden vor Ort eingemessen und
# in settings.py gespeichert, und ein getippter Wert schlaegt den gespeicherten.
# Wer hier eine Zahl fest verdrahtet, kann sie an der Operator-Seite nicht mehr
# aendern. Einmessen: Pegel auf http://127.0.0.1:5051/operator ablesen, waehrend
# der Schalter AUS ist -- der richtige Wert liegt knapp darueber.
#
# Abschalten fuer eine Sitzung:  KG_MIC_GATE=0 ./scripts/start-stt-mac.sh
GATE=(--mic-gate)
if [ "${KG_MIC_GATE:-1}" = "0" ]; then
  GATE=()
  echo "HINWEIS: Mikrofonschalter AUS (KG_MIC_GATE=0) -- es wird durchgehend erkannt."
fi

# --- Welcher Anbieter erkennt? ----------------------------------------------
# 🔴 EU-SOUVERAENITAET IST DIE VOREINSTELLUNG, NICHT DIE AUSNAHME.
# Die ganze Kette laeuft bewusst in Europa: Infomaniak in Genf fuer Sprache,
# Analyse und Embeddings, BFL in der EU fuer Bilder. Der Zweig im fremden Repo
# heisst `eu-souveraen/infomaniak-whisper`. Das ist keine Vorliebe, das ist die
# Zusage an Menschen, die hier ihre Stimme hergeben.
#
# ElevenLabs sitzt in den USA. Deshalb ist der Fallback ein SCHALTER, kein
# Automatismus:
#   * Ein automatischer Wechsel wuerde bei jedem Aussetzer stillschweigend
#     Stimmen ausserhalb der EU verarbeiten -- niemand haette entschieden.
#   * Das Backend wird ausserdem beim START gewaehlt und laesst sich waehrend
#     des Laufs gar nicht tauschen; ein "Fallback im Fehlerfall" gaebe es
#     technisch nur als Neustart.
# Also dieselbe Regel wie beim Spiegel-Uploader: getippt = entschieden.
#
# 2026-09-02, gemessen: Infomaniaks Whisper (`/1/ai/…/audio/transcriptions`)
# antwortete ueber zehn Minuten mit 502/503 und einer HTML-Seite "service
# unavailable"; 26 erkannte Aeusserungen, 0 Transkripte. LLM und Embeddings
# desselben Anbieters (`/2/ai/…`) liefen dabei tadellos -- der Ausfall betraf
# nur das Whisper-Produkt. Genau dafuer gibt es diesen Schalter.
#
#     KG_STT=elevenlabs ./scripts/start-stt-mac.sh
ANBIETER="${KG_STT:-infomaniak}"

case "$ANBIETER" in
  infomaniak)
    BACKEND=(infomaniak-whisper --api-key-env HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY)
    echo "  Anbieter:  Infomaniak Whisper (Genf) — in der EU"
    ;;
  elevenlabs)
    if [ -z "${ELEVENLABS_API_KEY:-}" ]; then
      echo "FEHLER: ELEVENLABS_API_KEY fehlt." >&2
      echo "        Schluessel holen: https://elevenlabs.io/app/settings/api-keys" >&2
      echo "        Dann in $KG_REPO/.env eintragen:" >&2
      echo "          ELEVENLABS_API_KEY=sk_…" >&2
      exit 1
    fi
    # `scribe_v2_realtime` streamt und schneidet die Aeusserungen serverseitig
    # selbst zu -- der VAD aus `vad.py` wird dabei nicht gebraucht. Der
    # Mikrofonschalter dagegen schon: er sitzt in `_channel_parent`
    # (args.py:90) und gilt fuer beide Backends gleich.
    BACKEND=(elevenlabs-scribe --api-key-env ELEVENLABS_API_KEY)
    echo "  Anbieter:  🔴 ElevenLabs Scribe — USA, NICHT in der EU."
    echo "             Stimmen der Besucher verlassen damit den EU-Raum."
    echo "             Zurueck: dieses Fenster beenden und ohne KG_STT starten."
    ;;
  *)
    echo "FEHLER: KG_STT='$ANBIETER' kenne ich nicht." >&2
    echo "        Moeglich: infomaniak (Vorgabe) oder elevenlabs" >&2
    exit 1
    ;;
esac
echo ""

# --- Vorabprobe: antwortet der Anbieter ueberhaupt? --------------------------
# 🔴 WARUM (2026-09-02, real passiert): Bei einem Whisper-Ausfall startet der
# Dienst voellig normal. `/status` sagt "running", der Sammelstart setzt ein
# gruenes Haekchen, der Pegel schlaegt aus, das Gate oeffnet, ein Interview
# beginnt -- und kein einziges Wort kommt an. Der Fehler steht nur im Log, und
# zwar unter 17.000 Zeilen `GET /levels`. Es hat eine Viertelstunde gekostet,
# das zu finden.
#
# Geprueft wird die GANZE Kette, nicht nur das Absenden: der Endpunkt gibt
# zuerst eine `batch_id` zurueck und das Ergebnis kommt erst beim Abholen.
# Waehrend des Ausfalls lieferte das blosse Absenden zeitweise 200 -- eine
# Probe, die dort aufhoert, haette "alles gut" gemeldet.
#
# Sie WARNT nur und blockiert nie: ein Anbieter, der gerade flackert, darf den
# Start nicht verhindern. Abschalten: KG_STT_PROBE=0
if [ "$ANBIETER" = "infomaniak" ] && [ "${KG_STT_PROBE:-1}" != "0" ]; then
  probe_wav=$(mktemp -t kgprobe).wav
  "$PY" - "$probe_wav" <<'PYCODE' 2>/dev/null
import sys, wave, struct, math
w = wave.open(sys.argv[1], "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
w.writeframes(b"".join(struct.pack("<h", int(6000 * math.sin(2*math.pi*300*i/16000))) for i in range(4800)))
w.close()
PYCODE
  urteil=$(
    antwort=$(curl -s --max-time 20 -H "Authorization: Bearer $HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY" \
              -F "file=@$probe_wav;type=audio/wav" -F "model=whisper" -F "language=de" \
              "https://api.infomaniak.com/1/ai/110416/openai/audio/transcriptions" 2>/dev/null)
    batch=$(printf '%s' "$antwort" | "$PY" -c "import json,sys; print(json.load(sys.stdin).get('batch_id',''))" 2>/dev/null)
    if [ -z "$batch" ]; then echo "kein-batch"; else
      for _ in 1 2 3 4 5 6; do
        st=$(curl -s --max-time 15 -H "Authorization: Bearer $HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY" \
             "https://api.infomaniak.com/1/ai/110416/results/$batch" 2>/dev/null \
             | "$PY" -c "import json,sys; d=json.load(sys.stdin); d=d.get('data',d); print(str(d.get('status','')).lower())" 2>/dev/null)
        # Kein `case`: bash 3.2 (macOS) beendet die $( )-Ersetzung an der
        # Klammer des case-Musters -- "syntax error near unexpected token ;;".
        if [ "$st" = "ok" ] || [ "$st" = "done" ] || [ "$st" = "success" ] || [ "$st" = "finished" ]; then
          echo "gut"; break
        fi
        sleep 2
      done
    fi
  )
  rm -f "$probe_wav"
  if [ "$urteil" != "gut" ]; then
    echo "🔴 Infomaniak Whisper antwortet NICHT ($urteil)." >&2
    echo "   Der Dienst startet trotzdem — Pegel, Gate und Interview laufen," >&2
    echo "   aber es kommt KEIN Text an. Das sieht von aussen wie 'alles gut'." >&2
    echo "" >&2
    echo "   Ausweichen (🔴 USA, verlaesst den EU-Raum):" >&2
    echo "     KG_STT=elevenlabs ./scripts/start-stt-mac.sh" >&2
    echo "   Nachsehen, ob er zurueck ist:" >&2
    echo "     ./scripts/start-stt-mac.sh --probe" >&2
    echo "" >&2
  fi
fi

set -o pipefail
"$PY" -m fundusapps.stt_server \
    --language de \
    "${BACKEND[@]}" \
    "${GATE[@]}" \
    "$@" 2>&1 | tee -a "$LOG"
CODE=${PIPESTATUS[0]}

echo ""
if [ "$CODE" -ne 0 ]; then
  echo "🔴 Die Spracherkennung ist mit Code $CODE beendet." >&2
  echo "   Ohne sie gibt es kein Interview. Log: $LOG" >&2
  # 🔴 DER HAEUFIGSTE FALL, und der einzige mit einer klaren Handlung:
  # Das eingetragene Geraet ist nicht angesteckt. Der fremde Dienst sagt dazu
  # `ValueError: Audio device '…' not found` samt Traceback — richtige
  # Diagnose, falsche Hilfe. Wer um 09:00 vor der Station steht, braucht
  # keinen Stacktrace, sondern die zwei Wege.
  #
  # Gegen die fremde MELDUNG geprueft und nicht gegen den Rueckgabecode: der
  # ist 1 fuer alles. Aendert `meredityman/fundusbot` den Wortlaut, faellt der
  # Hinweis weg — schlimmer als vorher wird es dadurch nicht.
  if grep -q "Audio device .* not found" "$LOG" 2>/dev/null; then
    GESUCHT=$(sed -n "s/.*Audio device '\([^']*\)' not found.*/\1/p" "$LOG" | tail -1)
    echo "" >&2
    echo "   Das eingetragene Mikrofon (${GESUCHT:-?}) ist nicht da." >&2
    echo "   Zwei Wege:" >&2
    echo "     1. Geraet anstecken und dieses Fenster neu starten." >&2
    echo "        Was gerade da ist:  ./scripts/start-stt-mac.sh --geraete" >&2
    echo "     2. Auf ein anderes umstellen — in $FB/.env:" >&2
    echo "          SST_AUDIO_DEVICES=MacBook      (eingebautes Mikrofon)" >&2
    echo "          STT_AUDIO_DEVICES_SR=48000     (dessen Rate)" >&2
    echo "        Der Wert ist ein SUBSTRING des Geraetenamens." >&2
    echo "        Danach den Pegel pruefen: ./scripts/pruefe-mikrofon.sh 6" >&2
  fi
else
  echo "Spracherkennung beendet."
fi
exit "$CODE"
