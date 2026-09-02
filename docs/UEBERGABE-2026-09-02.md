# Übergabe an eine neue Session — 2026-09-02, 09:40

## Wo du bist

**Kollektivgedächtnis**, Kunstinstallation, NEW bauhaus festival, Weimarhalle.
Läuft seit 2026-09-01 auf Birks **MacBook** (vorher ein Windows-Rechner).
Repo: `/Users/macbook/Projekte/kollektivgedaechtnis`, Zweig `master`, alles
gepusht (Stand `8ead254`).

Zwei Werkzeuge, ein Vertrag: **kg** (Kern, Port 8800) und **kg2** (Traum, Port
8810), verbunden nur über `graph.json`. Dazu ein **fremder** STT-Dienst auf
Port 5051 aus `meredityman/fundusbot`, Zweig `eu-souveraen/infomaniak-whisper`,
in `~/projekte/fundusbot`. 🔴 **Dieses fremde Repo wird nicht geforkt** — das
ist eine Projektregel. Änderungen dort sind ausgeschlossen; Paketinstallationen
in sein venv sind erlaubt (heute geschehen, siehe unten).

## Was gerade läuft

| Dienst | Port | Zustand |
|---|---|---|
| Spracherkennung | 5051 | läuft, Backend **ElevenLabs Scribe** |
| Kern | 8800 | läuft |
| Traum | 8810 | läuft |
| Spiegel-Uploader | — | läuft, öffentliche Seite ist frisch |

Datenbank ist **frisch** (heute 08:24 geleert). Der alte Stand liegt vollständig
unter `~/kg-archiv/vor-neustart-20260902-082432/` (8,1 MB, 37 Dateien).

Öffentliche Seite: <https://kollektivgedaechtnis.flashclash.de> (Empfänger auf
herkules, `91.98.143.165`, per SSH als `fundusbot` erreichbar).

## 🔴 Die Lage des Tages: Infomaniaks Whisper ist ausgefallen

Um 08:27 fragte Birk, warum keine Transkriptionen erscheinen. Alles sah gut
aus — STT-Abzeichen grün, Pegel schlug aus, Mikrofongate öffnete, ein Interview
lief — und es kam **kein einziges Wort** an. Gemessen: 26 erkannte Äußerungen,
0 Transkripte. Sichtbar nur im Log des fremden Dienstes, unter 17.000 Zeilen
`GET /levels`.

**Der Befund:** Infomaniaks Audio-Teil (`/1/ai/…`) antwortet mit 502/503 und
einer HTML-Seite „service unavailable". Der Textteil (`/2/ai/…`, Kimi-K2.6 und
`bge_multilingual_gemma2`) läuft dabei **tadellos**. Es ist also nur Whisper.
Zwischenzeitlich kam Whisper halb zurück und brauchte **23–34 Sekunden** statt
der normalen 1,8–4 s, bei etwa 40 % Erfolgsquote — nicht brauchbar.

**Aktuelle Lösung:** Umgeschaltet auf **ElevenLabs Scribe**. Guthaben ist
aufgeladen, der Schlüssel liegt als `ELEVENLABS_API_KEY` in der `.env` des
Projekts. Direkt geprüft: ElevenLabs erkennt eine deutsche Sprachprobe
fehlerfrei. Der laufende Dienst verbindet sich seit dem Umschalten **ohne einen
einzigen Fehler**.

🔴 **ElevenLabs sitzt in den USA.** Die ganze Kette ist bewusst EU-souverän
gebaut (Infomaniak in Genf, BFL in der EU). Das ist der Grund, warum es
**keinen automatischen Fallback** gibt: gedrückt heißt entschieden, wie beim
Spiegel-Uploader. Sobald Infomaniak zurück ist, gehört zurückgeschaltet.

## Was heute gebaut wurde

### `kg/stt_health.py` — die Aufsicht über die Spracherkennung
Misst im Minutentakt die **ganze** Kette bei Infomaniak (0,3 s Sinuston,
absenden **und** abholen). Kennt drei Lagen: geht / geht nicht / noch nicht
geprüft. Kann den Anbieter wechseln (Port 5051 beenden, Startskript mit
`KG_STT=…` neu starten). 18 Tests, Mutationen geprüft.

🔴 **Warum die ganze Kette:** Das bloße Absenden lieferte während des Ausfalls
zeitweise HTTP 200 (6 von 8), obwohl nie ein Ergebnis kam — es gibt nur eine
`batch_id` zurück, der Text kommt beim Abholen. Eine Prüfung, die dort aufhört,
meldet in genau diesem Ausfall „alles gut". Der Test dazu heißt
`test_ein_erfolgreiches_absenden_allein_reicht_nicht`.

### Bedienpult (`:8800/operator`)
Neue Zeile unter den Interviewknöpfen: Whisper-Lampe, laufender Anbieter,
Wechselknopf. Bewusst **neben** dem bestehenden STT-Abzeichen und nicht darin —
das beantwortet „steht der Draht zu 5051" und war beim Ausfall die ganze Zeit
grün. Zwei Fragen, zwei Anzeigen.
Routen: `GET /api/stt`, `POST /api/stt/anbieter`.

### `KG_STT=elevenlabs` in `scripts/start-stt-mac.sh`
**Kein Fork nötig** — das fremde Repo bringt `elevenlabs_scribe_backend.py`
längst mit, es ist nur ein anderer Unterbefehl. `--mic-gate` liegt in
`_channel_parent` (`args.py:90`) und gilt für beide Backends. Dazu eine
Vorabprobe beim Start, die warnt (nie blockiert), wenn der Anbieter weg ist.

### Schalter für die Außendienste
`scripts/start-station.sh` kennt jetzt `--mit-spiegel`, `--mit-abholer`,
`--mit-allem` und `--trocken`. `stop-station.sh` kennt die beiden ebenfalls —
sonst hätte ein „Stopp" einen Uploader ins offene Netz weiterlaufen lassen und
dabei „frei" gemeldet.

## Bedienung

```bash
./scripts/start-station.sh                 # STT, Kern, Traum. Nichts nach draußen.
./scripts/start-station.sh --mit-spiegel    # zusätzlich: öffentliche Seite versorgen
./scripts/start-station.sh --trocken        # nur sagen, was starten würde
./scripts/stop-station.sh                   # alles beenden, mit Beleg

KG_STT=elevenlabs ./scripts/start-stt-mac.sh   # Anbieter von Hand
```

Adressen (Browserfenster öffnet man selbst — ausdrücklicher Wunsch):

```
Touchfläche   http://127.0.0.1:8800/projection?touch=1&theme=f
Bedienpult    http://127.0.0.1:8800/operator
Plenarsaal    http://127.0.0.1:8800/plenum
Traum         http://127.0.0.1:8810/dream
Mikrofon      http://127.0.0.1:5051/operator
```

`?touch=1` ist **nicht optional** — ohne den Parameter gibt es weder Zoomregler
noch Bedienleiste. `theme=f` ist das Layout vom 2026-09-01.

## ✅ Die ganze Kette ist durchgemessen (09:35, mit Birk am Mikrofon)

```
Sprache → ElevenLabs → Kern → Datenbank (p3, 114 Zeichen)
        → Begriffe „Hochhaus" und „Ausblick", je mit Belegstelle
        → Graph: 5 Knoten, 2 Kanten
        → öffentlicher Spiegel: 0,5 s alt
```

Erkannt wurde wortgenau: *„Ich würde gerne in einem Hochhaus leben, wo ich,
ähm, mit Screens an den Fenstern einen ganz tollen Ausblick habe."*
Es funktioniert also alles — mit ElevenLabs als Anbieter.

## 🔴 Zwei Zustände, die auseinanderlaufen können — der gefährlichste Fund

Beim Test trat **zweimal** dasselbe Muster auf, an zwei verschiedenen Stellen:

**1. Im STT-Dienst.** `/levels` meldete `mic_gate.mic_on: true` bei gleichzeitig
`status: "paused"`. Der Dienst verwirft im Pausenzustand alle Audiodaten
(`sr.py`: `audio_queue.queue.clear()`). Er war also taub, während alles nach
„an" aussah. Geholfen hat `curl -X POST http://127.0.0.1:5051/resume`.

**2. Im Kern.** `/api/state` meldete `mic_on: true` bei `interview: None`.
Sprache wurde erkannt und in `data/transcript.jsonl` geschrieben, aber keiner
Person zugeordnet — der Kern verwirft Text ohne offenes Interview, zu Recht.
Geholfen hat „Interview starten" im Bedienpult.

**Warum es sich nicht von selbst erholt:** Das Mikrofongate handelt nur bei
ÜBERGÄNGEN (`vad.py`). Steht sein `mic_on` schon auf `true`, schickt es nie
wieder ein „resume" oder „Interview starten" — egal wie laut jemand spricht.
Der Zustand ist stabil falsch.

**Das ist der Fehler, der eine Ausstellung ruinieren kann**, weil er wie
Normalbetrieb aussieht: Lampen grün, Pegel schlägt aus, und nichts wird
aufgezeichnet. Ein Vorschlag für die nächste Session: Der Kern könnte einen
Widerspruch selbst erkennen — kommt ein `final` herein, während `mic_on` wahr
und kein Interview offen ist, ist das ein Beleg dafür, dass jemand spricht.
Entweder ein Interview eröffnen oder wenigstens im Bedienpult laut werden.
Beim STT-Dienst genügt eine Prüfung `mic_on && status == "paused"` → `/resume`.

## Offen — ehrlich, nicht beschönigt

1. **Die Zustandsdivergenz oben** ist nicht behoben, nur erkannt und von Hand
   umgangen. Sie ist der wichtigste offene Punkt.

2. **Der fremde STT-Dienst wiederholt nichts.** Im Quelltext steht wörtlich
   „Kein Retry, kein Anhalten: der Chunk ist verloren". Jeder Satz während
   eines Anbieterausfalls ist endgültig weg — anders als beim Kern, der seit
   2026-09-01 einen Warteplan hat (`kg/llm.py`).

3. **Lokales Whisper wäre die bessere Antwort** als ElevenLabs: `faster-whisper`
   im venv des fremden Dienstes, Modell `large-v3-turbo` (~1,6 GB), CPU statt
   CUDA. Nichts verlässt den Rechner, souveräner als Infomaniak. Nicht
   installiert, Geschwindigkeit an diesem Gerät ungemessen.

4. **Das Mikrofongate flattert** um den Rauschteppich: Schwelle 0,0006,
   Ruhepegel 0,0006–0,0011. Es öffnet und schließt dadurch von selbst und
   startet/beendet Interviews. Einmessen: `./scripts/einmessen-mikrofon.sh`.

5. **Der Merge-Richter ist instabil** (etwa 1 von 5 Läufen fasst etwas falsch
   zusammen, gelegentlich Tippfehler in Begriffen auf der Wand). Birk hat einen
   „zweiten Judge"/Validator vorgeschlagen; Entwurf besprochen, ausdrücklich
   verschoben.

6. **Stecken gebliebenes „transcribing"-Abzeichen** in der Bedienseite des
   fremden STT-Dienstes (`operator.html:601`). Gemeldet, nicht behoben —
   fremdes Repo.

7. **Testsuite ist grün.** 1429 bestanden, 3 übersprungen, dazu 51
   Browsertests in eigener Datei. Der eine rote Test war ein echter Fund und
   ist behoben: Mein Probelauf setzte den Infomaniak-Schlüssel in die
   `curl`-Befehlszeile, wo ihn jeder Nutzer per `ps` lesen kann — jetzt geht er
   über `curl --config -` durch eine Pipe (Commit `d77cb7c`, mit Gegenprobe
   nachgemessen).

   🔴 **Der vermutete Playwright-Hänger war keiner.** Die Suite ist schlicht
   lang: `tests/test_prerender.py` rendert 1920×1080-PNGs und braucht allein
   ~7 Minuten; `pytest -q` puffert beim Umleiten in eine Datei, was wie ein
   Hänger aussieht. Für sichtbaren Fortschritt:
   `script -q /dev/null uv run pytest -v …`. Ein voller Lauf dauert ~17 min.

## Arbeitsregeln, die hier gelten

* **Miss, statt zu vermuten.** Zwei Fehldiagnosen heute Morgen kamen daher, dass
  ich den falschen Pfad (`/1/` statt `/2/`) und nur die halbe Kette gemessen
  habe. Beides steht als Kommentar im Code, damit es nicht wiederkehrt.
* **Mutationstests.** „Eine Wache, die nie ausgelöst hat, ist unbewiesen." Jede
  neue Prüfung wird durch absichtliches Kaputtmachen belegt. Heute fiel dabei
  auf, dass ein bestehender Test durch eine Umformulierung **still grün**
  geworden war, ohne noch etwas zu belegen.
* **Prüfen durch Ausführen, nicht durch Lesen.** Tests, die Quelltext nach
  Mustern absuchen, veralten unbemerkt. Die zwei Trennungstests laufen jetzt
  über `start-station.sh --trocken`.
* **Was nach draußen geht, entscheidet Birk.** Uploader, Abholer, fremder
  Anbieter: nie automatisch, immer ein getippter Schalter oder ein Knopf.
* Antworten auf **Deutsch**, mit korrekten Umlauten.

## Wo mehr steht

* `docs/STAND.md` — das eine Dokument, mit dem eine Session anfängt. §4z ist
  der Whisper-Ausfall in voller Länge.
* `docs/CHECKLISTE-ausstellungstag.md` — ganz oben: „ES KOMMT KEIN TEXT AN?"
* `docs/BETRIEB-stt-infomaniak.md` — die Fallen des fremden Dienstes.
