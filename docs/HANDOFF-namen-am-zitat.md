# Handoff: Namen der Personen — im Interview fragen, am Zitat zeigen

**Für eine neue Session mit sauberem Kontext.** Repo `~/projekte/kollektivgedaechtnis`,
Branch `master`, öffentlich (MIT). **Festival: NEW bauhaus, 2./3. September 2026,
Weimarhalle.**

> Stand: 2026-08-31 abends. Der Kamera-Teil des vorigen Handoffs ist erledigt
> (`docs/decisions/kamera-traumbegriffe.md`); die überlappenden Kästchen sind
> es auch, und zwar anders als dort vermutet — siehe Abschnitt 3, das ist die
> wichtigste Lehre für die nächste Session.

---

## 1. Die Aufgabe (Birk, 2026-08-31)

Wörtlich: „dass auch im Interview der Name von der Person abgefragt werden soll
und der, wenn man die Person anklickt, auch vor dem Zitat stehen soll."

Zwei Hälften, die getrennt zu bauen sind:

1. **Erhebung:** Das Interview fragt den Namen ab und speichert ihn zur Person.
2. **Anzeige:** Tippt ein Besucher ein Portrait an, steht der Name **vor** dem
   Zitat.

### Was zuerst zu klären ist — Design, nicht Code

Diese Fragen gehören Birk und sind NICHT entschieden. Einzeln stellen, mit
Empfehlung, jeweils auf Antwort warten (kein Fragenstapel):

1. **Wann im Interview wird gefragt?** Vor der ersten Leitfrage („Wie heißt
   du?" als Einstieg) oder am Ende? Der Einstieg ist der natürlichere Ort und
   entspannt die Situation; am Ende weiß der Befragte schon, worauf er sich
   einlässt, und kann bewusster entscheiden.
2. **Was passiert, wenn jemand den Namen NICHT nennen will?** Eine
   Kunstinstallation im öffentlichen Raum braucht diesen Ausweg. Vorname
   genügt? Ein Platzhalter? Gar nichts anzeigen?
3. **Wie erscheint der Name am Zitat?** „Anna: «…»" oder „«…» — Anna" oder der
   Name als eigene Zeile darüber? Das ist eine Bildentscheidung, gehört zu
   Nina/Birk und sollte an einem gerenderten Beispiel entschieden werden, nicht
   im Gespräch.
4. **Steht der Name auch AM PORTRAIT im Graphen** (dauerhaft sichtbar) oder nur
   im Zitat-Overlay beim Antippen? Dauerhaft macht das Netz lesbarer und die
   Wand persönlicher — kostet aber Fläche und wirft die Datenschutzfrage
   schärfer.

### 🔴 Datenschutz — vor dem ersten Commit klären

Namen sind personenbezogene Daten, und das Bestehende ist bewusst anonym: Die
Personenknoten heißen `p1`…`p60`, es gibt kein Namensfeld. Das ändert die
Rechtslage der Station.

- Die Einwilligung muss den Namen ausdrücklich abdecken. Es gibt bereits
  Datenschutz-Punkte in der Nextcloud-README (Einwilligung, Aufbewahrung,
  Zugriffskreis, mit Nina abzustimmen) — die sind zu erweitern, BEVOR die
  Station Namen sammelt.
- Ein Widerruf muss den Namen entfernen können, ohne den Knoten zu zerstören.
- **Diese Entscheidung gehört Birk und Nina, nicht dem Agenten.**

### Vorhandene Bausteine

- **Zitat-Overlay:** `frontend/static/quote-overlay.js`, angehängt in
  `frontend/projection.html` über `attachQuoteOverlay(view)`; gespeist aus
  `quotes` in `graph.json` (`kg/export.py`, `_quotes(store)`).
- **Personenknoten:** `kg/export.py` baut sie aus `store.list_persons()` — dort
  käme ein `name`-Feld dazu, wie `portrait` heute schon eines ist.
- **Interviewführung:** `kg/core.py` (Transkript-Events), Leitfragen-Logik im
  Umfeld von `kg/cycle.py`. **Achtung:** Der Commit `c6347bd` heißt „Die
  Leitfrage ist ersatzlos weg" — die Interviewführung wurde gerade geändert,
  also den aktuellen Stand lesen und nicht dem verlassen, was ältere Dokumente
  beschreiben.
- **Speicherung:** `kg/store.py`, Tabelle `person`. Eine Migration ist nötig;
  bestehende Zeilen brauchen einen Nullwert.

### Architekturgrenze, die auch hier hält

Tool 1 (Graph) darf Tool 2 (Traum) nicht kennen. Falls der Name je im
Bildkanal auftauchen soll: Tool 2 liest `graph.json` und darf nichts
zurückschreiben (`kg2/graph_client.py` hat per Konstruktion kein POST,
`tests/test_dream_contract.py` bewacht das am Quelltext).

---

## 2. Arbeitsweise — nicht verhandelbar

Aus der Erfahrung dieser Session, wörtlich von Birk gefordert:

- **Nach jeder Änderung am GERENDERTEN BILD messen, nie am Code.** Muster
  siehe Abschnitt 4.
- **Beim Serverstart prüfen, ob ein alter Prozess den Port hält** (`ss`, `kill`,
  `ps -o lstart=`). Das hat schon einmal zwei Stunden Arbeit unausgeliefert
  gelassen, und in DIESER Session liefen tatsächlich wieder zwei Server
  gleichzeitig, einer davon vom Vortag.
- **Bilder beurteilt Birk, nicht der Agent.** Zeigen, nur Zählbares messen.
- **Cytoscape-Eigenschaften gegen das vendorierte Bundle prüfen** (3.30.2), nie
  gegen die Doku — die ist neuer:
  `grep -c "eigenschaft" frontend/static/vendor/cytoscape.min.js`
- **Eine Frage pro Nachricht**, mit Empfehlung, dann warten.

### ⚠️ Parallel-Session im selben Arbeitsbaum

Am 2026-08-31 lief eine zweite Session im selben Verzeichnis (PID 31946, ab
15:31). Sie hat mitten in der Arbeit committet, eine abweichende Fassung des
Handoffs geschrieben und den Arbeitsbaum zeitweise auf einen abgelösten HEAD
gezogen. Folgen: ein `git stash` nahm nur die uncommitteten Änderungen zurück,
was zu einer falschen Schlussfolgerung führte, und beim Zusammenführen wären
fast gemessene Werte verloren gegangen.

**Vor Arbeitsbeginn prüfen:** `ps -eo pid,lstart,cmd | grep pytest`. Immer
pfadgenau committen (`git commit -m "…" -- <pfade>`, `-m` vor `--`).

---

## 3. Die überlappenden Kästchen — ERLEDIGT, und die Diagnose war falsch

**Ergebnis: 42 → 4 überlappende Paare bei 110 Begriffen.** Ohne eine Zeile
Code.

Der vorige Handoff nannte hier eine „eine Zeile" als nächsten Schritt:
`settlePlacement` erkenne das Theme über `cy.nodes('.term')[0].style('text-valign')`,
und der Stil sei zu diesem Zeitpunkt noch nicht berechnet, also müsse die
Erkennung an der CSS-Variablen `--schwarzplan` hängen.

**Das stimmt nicht. Gemessen:**

```
text-valign im Aufruf         'center'   → die Erkennung greift
settlePlacement(cy)           42 → 0 Paare
settlePlacement(cy, 0.18)     42 → 0 Paare (erzwungen, gleiches Ergebnis)
```

`settlePlacement` funktionierte die ganze Zeit. Es wurde beim Laden nur **nie
ausgeführt**: Greift `restoring` (Crash-Recovery, Spec 10.5 — jeder Knoten hat
eine persistierte Position), überspringt `render()` die Migration und damit
`settlePlacement`. Die Wand reproduziert exakt die gespeicherte Anordnung.

Belegt durch den Abgleich von gerenderten mit gespeicherten Positionen:

```
Knoten in graph.json                      191
davon mit persistierter Position          170
gerenderte Position weicht ab               0   ← alles kommt aus der DB
```

Die 42 Paare steckten also in den **persistierten Positionen** — eingefroren,
als noch theme-e mit seiner anderen Geometrie galt (Punkt plus Text daneben
statt eines 185×75-Kästchens). Ein Layout, das nie für theme-f gerechnet
wurde.

**Die Lösung war, die Positionen zu verwerfen und neu layouten zu lassen.**
Gegenprobe auf einer DB-Kopie ohne Positionen: **0 Paare bei 110 Begriffen.**
Auf der Arbeits-DB bleiben 4 übrig (die Kamera läuft dort in `pan` und es
werden laufend neue Positionen geschrieben) — auch das ist gemessen und nicht
geglättet.

```bash
# Falls es wiederkommt (z.B. nach einem Theme-Wechsel):
cp out/sim20.db /tmp/backup.db          # immer erst sichern
uv run python -c "
import sqlite3; c=sqlite3.connect('out/sim20.db')
c.execute('delete from position'); c.commit()"
# danach Server neu starten -> das Layout rechnet frisch
```

> **Die Lehre, die über diesen Fall hinausgeht:** Der Handoff hatte eine
> plausible Codestelle im Verdacht, und die Versuchung war groß, dort „die eine
> Zeile" zu ändern. Zehn Minuten Messung zeigten, dass die Funktion korrekt
> ist und schlicht nicht aufgerufen wird. **Eine geerbte Diagnose ist eine
> Hypothese, kein Befund** — auch wenn sie im Handoff wie eine Tatsache steht.

---

## 4. Umgebung

**Server starten** (Tool 1, Graph, Replay mit 60 Interviews). Zuerst den Port
freimachen:

```bash
cd ~/projekte/kollektivgedaechtnis
ss -tlnp | grep 8801                    # läuft da noch was?
kill <pid>
uv run python -c "
import uvicorn
from pathlib import Path
from kg.store import Store
from kg.config import load_config
from kg.bus import EventBus
from kg.server import create_app
cfg=load_config(Path('config.example.toml'))
app=create_app(Store.open(Path('out/sim20.db')), cfg, EventBus())
uvicorn.run(app, host='0.0.0.0', port=8801, log_level='warning')
"
# PRÜFEN, welcher Prozess wirklich antwortet:
ps -o lstart= -p $(ss -tlnp | grep ':8801' | grep -oP 'pid=\K[0-9]+')
```

**Adressen** (vServer über Tailscale, `100.75.24.33`):

| | |
|---|---|
| Projektion theme-f | `:8801/projection?theme=f` |
| dasselbe mit Touch | `:8801/projection?theme=f&touch=1` |
| Vergleich (Punkt+Text) | `:8801/projection?theme=e` |
| Operator Tool 1 | `:8801/operator` |
| Tool 2 (Traum) | `:8810/dream`, `:8810/operator` — braucht `config2.toml` |

**Kamera-Modi** heißen im Operator-Dropdown:
`fit` = „alles zeigen" · `manual` = „manuell" · `pan` = „automatisch schwenken".
Vorgabe ist `pan` (`default_camera_mode` in `kg/config.py`) — greift aber nur
bei einer FRISCHEN Datenbank; ein gespeicherter Operator-Wert gewinnt bei jedem
Neustart (Spec 7, 10.5). Bei Zoom 1,00× läuft die Fahrt ins Leere, für eine
sichtbare Bewegung mindestens ~1,5× (der Replay-Stand steht auf 1,95×).

**Am Bild messen** — dieses Muster hat in dieser Session jeden Fehler gefunden:

```python
# tests/test_zzz_probe.py, danach LÖSCHEN
def test_p(page):
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto("http://127.0.0.1:8801/projection?theme=f")
    page.wait_for_function("window.kgReady === true", timeout=90000)
    page.wait_for_function("() => window.kgView.layoutPending === false", timeout=90000)
    page.wait_for_timeout(6000)
    r = page.evaluate("""() => {
        const cy = window.kgView.cy;
        const bb = n => n.boundingBox({includeLabels:true, includeNodes:true});
        const ov = (a,b) => !(a.x2<b.x1||b.x2<a.x1||a.y2<b.y1||b.y2<a.y1);
        const t = cy.nodes('.term'); const k = t.map(bb);
        let paare=0;
        for (let i=0;i<k.length;i++) for (let j=i+1;j<k.length;j++) if (ov(k[i],k[j])) paare++;
        return { paare, terms: t.length };
    }""")
    print("\nPAARE", r)
    page.screenshot(path="/tmp/shot.png")
```

**Testsuite:** zwei Blöcke wegen Laufzeit.

```bash
uv run pytest --collect-only -q | tail -1     # Zahl VORHER bestimmen (993)
uv run pytest --ignore=tests/test_prerender.py --ignore=tests/test_projection.py -q   # ~15 min
uv run pytest tests/test_projection.py tests/test_prerender.py -q                     # ~21 min
```

> Ein Hintergrundlauf verifiziert den Commit, auf dem er **gestartet** ist.

**Wenn der Prerender/Determinismus rot wird:** Die Kamera-Traumkopplung ist für
Aufnahmen abgeschaltet (`_open_projection` ruft `setDreamCamera(false)`, direkt
nach `page.goto` — der Zeitpunkt ist entscheidend, Begründung in
`docs/decisions/kamera-traumbegriffe.md`).

---

## 5. Stand des Gesamtprojekts

**🔴 Nur Birk:** OpenRouter-Guthaben **14,92 USD**, zwei Ausstellungstage ≈ 11.
https://openrouter.ai/credits · Datenschutz-Punkte in der Nextcloud-README mit
Nina abstimmen (und um die Namensfrage aus Abschnitt 1 erweitern).

**Erledigt am 2026-08-31:**
- Kamera an die Traumbegriffe gekoppelt: 5/5 Traumbegriffe und 18/18 Personen
  im Bild statt vorher 3/5 (`docs/decisions/kamera-traumbegriffe.md`)
- Überlappende Kästchen: 42 → 4 (Abschnitt 3)

**Weiterhin offen:** Bildsprache endgültig bestätigen (Spec §1, gehört Birk) ·
Satz-Bild-Deckung 31 % (`docs/decisions/satz-bild-deckung.md`) · Zitate ja/nein ·
40-Bilder-Serie (≈5,55 USD, braucht Birks OK) · Reglerstufen vor Ort am Beamer.

**Vollständiger Kontext des Bildkanals:** `docs/HANDOFF-2026-08-30.md`
**Kamera-Entscheidungen:** `docs/decisions/kamera-traumbegriffe.md`, `d4-camera.md`
