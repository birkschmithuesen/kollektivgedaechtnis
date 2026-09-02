# Checkliste Ausstellungstag — Stand 2026-09-02, Morgen

---

## 🔴 2026-09-02, 08:27 — ES KOMMT KEIN TEXT AN? Zuerst hier nachsehen.

**Das Bild:** Alles sieht gut aus. Das STT-Abzeichen im Bedienpult ist grün,
der Pegel schlägt aus, das Mikrofongate öffnet, ein Interview startet von
selbst — und im Transkript steht nichts. Kein Fehler, keine rote Lampe, nichts.

**Der Grund an diesem Morgen:** Infomaniaks Whisper war weg. Der ganze
`/1/ai/…`-Baum antwortete mit 502/503 und einer HTML-Seite „service
unavailable". Zwischen 08:27 und 08:40: **26 erkannte Äußerungen, 0
Transkripte.** Das LLM und die Embeddings desselben Anbieters (`/2/ai/…`)
liefen dabei tadellos — es war allein das Audio-Produkt.

**Wo du es jetzt siehst:** Im Bedienpult, zweite Zeile unter den
Interviewknöpfen.

| Anzeige | Bedeutung |
|---|---|
| `Whisper ok` (grün) | Der Anbieter hat gerade die ganze Kette geschafft |
| `Whisper ✗` (rot) | Er antwortet nicht — daneben steht, woran es lag |
| `Whisper ?` (grau) | Noch nicht geprüft. **Keine Entwarnung.** |

Daneben steht, wer gerade erkennt, und ein Knopf, um zu wechseln.

**Warum das STT-Abzeichen daneben nichts hilft:** Es beantwortet eine andere
Frage — „steht die Verbindung zum Dienst auf 5051". Die stand die ganze Zeit.

### Was du tun kannst, in dieser Reihenfolge

1. **Warten.** Der Ausfall war ein Anbieterproblem, kein Fehler an der
   Station. Die Anzeige wird von selbst grün. Prüfen von Hand:
   `./scripts/start-stt-mac.sh --geraete` sagt nichts darüber — nimm das
   Bedienpult oder starte neu, die Vorabprobe meldet sich.

2. **Auf ElevenLabs wechseln.** Knopf im Bedienpult, oder von Hand:
   `KG_STT=elevenlabs ./scripts/start-stt-mac.sh`
   🔴 **ElevenLabs steht in den USA.** Die Stimmen der Besucher verlassen
   damit den EU-Raum. Die ganze Kette ist bewusst EU-souverän gebaut
   (Infomaniak in Genf, BFL in der EU) — das ist die Zusage an Menschen, die
   hier ihre Stimme hergeben. Deshalb kein automatischer Fallback: gedrückt
   heißt entschieden.
   **Braucht `ELEVENLABS_API_KEY` in der `.env`** (Stand 2026-09-02: nicht
   vorhanden). Schlüssel: <https://elevenlabs.io/app/settings/api-keys>

3. **Lokales Whisper.** Der fremde Dienst kann `whisper` und
   `whisper-streaming` (faster-whisper) — nichts verlässt dann den Rechner,
   kein Schlüssel nötig, das wäre souveräner als Infomaniak. Aber:
   `faster_whisper` ist im venv des Dienstes **nicht installiert**, und das
   Modell `large-v3-turbo` sind rund 1,6 GB. Auf CPU statt CUDA
   (`--device cpu --compute_type int8`) ist die Geschwindigkeit an diesem
   Gerät ungemessen. **Kein Weg für fünf Minuten vor der Öffnung**, aber der
   richtige, wenn das öfter passiert.

### Was während eines Ausfalls verloren geht

Jeder gesprochene Satz. Der fremde STT-Dienst versucht es **nicht noch
einmal** — im Quelltext steht wörtlich „Kein Retry, kein Anhalten: der Chunk
ist verloren, der Server läuft weiter". Anders als beim Kern, der seit
2026-09-01 einen Warteplan für Anbieterausfälle hat (`kg/llm.py`). Die
STT-Seite liegt im fremden Repo und wird laut Projektregel nicht geforkt.

---

## Die Werkzeuge auf einen Blick

Stand 2026-09-02. Alles unter `scripts/`, alles vom Repo-Verzeichnis aus.

| Wofür | Befehl |
|---|---|
| **Alles starten** (STT, Kern, Traum; leise, ohne Browserfenster) | `./scripts/start-station.sh` |
| **Alles beenden** — und nachprüfen, dass es wirklich aus ist | `./scripts/stop-station.sh` |
| Nur die Spracherkennung, eigenes Fenster | `./scripts/start-stt-mac.sh` |
| Kern + Traum + Browserfenster (alter Weg) | `./scripts/start-mac.sh` |
| Mikrofonnamen auflisten | `./scripts/start-stt-mac.sh --geraete` |
| Pegel gegen die VAD-Schwelle messen | `./scripts/pruefe-mikrofon.sh 6` |
| Mikrofonschalter einmessen (aus/an) | `./scripts/einmessen-mikrofon.sh` |
| Im Tailnet freigeben — und nur dort | `./scripts/tailscale-freigeben.sh` |
| Ein gefahrenes Interview neu auswerten | `uv run python scripts/neu-analysieren.py --letzte` |
| Zwischen Demodaten und echter DB wechseln | `uv run python scripts/dichte-umschalten.py --stufe status` |
| Den öffentlichen Spiegel beliefern | `./scripts/spiegel-start-mac.sh --pruefen` |
| Fotos von Handys **ohne** Tailnet abholen | `./scripts/abholer-start-mac.sh --pruefen` |

🔴 **Spiegel und Abholer laufen NICHT im Sammelstart mit** — beide gehen nach
draußen. Der Uploader schiebt Interviewdaten ins öffentliche Netz, der Abholer
darf beim Spiegel löschen (er braucht das starke Token). Beide brauchen
`~/.kg-mirror-token`; anlegen mit `scripts/token-verteilen.sh datei ~/.kg-mirror-token`.

🔴 **Der Abholer braucht ein OFFENES Interview.** Ein Foto ohne laufendes
Interview weist die Station mit 409 ab; die Datei bleibt im Posteingang und
wird beim nächsten Takt erneut zugestellt. Richtig so — sieht im Log aber nach
einer Schleife aus. `--pruefen` sagt es dir vorher.

🔴 **Vor `dichte-umschalten.py` und `neu-analysieren.py` muss die Station aus
sein.** Beide prüfen es selbst und verweigern sonst den Dienst — der laufende
Kern hält `kg.db` offen.

**Erste Einrichtung, einmalig:** `./scripts/einrichten-mac.sh`, dann
`./scripts/einrichten-stt-mac.sh`.

---

## ✅ Erster echter Start auf dem MacBook — gemessen, 2026-09-01 22:00–22:40

Die Station ist auf diesem Gerät hochgefahren. Was **belegt** ist, mit dem
Beleg daneben; was offen bleibt, steht darunter.

| Geprüft | Beleg |
|---|---|
| Kern startet | HTTP 200 auf `/api/state` nach 10 s |
| Alle Seiten | `/projection?touch=1`, `/operator`, `/operator-plenum`, `/touchtest`, `/graph.json` je HTTP 200; `/plenum` → 307 auf `/projection?plenum=1` |
| `?touch=1` trifft | `frontend/projection.html:213` prüft `params.get('touch') === '1'` — genau der Wert, den `start-mac.sh` setzt |
| Telegram-Bot | `getMe` HTTP 200 |
| STT-Dienst | `/status` HTTP 200 nach 3 s, Backend `InfomaniakWhisperBackend` |
| Mikrofon | `MacBook Pro Microphone` (Index 3, mono, 48 kHz), `/levels` zeigt Pegel 0,10–0,30 und `signal: true` — **keine Nullen**, die macOS-Freigabe steht also |
| Transkription | Testsatz über die Lautsprecher ins Mikrofon → `final`-Ereignis im Kern, `data/transcript.jsonl` mit `"backend": "infomaniak-whisper"` |
| Infomaniak Chat | HTTP 200, 0,59 s |
| Infomaniak Embeddings | HTTP 200, Vektor kommt |
| BFL/EU-Schlüssel | HTTP 422 auf `flux-2-pro-preview` (= an der Auth vorbei, Endpunkt existiert) |
| Demodaten | Stufen 1/10/40/60 erzeugt, echte Gesichter belegt (Graustufen-Streuung 63,9–73,5 und pro Bild verschieden — nicht die 46,8 der leeren Flächen) |

### Vier Fehler gefunden und behoben

1. 🔴 **`config.toml` liess sich gar nicht einlesen.** Der Infomaniak-Block war
   einkommentiert worden, die OpenRouter-Zeilen dahinter blieben stehen —
   `embedding_model`/`embedding_url` doppelt vergeben, und `tomllib` bricht bei
   doppelten Schlüsseln ab (`Cannot overwrite a value (at line 153)`). Die
   Station konnte in diesem Zustand **nicht starten**, nicht erst beim ersten
   Embedding. Die US-Zeilen stehen jetzt auskommentiert da.
2. 🔴 **`config2.toml` fehlte ganz.** Angelegt, auf BFL/EU gesetzt (Sollwerte
   der Liste unten) — **und Stufe 1 mit umgestellt**: die Vorlage steht auf
   `claude-opus-5` im Anthropic-Modus, `ANTHROPIC_API_KEY` gibt es hier
   bewusst nicht. Ohne Satz kein Bild; der Traum wäre komplett tot gewesen.
   Läuft jetzt über Infomaniak wie der Kern, mit `condense_reasoning_effort = "none"`.
3. 🔴 **Das Weckwort-Modell lief ins Leere.** `wake_word_llm_api_mode =
   "anthropic"` ohne Schlüssel — der Weg, der am 2026-08-30 extra für
   „Hiermit beende ich das Interview." gebaut wurde, war still tot (ein Fehler
   dort beendet nichts, also fällt es niemandem auf). Jetzt Infomaniak,
   Kimi-K2.6, gemessene 0,59 s gegen ein Budget von 6 s.
4. 🔴 **`dichte-umschalten.py` war auf dem Mac nicht lauffähig** — feste
   Windows-Pfade und eine PowerShell-Portprüfung. Beides **ohne Absturz**: aus
   `C:\Users\birk\…` wird auf dem Mac ein relativer Ordnername, und die
   Portwache fiel per `except` auf „es läuft nichts". Das Skript meldete
   plausibel „Stufe echt, keine Datenbank" und hätte mitten in die laufende
   Station geschrieben. Jetzt Basis aus dem Skriptort, Portprüfung per Socket.
   Gegenprobe gefahren: bei laufendem Kern verweigert es den Dienst.

### 🔴 Der Mikrofonschalter: zwei Defekte, 2026-09-01 abends

**C. „Aus" war unerreichbar — eine Zahl, kein hängender Dienst.**
Der Gate kennt zwei Schwellen (`vad.py:196-203`): über `threshold` → an,
unter `threshold × release_ratio` → aus, **dazwischen bleibt es, wie es ist**.
Eingestellt war 0,0004 mit ratio 0,5, also eine Aus-Schwelle von **0,0002**.
Gemessen am ZOOM AMS-24 mit ausgeschaltetem Mikrofon (74 Werte in 30 s):
**0,00020 bis 0,00029**. Die Rauschgrenze lag also ÜBER der Aus-Schwelle —
jeder Messwert fiel ins Hystereseband, `mic_on` klebte auf `true`, und das
Mikrofon konnte nicht mehr ausgehen.

Gesetzt ist jetzt `threshold = 0,0009`, `ratio = 0,5` → aus unter **0,00045**.
Gegenprobe gefahren: `pending=False`, nach der Entprellung `mic_on=False`,
`Interview signal sent: stop`, Kern steht auf `mic_on=False`.

🔴 **Das ist eine Zwischenschwelle, keine eingemessene.** Sie stützt sich auf
den gemessenen Ruhepegel und auf zwei beobachtete An-Ereignisse (0,00186 und
0,00603). Was **fehlt**, ist der schwierige Zustand: *Mikrofon an, aber
niemand spricht.* Liegt der unter 0,00045, fällt der Gate in jeder Sprechpause
auf „aus" und beendet mitten im Interview. Das dauert 30 Sekunden:

```bash
./scripts/einmessen-mikrofon.sh
```
Misst beide Zustände, prüft die Trennschärfe und setzt die Werte selbst
(der Dienst speichert sie nach `settings/stt_runtime.json`).

**D. Die Anzeige „transcribing" wird nie zurückgesetzt.**
`operator.html:601` setzt das Abzeichen bei einem Partial mit
`status="transcribing"` und räumt es nur ab, wenn ein weiteres Ereignis kommt.
Eine Pause sendet keines. Am 2026-09-01 hing Turn `01M1FC3VJG…` (Sprachende
22:56:02, kein `final` nach 11,8 s — die zwei Turns davor brauchten 3,97 s und
1,91 s), dann kam `POST /pause`. Die Seite zeigte danach dauerhaft
„transcribing" für einen Turn, den es nicht mehr gab.

**Nicht behoben, mit Absicht:** die Datei liegt im fremden Repo, und
`config.toml` sagt dazu ausdrücklich *„Do not fork it."* Für den Betrieb
heißt das: **dem Abzeichen nicht glauben.** Was wirklich gilt, steht in
`curl -s http://127.0.0.1:5051/status` (`listening` / `paused`) und im
`mic_on` aus `/levels`.

### 🔴 Plenum-Schirm auf einem zweiten Rechner — nur über Tailscale

```bash
./scripts/tailscale-freigeben.sh      # Station muss laufen
```
Dann dort öffnen: `http://100.95.122.67:8800/plenum` und `…/operator-plenum`
(oder `http://birk:8800/plenum` bei aktivem MagicDNS).

**Alle drei Dienste bleiben auf `127.0.0.1`.** `tailscale serve` nimmt die
Anfrage im Tailnet an und reicht sie an Loopback weiter. Gemessen 2026-09-01:
Tailnet HTTP 200 über IP *und* Namen, WLAN-Adresse auf allen drei Ports 000,
lokal unverändert 200.

**Warum nicht `0.0.0.0` plus Firewall-Freigabe** (Birk: *„es soll unbedingt nur
im tailscale erreichbar bleiben!"*): das öffnet die Bedienpulte auch im
Ausstellungs-WLAN, und die haben keine Anmeldung.

🔴 **`--tcp`, nicht `--http`.** Mit `--http` bindet serve an den MagicDNS-Namen:
`http://birk:8800` antwortet, `http://100.95.122.67:8800` gibt **404**. Ohne
MagicDNS auf dem zweiten Rechner steht man dann vor einer Station, die laut
Statusausgabe läuft und trotzdem nicht aufgeht.

**Am Rande gefunden, für den Fall der Fälle:** die macOS-Anwendungsfirewall
filtert nach **Binary**, nicht nach Port, und filtert Loopback nicht. Als
`server_host` versuchsweise auf `0.0.0.0` stand, war es trotzdem nur lokal
erreichbar — in der Freigabe steht nur `/usr/bin/python3`, unsere Dienste
laufen unter dem Brew-Python. Das Fehlerbild führt in die Irre: TCP verbindet,
die Antwort bleibt aus (`Empty reply from server`), und im uvicorn-Zugriffslog
steht **nichts**. Gegenprobe, gleiche Maschine, gleicher Moment: `/usr/bin/python3`
(freigegeben) → Tailscale und LAN je 200; Brew-Python → nur 127.0.0.1.
Über `tailscale serve` spielt das keine Rolle, weil `tailscaled` freigegeben ist.

### 🔴 Der Portraitzuschnitt schnitt immer mittig — `cv2` fehlte

Birk: *„das foto aus der app wird nicht wie gewünscht per opencv gezoomed und
zentriert."* Gemessen: **`cv2` war auf dieser Maschine gar nicht installiert**
und stand auch in keiner Abhängigkeit. `kg/photos.py::_gesicht_finden` steigt
beim `ImportError` aus — und zwar **ohne Logzeile** —, also griff bei jedem
Foto der mittige Rückfallweg. Der Weg war gebaut, nur nie erreichbar.

`opencv-python-headless>=4.10,<5` steht jetzt in `pyproject.toml`.
🔴 **Das `<5` ist Pflicht, nicht Vorsicht:** OpenCV 5.0 hat `CascadeClassifier`
und die Kaskadendateien entfernt. `kg/photos.py` fängt das ab und warnt — fällt
dann aber wieder auf den mittigen Schnitt zurück.

Gemessen nach der Installation an einem nachgebauten Booth-Foto (3024×4032,
Person seitlich):

| | Ausschnitt | Gesicht waagerecht |
|---|---|---|
| vorher (mittig) | 3024 px | wo es zufällig lag |
| jetzt (am Gesicht) | 1076 px = **2,81× enger** | **50 %**, also zentriert |

An 8 echten Portraits: 8 von 8 Gesichter erkannt. 35 Foto-Tests grün
(`test_photos.py`, `test_photos_gesicht.py`, `test_server_photo.py`).
Der Zuschnitt hängt an beiden Uploadwegen — `kg/server.py:567` (App) und
`kg/telegram_bot.py:80`.

⚠️ **Nach dem Nachinstallieren muss die Station neu gestartet werden** — ein
laufender Python-Prozess sieht ein frisch installiertes Modul nicht. Erledigt.

### 🔴 Zwei Dinge, die du wissen musst — nicht behoben, sondern Betrieb

**A. Die Reglerwerte überleben ein Umschalten der Dichte NICHT.**
Sie liegen über `store.set_setting` in `data/kg.db`, und genau diese Datei
ersetzt `dichte-umschalten.py`. Nachgesehen: die aktive DB steht auf
`max_terms = 32`, die Demo-DB bringt `max_terms = 999` mit.
→ **Erst umschalten, dann einstellen.** Wer auf Stufe 60 kalibriert und danach
auf `echt` geht, fängt bei den Vorgabewerten wieder an.

**B. Infomaniak war heute Abend rund fünf Minuten komplett aus.**
Um 22:12 lieferte Chat HTTP 200 in 0,59 s, um 22:15 bis 22:20 kam auf **jedem**
Pfad HTTP 503 mit der Seite *„Service momentanément indisponible"* — Chat,
Embeddings und Transkription gleichzeitig. Um 22:20:38 war es zurück.
An diesem einen Anbieter hängen **Analyse, Weckwort, Embeddings und
Spracherkennung**. Fällt er morgen aus, steht die Station still, ohne dass ein
Fehler in unserem Code liegt. Fehlerbild im STT-Log:
`infomaniak transcription failed … Response ended prematurely`.
Die erste Transkription nach der Rückkehr brauchte 17,3 s statt der am
2026-08-31 gemessenen ~3 s (Rückstau).

### Noch offen an diesem Gerät

- **Es gibt hier keine Datenbank aus dem Ausstellungsbetrieb.** `data/` ist
  leer (0 Personen), `data-echt/` existiert noch nicht. Die echten Interviews
  vom Windows-Rechner sind **nicht** mit umgezogen. Falls sie gebraucht
  werden, müssen sie von dort geholt werden — die Maschine ist offline.
- Fenster auf den richtigen Schirm schieben und Vollbild (geht nur von Hand).
- Ob am Interview ein externes Mikrofon hängen soll: `ZOOM AMS-24` ist am Mac
  sichtbar (Index 0, stereo, 44100 Hz), eingetragen ist derzeit das eingebaute
  Mikrofon. Umstellen in `~/projekte/fundusbot/.env`
  (`SST_AUDIO_DEVICES`, `STT_AUDIO_DEVICES_SR`) — bei einem Stereo-Eingang
  zusätzlich `--channels regie audience` an `start-stt-mac.sh` anhängen.

---

Kein Handoff, sondern die Liste zum Abhaken. Was hier steht, ist **geprüft
oder ausdrücklich als ungeprüft markiert** — nichts dazwischen.

---

## 🔴 ZUERST: Die Station läuft jetzt auf dem MacBook

Nicht mehr auf dem Windows-Tracking-Laptop. **Damit gibt es keinen Fernzugriff
mehr** — Dateien kommen über `git pull` dorthin, Birk startet neu.

**Starten (seit 2026-09-01 der Weg):**
```bash
cd <repo> && ./scripts/start-station.sh
```
Startet **alle drei** Dienste — Spracherkennung (mit Mikrofonschalter), Kern
und Traum — in EINEM Fenster und öffnet **keine** Browserfenster (Birk:
„die Browser-Fenster will ich selbst öffnen"). Auf den Schirm kommt nur, was
eine Handlung auslöst; alles andere liegt in `~/kg-logs/`.

**Beenden:** Strg-C in demselben Fenster, oder `./scripts/stop-station.sh`.

🔴 **`pkill -f "python -m kg …"` beendet den Kern NICHT.** macOS nennt das
Binary `Python` mit großem P, und `pkill -f` unterscheidet Groß- und
Kleinschreibung — das Muster trifft nur den `uv run`-Mantel. Am 2026-09-01
lief dadurch ein zweiter Kern weiter und stritt sich um den Telegram-Bot
(`telegram.error.Conflict`); zwei Kerne sassen dabei auch SIGTERM aus.
`stop-station.sh` geht deshalb über den PORT statt über den Namen und **prüft
danach nach**. Vor jedem `dichte-umschalten.py` nötig.

**Die alten Skripte bleiben** und sind unverändert benutzbar:
`start-mac.sh` (Kern + Traum + Fenster, ohne Spracherkennung) und
`start-stt-mac.sh` (Spracherkennung allein). `start-station.sh` ruft genau
diese beiden auf — es gibt keine zweite Fassung ihrer Logik.
Neu an `start-mac.sh`: `KG_FENSTER=0` lässt die Fenster weg, und die
Wandadresse trägt jetzt ausdrücklich `&theme=f`.

**Beim ersten Start von Hand nötig:** Das Wandfenster auf den richtigen Schirm
schieben und dort per grünem Knopf auf Vollbild. Danach merkt es sich das —
die zwei Fenster haben getrennte Browserprofile. macOS lässt die Position
nicht per Startschalter erzwingen; genau der Versuch war auf Windows die
Ursache dafür, dass die Touchfläche auf dem falschen Schirm landete.

**Adressen:**
| | |
|---|---|
| Touchfläche Foyer | `http://127.0.0.1:8800/projection?touch=1` |
| Bedienpult Foyer | `http://127.0.0.1:8800/operator` |
| **Plenarsaal** | `http://127.0.0.1:8800/plenum` |
| **Saal-Bedienpult** | `http://127.0.0.1:8800/operator-plenum` |
| Touch-Diagnose | `http://127.0.0.1:8800/touchtest` |
| Traum | `http://127.0.0.1:8810/dream` |

🔴 **`?touch=1` ist nicht optional.** Ohne den Parameter hängt sich die
Touch-Steuerung nicht ein: keine Zoomgeste, kein Zoomregler, keine
Bedienleiste. Auf dem Windows-Rechner fehlte er über ein Jahr unbemerkt.

---

## Vor dem Publikum abzuhaken

🔴 **Morgen früh ist keine Zeit mehr zum Testen** (Birk, Vorabend). Die Liste
ist deshalb nach Dringlichkeit geordnet: **1 bis 3 sind Blocker** — ohne sie
läuft die Station nicht oder liefert falsche Daten. Alles danach ist Feinschliff.

- [ ] **1. Startskript läuft durch**, beide Fenster offen, Wand im Vollbild auf
      dem richtigen Schirm
- [ ] **2. STT-Dienst laeuft** (Port 5051) — Punkt steht unten mit dem
      Startbefehl. **Ohne ihn gibt es kein einziges Interview.**
- [ ] **3. Echte Datenbank aktiv, nicht die Demodaten.**
      `python scripts/dichte-umschalten.py --stufe echt` (Station vorher
      beenden — das Skript prüft es selbst). Aktuell liegt **Stufe 60** auf.
- [ ] **Zehn leere Personen ausblenden** (aus meinen Testfotos, sie erscheinen
      sonst als leere Scheiben an der Wand). Entscheidung steht bei Birk:
      `hidden=1` statt löschen. Details: `docs/STAND.md` §2j.
- [x] ~~Erklärungstext für den Plenarsaal einsetzen~~ — steht seit
      2026-09-01 (`frontend/static/plenum-hinweis.js`). Der QR-Code kommt
      danach als zweiter Takt über die ganze Fläche; in der Ecke steht im
      Saal keiner mehr.
- [ ] **EU-Kette beim Traum prüfen** — der Bildweg steht in **`config2.toml`**
      (nicht `config.toml`). Auf der Station war er korrekt auf BFL/EU gesetzt;
      die mitgelieferte `config2.example.toml` steht aber auf OpenRouter.
      Sollwerte: `image_api_mode = "bfl"`, `image_model = "flux-2-pro-preview"`,
      `image_url = "https://api.eu.bfl.ai/v1"`, `image_api_key_env = "BFL_API_KEY"`.
- [ ] **Ein echtes Interview durchspielen**: **Interview starten** (Schalter
      am Mikrofon oder Knopf in der Handy-App) → Foto → Portrait → Analyse →
      erscheint an der Wand.
      🔴 **Seit 2026-09-01 eröffnet ein Foto KEIN Interview mehr.** Wer zuerst
      fotografiert, bekommt „Kein Interview offen" (HTTP 409) — das ist kein
      Fehler, sondern die neue Reihenfolge. Ein zweites Foto im laufenden
      Gespräch ersetzt nur das Bild und teilt das Interview nicht mehr.
- [ ] Größen am Bedienpult einstellen (Zoom, Portrait, Tempo, Begriffe) —
      **getrennt für Foyer und Saal**, die Werte werden gespeichert

---

### Zu Punkt 2 — der STT-Dienst

Der Erkenner laeuft als eigener Prozess auf Port 5051 und liegt **nicht** in
diesem Repo. Auf dem Windows-Rechner startete ihn `kg-start\dienste\dienst-stt.bat`.
**Fuer den Mac gibt es das jetzt** (2026-09-02) — `start-mac.sh` startet ihn
weiterhin NICHT mit, er laeuft in einem eigenen Fenster:

```bash
./scripts/einrichten-stt-mac.sh    # einmalig: klont fundusbot, venv, .env, Probelauf
./scripts/start-stt-mac.sh         # jedes Mal, VOR start-mac.sh
./scripts/start-stt-mac.sh --geraete   # Mikrofonnamen auflisten
```

Pruefen, ob er laeuft: `curl -s http://127.0.0.1:5051/status`

🔴 **Der an der Station abgelesene Windows-Befehl laeuft auf dem Mac NICHT
unveraendert.** Drei Dinge stehen dem im Weg — alle am Quelltext belegt, nicht
vermutet (2026-09-02):

1. **`--channels regie` muss weg.** `regie` ist in `sr.py` nur ein Name fuer
   Kanal 0 eines **Stereo**-Stroms (`_CHANNEL_IDX`), und jedes bekannte
   Kanallabel erzwingt `num_channels = 2`. Am Windows-Rechner haengt eine
   Fireface UFX III (Kanaele 13/14 ueber ASIO); das MacBook-Mikrofon ist mono,
   der Stream scheitert. Ohne die Fahne laeuft ein Recognizer mit
   `recognizer_id="0"` — fuer den Core folgenlos, er verzweigt allein auf
   `type == "final"` (durchgefahren: Event kommt an, Mutationsprobe rot).
2. **Der Dienst braucht eine eigene `.env`** in seinem Checkout. `args.py`
   liest `STT_HOST`, `STT_PORT`, `SST_AUDIO_DEVICES` (Tippfehler im fremden
   Code: `SST_`, nicht `STT_`) und `STT_AUDIO_DEVICES_SR` mit **hartem**
   Schluesselzugriff — ohne die Datei stirbt er beim Import mit
   `KeyError: 'STT_HOST'`. Das Einrichtskript legt sie an und traegt den
   Infomaniak-Schluessel aus der Station ein.
3. **Nicht `requirements/requirements.txt` installieren.** Die volle Liste zieht
   torch/TTS/faster-whisper (mehrere GB). Der STT-Pfad braucht sieben Pakete;
   `vosk` ist darunter, weil `backends/__init__.py` es **eager** importiert —
   gepinnt auf **0.3.44**, weil die aktuelle 0.3.45 auf PyPI **kein
   macOS-Wheel** hat. Zusaetzlich `brew install portaudio`, sonst scheitert
   `sounddevice` beim Import.

Der Branch ist **`eu-souveraen/infomaniak-whisper`**, nicht der in
`docs/stt-contract.md` oben genannte `win_fundusfantasma-dev-clean` — dort
fehlt `infomaniak_whisper_backend.py` ganz (mit `git ls-tree` nachgesehen).

---

## Heute behoben (69 Commits) — alles gepusht

| Was | Beleg |
|---|---|
| **Kamerasprung** | Sprunghöhe 44,9 % → 0,32 %, Frame für Frame gemessen; kam vom Verfall des Traumgebiets nach 4 min |
| **Ausschnitt zog sich auf** | `spreadTo` 2,1 → 1,0; der Zoomregler bestimmt die Bildgröße allein |
| **Wand stand nach jeder Übergabefahrt still** | Fehler von mir (`capped`/`gewuenscht`), tötete die Bildschleife nach 300 ms |
| **Zwei-Finger-Zoom auf dem Mac** | Chromium meldet die Geste als `wheel`+`ctrlKey`, Cytoscape suchte bei `touches[1]` |
| **Zoomregler auf der Touchfläche** | eingebaut, rein lokal — verstellt nie die andere Fläche |
| **GPU-Drosselung Windows** | Energieprofil „Balanced" → Höchstleistung; Taktschwankung 28 % → 3 % |
| **Brave auf falscher Grafikkarte** | Intel 22,9 % → 1,4 %, CPU-Last von Brave −⅓ |
| **Tempo- und Portraitregler wirkungslos** | Tempo stand am Anschlag; Portraitgröße war über 87 px gedeckelt |
| **Zitatkarte zu groß** | auf 40 % über eine Stellschraube (`--quote-scale`) |
| **Demodaten ohne Gesichter/Namen** | 16 echte Gesichter lagen ungenutzt im Repo; Namen + Zitate ergänzt |
| **Plenarsaal-Ansicht** | eigene Auflage `?plenum=1` + eigenes Bedienpult, Foyer baulich unberührt |
| **Harte schwarze Kante um Portraits** | `--person-fill` war Schwarz statt transparent |

---

## 🔴 Offen — ehrlich, nicht beschönigt

**Erledigt seit dem ersten Entwurf dieser Liste:**
- **Portraitgröße** — behoben (`67d0d71`). Der Regler ist jetzt **Deckel UND
  Maßstab**: er wirkt an beiden Stellen derselben Formel. Gemessen auf der
  Harness (20 Personen, natürliche Scheibe 47,9 px): 120 → 47,9 px, 199 →
  79,5, 260 → 103,8, 700 → 279,6. Mit der alten reinen Deckelung: **sechsmal
  47,9** — der Regler bewegte nichts, und das war Birks ganzer Befund.
  50 Tests grün, Mutationsprobe gefahren (Maßstab entfernt → Test rot).

**Ungeprüft, weil kein Gerätezugriff:**
- 🔴 **Der Zoomregler ist der Bedienweg — nicht die Zwei-Finger-Geste**
  (Birk, 2026-09-01 abends): *„Wir prüfen die Zweifingergeste nicht mehr,
  sondern haben jetzt den Zoomregler. Morgen früh ist keine Zeit mehr zum
  Testen."* Der Regler sitzt am Rand der Touchfläche, wirkt rein lokal und
  wird über „Übersicht" zurückgesetzt. Die Geste bleibt eingebaut und
  funktioniert, falls sie greift — sie ist aber **nicht mehr der geplante
  Weg** und wird nicht getestet. `/touchtest` bleibt für den Notfall.
- Ob der Zoomregler sich am 65-Zoll-Schirm gut anfühlt (Griffgröße,
  Empfindlichkeit) — **das ist der einzige Touch-Punkt, der morgen zählt**
- Ob die Plenar-Ansicht aus 15 m lesbar ist. Alle Werte sind über CSS-Variablen
  einstellbar, aber **niemand hat sie an der Wand gesehen**.
- Ob der QR-Code aus dem Saal scanbar ist (er ist dort größer, aber ungemessen)

**Bewusst nicht gemacht:**
- **Der weiße Rand.** Gemessen wurden vier Kandidaten; der wahrscheinlichste
  ist die weiße Ruhezone des QR-Codes — die aber **ist** der Code, vier Module
  Rand sind Vorschrift. Ein vierter Kandidat steht in keinem Stylesheet: ein
  Browser ohne Vollbild oder ein Beamer mit falschem Seitenverhältnis. **Ein
  Blick auf den Schirm entscheidet das.**
- **`kollektivtraum.bat` reparieren** (fehlendes `?touch=1`, gleiche
  Fensterposition). Nur nötig, falls auf Windows zurückgewechselt wird.
- **Analyse-Prompt:** Zwei von fünf echten Interviews liefern in 6 von 6 Läufen
  **gar nichts** — kein Begriff, kein Zitat, kein Name. Diese Personen kämen
  als leere Scheibe an die Wand. Ursache **ungeklärt**; ein delegierter Lauf
  hat meine Hypothese widerlegt und einen Fehler in meinem Messskript gefunden.
  Details: `docs/STAND.md` §2h.

**Falls das Ruckeln zurückkommt:**
Der Windows-Rechner ist inzwischen repariert (Energieprofil + Grafikkarte).
Der Rückweg steht offen — aber er ist **kein Schnellweg**: dort fehlt in
`kollektivtraum.bat` das `?touch=1`, und beide Fenster starten auf derselben
Bildschirmposition. Ohne diese zwei Korrekturen landet die Touchfläche wieder
auf dem falschen Schirm und hat weder Regler noch Bedienleiste. **Am
Ausstellungsmorgen ist das keine Option**, sondern eine Entscheidung für später.

---

## Wo was steht

- `docs/STAND.md` — alle Messungen mit Zahlen, §2a bis §2o
- `docs/ARBEITSREGELN-ausstellungsrechner.md` — Regeln aus echten Fehlern
- `AGENTS.md` — Projektregeln, inklusive des Rechnerwechsels und der Lehre
  daraus (`?touch=1` fehlte auf Windows über ein Jahr unbemerkt)
- `scripts/start-mac.sh` — die neue Startdatei
- `scripts/dichte-umschalten.py` — zwischen Demodaten und echter DB wechseln
