# STT-Backends für den externen Server

Was hier liegt, gehört **nicht** zu diesem Paket, sondern in den
fundusbot-Checkout. Der STT-Server ist ein fremdes Repo und wird nicht gegabelt
(spec 4, `docs/stt-contract.md`) — deshalb liegt der Quelltext hier, wird hier
getestet (`tests/test_stt_backend_infomaniak.py`, 16 Tests, keiner geht ins
Netz) und drüben nur eingespielt.

* `infomaniak_whisper_backend.py` — Whisper bei Infomaniak, im
  **Batch-Betrieb** (`wants_streaming() → False`). Vertrag:
  `docs/stt-contract.md`, Abschnitt „Zweiter Vertrag: Batch".

---

## Einspielen in `meredityman/fundusbot`

Branch `win_fundusfantasma-dev-clean`, Pfad `fundusapps/stt_server/`.
**Regel: niemals auf `master`/`main`, immer ein eigener Branch, Pull Request
nur auf ausdrückliche Ansage.**

### 1. Datei kopieren

```bash
cp stt_backends/infomaniak_whisper_backend.py \
   <fundusbot>/fundusapps/stt_server/backends/
```

### 2. `backends/__init__.py` — Lader und Zweig

Nach den anderen `_lazy_*`-Funktionen:

```python
def _lazy_infomaniak_whisper():
    from fundusapps.stt_server.backends.infomaniak_whisper_backend import (
        InfomaniakWhisperBackend,
    )
    return InfomaniakWhisperBackend
```

und in `get_backend_class`, vor dem abschließenden `return BACKENDS[name]`:

```python
    if name == "infomaniak-whisper":
        return _lazy_infomaniak_whisper()
```

Lazy wie die anderen: so zahlt eine Vosk-Installation den Import nicht.

### 3. `args.py` — Subparser

Hinter dem `elevenlabs-scribe`-Block:

```python
sp_ik = subparsers.add_parser('infomaniak-whisper',
                              help='Infomaniak Whisper, batched via VAD chunks',
                              parents=[_channel_parent])
sp_ik.add_argument('--model', default='whisper')
sp_ik.add_argument('--language', default='de')
sp_ik.add_argument('--base-url', dest='base_url',
                   default='https://api.infomaniak.com')
sp_ik.add_argument('--product-id', dest='product_id', default='110416')
sp_ik.add_argument('--api-key-env', dest='api_key_env',
                   default='INFOMANIAK_API_KEY',
                   help='Env var name to read the API key from.')
sp_ik.add_argument('--request-timeout', dest='request_timeout',
                   type=float, default=60.0)
sp_ik.add_argument('--vad_min_silence_ms', type=int, default=700)
sp_ik.add_argument('--vad_min_speech_ms', type=int, default=500)
sp_ik.add_argument('--vad_energy_threshold', type=float, default=0.01)
```

`parents=[_channel_parent]` ist nicht optional: ohne das stehen `--channels`
und `--asio-channels` nicht hinter dem Unterbefehl zur Verfügung.

### 4. `__main__.py` — die VAD-Parameter durchreichen

Dort steht heute:

```python
    if args.backend == "whisper":
        vad_kwargs = dict(...)
```

Das muss den neuen Namen mitnehmen, sonst werden die drei `--vad_*`-Optionen
oben stumm ignoriert und es gelten die Vorgaben aus `STTRecognizer.__init__`
(500 ms / 250 ms / 0.01):

```python
    if args.backend in ("whisper", "infomaniak-whisper"):
```

### 5. Starten

```bash
export INFOMANIAK_API_KEY=...    # auf Birks Rechner:
# export INFOMANIAK_API_KEY="$HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY"
# oder direkt:  --api-key-env HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY

python -m fundusapps.stt_server infomaniak-whisper --language de
```

Der Kollektivgedächtnis-Core braucht dafür **keine Änderung**: er konsumiert
`type == "final"` und sieht nicht, woher die Events kommen. `stt_url` in der
`config.toml` bleibt, wie es ist.

---

## Was zu wissen ist, bevor das live geht

**Die Segmentierung entscheidet über die Latenz.** Gemessen am 2026-08-31
(Upload + Transkription + Polling, Ende zu Ende):

| Audiolänge | e2e | Faktor |
|---|---|---|
| 5,3 s | 2,9 s | 0,55× realtime |
| 10,7 s | 3,6 s | 0,34× |
| 21,4 s | 3,8 s | 0,18× |
| 32,0 s | 4,7 s | 0,15× |

Der Overhead ist mit ~3 s fast konstant. Lange Chunks sind also *effizienter*,
aber träger: bei 10-Sekunden-Chunks steht der Text rund 13 s nach Sprechbeginn.
`--vad_min_silence_ms` ist der Hebel dafür — höher heißt längere Chunks, mehr
Latenz, weniger Aufrufe. Der Vorschlag oben (700 ms) zielt auf 5-15 s Sprache
pro Chunk.

**`partial`-Events gibt es nicht mehr.** Sie gehen laut Vertrag ausschließlich
an die Operator-Anzeige, nie in die Pipeline-Logik. Die Status-Partials
(„speech_detected", „transcribing") published der Recognizer selbst, sobald
`wants_streaming()` False ist — die Anzeige bleibt also nicht stumm, sie zeigt
nur keinen mitlaufenden Text mehr.

**`turn_id` bleibt erhalten.** Der `VadChunker` vergibt sie pro Chunk (ULID)
und reicht sie bis in das `final`-Event durch.

**Ein Fehlschlag hält nichts an.** Upload oder Polling scheitern → loggen,
Chunk verwerfen, weiterlaufen. Kein Retry pro Chunk: eine Wiederholung landet
nach dem nächsten Satz und verwirrt mehr, als sie rettet.

**Kosmetik, kein Fehler:** `TranscriptionEvent.backend` ist in `events.py` als
`Literal[...]` typisiert und kennt `"infomaniak-whisper"` nicht. Dataclasses
prüfen Typen zur Laufzeit nicht, es funktioniert also — wer das Literal beim
Einspielen erweitert, tut es aus Ordnungsliebe, nicht aus Not.

**HTTP-Bibliothek:** das Backend nimmt `requests`, wenn vorhanden, sonst
`httpx`. Der fundusbot-Checkout hat `requests` bereits (`botland_callbacks`),
es kommt also keine neue Abhängigkeit dazu.
