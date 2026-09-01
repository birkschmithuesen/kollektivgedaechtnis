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

## 2d. ✅ Geklärt: auf dem Handy liegt die alte APK v1

`1788261234_app754.jpg` kam mit 4,4 MB in 3024×4032 an, obwohl der App-Code auf
1024 px verkleinert. **Ursache belegt 2026-09-01, 15:15** — die APKs im
DEX-String-Pool verglichen:

| APK | gebaut | `verkleinere` / `MAX_KANTE` | Sucherrahmen + Vorschau |
|---|---|---|---|
| **v1** | 10:00 | **fehlt** | fehlt |
| v2–v5 | 10:26–12:04 | vorhanden | fehlt |
| **v6** | 12:31 | vorhanden | **vorhanden** |

Der Verkleinerungs-Commit `0320093` ist von 10:26 — **v1 kann es schlicht
nicht.** Damit ist der Widerspruch aufgelöst: kein Codefehler, eine alte
Installation.

🔴 **v6 ist die einzige vollständige APK** (`out/kollektivgedaechtnis-foto-v6.apk`,
3,6 MB, nicht im Git). Signatur mit dem echten Werkzeug geprüft (apksigner auf
herkules, die Toolchain liegt dort): **`Verifies`**, v2-Schema, ein Signierer —
für Android 7+ ausreichend. Berechtigungen nur CAMERA, INTERNET,
ACCESS_NETWORK_STATE, DUMP.

**Vor dem nächsten Fototest v6 installieren**, sonst misst der Test eine andere
Kette als die vom Ausstellungstag. Kontrolle ohne Nachdenken: `pruefe-neue-fotos.py`
meldet jedes Foto mit langer Kante über 1024 px als „kam NICHT durch die aktuelle
App".

⚠️ **Prüfmethode, die NICHT funktioniert:** `unzip` gibt es auf dem vServer
nicht, und `strings` auf der APK liefert nichts (DEX ist komprimiert). Beides
sah nach „Marker fehlt" aus und war nur ein kaputtes Werkzeug. Richtig ist
`zipfile` + Suche im entpackten DEX (so gemacht).

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

### Die eigentliche Stellschraube — eingebaut, dann NACHGESCHÄRFT

🔴 **Die hier beschriebene harte Untergrenze gilt so nicht mehr.** Sie war zu
grob und nahm knappen Fällen den Zoom — Birk hat das am selben Tag am Material
gesehen. Ersetzt durch `MAX_HOCHRECHNUNG = 1.3`, **siehe §2g**. Der Abschnitt
bleibt stehen, weil die Messung dahinter weiter gilt.

### Die erste Fassung (überholt)

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

## 2f. Neustart + Rückweg-Test — gefahren 2026-09-01, 15:00–15:20

Birk (nur am Handy): *„Starte alles neu und lass den Test machen, ob der Foto
Ausschnitt zurück auf die Handy App kommt."* Ohne Gerät nachgefahren — der
Rückweg ist per HTTP prüfbar, weil die App nichts anderes tut.

### Der Neustart

Gestoppt mit `scripts/station-stop.ps1` (die Muster von
`kollektivtraum-stop.bat`, aber ohne `pause`, sonst hängt es über SSH). Vorher
`schtasks /end /tn KgKernTest` — die Testkrücke hielt den alten Kern und hätte
Port 8800 blockiert. Danach **alle Ports frei**, gemessen.

Gestartet über eine geplante Aufgabe `KgVollstart` mit `/it` (interaktiv), die
`kollektivtraum.bat` in **Session 6** ausführt — dort, wo `SF-Tracking`
angemeldet ist. Ein direkter SSH-Start wäre mit der Sitzung gestorben
(Arbeitsregel 4).

**Ergebnis, gemessen statt geglaubt** (`schtasks /run` meldet Erfolg auch ohne
Start, Pitfall 3):

| | vorher | nachher |
|---|---|---|
| Kern 8800 | läuft | **HTTP 200** |
| **Traum 8810** | **läuft nicht** | **HTTP 200** ✅ |
| STT 5051 | läuft | läuft |
| Repo-Stand | `7ede951` | **`b5c2c8e`** (Schritt `[0/6]` hat selbst gezogen) |

🔴 **Der Traum läuft damit erstmals** — der Punkt aus §3 hat sich mit dem
regulären Start von selbst erledigt. Die kaputte Aufgabe `KgDream` (zeigt auf
`C:\Users\birk\kg_dream.bat`) wurde dafür **nicht** gebraucht und **nicht**
angefasst; der reguläre Weg startet den Traum als `[3/6]`.

### Der Rückweg zur App — funktioniert

`scripts/pruefe-app-rueckweg.py` fährt exakt die Kette der App: rohe JPEG-Bytes
in den Rumpf (kein multipart), Antwort lesen, Portrait über `/media/portraits/`
abholen. Eingeworfen wurde das Matsch-Foto `1788105156_5.jpg`:

```
1. POST /api/photo   -> HTTP 200
   {"ok":true,"portrait":"1788267931_app849.png"}
2. Portraitname      -> 1788267931_app849.png
3. GET /media/portraits/1788267931_app849.png
   -> HTTP 200, 245 kB, image/png
```

Alle drei Glieder sind belegt — auch das dritte, an dem die Vorschau hängt. Ein
`ok: true` allein hätte nichts bewiesen: die Vorschau blieb schon einmal stumm,
weil eine Gegenstelle `ok` sagte, aber kein `portrait`-Feld lieferte.

### Der Fix wirkt im laufenden Betrieb

Das Portrait, das der **laufende Server** für dieses Foto geschrieben hat, hat
Schärfe **229,4**. Derselbe Wert kommt heraus, wenn man `make_portrait` mit
Untergrenze fährt — ohne sie sind es **3,1**:

| `1788105156_5.jpg`, fertiges Portrait | Schärfe |
|---|---|
| ohne Untergrenze (alter Zustand) | **3,1** |
| mit Untergrenze (jetzt live) | **229,4** |

**Gegenprobe** an einem guten Foto (`1788115087_6.jpg`): 7,1 gegen 7,1 —
unverändert. Die Regel fasst nur den kaputten Fall an.

🔴 **Zwei Fehlvergleiche unterwegs, damit sie niemand wiederholt:**
1. Das neue Portrait (229,4) gegen das **alte auf der Platte** (738,3) zu
   halten ist ungültig — das alte stammt aus einem anderen Zuschnitt (mittiger
   Schnitt, weil die Erkennung damals nicht griff), nicht aus dem alten Code.
2. Den **Zuschnitt** (1552,5) gegen das **fertige Portrait** (229,4) zu halten
   ebenso: Maske und Goldring senken die Kantenschärfe systematisch. Vergleiche
   nur Endprodukt gegen Endprodukt, durch denselben `make_portrait`.

### Was das NICHT beweist

- **Die App selbst wurde nicht getestet** — nur ihr Weg. Ob das Handy die
  Vorschau anzeigt, hängt zusätzlich an der installierten APK (§2d).
- Der Einwurf hat, wie vorgesehen, **ein Interview eröffnet**. Der
  Personenzähler ist entsprechend um eins höher.

---

## 2g. 🔴 Birks Fototest am Gerät — zwei Befunde, beide behoben (2026-09-01, 15:30)

Birk hat mit v6 ein Foto **mit drei Personen** gemacht. Zwei Einwände, beide
berechtigt, beide gemessen und gefixt.

### Einwand 1: „nicht auf das zentrale Gesicht gezoomed"

**Das war mein eigener Fix von mittags.** Die harte Untergrenze
`MINDEST_AUSSCHNITT = 512` weitete *jeden* Ausschnitt unter 512 px auf — auch
den, dem gar kein Matsch drohte. An Birks Foto (`1788269177_app363.jpg`):

| | Ausschnitt | Zoom | Schärfe |
|---|---|---|---|
| alte harte Grenze | 512 px | **79 %** | 158 |
| **neu, Faktor 1,3** | **402 px** | **100 %** | 52 |

Der Ausschnitt hätte nur **1,27×** hochgerechnet werden müssen — die Regel
behandelte das wie den echten Schadensfall von 4,2×.

**Neue Regel:** `MAX_HOCHRECHNUNG = 1.3` in `kg/photos.py`. Nicht die
Ausschnittgröße wird begrenzt, sondern die **Hochrechnung**. Bis 1,3× bleibt der
Zoom unangetastet, erst darüber wird aufgeweitet — und nur so weit, dass die
Grenze eingehalten ist.

**1,3 ist gemessen** (`scripts/kompromiss-zoom-schaerfe.py`, 6 Kandidaten von
1,0 bis „ohne Grenze"): Es ist der größte Faktor, bei dem **alle** Portraits über
der Matschschwelle (~50) bleiben und Birks Foto den vollen Zoom behält.

| Foto (Gesicht) | alt: Zoom/Schärfe | neu: Zoom/Schärfe |
|---|---|---|
| app363 (201 px) | 79 % / 158 | **100 % / 52** |
| app893 (71 px) | 28 % / 743 | **36 % / 93** |
| app849 (61 px) | 24 % / 229 | **31 % / 107** |

Ohne jede Grenze fällt app849 auf Schärfe **3,1** — der ursprüngliche Matsch.
Die Regel bleibt also nötig, sie war nur zu grob.

**Tests:** neuer Test `test_ein_knapp_zu_kleiner_ausschnitt_behaelt_seinen_zoom`
mit Birks echten Zahlen. **4 Mutationsproben, alle tot** — darunter „zurück zur
alten harten Grenze 512", die genau seinen Einwand rot macht.

### Einwand 2: „soll aber Vollbild angezeigt werden"

Die Vorschau hing als **140dp-Kachel** in der Ecke. Auf einer Briefmarke ist
nicht zu beurteilen, ob der Ausschnitt sitzt — und genau dafür ist sie da.
Jetzt formatfüllend über dem Sucher, `fitCenter` auf Schwarz (derselbe
Hintergrund wie die Projektionswand, also dasselbe Urteil).

Drei Folgeänderungen, die ohne den Umbau nicht nötig waren:
- **Auslösen blendet die alte Vorschau weg** — sonst schießt man blind, weil das
  vorige Portrait den Sucher verdeckt. Als Eckkachel war das egal.
- **Statuszeile sagt „antippen zum Schließen"** — formatfüllend sieht es sonst
  aus, als hänge die App.
- Beim Schließen zurück auf „Gesendet — Interview läuft".

### v7 gebaut und geprüft

`out/kollektivgedaechtnis-foto-v7.apk` (4,6 MB) — **inzwischen durch v8 ersetzt (§2i)** — gebaut auf herkules
(`~/kg-android`, die Toolchain liegt dort — auf dem vServer gibt es keine).

**Belegt, nicht angenommen:** im Binär-Layout von v6 steckt der 140dp-Wert, in
v7 nicht mehr → formatfüllend. Der neue String `vorschau_offen` ist in v7,
in v6 nicht. Signatur `Verifies`, Zertifikat **identisch mit v1/v6**
(`b1f145d4…`) → **drüber installieren, kein Deinstallieren nötig**.

⚠️ **Die Station braucht den Zoom-Fix noch:** Sie läuft auf `b5c2c8e` (harte
Grenze). Der neue Faktor wirkt erst nach einem Neustart über die
START-Verknüpfung. Ohne den bleibt es beim 79-%-Zoom, auch mit v7.

---

## 2h. Analyse-Prompt: zwei Sprecher — und ein größerer Befund (2026-09-01, 16:20)

Birk: *„Im Interview sprechen die fragende Person und die antwortende Person in
dasselbe Mikrofon. Es macht Sinn, das in den Analyse-Prompt zu schreiben — nur
die Aussagen der antwortenden Person zählen, die Fragen sind aber für den
Kontext wichtig. Und die Fragen sind nicht zwangsläufig exakt die drei
gesetzten."*

**Die Prämisse stimmt, gemessen:** `scripts/finde-interviews.py` über alle 44
Sitzungen im Transkript — **überall genau EIN `recognizer_id`**. Die Station
läuft mit `--channels regie`, beide Stimmen landen unmarkiert im selben Kanal.
Die Trennung kann also nur der Prompt leisten, nicht die Technik.

### Was im Prompt steht (`kg/extraction.py`)

Neuer Block „ZWEI STIMMEN, EIN KANAL" mit drei Regeln: Begriffe und Zitat
**nur** aus den Antworten; die Fragen als **Kontext** mitlesen (eine Antwort wie
„Ja, unbedingt, aber nur wenn die Leute vor Ort mitreden" ist ohne die Frage
sinnlos); und die Frage **nicht** zum Thema der Antwort machen. Dazu ein
Abschnitt, dass die drei Leitfragen **der Plan sind, nicht das Protokoll** —
frei formuliert, gekürzt, umsortiert, übersprungen. Und beim Namen: auch die
fragende Person stellt sich vor, oft **zuerst** — der erste Name ist nicht
automatisch der richtige.

### 🔴 Gemessen: der Zusatz hilft kaum

`scripts/ab-analyse-prompt.py`, 5 echte Interviews × 3 Läufe je Fassung
(30 LLM-Aufrufe):

| Fassung | Begriffe im Schnitt | mit Zitat | mit Name | **leer** |
|---|---|---|---|---|
| ohne Block | 1,6 | 6/15 | 6/15 | **9/15** |
| mit Block | 2,3 | 6/15 | 5/15 | **8/15** |

Mehr Begriffe, aber Zitat und Name unverändert — bei dieser Stichprobe ist das
**kein belastbarer Gewinn**. Der Block bleibt trotzdem drin: Er beschreibt die
Wirklichkeit korrekt, und der Schaden ist messbar null.

### 🔴 Der eigentliche Fund: 2 von 5 Interviews liefern GAR NICHTS

Und zwar **reproduzierbar, in beiden Fassungen**:

| Sitzung | Zeichen | Ergebnis über 6 Läufe |
|---|---|---|
| 37 | 3258 | **6/6 voll** (6 Begriffe, Zitat, Name — stabil) |
| 6 | 2973 | 6/6 voll, aber schwankende Qualität |
| 5 | 3349 | 5/6 **leer** |
| **19** | 2945 | **6/6 leer** |
| **30** | 4689 | **6/6 leer** |

Ein leeres Ergebnis heißt: die Person bekommt **keinen Begriff, kein Zitat,
keinen Namen** — sie erscheint als leere Scheibe auf der Wand. Das ist der
Unterschied zwischen „Prompt-Feinschliff" und „ein Drittel der Besucher fällt
aus".

**➜ Als Aufgabe an Claude Code delegiert (2026-09-01, 16:40)**, Opus mit
`--effort high` + ultrathink. Brief: `/tmp/brief-leere-interviews.md`. Auftrag:
Ursache belegen (nicht raten), beheben, Test mit Mutationsprobe, committen ohne
push. Rechte über `--settings` statt `--dangerously-skip-permissions` (das ist
auf diesem Server hart geblockt) — `ssh`/`scp`/`git push` sind **verboten**,
damit der Agent die PII-Transkripte auf der Station gar nicht erreichen kann.
Ausdrücklich untersagt: die volle 25-Minuten-Suite. Nur
`pytest -k "extraction or pipeline"` (Baseline **29 passed**, ~10 s).

**Der Grund liegt am Interview, nicht am Prompt** (der Ausfall ist in beiden
Fassungen identisch). Sitzung 30 hat 825 Wörter, aber die häufigsten sind
„ähm 34, ja 30, wir 30, mhm 16" — das ist ein **Arbeitsgespräch** (Aufbau,
Technik), kein Interview. Solche Aufnahmen korrekt zu verwerfen ist richtig.
**Ungeprüft ist, ob Sitzung 5 und 19 auch Arbeitsgespräche sind** — dafür
müsste jemand hineinhören, und das ist eine Sichtprüfung an realen Aussagen,
kein Agentenschritt.

### Nebenbefund: `interview_end_index` ist instabil

Derselbe Text, derselbe Prompt, drei Läufe — das gefundene Ende schwankt
zwischen **0 % und 100 %** (Sitzung 30: 100, 0, 100, 52, 100, 49). Bei 0 % wird
das ganze Interview verworfen. Nur Sitzung 37 ist stabil (56–100 %). Das ist ein
eigener Fehler, unabhängig von den zwei Sprechern, und **nicht behoben**.

🔴 **PII-Disziplin eingehalten:** Alle Skripte laufen auf der Station und geben
nur Kennzahlen und die extrahierten Begriffe aus. Transkripttext, Zitate und
Namen realer Personen sind **nie** in den Agenten-Kontext gelangt.

---

## 2i. Auflösung zurück auf 1600 px — die frühere Messung galt nur für ferne Personen

Birk: *„Wieso das Foto nicht mit besserer Auflösung reinholen"* und, entscheidend:
*„in der Installation wird es gar nicht so weit weg sein."*

**Der zweite Satz kippt die Messung von 15:10 (§2e).** Dort kam heraus: mehr
Auflösung = unschärfere Portraits. Das galt für Fotos mit **kleinen, fernen**
Gesichtern — bei höherer Auflösung greift die Erkennung dort öfter, und ein
enger Gesichtsausschnitt hat weniger Pixel als der weite mittige Schnitt.

Bei **nahen** Personen dreht sich das um. Die Rechnung ist einfach und hängt an
`GESICHTS_ZOOM = 2.0`:

> Ausschnitt = Gesicht × 2. Für ein Portrait von 512 px ohne Hochrechnung muss
> das Gesicht also **mindestens 256 px** groß sein.

Gemessen an Birks Booth-Fotos, alle bei 1024 px geliefert:

| Foto | Gesicht | Ausschnitt | Hochrechnung |
|---|---|---|---|
| app849 | 61 px | 122 px | 4,2× |
| app893 | 71 px | 142 px | 3,6× |
| app363 (3 Personen) | 201 px | 402 px | 1,27× |
| app043 | 218 px | 436 px | 1,17× |

**Alle vier unter 256 px** — jedes Portrait wurde hochgerechnet. Bei 1600 px
sind dieselben Gesichter 1,56× größer (201 → 314 px), der Ausschnitt kommt über
512, und das Portrait besteht aus **echten** Pixeln statt gerechneten.

Dazu ein zweiter Befund: `1788261234_app754.jpg` (3024×4032, das einzige
unverkleinerte Foto) — die Kaskade findet das Gesicht **nur im Original**, ab
2048 px nicht mehr. Mehr Auflösung hilft dort auch der Erkennung.

**`Bildbytes.MAX_KANTE` steht jetzt auf 1600** (war 1024). Preis: grob 2,4× die
Datenmenge. Am Booth zählt Tempo — wird das Senden spürbar langsam, ist das die
erste Stellschraube zurück.

🔴 **Nicht gemessen, weil es die Fotos nicht hergibt:** ob die Erkennung bei
1600 px genauso zuverlässig greift wie bei 1024. Alle vorhandenen App-Fotos
**sind** bereits auf 1024 verkleinert — man kann sie nicht vergrößern, ohne
Pixel zu erfinden. Das beantwortet erst der nächste Fototest mit v8.

---

## 2j. Die leeren Interviews: die billige Erklärung trägt nicht (2026-09-01, abends)

Bearbeitung des Briefs aus §2h. **Die naheliegende Hypothese ist widerlegt**,
und zwar zweimal — an den bereits vorliegenden Zahlen und am Code selbst.

### Widerlegung 1: `end_index = 0` verwirft im Code gar nichts

`kg/pipeline.py` schneidet mit `text[:end].strip() or text.strip()` — bei
`end = 0` fällt das auf den **vollen Text** zurück. Und `result.terms` wird vom
Index überhaupt nie berührt. Ein Lauf mit `end = 0`, sechs Begriffen, Zitat und
Namen durch die echte Pipeline gefahren:

```
status: done | Kanten: 2 | Zitate: 1 | Name: 'Mara' | Transkript: 213/213 Zeichen
```

Nichts geht verloren. Der Satz „bei `interview_end_index = 0` ist das ganze
Interview verworfen" gilt **nur als Anweisung an das Modell**, nicht im
Programm.

### Widerlegung 2: leere Läufe gibt es auch ganz ohne Beschneidung

Nachgerechnet an der Messung aus §2h: von 30 Läufen waren **17 leer**, aber nur
**7 hatten `ende = 0 %`** — also höchstens **41 %**. Entscheidender ist die
Gegenrichtung: mindestens **6 leere Läufe hatten `ende = 100 %`** (Sitzung 30
allein 3), dort wurde also **überhaupt nichts abgeschnitten** und es kam
trotzdem nichts. Der Ende-Index kann für diese Läufe nicht die Ursache sein.

### 🔴 Und: ein Teil der Messung war das Messwerkzeug

`scripts/ab-analyse-prompt.py` verbuchte einen **fehlgeschlagenen** LLM-Aufruf
als `terms=0, quote=0, name=0, ende=0.0` — und den Fehlertext hat es zwar
gespeichert, aber **nie gedruckt**. Jeder Fehler erschien dadurch gleichzeitig
als „leer" **und** als „ende = 0 %". Die Korrelation zwischen den beiden
Befunden aus §2h ist zu einem guten Teil dieses Skript gewesen. Passend dazu:
Sitzung 37 hat als einzige **keine** leeren Läufe — und als einzige **keine**
Null im Ende-Index. Das Skript zählt jetzt Fehler getrennt und druckt sie.

**Folge:** die „Instabilität zwischen 0 % und 100 %" ist enger als berichtet.
Ohne die vermutlichen Fehlläufe bleibt Sitzung 30 bei 49–100 %.

### Was gebaut wurde (`kg/extraction.py`, `kg/pipeline.py`)

Drei getrennte Sicherungen für drei getrennte Fehlerbilder:

1. **Plausibilitätsprüfung des Ende-Index.** Lässt der gemeldete Index von
   einem substanziellen Transkript weniger übrig als `MIN_INTERVIEW_CHARS`
   (400 Zeichen — zwei Zitatlängen, hergeleitet aus dem 200-Zeichen-Deckel von
   Aufgabe 3), wird er **verworfen statt befolgt**. Plausible Werte bleiben
   unangetastet: Sitzung 37 schnitt bei 56–100 %, solche Urteile überstimmt die
   Prüfung ausdrücklich nicht. Das schützt vor dem realen Schaden — 2 % von
   2945 Zeichen sind 59 Zeichen gespeichertes Transkript.
2. **Zweiter Anlauf ohne Ende-Suche.** Nur wenn das Ergebnis **komplett** leer
   ist (kein Begriff, kein Zitat, kein Name) **und** der Text substanziell ist.
   `EXTRACTION_SYSTEM_WITHOUT_END` entsteht aus derselben Vorlage wie
   `EXTRACTION_SYSTEM` und unterscheidet sich in **genau einer** Stelle:
   Aufgabe 1. Alle inhaltlichen Regeln bleiben — auch „Lieber weniger Begriffe
   als schwache Begriffe" und „Rate nicht". Ein Arbeitsgespräch darf also
   weiterhin nichts liefern (§2h, Sitzung 30). Der Rückfall bettelt nicht, er
   nimmt eine Variable heraus. Scheitert er selbst, bleibt es beim ersten
   Ergebnis — nie ein `failed`, wo vorher ein gültiges (leeres) Ergebnis stand.
3. **Nichts geht mehr lautlos durch.** `kg/pipeline.py` protokolliert jede
   Person, die ohne Begriff, Zitat und Namen endet, mit Kennzahlen (keine
   Texte). Der Status bleibt `done` — die Analyse **ist** gelaufen, und ein
   `failed` würde eine Person, die schlicht nichts Verwertbares gesagt hat, als
   Systemfehler ausweisen.

Der normale Prompt ist dabei **zeichengleich mit dem gemessenen** geblieben
(gegen `HEAD` verglichen, identisch) — die Umstellung auf eine gemeinsame
Vorlage hat den Text nicht angefasst.

**Der Rückfall ist zugleich die Messung.** Rettet er die leeren Fälle im
Betrieb, ist die Ein-Aufruf-Kopplung belegt und steht im Log der Ausstellung.
Rettet er sie nicht, war es der Text.

Tests: `pytest -k "extraction or pipeline"` **40 passed** (Baseline 29, 11 neu),
jede der drei Sicherungen einzeln mit Mutationsprobe rot bekommen (2/2/1 Tests).

### 🔴 Was NICHT gelöst ist

* **Warum das Modell bei substanziellem Text nichts liefert**, ist weiter
  offen. Der Verdacht steht: `interview_end_index` ist das **erste** Feld des
  Schemas (nachgesehen: `properties` und `required` beide in dieser
  Reihenfolge), das Modell muss den Zeichen-Index also nennen, **bevor** es
  irgendetwas Inhaltliches geschrieben hat — und alles Weitere entsteht unter
  dieser eigenen, ungeprüften Festlegung. Belegt ist das **nicht**; dafür
  braucht es einen Lauf gegen echte Sitzungen.
* **Die 7 vermuteten Fehlläufe sind nicht aufgeklärt.** Es sind ~23 % harte
  Ausfälle, und niemand weiß bisher woran — der erste Verdacht ist
  `max_tokens` (16000) bei `llm_effort = "high"`. Das druckt das reparierte
  Skript jetzt aus, ein Lauf genügt.
* **Ob Sitzung 5 und 19 Arbeitsgespräche sind**, ist weiter ungeprüft
  (Sichtprüfung an realen Aussagen, §2h).
* **Feldreihenfolge im Schema nicht getauscht.** Das wäre die naheliegende
  Konsequenz aus dem Verdacht oben und ein Einzeiler — aber sie ändert
  **jeden** Aufruf statt nur der scheiternden, ungemessen, am Vorabend. Erst
  messen, dann tauschen.

**➜ Zu fahren auf der Station:** `scripts/pruefe-leere-extraktion.py`
(nur Kennzahlen, kein Transkripttext, keine Begriffe). Beantwortet in einem
Lauf: wie viele Fehler statt leerer Ergebnisse; ob leere Läufe sich beim
Ende-Index häufen; und ob der zweite Anlauf rettet.

---

## 3. 🔴 Was NICHT geprüft ist

Ehrlich getrennt: gemessen ist nur, was hier nicht steht.

| Punkt | Warum offen |
|---|---|
| **Ein kompletter Durchlauf** — Foto → Interview → Verdichtung → Traum → Wand | Nie am Stück gefahren. Das ist der Zweck der nächsten Session. |
| **Traum (Port 8810)** | ✅ **Läuft seit 2026-09-01, 15:05** (HTTP 200), hochgekommen mit dem regulären Start als `[3/6]` — siehe §2f. Die geplante Aufgabe `KgDream` ist weiterhin kaputt (zeigt auf `C:\Users\birk\kg_dream.bat`, letzter Lauf `-2147023829`), wird aber für den regulären Weg **nicht gebraucht**. Aufräumen oder löschen ist Birks Entscheidung. |
| **Die Wand am Beamer** | Legende, QR-Größe und Portraitausschnitt sind an Messbildern beurteilt, nicht im Raum. Ob 132 px QR aus Besucherabstand reichen, weiß nur der Raum. |
| **Gesichtserkennung an echten Booth-Fotos** | **Teilweise erledigt, siehe §2c.** Gemessen an allen 7 Bestandsfotos (Trefferquote, Auflösung, Neigung, zweite Kaskade). **Offen bleibt genau das, wofür neue Fotos nötig sind:** mehrere Personen im Bild (kam im Bestand kein einziges Mal vor), Halbprofil, Sonnenbrille, Gegenlicht. |
| **Der End-to-End-Durchlauf** | **Teilweise.** Foto → Portrait → zurück zur App ist gefahren und belegt (§2f), alle Dienste laufen (8800/8810/5051). **Nicht gefahren:** Interview → Verdichtung → Traum → Wand — das braucht eine sprechende Person vor dem Mikrofon und den Beamer im Raum, ein Agent kann es nicht allein. |
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
- ✅ **Die Station läuft auf dem Fix.** Nach dem Neustart steht sie auf `b5c2c8e`
  (Schritt `[0/6]` hat selbst gezogen), und der Fix ist im laufenden Betrieb belegt:
  Schärfe 3,1 → 229,4 am fertigen Portrait, gute Fotos unverändert (§2f).
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

### 🔴 So läuft der Fototest mit dem Handy (alles vorbereitet)

**Schritt 1 — v8 installieren.** Auf dem Handy liegt v1 (§2d), die verkleinert
nicht und hat weder Sucherrahmen noch Vorschau. **`out/kollektivgedaechtnis-foto-v8.apk`** (v6/v7 überholt, §2g/§2i)
auf dem vServer, signiert und geprüft. **Einfach drüber installieren** — v1 und
v6 tragen dasselbe Zertifikat (SHA-256 `b1f145d4…`, Android-Debug-Key,
mit apksigner gegengeprüft), ein Update ist also möglich, ohne vorher zu
deinstallieren. Die Daten der App bleiben damit auch erhalten.

**Schritt 2 — App einstellen.** Weg „Direkt zur Station", Adresse
`100.94.47.6:8800`. Der Spiegel-Weg ist für Handys ohne Tailnet und liefert
**keine** Vorschau.

**Schritt 3 — fotografieren.** Was fehlt, ist genau das:
- **Mehrere Personen im Bild** — die Kernfrage („gewinnt das größte Gesicht?")
  ist an den Bestandsfotos nicht beantwortbar, in keinem war mehr als ein Gesicht.
- **Halbprofil, geneigter Kopf, Gegenlicht, Brille** — die vermuteten Ausfälle.
- **Jemand weit hinten im Bild** — der Fall, für den die Untergrenze gebaut ist.

Jedes Foto eröffnet ein Interview und schließt das vorige; der Personenzähler
steigt also. Das ist erwartet.

**Schritt 4 — auswerten, sofort und ohne Handarbeit:**

```cmd
cd C:\Users\SF-Tracking\kg-start
C:\Users\birk\kollektivgedaechtnis\.venv\Scripts\python.exe pruefe-neue-fotos.py --seit-minuten 20
```

`scripts/pruefe-neue-fotos.py` nennt je Foto: Anzahl Gesichter, welches gewann,
ob die **Untergrenze** einsprang, die Schärfe des Portraits — und unterscheidet
dabei ein **verwackeltes Foto** von einem schlechten Zuschnitt (sonst sucht man
den Fehler an der falschen Stelle; genau das ist mir am 2026-09-01 passiert).
Meldet es „lange Kante > 1024", läuft noch die alte APK.

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
| Geplante Aufgabe `KgKernTest` | Ausstellungsrechner | **beendet 2026-09-01, 15:00** (`schtasks /end`) — sie hielt den alten Kern und blockierte Port 8800 vor dem Neustart. Die Aufgabe ist noch **registriert** (Status „Bereit"), läuft aber nicht. Entfernen mit `schtasks /delete /tn "KgKernTest" /f` — **Löschen ist Birks Entscheidung**. |
| Geplante Aufgabe `KgVollstart` | Ausstellungsrechner | von mir angelegt, um `kollektivtraum.bat` in Birks Sitzung zu starten (§2f). Tut dasselbe wie die START-Verknüpfung. Kann weg: `schtasks /delete /tn "KgVollstart" /f`. |
| Worktree `kg-app` | `$VOL/projekte/kg-app` | gehört der Foto-Session, steht auf `master` |
| Ordner `kg-start\probe\` | Ausstellungsrechner | Kopie von `kg/photos.py` für die Vorher/Nachher-Messung der Untergrenze (§2e). Die Station selbst wurde dafür **nicht** angefasst. Kann weg: `rmdir /s /q C:\Users\SF-Tracking\kg-start\probe` — **Löschen ist Birks Entscheidung**, deshalb liegen gelassen. |
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
