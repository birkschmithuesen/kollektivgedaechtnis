# STT server contract (verified 2026-08-12)

**Source of truth:** private repo `meredityman/fundusbot`, branch
`win_fundusfantasma-dev-clean`, path `fundusapps/stt_server/`.
Read with `gh api repos/meredityman/fundusbot/contents/fundusapps/stt_server/<file>?ref=win_fundusfantasma-dev-clean --jq .content | base64 -d`.
Verified files: `events.py`, `app.py`, `args.py`,
`backends/elevenlabs_scribe_backend.py`.

**Do NOT fork or modify this server.** The Core is an independent SSE consumer.

## Run

```bash
python -m fundusapps.stt_server elevenlabs-scribe --language de
```

Backend name on the wire: `elevenlabs-scribe` (`BACKEND_NAME` in
`elevenlabs_scribe_backend.py`). API key from the env var named by
`--api-key-env`, default **`ELEVENLABS_API_KEY`**. Other options: `--model`
(default `scribe_v2_realtime`), `--commit-strategy` (`vad` | `manual`, default
`vad`), `--silence-timeout` (default `0.7`). Host/port come from `STT_HOST` /
`STT_PORT` in the server's own `.env`.

## Endpoints

`GET /events` (SSE), `GET /status`, `POST /pause`, `POST /resume`,
`GET /operator`. We use `/events` and `/status` only.

## Wire format

Unnamed SSE messages, one JSON object per event:

```
data: {"recognizer_id": "left", "type": "final", ...}\n\n
```

Between events, `: keep-alive\n\n` comments every 15 s (from `app.py:events()`).

## Event fields (`events.py`, TranscriptionEvent — TEN fields)

| field | type | note |
|---|---|---|
| `recognizer_id` | str | per audio channel |
| `type` | `"partial"` \| `"final"` | we consume `final` only |
| `text` | str | |
| `timestamp` | float | wall clock, epoch seconds |
| `backend` | str | `elevenlabs-scribe` here |
| `status` | str \| null | |
| `confidence` | float \| null | not set by the Scribe backend |
| `turn_id` | str \| null | ULID, stable per utterance |
| `partial_seq` | int \| null | partials only |
| `extending` | bool \| null | **NEW** — see below |

## `extending` — why it exists

ElevenLabs Scribe **revises** partials mid-utterance (unlike the
LocalAgreement-2 whisper path, whose partials are strictly growing prefixes).
Per `on_partial_transcript`, the backend emits two parallel partial streams:
`extending=False` for every distinct live partial (the revisable full text) and
`extending=True` for the confirmed, strictly-growing prefix. `null` means the
backend does not distinguish (legacy vosk / whisper).

`final` events are published by `on_committed_transcript` and leave `extending`
at its default `null`.

**Consequence for us:** we consume `type == "final"` only, so `extending` never
affects our logic — the decoder must merely tolerate the field. Partials go to
the operator display, where revision is fine.

## Utterance boundaries are the provider's, not ours

With the default `--commit-strategy vad`, a `final` is emitted exactly when
ElevenLabs' server VAD sends `committed_transcript`
(`elevenlabs_scribe_backend.py`; its `tick()` is a documented no-op).
**We do not implement silence detection.**

## Optional live re-check on site

```bash
curl -s http://127.0.0.1:5051/status
curl -N -s --max-time 20 http://127.0.0.1:5051/events | head -20
```

---

# Zweiter Vertrag: Batch (`infomaniak-whisper`, 2026-08-31)

**Der Vertrag oben gilt unverändert weiter.** Dies hier ist ein zweites
Backend desselben Servers, kein Ersatz: derselbe Prozess, dieselben Endpunkte,
dieselbe Wire-Form. Umgeschaltet wird beim Start des STT-Servers
(`python -m fundusapps.stt_server infomaniak-whisper --language de`), nicht in
der `config.toml` des Cores.

Quelltext und Einspielanleitung: `stt_backends/` in diesem Repo.

## Was sich ändert — und was ausdrücklich nicht

| | `elevenlabs-scribe` (Vertrag oben) | `infomaniak-whisper` |
|---|---|---|
| Betriebsart | Streaming (`wants_streaming() → True`) | Segmented (`→ False`) |
| Äußerungsgrenzen | Server-VAD von ElevenLabs | lokaler `VadChunker` (`vad.py`) |
| `final` | pro committed transcript | **pro VAD-Chunk, unverändert im Format** |
| `partial` mit Text | ja | **nein** |
| `partial` als Status | — | `speech_detected`, `transcribing` (vom Recognizer) |
| `turn_id` | ULID pro Äußerung | ULID pro Chunk, durchgereicht |
| `confidence` | nicht gesetzt | nicht gesetzt |
| `extending` | `True`/`False` bei Partials | immer `null` |
| Latenz | quasi-live | ~3 s Overhead + Chunklänge |

**Für den Core ändert sich nichts.** `kg/stt_client.py` konsumiert
ausschließlich `type == "final"` und kennt die Herkunft nicht. Es gibt keinen
Codepfad im Core, der auf `partial` reagiert — Partials gehen an die
Operator-Anzeige, und dort ist ihr Ausbleiben eine Anzeigefrage, keine
Funktionsfrage. Wake-Word- und Stopp-Erkennung arbeiten auf `final`-Texten und
laufen weiter, nur mit Chunk-Latenz; der 15-Minuten-Timeout und die
Textnachricht an den Bot bleiben die sicheren Wege.

## Der Endpunkt (gemessen am 2026-08-31 gegen die echten Adressen)

* **Absenden:** `POST https://api.infomaniak.com/1/ai/{produkt}/openai/audio/transcriptions`
  (multipart: `file`, `model=whisper`, `language=de`,
  `response_format=verbose_json`) → `{"batch_id": "..."}`.
  ⚠️ **Nicht** unter `/2/.../openai/v1/` — dort 404. Der Chat-Endpunkt liegt
  auf `/2/`, die Transkription auf `/1/`.
* **Ergebnis:** `GET https://api.infomaniak.com/1/ai/{produkt}/results/{batch_id}`
  → `{"status": "success", "data": "<JSON-String>"}`. `data` ist ein **String**
  mit `text`, `segments` (je `start`/`end`), `language`, `duration`.
* **Grenzen:** 25 MB pro Datei; mp3/mp4/aac/wav/flac/ogg/opus/wma/m4a/webm.
* **Schlüssel:** Umgebungsvariable, Header `Authorization: Bearer …`.

**Ende-zu-Ende-Latenz** (Upload + Transkription + Polling): 2,9 s für 5,3 s
Audio · 3,6 s für 10,7 s · 3,8 s für 21,4 s · 4,7 s für 32,0 s. Der Overhead
ist mit ~3 s fast konstant — längere Chunks sind effizienter, aber träger.

## Fehlerbild

Ein fehlgeschlagener Upload oder Poll verwirft den Chunk und läuft weiter; der
Server hält nie an, und es gibt keinen Retry pro Chunk. Auf der Konsumentenseite
sieht das aus wie eine Äußerung, die nie gesprochen wurde — dieselbe Klasse von
Verlust wie ein nicht erkanntes Wort, und derselbe Umgang damit: aussitzen.

---

# Dritter Vertrag: der Mikrofonschalter (2026-08-31)

**Neu ist hier die Richtung.** Die beiden Verträge oben beschreiben, was wir
vom STT-Server *lesen*. Dieser beschreibt, was der STT-Server bei uns
*aufruft* — der einzige Fall, in dem er das tut.

Ausgelöst wird er vom `--mic-gate` des STT-Servers: am Mikrofon hängt ein
physischer Schalter, „aus" heißt, der Pegel fällt auf das Grundrauschen des
Wandlers. Hysterese (an über der Schwelle, aus erst unter der halben) und eine
Mindestdauer (Default 1500 ms) machen daraus einen Zustand statt eines
Flatterns.

## Der Aufruf

```
POST http://<core>:8800/api/interview_switch
{"on": false, "source": "mic_switch"}   ->  200 {"ok": true, "on": false}
```

Der STT-Server ruft aus einem Wegwerf-Thread heraus auf, Timeout (2 s, 5 s),
kein Retry. Ein nicht erreichbarer Core wird dort geloggt und sonst
ausgesessen — genau wie ein verworfener Chunk oben.

## Was der Core damit macht — und was nicht

| | |
|---|---|
| `on: false` | schließt das offene Interview, `stop_reason="mic_switch"` (`SessionTracker.mic_switch` → `_close`). Die Pipeline läuft an wie nach einer gesprochenen Schlussphrase. |
| `on: true` | eröffnet ein Interview **ohne Porträt**, wenn keines offen ist: `opened`-Grund `"mic_switch"`, `Core._open` legt die Person mit `photo_path=None, portrait_path=None` an. Ist bereits eines offen, passiert nichts. |
| beides | setzt die Einstellung `mic_on` und meldet sie über `/events` an die Bedienseite (Abzeichen `MIC` neben `STT`). |

**Warum `on: true` eröffnet** (Birk, 2026-09-01; bis dahin galt hier das
Gegenteil): „Es kann ja sein, dass irgendwer nicht will, dass ein Foto von ihm
oder ihr gemacht wird." Der Grund ist nicht technisch. Ein Besucher, der kein
Bild von sich möchte, muss trotzdem am Kollektivgedächtnis teilnehmen können —
bei einer Arbeit über Datenschutz und Überwachung wäre ein Zwangsfoto als
Eintrittskarte ein Widerspruch in sich. Technisch stand dem nie etwas im Weg:
`photo_path` und `portrait_path` sind in `person` seit jeher nullbar, und die
Wand verträgt einen Knoten ohne Bild.

Die beiden Eingänge bleiben am `opened`-Grund unterscheidbar (`"photo"` gegen
`"mic_switch"`), und der Schalter ist in beide Richtungen idempotent: AN bei
offenem Interview eröffnet nichts, AUS bei geschlossenem schließt nichts.

## Ein Foto, das nachkommt

Wer per Schalter begonnen hat und sich mitten im Gespräch **doch**
fotografieren lässt, bekommt sein Bild an die laufende Person nachgetragen
(`set_person_portrait`) — das Interview läuft weiter, dieselbe `started_at`,
derselbe Transkript-Ausschnitt. Der Tracker meldet dafür eine dritte
Übergangsart neben `opened` und `closed`: `portrait` mit dem Grund
`"late_photo"`.

**Nur in genau diesem Fall.** Ein Foto auf ein per Foto eröffnetes Interview
ist weiterhin der nächste Besucher und schließt das laufende mit
`"new_photo"`; ebenso das zweite Foto nach einem bereits nachgereichten
Porträt. Würden die beiden Fälle vermischt, überschriebe der nächste Besucher
still das Porträt des vorigen, statt einen eigenen Knoten zu bekommen — ein
Datenverlust, den auf der Wand niemand als solchen erkennen könnte. Der
Tracker merkt sich dafür, ob das offene Interview noch ohne Porträt ist; nach
einem Neustart liest `Core` diese Tatsache aus der Datenbank nach
(`open_person().portrait_path is None`), wie schon `open_since`.

## Wie ein Mensch ohne Foto auf der Wand steht

Als einfarbige, ruhige Scheibe in der Farbe der ruhenden Begriffsränder
(`--person-blank`, in theme-f `#6E6656`), sonst in nichts von den anderen
Knoten verschieden. **Kein Platzhalter-Avatar, kein Fragezeichen, kein Icon:**
Wer sich gegen ein Bild entscheidet, ist kein fehlendes Bild. Die eigene Farbe
ist nötig, weil in theme-f alles, was eine Scheibe sonst trägt, aus dem PNG
kommt — `--person-fill` ist Schwarz auf schwarzem Grund, Ring, Ringecho und
Lichthof stehen auf 0. Am Bild gemessen war ein Knoten ohne Portrait dort
buchstäblich nichts (247 von 28392 Pixeln nicht schwarz, und die kamen von der
Kante zum Begriff).

`mic_on` ist ausdrücklich **nicht** `stt_connected`. Das eine sagt, ob der
Erkennungsserver erreichbar ist, das andere, ob das Mikrofon im Raum
eingeschaltet ist. Sie zusammenzulegen hieße, ein abgeschaltetes Mikrofon nicht
mehr von einem abgestürzten STT-Server unterscheiden zu können — in genau dem
Moment, in dem jemand auf die Leiste schaut.

## Nebenwirkung auf den SSE-Strom

Der STT-Server legt den Schalterwechsel zusätzlich als Ereignis auf seinen Bus
und damit in `/events`:

```
data: {"type": "mic_gate", "mic_on": false, "level_rms": 0.0004,
       "threshold": 0.002, "timestamp": 1756..., "recognizer_id": "mic_gate"}
```

**Für uns folgenlos, aber nachgeprüft:** `TranscriptionEvent.from_dict` ist
tolerant gegenüber unbekannten Schlüsseln und fehlenden Feldern, und
`STTClient._dispatch` verzweigt allein auf `type in ("final", "partial")`.
Ein `"mic_gate"` läuft also durch, ohne etwas anzufassen. Das Ereignis ist für
die Operator-Anzeige des STT-Servers da, nicht für uns.
