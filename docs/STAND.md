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

## 3. 🔴 Was NICHT geprüft ist

Ehrlich getrennt: gemessen ist nur, was hier nicht steht.

| Punkt | Warum offen |
|---|---|
| **Ein kompletter Durchlauf** — Foto → Interview → Verdichtung → Traum → Wand | Nie am Stück gefahren. Das ist der Zweck der nächsten Session. |
| **Traum (Port 8810)** | Läuft laut Handoff der anderen Session nicht. Ursache unbekannt. |
| **Die Wand am Beamer** | Legende, QR-Größe und Portraitausschnitt sind an Messbildern beurteilt, nicht im Raum. Ob 132 px QR aus Besucherabstand reichen, weiß nur der Raum. |
| **Gesichtserkennung an echten Booth-Fotos** | Gemessen an einem einzelnen Foto und an Testmustern. Halbprofil, Sonnenbrille, Gegenlicht: ungeprüft. |
| **Flackern der Wand** | Cron-Job als Ursache **widerlegt** (gemessen). HDR ist der Hauptverdacht (Display-Ereignis 4121), nicht bewiesen. |
| **Doppelter Uploader** | Lief heute Morgen zweimal (PID 5348 + 11508). Nach dem Neustart nicht erneut geprüft. |
| **STT-Textfenster, rechte Spalte** | Bleibt leer, weil nur ein Erkenner läuft (`--channels regie`). Liegt im fremden Repo `meredityman/fundusbot`. |

---

## 4. Entscheidungen, die BIRK trifft

Kein Agent setzt diese Werte allein — sie sind Setzungen, keine Messergebnisse:

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

### 🔴 Der Auftrag: die Testreihe zur Gesichtserkennung fahren

Foto-App, Sucherrahmen, Portrait-Vorschau und Messwerkzeug sind **gebaut und
einsatzbereit — gemessen ist nichts.** Birk hat die Durchführung ausdrücklich
an die übernehmende Session übergeben. Das ist die eigentliche Aufgabe, keine
Restnotiz.

Vollständiger Auftrag: `docs/HANDOFF-foto-app-uebergabe.md`
Ablauf + Messwerkzeug: `docs/HANDOFF-fototest-zuschnitt.md`
(`scripts/pruefe-gesichtserkennung.py` nennt **alle** gefundenen Gesichter und
den gewählten Ausschnitt — nicht nur das Ergebnis.)

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
| Geplante Aufgabe `KgKernTest` | Ausstellungsrechner | `schtasks /delete /tn "KgKernTest" /f` — war eine Testkrücke, kein Dauerzustand. Nicht selbst entfernt: die Station lief gerade, und ein Eingriff in den Aufgabenplaner während des Betriebs ist Birks Entscheidung. |
| Worktree `kg-app` | `$VOL/projekte/kg-app` | wird noch von der Foto-Session benutzt |
| APK `out/kollektivgedaechtnis-foto-v6.apk` | vServer | bewusst nicht im Git (3,6 MB Binär), neu bauen nach `android/README.md` |

**Erledigt am 2026-09-01:**

- **Testempfang auf Port 8805 beendet** (`scripts/testempfang.py`, PID 857211
  und Kinder). Port ist frei, nachgeprüft mit `ss -tlnp`.
- **Doppelter `kg-start` unter `birk`** nach
  `C:\Users\birk\station-sicherung-2026-09-01\kg-start-birk-ungenutzt\`
  verschoben (nicht gelöscht). Vorher geprüft: alle drei Dienst-Skripte darin
  waren bit-identisch mit denen unter `SF-Tracking`, und die Startdatei nutzt
  `%~dp0dienste` — also ihren eigenen Ordner, nie den unter `birk`.
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
