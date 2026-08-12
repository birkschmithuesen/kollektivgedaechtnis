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
