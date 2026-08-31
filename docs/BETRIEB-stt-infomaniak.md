# STT über Infomaniak Whisper — Betrieb auf der Ausstellungsmaschine

**Stand 2026-08-31**, live verifiziert auf `tracking-laptop`
(`DESKTOP-QTVMC5L`, Tailscale `100.94.47.6`) mit dem ZOOM AMS-24.

Dieses Dokument beschreibt den **Betrieb**. Die Einhängung in den STT-Server
steht in `stt_backends/README.md`, die Anbieter-Entscheidung in
`entities/artesmobiles/.../eu-datensouveraenitaet-umbau.md`.

---

## Was läuft wo

| Dienst | Verzeichnis | Port |
|---|---|---|
| STT-Server (fundusbot) | `C:\Users\birk\fundusbot` | 5051 |
| Core Tool 1 (kg) | `C:\Users\birk\kollektivgedaechtnis` | 8800 |
| Traum Tool 2 (kg2) | dasselbe Verzeichnis | 8810 |

Der STT-Server liegt in einem **fremden Repo** (`meredityman/fundusbot`).
Auf der Maschine ist es kein Git-Checkout, sondern ein entpacktes Archiv —
Änderungen werden per `scp` eingespielt, nicht per `git pull`.

## Starten

Zwei Fenster, in dieser Reihenfolge — der Core darf zuerst laufen, der
STT-Server verbindet sich dorthin.

**1. STT-Server:**
```bat
cd C:\Users\birk\fundusbot
set INFOMANIAK_API_KEY=%HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY%
.venv\Scripts\python.exe -m fundusapps.stt_server ^
  --audio_devices "ZOOM AMS-24" --sample_rates 44100 --language de --port 5051 ^
  infomaniak-whisper --language de --api-key-env INFOMANIAK_API_KEY ^
  --vad_min_silence_ms 700 --vad_min_speech_ms 500
```

**2. Core:**
```bat
cd C:\Users\birk\kollektivgedaechtnis
.venv\Scripts\python.exe -m kg --config config.toml
```

Operator-Ansicht: `http://localhost:5051/operator`

### 🔴 Die Argumentreihenfolge ist nicht beliebig

`--audio_devices` und `--sample_rates` sind `nargs='+'` und schlucken gierig
alles Folgende. Steht der Backend-Name davor oder dazwischen, landet er in
der Zahlenliste:

```
error: argument --sample_rates: invalid int value: 'infomaniak-whisper'
```

**Regel: der Unterbefehl `infomaniak-whisper` steht immer ganz am Ende**,
seine eigenen Optionen dahinter.

---

## Die drei Fallen (alle am 2026-08-31 real aufgetreten)

### 1. Zwei Server gleichzeitig → Stille bei ausschlagendem Pegel

Das teuerste Fehlerbild, weil es **nicht wie ein Fehler aussieht**. Läuft
bereits ein STT-Server, hält er Mikrofon und Port. Ein zweiter Start
scheitert an der Portkollision, greift aber trotzdem auf das Audiogerät zu:
Das Pegelmeter schlägt aus, es kommt nur nie ein Transkript an, weil der
Prozess mit dem Mikrofon nicht der mit dem offenen Port ist.

**Vor jedem Start prüfen:**
```bat
tasklist | findstr python
netstat -ano | findstr :5051
```

**Aufräumen ohne den Core zu treffen** (PowerShell):
```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*stt_server*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```
Der Filter auf `stt_server` ist wichtig — ein pauschales
`taskkill /F /IM python.exe` reißt Core und Traum-Maschine mit.

Nebenwirkung derselben Ursache: Solange mehrere Prozesse das Interface
halten, ist die **Geräteliste in der Operator-Ansicht nicht lesbar**.

### 2. Über SSH gestartete Server sterben mit der Verbindung

Ein per SSH gestarteter Prozess ist Kind der SSH-Sitzung. Endet die
Verbindung, ist der Server weg — er läuft vorher einwandfrei, was die
Diagnose verschleiert.

Für Fernstarts hilft weder `start /b` noch `Start-Process -WindowStyle
Hidden`. Was funktioniert, ist WMI, weil es den Prozess an den Dienst hängt
statt an die Sitzung:

```powershell
Invoke-CimMethod -ClassName Win32_Process -MethodName Create `
  -Arguments @{CommandLine = 'cmd /c C:\Users\birk\stt-run.bat'}
```

**Und dabei:** Die Verschachtelung PowerShell → WMI → cmd zerlegt
Anführungszeichen. Aus `"ZOOM AMS-24"` wurde `'"ZOOM'`, mit entsprechendem
`ValueError: Audio device '"ZOOM' not found`. Deshalb den Startbefehl in
eine `.bat`-Datei schreiben und nur diese aufrufen.

`schtasks` ist keine Alternative: der Task meldete `Letztes Ergebnis:
267011` und startete gar nicht erst.

### 3. Operator-Ansicht zeigt nichts, obwohl die Erkennung läuft

Das Log enthält `Dispatching final transcription`, die Ansicht bleibt leer.

Der `EventBus` (`events.py`) verteilt nur an Abonnenten, die **im Moment des
`publish`** eingetragen sind — keine Historie, kein Nachliefern. Reißt der
SSE-Stream (`GET /events`) ab, geht jedes Ereignis in der Lücke ersatzlos
verloren. Beobachtet wurden Neuverbindungen alle 30–60 s.

Zur Unterscheidung:
* Pegel läuft, Text fehlt → Anzeige-/Streamproblem, **nicht** die Erkennung.
  (`/levels` ist normales Polling und läuft unabhängig weiter.)
* Nichts im Log → dann erst ist die Erkennung dran.

Ob eine Verbindung steht: `findstr "GET /events"` im Serverlog.

---

## Was normal ist und kein Fehler

**„Vielen Dank." aus dem Nichts.** Whispers bekannte Halluzination bei Stille
oder Rauschen. Erscheint als vollwertiges Transkript.

**VAD-Ereignis ohne Transkript.** Das Backend verwirft leere Ergebnisse
absichtlich (`infomaniak_whisper_backend.py`): *„Stille bleibt Stille — ein
leeres `final` wäre eine Äußerung im Transkript, die niemand gemacht hat."*
Auf `--vad_energy_threshold` reagieren, wenn es zu oft passiert.

**Keine mitlaufenden Partials.** Whisper-Batch kennt keinen wachsenden Text;
der Recognizer sendet Status-Partials (`speech_detected`, `transcribing`).
Laut STT-Vertrag hängt an Partials keine Pipeline-Logik — nur die Anzeige
ändert sich.

---

## Gemessene Latenz (live, ZOOM AMS-24, 2026-08-31)

| Äußerung | Sprechende → Text |
|---|---|
| „Test 1, 2, 3" | 4,30 s |
| „Dann scheint das jetzt hier zu laufen, oder?" | 2,89 s |
| „Hallo, hallo, 123, das ist ein Test. Jetzt erzähle ich mal ein bisschen was und schaue, ob das alles durchkommt." (112 Zeichen) | 3,07 s |

**Der Overhead ist mit rund 3 s fast konstant** — er hängt am Netzweg, nicht
an der Länge. Das deckt sich mit der Messung gegen Dateien (5,3 s Audio →
2,9 s; 32 s Audio → 4,7 s).

Für den Betrieb heißt das: Längere Chunks sind effizienter und zugleich
träger. `--vad_min_silence_ms` ist der Hebel; 700 ms zielt auf 5–15 s
Sprache pro Chunk. Das Wake-Word arbeitet auf `final`-Texten und wird um
diese Spanne träger.

---

## Ausfall der Verbindung

Ein fehlgeschlagener Chunk wird geloggt und verworfen, ohne Retry — eine
Wiederholung landete nach dem nächsten Satz und verwirrte mehr, als sie
rettet. Bei anhaltendem Ausfall ist der Rückfallweg ElevenLabs Scribe:
derselbe Server, anderer Unterbefehl (`elevenlabs-scribe`), `ELEVENLABS_API_KEY`
in der `.env`. Das verlässt allerdings den EU-Rechtsraum.

## Schlüssel

`HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY` liegt als Benutzer-Umgebungs­variable
auf der Maschine (80 Zeichen). Der Startbefehl kopiert ihn nach
`INFOMANIAK_API_KEY`, den der Server erwartet.

Prüfen, ohne ihn anzuzeigen:
```powershell
$k = [Environment]::GetEnvironmentVariable('HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY','User')
if ($k) { "$($k.Length) Zeichen" } else { "nicht gesetzt" }
```

**Hinweis zu Logs:** Der Server druckte beim Start die komplette `.env` im
Klartext, inklusive `ELEVENLABS_API_KEY`. Auf dem Branch
`eu-souveraen/infomaniak-whisper` ist das behoben (Werte maskiert, Namen
bleiben). Ältere Logs unter `logs\sst_server\` können den Schlüssel noch
enthalten — beim Weitergeben prüfen.
