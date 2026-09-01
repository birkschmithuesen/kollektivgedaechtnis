# Handoff: Foto-App — Übergabe an die nächste Session (2026-09-01)

> 🔴 **OFFENER AUFTRAG: die Testreihe zur Gesichtserkennung fahren.**
> Gebaut ist alles, **gemessen ist nichts**. Birk erwartet, dass die
> übernehmende Session das durchführt — siehe Abschnitt „AUFTRAG" weiter
> unten. Nicht als Restnotiz behandeln, das ist die eigentliche Aufgabe.

Diese Sitzung ist abgeschlossen. Alles committet und auf `master` gepusht
(23 Commits, `7dd94a6` … `cb802de`).

**Zuerst lesen:** `AGENTS.md`, dann
`docs/ARBEITSREGELN-ausstellungsrechner.md`. Jede Regel dort ist ein Fehler,
der heute wirklich passiert ist.

---

## Was gebaut wurde

| Was | Wo |
|---|---|
| Android-Foto-App | `android/` · `android/README.md` |
| `POST /api/photo` (direkter Weg) | `kg/server.py` |
| Foto-Einwurf über den Spiegel | `mirror/receiver.py` (`/ingest/photo`, `/eingang`) |
| Abholer auf der Station | `mirror/abholer.py` · `mirror/abholer-start.bat` |
| Sucherrahmen + Portrait-Vorschau | `docs/HANDOFF-fototest-zuschnitt.md` |
| Messwerkzeug Gesichtserkennung | `scripts/pruefe-gesichtserkennung.py` |
| Testgegenstelle (ohne LLM/Kosten) | `scripts/testempfang.py` |

Fertige APKs: `out/kollektivgedaechtnis-foto-v6.apk` (nicht im Git — 3,6 MB
Binaries gehören nicht ins Repo; neu bauen nach `android/README.md`).

---

## 🔴 Was diese Session hinterlassen hat und aufgeräumt gehört

1. **Worktree `~/projekte/kg-app`** (= `$VOL/projekte/kg-app`, auf `master`).
   Wer ihn nicht braucht:
   ```bash
   cd ~/projekte/kollektivgedaechtnis
   git worktree remove /mnt/HC_Volume_106183673/projekte/kg-app
   ```
   Der gemeinsame Checkout `~/projekte/kollektivgedaechtnis` stand die ganze
   Zeit auf `mikrofonschalter/interview-signal` und wurde **nicht** angefasst.

2. **Geplante Aufgabe `KgKernTest`** auf dem Ausstellungsrechner. Damit habe
   ich den Kern für den Test gestartet (ein SSH-Start stirbt mit der
   Sitzung). Sie ist kein Dauerzustand:
   ```cmd
   schtasks /delete /tn "KgKernTest" /f
   ```
   Der reguläre Weg ist Birks START-Verknüpfung.

3. **Testempfang auf dem vServer**, Port 8805 (`scripts/testempfang.py`).
   Läuft noch, hält Port und etwas Speicher. Einfach beenden.

4. **`kg-start` existiert doppelt** auf dem Rechner — unter `birk` und unter
   `SF-Tracking`. Beide sind jetzt identisch, aber die Dopplung ist die
   Fehlerquelle von gestern. **Löschen ist Birks Entscheidung**, deshalb
   liegen gelassen. Vorschlag: `C:\Users\birk\kg-start\` entfernen, die
   Desktop-Verknüpfung zeigt auf die `SF-Tracking`-Fassung.

5. **Sicherungen auf dem Rechner** (können weg, wenn alles läuft):
   `kollektivtraum.bat.bak-vor-abholer`, `...bak-vor-vereinigung` (in beiden
   `kg-start`), `receiver.py.bak-<zeitstempel>` in `~/kg-mirror/mirror/` auf
   herkules.

---

## Zustand der Station jetzt

| | |
|---|---|
| Kern (8800) | läuft, über Tailnet erreichbar, `server_host = 0.0.0.0` |
| Traum (8810) | **läuft nicht** — für den Fototest nicht nötig |
| STT (5051) | läuft |
| `cv2` | 4.14.0, Kaskade lädt, Erkennung aktiv |
| Spiegel (herkules) | läuft, `KG_FOTO_TOKEN` gesetzt |
| Abholer | in der Startdatei als `[5/6]`, läuft **nicht** dauerhaft |

**Der Abholer ist noch nie im Dauerbetrieb gelaufen** — nur zweimal von Hand
angestoßen, beide Male erfolgreich (einmal vom vServer, einmal vom
Ausstellungsrechner aus). Beim ersten echten START zeigt sein Fenster
„Foto zugestellt", wenn etwas über den Spiegel kommt.

---

## 🔴 AUFTRAG AN DIE ÜBERNEHMENDE SESSION: die Testreihe fahren

**Das ist die eigentliche Aufgabe, nicht eine Restnotiz.** Birk,
2026-09-01: *„Der Test steht noch aus und soll dann von der neuen Session
durchgeführt werden."*

Gebaut und bereitgestellt ist alles; **gemessen ist nichts.** Die Station
läuft, die Werkzeuge liegen, die App zeigt Rahmen und Vorschau — aber es
existiert keine einzige Auswertung.

### Was zu tun ist

1. **Voraussetzungen prüfen** (nicht annehmen — sie waren heute alle
   mindestens einmal falsch):
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" --max-time 12 http://100.94.47.6:8800/api/state   # 200?
   ssh SF-Tracking@100.94.47.6 "cd C:\Users\SF-Tracking\kg-start && C:\Users\birk\kollektivgedaechtnis\.venv\Scripts\python.exe pruefe-gesichtserkennung.py"
   ```
2. **Birk fotografieren lassen.** App auf „Direkt zur Station",
   `100.94.47.6:8800`. Er macht die Fotos — insbesondere **mit mehreren
   Personen im Bild**, das ist der Kern der Frage. Die Vorschau in der App
   zeigt ihm sofort den Zuschnitt.
3. **Jedes Foto durch das Messwerkzeug schicken:**
   ```cmd
   pruefe-gesichtserkennung.py <foto.jpg>
   ```
   Fotos liegen auf der Station unter
   `C:\Users\birk\kollektivgedaechtnis\data\photos\`.
4. **Zahlen sammeln, nicht Eindrücke.** Je Foto: Anzahl gefundener
   Gesichter, welches gewählt wurde, Größe/Flächenanteil, ob der Ausschnitt
   am Anschlag oder am Bildrand klemmte. Aggregieren **im Code**, nicht im
   Kopf.
5. **Ergebnis Birk vorlegen** — mit Empfehlung, aber die Entscheidung ist
   seine (siehe unten).

### Was die Messung beantworten soll

- **Trifft die Haar-Kaskade zuverlässig genug?** Bekannte Grenze: sie findet
  nur **frontale** Gesichter. Halbprofil und geneigte Köpfe fallen durch →
  mittiger Schnitt. Häuft sich das, ist es eine Verfahrensgrenze, kein
  Einstellungsproblem, und der Erkennerwechsel steht an
  (`face_recognition`/dlib, verlangt vom Handoff 2026-08-31 Punkt 1 —
  ausdrücklich **nicht ohne Messung an echten Booth-Fotos** entscheiden).
- **Stimmt „das größte Gesicht gewinnt"?** Aktuelle Annahme in
  `kg/photos.py`: befragte Person steht vorn, Interviewer weiter hinten.
  Ungemessen.
- **Sitzen `GESICHTS_ZOOM = 2.0` und `GESICHTS_BIAS = 0.46` richtig?**
  Gesetzte, nicht gemessene Werte.

🔴 **Die letzten beiden sind ästhetische Entscheidungen — die trifft Birk am
Material, nicht der Agent.** Messen, vorlegen, ihn entscheiden lassen.

Ablauf im Detail: `docs/HANDOFF-fototest-zuschnitt.md`.

---

## Weitere offene Punkte

- **Erkennerwahl per Messung** (Haar-Kaskade vs. `face_recognition`/dlib) —
  Ergebnis der Testreihe oben.
- **Kosmetischer Fehler beim Selbstnachziehen der Startdatei:** cmd meldet
  zweimal `'die' is not recognized`. Aus dem Bestand, nicht von dieser
  Session (geprüft), blockiert nichts. Bewusst nicht kurz vor dem
  Ausstellungstag angefasst.
- **Code-Umzug von `C:\Users\birk` nach `SF-Tracking`** — von Birk gewünscht,
  von mir **abgeraten und aufgeschoben**: venvs und die Python-Installation
  haben absolute Pfade eingebacken, ein Umzug macht jeden Dienst kaputt und
  braucht einen Neuaufbau aller Umgebungen. Kein Rechteproblem (gemessen).
  Nach der Ausstellung, nicht davor.
- **Abholer im Dauerbetrieb** ist ungetestet (nur `einmal()` erprobt).

---

## Was NICHT testgedeckt ist (damit es niemand für geprüft hält)

- `Bildbytes.verkleinere`, der Clipboard-Einfügen-Knopf, `SucherRahmen.onDraw`
  — alle drei brauchen Android; auf der JVM gäbe es nur Attrappen.
  Belegt wurden sie am Gerät (4,4 MB → 99 kB in der Statuszeile).
- Der **Abholer im Dauerbetrieb** (`laufe()`); getestet ist `einmal()`.

## Was belegt ist

- Gesamtsuite 1074 passed / 4 skipped; 23 Kotlin-Tests.
- **Zehn Mutationsproben**, jede tötet ihren Test. Darunter die tragende:
  „Foto-Token darf auch, was das starke darf" → rot.
- End-to-End über echte Server: Einwurf per HTTPS → Abholer → Station →
  Portrait; Foto-Token gegen `/ingest/graph` und `/eingang` je **401**.
- APK: `apksigner verify` → *Verifies*, Berechtigungen nur
  CAMERA/INTERNET/ACCESS_NETWORK_STATE.
