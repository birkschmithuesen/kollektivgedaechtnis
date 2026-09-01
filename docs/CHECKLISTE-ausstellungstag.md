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
- [ ] **🔴 STT-Dienst auf dem Mac starten — sonst kein Interview.** Der
      Erkenner läuft als eigener Prozess auf Port 5051 und liegt **nicht** in
      diesem Repo. Auf dem Windows-Rechner tat das
      `kg-start\dienste\dienst-stt.bat`; **für den Mac gibt es dafür noch
      keine Entsprechung.** Der Befehl, an der Station abgelesen:
      ```
      python -m fundusapps.stt_server --language de infomaniak-whisper \
             --channels regie --api-key-env HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY
      ```
      Braucht den `fundusbot`-Checkout auf dem Mac. `scripts/start-mac.sh`
      startet ihn **nicht** mit — das war eine falsche Annahme meinerseits.
- [ ] **🔴 EU-Kette schließen: der Traum läuft noch über die USA.** In der
      `config.toml` steht keine `image_`-Zeile, also gilt die Vorgabe
      `openrouter` + `google/gemini-3-pro-image` — der `BFL_API_KEY` liegt
      ungenutzt daneben. Vier Zeilen fehlen, sie stehen in
      `docs/env-vorlage-eu.txt`. Alles andere (Analyse, Weckwort, Embeddings,
      Spracherkennung) läuft bereits über Infomaniak.
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

**Erledigt seit dem ersten Entwurf dieser Liste:**
- **Portraitgröße** — behoben (`67d0d71`). Der Regler ist jetzt **Deckel UND
  Maßstab**: er wirkt an beiden Stellen derselben Formel. Gemessen auf der
  Harness (20 Personen, natürliche Scheibe 47,9 px): 120 → 47,9 px, 199 →
  79,5, 260 → 103,8, 700 → 279,6. Mit der alten reinen Deckelung: **sechsmal
  47,9** — der Regler bewegte nichts, und das war Birks ganzer Befund.
  50 Tests grün, Mutationsprobe gefahren (Maßstab entfernt → Test rot).

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
