# Stand vor dem End-to-End-Test — 2026-09-01

**Das ist das EINE Dokument, mit dem eine neue Session anfängt.** Es sagt, was
läuft, was ungeprüft ist und was zuerst zu tun wäre. Alles Ältere liegt unter
`docs/archiv/` und ist erledigt.

**Festival: NEW bauhaus, 2./3. September 2026, Weimarhalle — morgen.**

> Vorher lesen, in dieser Reihenfolge:
> `AGENTS.md` (kurz) → `docs/ARBEITSREGELN-ausstellungsrechner.md` (vollständig,
> jede Regel dort hat einmal Arbeit gekostet).

---

## 1. Wo alles steht

| | |
|---|---|
| Repo, Branch | `birkschmithuesen/kollektivgedaechtnis`, `master` |
| Ausstellungsrechner | `100.94.47.6` (Tailscale), Windows, **als `SF-Tracking` einloggen** |
| Code auf der Station | `C:\Users\birk\kollektivgedaechtnis` (absolute Pfade eingebacken — bleibt dort) |
| Startdatei, die wirklich läuft | `C:\Users\SF-Tracking\kg-start\kollektivtraum.bat` |
| Startknopf | Desktop von `SF-Tracking`: „Kollektivtraum START" |
| Testsuite | `uv run pytest -q` — **1199 grün**, ~27 min |

Die Station zieht bei jedem Start selbst von GitHub (`[0/6]`) und erneuert
dabei auch ihre eigene Startdatei. **Änderungen an der Startdatei gehören ins
Repo** (`mirror/kollektivtraum.bat`), sonst werden sie beim nächsten Start
lautlos überschrieben.

---

## 2. Was seit gestern dazugekommen ist

Zwei Sessions haben parallel gearbeitet; alles liegt zusammengeführt auf
`master`.

### Wand und Bild

- **Zoomregler wirkt wieder.** Der Traum-Zweig multiplizierte den Reglerwert
  nicht — und weil fast immer ein Traumgebiet gilt (4 min Haltezeit), wirkte
  der Regler an der Wand praktisch nie. Gemessen: Faktor 3 ergab 1,00×.
- **Kamerafahrt springt nicht mehr.** Drei Ursachen, alle gemessen: ein nie
  verworfener Zoom-Cache, ein beim Start eingefrorenes Fahrtziel, und die
  Kamera, die während des Layout-Umbaus weiterfuhr. Größter Sprung eines
  Frames: **618 px → 65 px**, Median 6,2 → 0,0.
- **Kamerafahrt zoomt nicht mehr ins Leere.** Ein Ziel am Rand ließ den halben
  Schirm schwarz. Der Ausschnitt wird jetzt an die Knotenwolke geklemmt
  (`RAND_LUFT = 8 %`). Schlechteste Füllung **56 % → 85 %**, Median unverändert
  92 % — die Bremse greift nur dort, wo es nötig ist.
- **Legende** unten links: rot „oft genannt", blau „Nachbarn", gelb „vor Kurzem
  gesagt". Farben werden aus dem geladenen Theme gelesen, nicht dupliziert.
- **QR-Code** unten rechts, nackt und durchscheinend (70 %), ohne Text.
  Zielseite `kollektivgedaechtnis.flashclash.de`. Die 70 % sind gemessen: unter
  **46 %** liest ihn kein Dekodierer mehr.
- **Theme f** ist die Vorgabe ohne `?theme=`.

### Foto und Portrait

- **Gesichtserkennung** bestimmt den Ausschnitt (`GESICHTS_ZOOM = 2.0`,
  `GESICHTS_BIAS = 0.46`). Ohne `cv2` schneidet die Station bit-identisch wie
  vorher — der Rückfallweg ist unverändert.
- **cv2 ist auf der Station installiert** (`opencv-python-headless 4.14.0`,
  4 Kaskaden). 🔴 Immer `"<5"` pinnen: OpenCV 5 hat `CascadeClassifier`
  entfernt, und der Code fällt dann geräuschlos auf den mittigen Schnitt
  zurück.
- **Android-App** wirft Fotos direkt bei der Station ein (`POST /api/photo`).
  Handys ohne Tailnet werfen beim Spiegel ein, der **Abholer** (`[5/6]`) holt
  alle 2 s ab.
- **Rahmen + Vorschau** in der App: Details in `docs/HANDOFF-fototest-zuschnitt.md`.

### Interview

- **Mikrofonschalter** eröffnet und beendet Interviews
  (`POST /api/interview_switch`). Eine Person kann **ohne Foto** existieren —
  wer kein Bild von sich will, nimmt trotzdem teil. Auf der Wand erscheint eine
  Scheibe ohne Bild (`--person-blank`).
- **Interview-Stop-Knopf** im Operator als Rückfall, falls die Interviewperson
  den Schalter vergisst. Nur sichtbar, wenn ein Interview läuft. Ruft denselben
  Endpunkt wie der Schalter.
- **Namen am Zitat** funktionieren — es war nie ein Codefehler, die Station
  stand nur 28 Commits zurück und hatte die Datenbankspalte nicht.

### Betrieb

- **Start holt den Stand von GitHub** (`[0/6]`), mit `--ff-only`, 45-s-Limit,
  ohne blockierendes `pause`. Überspringen mit `set KG_KEIN_PULL=1`.
- **Neuer Durchlauf archiviert, statt zu löschen**
  (`scripts/neuer-durchlauf.sh` / `.bat`) → `archiv/<zeitstempel>/`.
- **Arbeitsregeln** stehen jetzt im Repo und werden über `AGENTS.md` geladen.

---

## 2b. Ist-Zustand der Station — gemessen 2026-09-01, 13:40

Nicht angenommen, sondern mit `Get-NetTCPConnection` und `curl` über das
Tailnet nachgesehen. `netstat | findstr` reicht hier NICHT: Es zeigte Port
8800 als leer an, obwohl der Kern lief und mit 200 antwortete.

| | Zustand |
|---|---|
| Repo auf der Station | `9674cbc`, identisch mit `master`, Arbeitsbaum sauber |
| **Kern (8800)** | **läuft**, `curl http://100.94.47.6:8800/api/state` → **HTTP 200** |
| **Traum (8810)** | **läuft nicht** — Ursache unbekannt, siehe §3 |
| Spiegel (8899) | läuft nicht |
| `cv2` im venv | **4.14.0**, `CascadeClassifier` vorhanden, 4 Kaskaden |
| Geplante Aufgaben | `KgCore`, `KgDream`, `KgStt`, `KgProxy` — alle „Bereit" |
| `KgKernTest` | **läuft gerade** (Testkrücke der Foto-Session, siehe §5b) |

Damit sind zwei der fünf Voraussetzungen aus dem Testauftrag erfüllt
(Kern antwortet, `cv2` aktiv) — die anderen erst beim Durchlauf prüfbar.

## 2c. Testreihe Gesichtserkennung — gefahren 2026-09-01, 14:00–14:30

**Der Auftrag aus §5 ist zur Hälfte erledigt:** alles, was an den **7 vorhandenen
Booth-Fotos** messbar war, ist gemessen. Was neue Fotos braucht (mehrere Personen
im Bild, Halbprofil, Gegenlicht), steht weiter aus — dafür muss Birk fotografieren.

Werkzeuge, alle im Repo unter `scripts/` und auf der Station in
`C:\Users\SF-Tracking\kg-start\`:

| Skript | Beantwortet |
|---|---|
| `messreihe-gesichtserkennung.py` | Trefferquote + Zuschnitt über einen ganzen Ordner |
| `grenze-gesichtserkennung.py` | ab welchem Neigungswinkel die Kaskade durchfällt; ob eine zweite Kaskade hilft |
| `aufloesungsreihe-gesichtserkennung.py` | kostet das Verkleinern Treffer? |
| `gegentest-minsize.py` | hängt der Verlust an der `minSize`-Kopplung? |

### 🔴 Der Hauptfund: die App verkleinert Treffer weg

Die App schickt jedes Foto auf **1024 px** lange Kante (`Bildbytes.MAX_KANTE`).
Gemessen über alle 7 Fotos, Trefferquote je Auflösung:

| Auflösung | Fotos mit Gesicht |
|---|---|
| Original | **5 / 7** |
| 1280 px | 4 / 7 |
| **1024 px (das, was die App schickt)** | **3 / 7** |
| 900 px | 4 / 7 |
| 640 px | 4 / 7 |

**Zwei von fünf erkannten Gesichtern gehen allein durchs Verkleinern verloren**
(`1788105156_5.jpg`, `1788261234_app754.jpg`). Das ist kein Randfall — es trifft
den Regelbetrieb, weil jedes App-Foto diesen Weg nimmt.

**Es ist nicht „kleiner = schlechter".** Bei `app754` sprang die Trefferzahl über
die Stufen 1, 0, 0, 0, 0, 1, 1, 1, 0 — nicht monoton. Die Erkennung hängt also
nicht an der Auflösung als solcher, sondern daran, wo das Gesicht in die
Skalenpyramide von `detectMultiScale` (`scaleFactor=1.1`) fällt.

**Ursache eingegrenzt** (`gegentest-minsize.py`): `kg/photos.py` koppelt die
Mindestgröße an die Bildgröße —
`mindest = max(30, int(min(bild.size) * 0.08))`. Bei 3024×4032 verlangt das
Gesichter ab 241 px, bei 768×1024 nur noch 61 px. Gemessen bei 1024 px:

| `minSize`-Regel | Fotos mit Gesicht |
|---|---|
| jetzt (8 % kurze Kante) | 3 / 7 |
| **4 % kurze Kante** | **4 / 7** |
| fest 30 px | 4 / 7 |
| fest 60 px | 3 / 7 |

Keine Variante erzeugte Mehrfach-/Fehltreffer. Am **Original** liefern alle vier
Varianten identisch 5/7 — die Regel wirkt sich also nur auf verkleinerte Bilder aus.

🔴 **Nicht geändert.** 7 Fotos sind keine belastbare Reihe, und der Eingriff
ginge einen Tag vor der Ausstellung in den Zuschnitt jedes Portraits. Die
Entscheidung liegt bei Birk — siehe §4.

### Die Verfahrensgrenze ist jetzt eine Zahl, keine Behauptung

`grenze-gesichtserkennung.py` legt jedes Foto in 9 Neigungen (0–50°) vor:

- Von den 5 Fotos mit Gesicht halten sie bis **0°, 25°, 30°, 40°** — sehr
  streuend, kein verlässlicher Grenzwinkel.
- **Die zweite Kaskade bringt fast nichts:** `frontalface_alt2` füllte
  **1 von 34** Lücken (3 %), `profileface` **0 von 34** (0 %). Der naheliegende
  Gratis-Fix („nimm zusätzlich die Profil-Kaskade") ist damit **gemessen
  erledigt** — er trägt nicht. Wenn mehr Robustheit nötig ist, führt der Weg
  über `face_recognition`/dlib, nicht über eine weitere Haar-Kaskade.

### Eine Falle im eigenen Messwerkzeug (dokumentiert, damit sie nicht wiederkehrt)

Die erste Fassung von `messreihe-gesichtserkennung.py` meldete „Kopfanteil im
Portrait" und gab bei vier verschiedenen Fotos identisch **25,0 %** aus. Grund:
Haar-Boxen sind quadratisch (`gw == gh`), also ist `(gw*gh)/seite²` exakt
`1/GESICHTS_ZOOM²` — die Zahl misst die eigene Formel, nicht das Foto. Dasselbe
gilt für Kopfhöhe (immer 50 %) und Sitz (immer 46 %), **außer** wo der Ausschnitt
an den Bildrand klemmt. Nur diese Klemmfälle sind eine Aussage. Steht als
Kommentar im Skript.

### Was die Zahlen NICHT hergeben

- **„Das größte Gesicht gewinnt" ist weiter ungeprüft.** In keinem der 7 Fotos
  fand die Kaskade mehr als ein Gesicht (`mehrere Gesichter im Bild: 0`). Genau
  Birks Kernfrage braucht also zwingend neue Fotos mit mehreren Personen.
- **`GESICHTS_ZOOM` / `GESICHTS_BIAS` sind an Zahlen nicht beurteilbar** (siehe
  Tautologie oben) — das geht nur am Bild, und die Entscheidung ist Birks.
- 2 der 7 Fotos (`_2`, `_9`) liefern in **keiner** Auflösung und **keinem**
  Winkel einen Treffer. Ob dort ein Gesicht drauf ist, weiß nur, wer sie ansieht.

---

## 2d. 🔴 Offener Widerspruch: ein Foto kam mit 4,4 MB an

`1788261234_app754.jpg` (heute 13:13, über `POST /api/photo`, also **durch die
App**) liegt mit **4.422.388 Bytes in 3024×4032** auf der Station — das ist
unverkleinerte Kameraauflösung.

Das widerspricht dem Code: `Bildbytes.verkleinere` skaliert auf 1024 px, und
`MainActivity.schiesse()` hat nur diesen einen Pfad. Der Code ist gegengelesen
und korrekt.

Wahrscheinlichste Erklärung, **unbestätigt**: auf dem Handy läuft noch
`kollektivgedaechtnis-foto-v1.apk` (gebaut 10:00) — der Verkleinerungs-Commit
`0320093` ist von **10:26**. v1 kann das schlicht nicht.

Das ist mehr als Kosmetik: die Verkleinerung ist genau der Schritt, der laut
Messung oben **Treffer kostet**. Solange unklar ist, welche APK auf dem Gerät
liegt, misst jeder Fototest womöglich eine andere Kette als die, die am
Ausstellungstag läuft. **Vor dem nächsten Test klären** — die Statuszeile der App
nennt die gesendete Größe („Wird gesendet … (180 kB)"); zeigt sie MB, ist es eine
alte APK.

---

## 2e. 🔴 Der Matsch kommt NICHT von der App-Auflösung — gemessen 2026-09-01, 15:10

Anlass: Birk, 2026-09-01 — *die App soll nicht so stark verkleinern, sonst sieht
das Portrait auf der großen Projektionsfläche matschig aus.* Nachgemessen mit
`scripts/schaerfereihe-portrait.py` über alle 7 Fotos. **Der Verdacht bestätigt
sich nicht, und die Ursache liegt woanders — an einer Stelle, die eine höhere
App-Auflösung sogar VERSCHLECHTERT.**

### Warum die Auflösung nicht der Hebel ist

Die Station schneidet **erst** zu und skaliert **dann** auf `portrait_size = 512`
(`kg/photos.py::make_portrait`). Bei erkanntem Gesicht ist der Ausschnitt
`2.0 × Gesichtsbreite` — er hängt an der **Gesichtsgröße**, nicht an der
Bildgröße. Gemessen liegt der Ausschnitt bei 1024 px Lieferung schon zwischen
550 und 1024 px, also **überall ≥ 512**. Es wird nirgends hochgerechnet:

| App liefert | Fotos hochgerechnet | mittlere Schärfe |
|---|---|---|
| **1024 px (heute)** | **0 / 7** | **357** |
| 1280 px | 1 / 7 | 335 (−6 %) |
| 1600 px | 1 / 7 | 336 (−6 %) |
| Original | 1 / 7 | 319 (−11 %) |

**Mehr Auflösung bringt keine Schärfe, sie kostet welche.** Der Grund ist kein
Bildfehler: Bei höherer Auflösung *greift die Erkennung öfter*, der Ausschnitt
wird enger und folgt dem Kopf — und ein enger Ausschnitt hat weniger echte Pixel
als der weite mittige Schnitt. Das ist der gewünschte Zuschnitt, aber er ist
rechnerisch weicher.

### Der wirkliche Matsch: ein kleines Gesicht wird 4,2-fach hochgerechnet

`1788105156_5.jpg` ist der Fall, den Birk vermutlich gesehen hat:

- Erkanntes Gesicht: **61 × 61 px** (0,4 % der Bildfläche — Person steht weit weg)
- Ausschnitt: `61 × 2.0` = **122 px**
- Hochgerechnet auf 512 → **Faktor 4,2**
- Schärfe: **9,6** gegenüber 677 beim mittigen Schnitt — **1 %**

🔴 **Und genau dieses Foto kippt in die Erkennung, sobald die App mehr liefert.**
Bei 1024 px findet die Kaskade nichts, schneidet mittig, 576 px, scharf. Ab
1280 px findet sie das kleine Gesicht — und das Portrait wird Matsch. Die
Erhöhung von `MAX_KANTE`, die ich in §4 als Weg (b) empfohlen hatte, **erzeugt
diesen Fall, statt ihn zu beheben.** Empfehlung zurückgezogen.

### Die eigentliche Stellschraube — ✅ EINGEBAUT 2026-09-01, 15:40

Es fehlte eine **Untergrenze**: Ein Ausschnitt unter `portrait_size` (512 px)
darf nicht hochgerechnet werden. Birk hat sich für **(A)** entschieden
(*„kleiner scharfer Kopf statt großer matschiger"*), umgesetzt in
`kg/photos.py` als `MINDEST_AUSSCHNITT = 512`:

```python
side = min(int(round(gw * GESICHTS_ZOOM)), width, height)
side = min(max(side, MINDEST_AUSSCHNITT), width, height)   # neu
```

Das `min(..., width, height)` außen ist nicht kosmetisch: Ist das Bild selbst
kleiner als 512, bleibt es beim größtmöglichen Quadrat — Pixel erfinden kann auch
diese Regel nicht.

**Belegt am echten Foto** (`scripts/beleg-untergrenze.py`, auf der Station gegen
eine Kopie gefahren, ohne den laufenden Kern anzufassen):

| `1788105156_5.jpg` | Ausschnitt | Skalierung | Schärfe |
|---|---|---|---|
| vorher | 122 px | 0,24× (hochgerechnet) | **9,6** |
| nachher | 512 px | 1,00× | **1552,5** |

**Und die anderen 6 Fotos sind unverändert** — jeweils identischer Ausschnitt und
identische Schärfe. Die Regel fasst genau den kaputten Fall an und sonst nichts.

**Tests:** 5 neue in `tests/test_photos_gesicht.py`, dazu die Hilfsformel
`_erwarteter_ausschnitt` nachgezogen. **4 Mutationsproben, alle tot:**
Untergrenze entfernt (6 Tests rot), `max`→`min` (12 rot), Klemmung ans Bild weg
(1 rot), `MINDEST_AUSSCHNITT = 0` (2 rot).

🔴 **Was das NICHT löst:** Die Erkennung findet dieses Gesicht überhaupt nur bei
kleinen Auflösungen (§2c). Die Untergrenze sorgt dafür, dass ein Treffer nicht
mehr schadet — sie macht die Erkennung nicht treffsicherer.

---

## 3. 🔴 Was NICHT geprüft ist

Ehrlich getrennt: gemessen ist nur, was hier nicht steht.

| Punkt | Warum offen |
|---|---|
| **Ein kompletter Durchlauf** — Foto → Interview → Verdichtung → Traum → Wand | Nie am Stück gefahren. Das ist der Zweck der nächsten Session. |
| **Traum (Port 8810)** | Läuft nicht. **Ursache eingegrenzt 2026-09-01, 14:25:** Die geplante Aufgabe `KgDream` startet `C:\Users\birk\kg_dream.bat` — eine **veraltete Datei außerhalb des Repos**, nicht den regulären Dienst `C:\Users\SF-Tracking\kg-start\dienste\dienst-traum.bat`. Letzter Lauf 2026-08-31 10:42, Ergebnis `-2147023829` (0xC000041D, „Fehler in einer Callback-Routine"). Das Traum-Log zeigt einen **erfolgreichen** Start um 12:59 (`Uvicorn running on 0.0.0.0:8810`) — er lief also und ist danach beendet worden, vermutlich mit dem Fenster. 🔴 **Nicht selbst gestartet:** der reguläre Weg ist Birks START-Verknüpfung, und `KgDream` zeigt auf die falsche Datei. Wer sie repariert, ändert eine geplante Aufgabe am Vorabend der Ausstellung — das ist Birks Entscheidung. |
| **Die Wand am Beamer** | Legende, QR-Größe und Portraitausschnitt sind an Messbildern beurteilt, nicht im Raum. Ob 132 px QR aus Besucherabstand reichen, weiß nur der Raum. |
| **Gesichtserkennung an echten Booth-Fotos** | **Teilweise erledigt, siehe §2c.** Gemessen an allen 7 Bestandsfotos (Trefferquote, Auflösung, Neigung, zweite Kaskade). **Offen bleibt genau das, wofür neue Fotos nötig sind:** mehrere Personen im Bild (kam im Bestand kein einziges Mal vor), Halbprofil, Sonnenbrille, Gegenlicht. |
| **Der End-to-End-Durchlauf** | **Nicht gefahren.** Nicht aus Zeitmangel: Foto einwerfen heißt ein Interview eröffnen, und ein Interview braucht eine sprechende Person vor dem Mikrofon. Ein Agent kann diesen Durchlauf nicht allein fahren — er kann ihn nur vorbereiten. Traum (8810) läuft weiterhin nicht (siehe unten). |
| **Flackern der Wand** | Cron-Job als Ursache **widerlegt** (gemessen). HDR ist der Hauptverdacht (Display-Ereignis 4121), nicht bewiesen. |
| **Doppelter Uploader** | Lief heute Morgen zweimal (PID 5348 + 11508). Nach dem Neustart nicht erneut geprüft. |
| **STT-Textfenster, rechte Spalte** | Bleibt leer, weil nur ein Erkenner läuft (`--channels regie`). Liegt im fremden Repo `meredityman/fundusbot`. |

---

## 4. Entscheidungen, die BIRK trifft

Kein Agent setzt diese Werte allein — sie sind Setzungen, keine Messergebnisse:

### 🔴 NEU 2026-09-01, aus der Testreihe (§2c) — das sind die dringenden

- **Soll die App weiter auf 1024 px verkleinern? → JA, gemessen (§2e).** Zwei
  Messungen ziehen hier gegeneinander, und die zweite gewinnt:
  – Mehr Auflösung **findet mehr Gesichter** (5/7 statt 3/7, §2c).
  – Mehr Auflösung **liefert unschärfere Portraits** (−6 bis −11 %, §2e) und
    erzeugt genau den Matsch-Fall, weil dann kleine, weit entfernte Gesichter
    erkannt und 4,2-fach hochgerechnet werden.
  🔴 **`MAX_KANTE = 1024` bleibt.** Meine frühere Empfehlung, auf 1600 zu gehen,
  ist durch §2e **widerlegt** — sie hätte die Bildqualität verschlechtert.
- **Der Matsch ist ein Zuschnitt-Problem, kein Auflösungsproblem.** ✅ **Erledigt
  2026-09-01:** Birk hat (A) entschieden, `MINDEST_AUSSCHNITT = 512` ist
  eingebaut und belegt (§2e). Schärfe im kaputten Fall 9,6 → 1552,5; die übrigen
  6 Portraits unverändert.
- **🔴 Die Station läuft noch auf dem alten Stand.** `git log` dort: `7ede951`,
  der Fix ist `4b8c0c5`. Die Änderung wirkt erst nach einem Neustart über die
  START-Verknüpfung (Schritt `[0/6]` zieht selbst von GitHub). **Nicht per SSH
  nachgezogen:** der Kern läuft gerade und antwortet auf 8800; ein Eingriff im
  Betrieb ist Birks Entscheidung.
- **`minSize` von 8 % auf 4 %** (§2c) bringt mehr Treffer — und ist jetzt
  **gefahrloser als vorher**, weil die Untergrenze den Matsch-Fall abfängt.
  Trotzdem nicht umgesetzt: 7 Fotos sind keine Reihe.
- **Welche APK liegt auf dem Handy?** Siehe §2d — bis das geklärt ist, misst
  jeder weitere Fototest womöglich eine andere Kette als die vom Ausstellungstag.
- **Fotos mit mehreren Personen fehlen komplett.** Die Kernfrage („gewinnt das
  größte Gesicht?") ist an den 7 Bestandsfotos **nicht beantwortbar** — in keinem
  fand die Kaskade mehr als ein Gesicht. Dafür muss Birk fotografieren.

### Bestehende Setzungen

- **Bei mehreren Gesichtern gewinnt das größte.** Annahme (die befragte Person
  steht vorn), nicht gemessen.
- **`GESICHTS_ZOOM = 2.0`, `GESICHTS_BIAS = 0.46`** — von Birk am eigenen Foto
  abgenommen, nicht optimiert. Sie stehen als feste Zahlen im Test, mit Datum
  und Zitat.
- **Haar-Kaskade findet nur frontale Gesichter.** Halbprofil fällt durch und
  landet im mittigen Schnitt. Das ist eine Verfahrensgrenze, keine Einstellung.
- **QR-Deckkraft 70 %** — bis etwa 55 % ist Luft, darunter neu messen.
- **Legende bei 45 % Deckkraft** — am Beamer noch nicht beurteilt.
- **Alternativ-Foto-Cache**: entschieden ist „Ersatzfoto der zuletzt
  interviewten Person zuordnen". Gebaut ist er **nicht**
  (`docs/HANDOFF-alternativ-foto-cache.md`).

---

## 5. Wenn die nächste Session anfängt

### Der Auftrag aus der Vorsession: zur Hälfte erledigt (§2c)

**Erledigt 2026-09-01:** alles, was an den 7 vorhandenen Booth-Fotos ohne Birk
messbar war — Trefferquote, Auflösungsabhängigkeit, Neigungsgrenze, zweite
Kaskade, `minSize`-Gegentest. Vier Messwerkzeuge liegen im Repo und auf der
Station. **Der Hauptfund (Verkleinern kostet Treffer) steht in §2c, die
Entscheidungen daraus in §4.**

**Offen und nur MIT Birk machbar** — das ist der Rest des Auftrags:

1. **Foto mit mehreren Personen** einwerfen. Die Kernfrage („gewinnt das größte
   Gesicht?") ist ohne solche Fotos nicht beantwortbar; im Bestand gibt es keins.
2. **Halbprofil / Gegenlicht / Brille** — die vermuteten Ausfälle.
3. Danach: `messreihe-gesichtserkennung.py <ordner>` über den erweiterten
   Bestand, die Zahlen stehen dann direkt vergleichbar neben §2c.

```cmd
cd C:\Users\SF-Tracking\kg-start
C:\Users\birk\kollektivgedaechtnis\.venv\Scripts\python.exe ^
  messreihe-gesichtserkennung.py C:\Users\birk\kollektivgedaechtnis\data\photos
```

Vorher `Bildbytes.MAX_KANTE` bzw. die APK-Frage aus §2d klären — sonst misst die
Reihe die falsche Kette.

### Der End-to-End-Durchlauf

**Nicht gefahren, und zwar aus einem strukturellen Grund:** Jedes Foto eröffnet
ein Interview, und ein Interview braucht eine sprechende Person vor dem Mikrofon.
Foto → Interview → Verdichtung → Traum → Wand ist als Kette **nicht
agentenfahrbar** — messbar ist nur, was der Agent vorbereitet hat:

| Glied | Stand 2026-09-01, 14:30 |
|---|---|
| Kern (8800) | läuft, HTTP 200 über Tailnet |
| STT (5051) | läuft |
| `cv2` + Kaskade | aktiv, 4.14.0 |
| Foto → Portrait | gemessen, siehe §2c |
| **Traum (8810)** | **läuft nicht** — §3, `KgDream` zeigt auf die falsche Datei |
| Interview / Wand | braucht Menschen und den Beamer |

Vor dem Durchlauf muss der Traum hoch (Birks START-Verknüpfung, nicht per SSH).

### Der Weg dorthin

1. `AGENTS.md` + `docs/ARBEITSREGELN-ausstellungsrechner.md` lesen.
2. Auf der Station als `SF-Tracking` anmelden, Station über den Desktop-Knopf
   starten (**nicht** über SSH — Dienste sterben mit der Sitzung).
3. Erreichbarkeit **messen**: `Get-NetTCPConnection` auf 8800, dann ein `curl`
   über das Tailnet. Ein Log, das „gestartet" sagt, ist kein Beleg.
4. Dann der Durchlauf: Foto einwerfen → Interview führen → schauen, ob Name,
   Portraitausschnitt, Zitat, Traum und Kamerafahrt zusammen stimmen.
5. Was auffällt, gehört in dieses Dokument — nicht in ein neues Handoff. Es
   lagen heute **elf** davon nebeneinander, acht davon erledigt.

### Zwei Fallen aus der Foto-Session

- Der **Sucherrahmen zeigt den Rückfallweg** (mittiger Schnitt), nicht den
  Gesichtsweg. Wer ihn ändert, muss `kg/photos.py::_square_crop` gegenlesen.
- Die **Vorschau kommt nur beim direkten Weg** (`100.94.47.6:8800`), nicht
  über den Spiegel — dort entsteht das Portrait erst beim Abholen. Kein
  Fehler.

---

## 5b. Was noch aufzuräumen ist

Aus der Foto-Session übrig, jeweils mit Begründung warum es nicht schon
erledigt ist:

| Was | Wo | Anmerkung |
|---|---|---|
| Geplante Aufgabe `KgKernTest` | Ausstellungsrechner | **läuft gerade** (gemessen 13:40). `schtasks /delete /tn "KgKernTest" /f` — war eine Testkrücke, kein Dauerzustand. Nicht selbst entfernt: sie hält womöglich den Kern, der gerade auf 8800 antwortet. Wer sie löscht, muss den Kern danach über die START-Verknüpfung neu starten. |
| Worktree `kg-app` | `$VOL/projekte/kg-app` | gehört der Foto-Session, steht auf `master` |
| APK `out/kollektivgedaechtnis-foto-v6.apk` | vServer | bewusst nicht im Git (3,6 MB Binär), neu bauen nach `android/README.md` |

**Erledigt am 2026-09-01, jeweils nachgeprüft:**

- **Testempfang auf Port 8805 beendet** (`scripts/testempfang.py`, PID 857211
  und Kinder). Port frei, geprüft mit `ss -tlnp`.
- **Doppelter `kg-start` unter `birk`** nach
  `C:\Users\birk\station-sicherung-2026-09-01\kg-start-birk-ungenutzt\`
  verschoben (nicht gelöscht), auf Birks Freigabe. Vorher geprüft: alle drei
  Dienst-Skripte darin waren bit-identisch mit denen unter `SF-Tracking`, und
  die Startdatei nutzt `%~dp0dienste` — also ihren eigenen Ordner, nie den
  unter `birk`. Die Desktop-Verknüpfung zeigt auf die `SF-Tracking`-Fassung.
- **Acht erledigte Handoffs** nach `docs/archiv/`, alle Verweise mitgezogen.

---

## 6. Wo die Sicherungen liegen

Auf der Station, `C:\Users\birk\station-sicherung-2026-09-01\`:

- `kg-start-birk-ungenutzt\` — der doppelte Startordner unter `birk`. Die
  Station startet aus `SF-Tracking`; dieser hier lief nie. Verschoben, nicht
  gelöscht.
- `kollektivtraum.bat.alt` — die Startdatei vor dem Pull-Schritt.
- `test_meta_antwort.py`, `test_mic_switch.py` — unversionierte Testdateien,
  die einem Pull im Weg standen.
- `C:\Users\birk\sicherung-arbeitsbaum-2026-09-01.patch` — 371 Zeilen aus dem
  Arbeitsbaum der Station (eine ältere Fassung des Mikrofonschalters).
  Zeile für Zeile geprüft: alles davon steckt in `master`.
