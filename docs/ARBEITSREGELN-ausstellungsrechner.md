# 🔴 Ausstellungsrechner — verbindliche Arbeitsregeln

**Für JEDE Session an diesem Projekt, auch parallele. Vor dem ersten Zugriff
auf den Ausstellungsrechner lesen.** Birk, 2026-09-01: „das ist von keiner
Session mehr in diesem Projekt, damit es nicht verwechselt wird."

Diese Datei steht bewusst im Repo-Root-Bereich `docs/` und ist aus
`README.md`, `docs/BETRIEB-ausstellungsrechner.md` und `AGENTS.md` verlinkt.
Wer die Regeln bricht, verliert Arbeit — die Fälle unten sind alle real
passiert, nicht ausgedacht.

---

## 1. Der Rechner

| | |
|---|---|
| Tailscale | `tracking-laptop` · `100.94.47.6` |
| Zugang | **nur SSH** (RDP ist zu) |
| **Arbeitsbenutzer** | **`SF-Tracking`** |
| Zweitbenutzer | `birk` — hält nur Code und Python, sonst nichts |

```bash
ssh -o BatchMode=yes SF-Tracking@100.94.47.6 "<cmd.exe-Befehl>"
```

---

## 2. 🔴 IMMER als `SF-Tracking`, NIE als `birk`

Beide SSH-Zugänge funktionieren — **das ist die Falle**. Als `birk` läuft
alles scheinbar, aber man arbeitet in einem Profil, in dem der Mensch nie
sitzt. Gemessen 2026-09-01:

| | `SF-Tracking` | `birk` |
|---|---|---|
| Desktop-Verknüpfungen START/STOP | **ja** | nein |
| Claude-Login | **ja** | nein |
| Der Mensch sitzt hier | **ja** | nein |

Wer etwas Sichtbares unter `birk` ablegt, legt es dorthin, **wo es am
Ausstellungstag niemand findet**.

### Wo was hingehört

| Was | Wohin | Warum |
|---|---|---|
| **Code, venvs, Repos** | `C:\Users\birk\...` | Fest verdrahtete absolute Pfade in `pyvenv.cfg` und jeder `Scripts\*.exe`. Python selbst liegt dort (`AppData\Local\Programs\Python\Python312`). Ein Verschieben macht **jeden** Dienst kaputt. |
| **Token, Logs, Verknüpfungen, Startdateien, Testskripte** | `%USERPROFILE%` (= `SF-Tracking`) | Alles, was der Mensch sieht oder pro Benutzer gilt. |

**Kein Rechteproblem:** `SF-Tracking` liest und schreibt in `C:\Users\birk`
einwandfrei (2026-09-01 geprüft: `data` und `kg-spiegel` schreibbar,
Station-Code + cv2 laufen als `sf-tracking`). Der Code muss also **nicht**
umziehen — ein Umzug wäre reiner Schaden.

---

## 3. 🔴 Die Startdatei NUR im Repo ändern

`kollektivtraum.bat` **zieht sich bei jedem Start selbst aus dem Repo nach**
(`:startdatei_nachziehen` kopiert `%KG%\mirror\kollektivtraum.bat` über die
laufende Kopie).

**Quelle der Wahrheit: `mirror/kollektivtraum.bat` im Repo.**

Eine Änderung in `C:\Users\...\kg-start\` wird beim nächsten Start
**lautlos überschrieben**. Am 2026-09-01 lagen deshalb **drei** Fassungen
nebeneinander (unter `birk`, unter `SF-Tracking`, im Repo) — eine hatte den
`git pull`-Schritt, eine den Foto-Abholer, keine beides.

Ablauf: im Repo ändern → committen → auf die Station kopieren
(`mirror/kollektivtraum.bat`) → beim nächsten Start zieht sie sich nach.

---

## 4. 🔴 Dienste NIE direkt über SSH starten

Ein per SSH gestarteter Prozess **stirbt mit der SSH-Sitzung**. Am
2026-09-01 sah das Log nach sauberem Start aus (`Uvicorn running on
0.0.0.0:8800`), und Minuten später lauschte nichts mehr auf dem Port — ohne
Fehlermeldung, was wie ein Absturz aussieht und keiner war.

**Richtig — losgelöst von der Sitzung:**

```bash
ssh SF-Tracking@100.94.47.6 'schtasks /create /tn "KgKernTest" \
  /tr "cmd /c C:\Users\SF-Tracking\kg-start\dienste\dienst-kern.bat" \
  /sc once /st 23:59 /f && schtasks /run /tn "KgKernTest"'
```

**Besser: den Menschen START drücken lassen.** Die Dienste öffnen sichtbare
Fenster auf seinem Bildschirm; ein Fernstart legt ihm Fenster hin, die er
nicht erwartet.

**Verifizieren, nicht annehmen** — „Log sagt gestartet" reicht nicht:

```bash
ssh SF-Tracking@100.94.47.6 'powershell -NoProfile -Command \
  "(Get-NetTCPConnection -LocalPort 8800 -State Listen -EA SilentlyContinue|Measure-Object).Count"'
curl -s -o /dev/null -w "%{http_code}\n" --max-time 12 http://100.94.47.6:8800/api/state
```

---

## 5. Vor „Feature X tut nichts": Stand prüfen

```bash
ssh SF-Tracking@100.94.47.6 "cd C:\Users\birk\kollektivgedaechtnis && git log --oneline -1"
```

Am 2026-09-01 stand die Station **28 Commits hinter `master`**. Ein fertiges
Feature war dort schlicht nicht vorhanden — sah wie ein Programmfehler aus,
war keiner. Seither zieht Schritt `[0/6]` beim Start automatisch.

---

## 6. Optionale Abhängigkeiten sind still

`cv2` fehlte auf der Station komplett — die Gesichtserkennung fiel
**geräuschlos** auf den mittigen Schnitt zurück (so gebaut, kein Fehler).
Eine Testreihe hätte den mittigen Schnitt gemessen und über eine Erkennung
geurteilt, die nie lief.

🔴 **`pip install opencv-python-headless` zieht Version 5 — und OpenCV 5 hat
`CascadeClassifier` entfernt.** Die Erkennung bleibt dann tot, nur mit 56 MB
Ballast. Richtig:

```bash
pip install "opencv-python-headless<5"
```

Prüfen mit `scripts/pruefe-gesichtserkennung.py` — das testet die ganze Kette
bis zur geladenen Kaskade, nicht nur „ist cv2 da".

---

## 7. Windows-Fallstricke (gemessen, nicht vermutet)

- **Batch braucht CRLF.** Ein Python-`write_text()` macht LF daraus, und die
  Datei bricht mitten in langen Zeilen ab (`'utSec' is not recognized`).
  Batch-Dateien **binär** lesen und schreiben (`read_bytes`/`write_bytes`).
- **`scp` prüfen, nicht annehmen.** Ein `scp` schlug still fehl; der
  Probelauf testete danach minutenlang die alte Datei. Nach jedem Kopieren
  die Größe gegenprüfen.
- **Erst gegen eine Kopie testen**, nie direkt an der Startdatei der Station.
  So fiel ein doppeltes `^^(` auf, das im Betrieb ein sichtbares `^` in die
  Ausgabe geschrieben hätte.
- **Anführungszeichen sterben unterwegs.** Verschachtelte Quotes über
  SSH → cmd → Python werden gefressen. Skript per `scp` ablegen und dort
  aufrufen, statt `python -c "..."` durchzureichen.
- Deutsche Windows-Oberfläche: Meldungen sind deutsch, `findstr` entsprechend.

---

## 8. Parallele Sessions

Es arbeitet mehr als eine Session an diesem Projekt. Vor jedem Eingriff:

```bash
cd ~/projekte/kollektivgedaechtnis && git status -sb && git log --oneline -3
```

Der gemeinsame Checkout steht oft auf einem fremden Branch. Eigene Arbeit in
einen **eigenen Worktree** (`git worktree add ~/projekte/kg-<zweck> master`),
nie in den gemeinsamen Checkout. Vor dem Push `git fetch` und prüfen, ob die
andere Session dieselben Dateien angefasst hat.
