# Handoff: Fototest mit Zuschnitt-Rückmeldung (Stand 2026-09-01)

**Für:** eine Session, die die Testreihe zur Gesichtserkennung fährt oder an
der Foto-App weiterarbeitet.
**Zuerst lesen:** `AGENTS.md` und
`docs/ARBEITSREGELN-ausstellungsrechner.md` — dort stehen die Regeln zum
Ausstellungsrechner (SF-Tracking, Startdatei nur im Repo, keine Dienste per
SSH). Ohne die verliert man Arbeit.

---

## Worum es geht

Birk will Fotos mit **mehreren Personen im Bild** testen und dabei sehen, ob
die Gesichtserkennung sauber trifft. Dafür gibt es seit heute zwei Hilfen in
der App und ein Messwerkzeug auf der Station.

---

## 1. Der Sucherrahmen (App)

`android/.../SucherRahmen.kt`, eingebunden in `activity_main.xml` als
Overlay über der Kameravorschau.

Gezeigt wird:
- **Goldener Kreis** = so beschneidet die Station am Ende
  (`soft_disc_mask`). Bewusst der Kreis und nicht nur das Quadrat: die Ecken
  fallen weg, und genau dort steht sonst eine Schulter, die man im Bild
  wähnte.
- **Abgedunkelter Bereich außen** = was weggeschnitten wird.
- **Dünner Ring** auf ~38 % der Höhe = wo der Kopf sitzen sollte
  (`GESICHTS_BIAS = 0.46` legt die Gesichtsmitte auf 46 % der
  Ausschnitthöhe).

🔴 **Der Rahmen bildet den RÜCKFALLWEG ab** (mittiger, größtmöglicher
quadratischer Ausschnitt), **nicht den Gesichtsweg**. Grund: wo die Station
ein Gesicht findet, weiß die App nicht — sie erkennt selbst keine Gesichter.
Findet die Station eines, wird der Ausschnitt **enger** und folgt dem Kopf;
der gezeigte Kreis ist dann die sichere Untergrenze (wer darin steht, ist auf
beiden Wegen drin).

Wer den Rahmen ändert, muss `kg/photos.py::_square_crop` gegenlesen. Ein
Rahmen, der etwas anderes verspricht als die Station tut, ist schlimmer als
keiner — man folgt ihm, und das Portrait sitzt trotzdem falsch.

## 2. Die Vorschau des fertigen Portraits (App)

Nach dem Auslösen erscheint unten links das **echte Portrait von der
Station**, 140 dp, antippen blendet es weg.

Kette:
1. `POST /api/photo` antwortet `{"ok": true, "portrait": "<dateiname>.png"}`
   (`kg/server.py`).
2. Die App liest das Feld (`Uploader.Ergebnis.Erfolg.portrait`) und holt das
   Bild über `GET /media/portraits/<dateiname>` — dieser Mount existierte
   schon.
3. `MainActivity.zeigeVorschau()` zeigt es an.

Bewusste Entscheidungen:
- **Das echte Portrait, keine Nachbildung in der App.** Eine app-seitige
  Nachrechnung würde irgendwann von `kg/photos.py` abweichen, und dann prüft
  man am Booth eine Attrappe statt des Ergebnisses.
- **Der Name statt des Bildes in der Antwort.** Ein Portrait ist ~100 kB, und
  am Booth zählt, dass der Auslöser schnell wieder frei ist.
- **Über den Spiegel gibt es keine Vorschau** — dort entsteht das Portrait
  erst beim Abholen, `portrait` bleibt `null`. Das ist kein Fehler.

Tests: `tests/test_server_photo.py` —
`test_die_antwort_nennt_das_portrait_damit_die_app_es_zeigen_kann` und
`test_das_portrait_ist_ueber_media_abrufbar`. Der zweite ist wichtig: ohne
ihn bliebe ein Umbenennen der Mount-Route grün und die Vorschau am Gerät
stumm.

⚠️ **Stolperstein, der schon einmal Zeit gekostet hat:** Die
Testgegenstelle `scripts/testempfang.py` gab anfangs kein `portrait`-Feld
zurück und mountete unter `/portraits` statt `/media/portraits`. Die Vorschau
blieb stumm, und es sah aus, als könne die App es nicht — dabei schwieg nur
die Attrappe. Beides ist gefixt; wer eine weitere Gegenstelle baut, muss
**beide** Hälften nachbilden.

## 3. Das Messwerkzeug (Station)

`scripts/pruefe-gesichtserkennung.py`, liegt auf dem Rechner unter
`C:\Users\SF-Tracking\kg-start\`.

```cmd
cd C:\Users\SF-Tracking\kg-start
C:\Users\birk\kollektivgedaechtnis\.venv\Scripts\python.exe pruefe-gesichtserkennung.py foto.jpg
```

Ohne Argument prüft es nur die Voraussetzungen. Mit Bild meldet es **alle**
gefundenen Gesichter mit Größe und Flächenanteil, welches gewählt wurde
(das größte) und wo der Ausschnitt landet — plus Warnungen, wenn der
Ausschnitt am Anschlag ist (Person zu weit weg) oder an den Bildrand
geschoben wurde (steht sehr seitlich).

Es prüft die **ganze Kette** bis zur geladenen Kaskade, nicht nur „ist cv2
da" — denn genau diese Frage war die irreführende (siehe unten).

---

## Voraussetzungen auf der Station (Stand jetzt erfüllt)

| | Stand |
|---|---|
| `server_host` | `0.0.0.0` ✓ (sonst antwortet der Kern nur sich selbst) |
| `cv2` | 4.14.0 ✓, Kaskade lädt |
| Kern (8800) | läuft, über Tailnet erreichbar (HTTP 200) ✓ |
| Traum (8810) | läuft NICHT — für den Fototest nicht nötig |

🔴 **cv2 fehlte bis heute komplett.** Die Erkennung fiel geräuschlos auf den
mittigen Schnitt zurück (so gebaut, kein Fehler, keine Meldung). Eine
Testreihe hätte den mittigen Schnitt gemessen und daraus über eine Erkennung
geurteilt, die nie lief.

🔴 **`pip install opencv-python-headless` zieht Version 5 — und OpenCV 5 hat
`CascadeClassifier` samt Kaskadendateien entfernt.** Gemessen:
`hasattr(cv2, "CascadeClassifier") == False`. Die Erkennung wäre weiterhin
tot gewesen, nur mit 56 MB Ballast. Richtig ist
`pip install "opencv-python-headless<5"`.

---

## Der Test selbst

**App einstellen:** Weg „Direkt zur Station", Adresse `100.94.47.6:8800`.
(Der Spiegel-Weg ist für Handys ohne Tailnet und liefert **keine** Vorschau.)

**Ablauf je Foto:** auslösen → Statuszeile zeigt Größe („Wird gesendet …
(180 kB)") → „Gesendet — Interview läuft" → Vorschau erscheint.

**Was zu erwarten ist:**
- Bilder sind ~150–250 kB (die App verkleinert auf 1024 px lange Kante).
  Kommen 4 MB an, greift das Verkleinern nicht.
- Jedes Foto eröffnet ein **neues Interview** und schließt das vorige. Der
  Personenzähler steigt also mit jedem Testfoto — das ist erwartet, keine
  Fehlfunktion.

**Auswertung:** die Fotos liegen auf der Station unter
`C:\Users\birk\kollektivgedaechtnis\data\photos\`, die Portraits daneben in
`portraits\`. Jedes Foto durch `pruefe-gesichtserkennung.py` schicken und die
Zahlen sammeln.

---

## Die offene Frage, die diese Testreihe beantworten soll

Der Handoff vom 2026-08-31 (Punkt 1) verlangt ausdrücklich, den Erkenner
**nicht ohne Messung an echten Booth-Fotos** zu wählen: Haar-Kaskade gegen
`face_recognition`/dlib. Diese Messung ist noch nicht gemacht.

**Bekannte Grenze der Haar-Kaskade:** sie findet **frontale** Gesichter.
Halbprofil und stark geneigte Köpfe fallen durch — dann greift der mittige
Schnitt. Wenn das bei den Testfotos gehäuft auftritt, ist das kein
Einstellungsproblem, sondern die Grenze des Verfahrens.

**Zwei ästhetische Entscheidungen liegen bei Birk, nicht beim Agenten:**
- Bei **mehreren Gesichtern** gewinnt aktuell das größte (`kg/photos.py`,
  Annahme: befragte Person steht vorn, Interviewer weiter hinten). Ob das am
  Booth stimmt, zeigt erst die Messung.
- `GESICHTS_ZOOM = 2.0` und `GESICHTS_BIAS = 0.46` sind gesetzte Werte, keine
  gemessenen. Wenn die Serie zeigt, dass Köpfe zu klein oder zu tief sitzen,
  ist das die Stellschraube — aber die Entscheidung trifft Birk am Material.

---

## Was NICHT testgedeckt ist (ehrlich benannt)

- `Bildbytes.verkleinere` — braucht Androids `Bitmap`, auf der JVM nur
  Attrappen. Belegt am Gerät über die Größenangabe in der Statuszeile
  (gemessen: 4,4 MB → 99 kB).
- Der Einfügen-Knopf für das Foto-Token (`ClipboardManager`) — dito.
- `SucherRahmen.onDraw` — reines Zeichnen, nur visuell prüfbar.
