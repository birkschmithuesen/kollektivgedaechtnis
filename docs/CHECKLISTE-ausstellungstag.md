# Checkliste Ausstellungstag — Stand 2026-09-01, Abend

Kein Handoff, sondern die Liste zum Abhaken. Was hier steht, ist **geprüft
oder ausdrücklich als ungeprüft markiert** — nichts dazwischen.

---

## 🔴 ZUERST: Die Station läuft jetzt auf dem MacBook

Nicht mehr auf dem Windows-Tracking-Laptop. **Damit gibt es keinen Fernzugriff
mehr** — Dateien kommen über `git pull` dorthin, Birk startet neu.

**Starten:**
```bash
cd <repo> && ./scripts/start-mac.sh
```
Öffnet Kern, Traum, Touchfläche (`?touch=1`) und Bedienpult. Beenden mit
Strg-C in demselben Fenster.

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

- [ ] **Startskript läuft durch**, beide Fenster offen, Wand im Vollbild auf
      dem richtigen Schirm
- [ ] **Echte Datenbank aktiv, nicht die Demodaten.**
      `python scripts/dichte-umschalten.py --stufe echt` (Station vorher
      beenden — das Skript prüft es selbst). Aktuell liegt **Stufe 60** auf.
- [ ] **Zehn leere Personen ausblenden** (aus meinen Testfotos, sie erscheinen
      sonst als leere Scheiben an der Wand). Entscheidung steht bei Birk:
      `hidden=1` statt löschen. Details: `docs/STAND.md` §2j.
- [ ] **Erklärungstext für den Plenarsaal einsetzen** —
      `frontend/static/plenum-hinweis.js`, Zeile 32 und 40. Steht bewusst als
      Platzhalter da, Inhalt ist Birks Sache.
- [ ] **Ein echtes Interview durchspielen**: Foto → Portrait → Analyse →
      erscheint an der Wand
- [ ] Größen am Bedienpult einstellen (Zoom, Portrait, Tempo, Begriffe) —
      **getrennt für Foyer und Saal**, die Werte werden gespeichert

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

**In Arbeit, läuft noch:**
- **Portraitgröße:** Mein Fix hat vier Tests gebrochen. Der Regler wirkt jetzt
  nach oben (richtig), aber die Scheiben wachsen nicht mehr mit dem Zoom mit
  (falsch). Ein delegierter Auftrag löst gerade beides gleichzeitig. **Bis
  dahin ist das Zoomverhalten der Portraits nicht wie vorher.**

**Ungeprüft, weil kein Gerätezugriff:**
- Ob die Zwei-Finger-Geste am iiyama unter macOS tatsächlich greift. `/touchtest`
  zeigt es in fünf Sekunden — drei Zeilen leuchten auf, je nach Kanal.
- Ob der Zoomregler sich am 65-Zoll-Schirm gut anfühlt (Griffgröße, Empfindlichkeit)
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
Dort funktioniert die Zwei-Finger-Geste nachweislich nativ. Der Rückweg steht
offen — es ist eine Entscheidung, kein technisches Hindernis.

---

## Wo was steht

- `docs/STAND.md` — alle Messungen mit Zahlen, §2a bis §2o
- `docs/ARBEITSREGELN-ausstellungsrechner.md` — Regeln aus echten Fehlern
- `AGENTS.md` — Projektregeln, inklusive des Rechnerwechsels und der Lehre
  daraus (`?touch=1` fehlte auf Windows über ein Jahr unbemerkt)
- `scripts/start-mac.sh` — die neue Startdatei
- `scripts/dichte-umschalten.py` — zwischen Demodaten und echter DB wechseln
