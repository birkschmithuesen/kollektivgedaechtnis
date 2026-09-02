# Übergabe an eine neue Session — 2026-09-02, 09:25

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

## Offen — ehrlich, nicht beschönigt

1. **Der letzte Beweis fehlt.** ElevenLabs ist direkt gegen die API geprüft
   (perfekte Erkennung) und der Dienst verbindet sich fehlerfrei — aber seit
   dem Umschalten hat niemand ins Mikrofon gesprochen. Die Strecke Mikrofon →
   ElevenLabs → Kern → Datenbank ist **nicht durchgemessen**. Erste Handlung
   einer neuen Session: einen Satz sprechen und `sqlite3 data/kg.db "select
   id,status,length(transcript) from person;"` ansehen.

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

7. **Testsuite:** Ein Lauf mit `-x -p no:randomly` hing über 15 Minuten ohne
   Ausgabe; Verdacht auf `tests/test_operator_ui.py` (Playwright). Läuft gerade
   getrennt zur Klärung. Die neuen und geänderten Tests sind grün:
   `test_stt_health.py` (18), `test_server_stt.py` (5),
   `test_spiegel_start_mac.py` + `test_abholer_start_mac.py` (19).

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
