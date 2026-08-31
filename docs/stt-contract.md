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
