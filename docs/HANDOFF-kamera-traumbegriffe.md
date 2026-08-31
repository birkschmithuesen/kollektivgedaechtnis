# Handoff: Kamera an die Traumbegriffe koppeln (+ theme-f fertigstellen)

**Für eine neue Session mit sauberem Kontext.** Repo `~/projekte/kollektivgedaechtnis`,
Branch `master`, öffentlich (MIT). **Festival: NEW bauhaus, 2./3. September 2026,
Weimarhalle — in zwei Tagen.**

---

## 1. Die Aufgabe — ERLEDIGT 2026-08-31

**Die vier Design-Fragen sind entschieden, gebaut und am gerenderten Bild
verifiziert.** Entscheidungen, Messungen und die Ursachenanalyse des Fehlers,
der die Kopplung zunächst wirkungslos machte, stehen in
`docs/decisions/kamera-traumbegriffe.md`. Kurzfassung der Antworten:

1. **Zwei Auslöser, nicht drei** — Portrait zu Interviewbeginn und neue
   Begriffe, beide sieht Tool 1 selbst. Der dritte („Bild fertig") entfällt:
   kg2 wählt seine fünf Begriffe zu Beginn des Zyklus und behält sie bis zum
   fertigen Bild, der Schwenk führe also dorthin, wo die Kamera längst steht
   — und wäre nur über einen Rückkanal erreichbar, den `kg2/graph_client.py`
   per Konstruktion nicht hat (`tests/test_dream_contract.py` bewacht das).
2. **Ausschnitt = die fünf PLUS ihre Personen.** Gemessen: die fünf allein
   ergäben Zoom 1.45 (1,6× enger als die kalibrierte Wand, zu wenig Fläche
   für die langen Labels), mit ihren 18 Personen 1.07.
3. **Zwischen zwei Träumen** wandert die Kamera weiter, aber im Traumgebiet,
   und der Ausschnitt weitet sich über vier Minuten von 1.0 auf 2.1 — „erst
   den Traum eins zu eins, dann immer mehr Kontext" (Birk).
4. **Touchscreen: kein Sonderfall**, die Vermutung unten hat sich nicht
   bestätigt. Im manuellen Modus wirkt nichts, das Gebiet wird trotzdem
   gemerkt, und beim Rückfall in die Automatik fährt die Wand zuerst dorthin
   — das deckt den Fall vollständig ab, ohne Fläche A auszunehmen.

```
vorher   3/5 Traumbegriffe im Bild, Zoom 0.886
nachher  5/5 Begriffe und 18/18 Personen, Zoom 1.068
```

> **Für den Betrieb wichtig:** Rundgang und Aufweitung leben im `pan`-Modus.
> `step()` steigt in `fit` aus, dort fährt die Kamera einmal auf das
> Traumgebiet und bleibt stehen. Vorgabe der Station ist `fit` (D4) — wer die
> wandernde Kamera und den wachsenden Radius auf der Wand sehen will, stellt
> den Operator auf `pan`.

### Die Lehre — Abschnitt 4 hat sich exakt wiederholt

Die erste Fassung war vollständig und plausibel: `focusDream()` lief,
`dreamState` meldete 23 Knoten, ein erzwungener Handover fuhr sauber von
0.886 auf 1.032. Der Zoom stand trotzdem über 40 Sekunden unverändert.

Ursache war eine Stelle, die niemand im Verdacht hatte: `setMode()`
unterschied nicht zwischen einem Moduswechsel und dem Neusetzen desselben
Modus — und `/events` schickt nach jedem `graph` auch ein `state`. Jeder
Graph-Push tötete den Handover, den derselbe Push eine Zeile vorher gestartet
hatte. **Im Code sah alles richtig aus.** Gefunden wurde es, indem `setMode`,
`_startHandover` und `_frame` mit einer Spur belegt wurden — nicht durch
Nachdenken.

<details>
<summary>Ursprüngliche Aufgabenbeschreibung (historisch, zur Einordnung)</summary>

**Die Kamera soll den Bildausschnitt zeigen, aus dem gerade das Bild entsteht.**

Fünf Begriffe werden je Traum mechanisch ausgewählt (`kg2.weighting.select_required`)
und tragen im Graphen die Klassen `.dream-anchor` (rot), `.dream-neighbour` (blau),
`.dream-recent` (gelb). Sie sind an der Wand farbig markiert — **aber die Kamera
weiß nichts davon.** Sie fährt ihre eigene Bahn, und gemessen liegen typischerweise
**zwei der fünf außerhalb des Bildausschnitts**:

```
Netz-Bounding-Box   x = -2019 … 1763   (3782 breit)
Fenster             1920 px, Zoom 0.874
gelbe Begriffe bei  x = -567 und -616  → außerhalb
```

Das ist **kein Fehler, sondern eine ungenutzte Chance**: In `camera.js` steht
ausdrücklich, dass „Fit-all bei 50 Personen unlesbar" ist — die Kamera zeigt
bewusst einen Ausschnitt und wandert. Nur wandert sie eben nicht dorthin, wo
gerade etwas passiert.

### Was Birk will
Die Kamera soll den Ausschnitt zeigen, der ins Bild eingeht. Das macht die
Station nachvollziehbar: Was an der Wand hängt, ist sichtbar aus DIESEM Teil
des Netzes entstanden.

### Was zuerst zu klären ist (Design, nicht Code)
Das ist der Grund, warum diese Session mit sauberem Kontext beginnen soll —
die folgenden Fragen sind **nicht** entschieden und gehören Birk:

1. **Wann bewegt sich die Kamera?** Beim Entstehen eines neuen Traums (alle
   ~4 Min) oder kontinuierlich? Ein Sprung mitten im Betrachten ist störend,
   ein zu langsames Nachführen zeigt den falschen Ausschnitt.
2. **Wie eng?** Nur die fünf Begriffe im Bild, oder mit ihren Personen drumherum
   (dann ist es ein deutlich größerer Ausschnitt)? Die fünf allein können weit
   auseinanderliegen — der Anker ist der meistgenannte Begriff der zuletzt
   befragten Person, die beiden „recent" sind ganz frische Einzelnennungen.
3. **Was passiert zwischen zwei Träumen?** Steht die Kamera still auf dem
   letzten Ausschnitt, oder wandert sie weiter wie bisher?
4. **Wie verhält sich das zum Touchscreen?** Dort greift der Besucher selbst
   ein (`?touch=1`). Eine Kamera, die alle vier Minuten wegspringt, während
   jemand zoomt, wäre unbrauchbar. Vermutlich: Kopplung nur auf Fläche B/C,
   nicht auf dem Touchscreen — aber das ist zu entscheiden.

</details>

### Vorhandene Bausteine (nichts davon muss neu gebaut werden)
- `frontend/static/camera.js` — `focus(eles, padding)` zeigt bereits auf eine
  **Teilmenge** von Elementen und lässt den Modus unangetastet. Das ist genau
  der Aufhänger. *Verwendet wurde am Ende der Handover-Mechanismus daneben:
  er fährt statt zu springen.*
- Die Klassen `.dream-anchor` / `.dream-neighbour` / `.dream-recent` liegen an
  den Knoten an; `cy.nodes('.in-dream')` liefert alle fünf.
- `graph.json` trägt `in_dream` (bool) und `dream_role` (anchor/neighbour/recent)
  je Begriff — berechnet in `kg/export.py`.
- Die Kamera-Modi stehen in `/api/state` (`camera_mode`, `camera_zoom`) und sind
  über das Operator-Fenster von Tool 1 steuerbar.

**Wichtige Architekturgrenze:** Tool 1 (Graph) darf Tool 2 (Traum) **nicht**
kennen — die Kopplung geht nur in eine Richtung, Tool 2 pollt `graph.json`.
`in_dream` funktioniert nur deshalb, weil Tool 1 dieselbe mechanische Auswahl
NACHRECHNET, statt sie zu erfragen. Eine Kamera-Kopplung muss diese Grenze
ebenfalls respektieren. **Sie hat gehalten — und war der Grund, den dritten
Auslöser zu streichen.**

---

## 2. Was am selben Abend noch offen blieb (theme-f)

`?theme=f` („Schwarzplan/Lichtnetz") ist Birks bevorzugte Richtung, aber nicht
fertig. Fertig ist:

- Begriffe als **runde Ringe** statt Punkt+Text, nicht ausgefüllt (Grund
  scheint durch)
- **Gold statt Rot** — gemessen an Birks Rendering
  `konzept-livegraph-touchscreen.png` im Vault: 77,6 % reines Schwarz, hellste
  Stellen #BEB497, warme Mitteltöne #836951, **kein Rot, kein Blau**
- **Glow** mit runden Ecken (`underlay-corner-radius: 28`)
- **Portrait-Feather**: harte Ellipsenmaske → Alpha-Verlauf; der goldene Ring
  IST der Übergang, kein Reifen außen herum (`kg/photos.py`, `ring_glow()`)

### 🔴 Der eine offene Fehler: die Kästchen überlappen sich
**30 überlappende Paare bei 110 Begriffen.** Zwei Ansätze sind **gemessen
gescheitert** — nicht wiederholen:

1. **Eigenes Ausweichverfahren** (`declutterPlates`): kostete **78 Sekunden**
   Ladezeit (theme-e: 8 s) und änderte **nichts** (`before == after` in jedem
   Lauf). Wieder entfernt.
2. **Eigene Zieldichte** (`PLATE_INK_FRACTION` in `settlePlacement`): Der
   Zweig wird **nie erreicht** — mit einem Zähler nachgewiesen, 0 Durchläufe.

**Die Ursache des zweiten Fehlschlags ist bekannt und der nächste Schritt:**
`settlePlacement` erkennt das Theme über `cy.nodes('.term')[0].style('text-valign')`.
Zu diesem Zeitpunkt tragen die Knoten **noch keinen berechneten Stil**. Die
Erkennung muss stattdessen an der CSS-Variablen `--schwarzplan` hängen — so wie
es in `createGraphView` bereits funktioniert:

```js
const schwarzplan = cssVar('--schwarzplan', '') === 'an';
```

Das ist **eine Zeile**. Sie wurde bewusst nicht mehr um 23:40 eingebaut, weil am
selben Abend zweimal etwas eingebaut wurde, das plausibel klang und nachweislich
nichts tat.

**Prüfvorschrift danach** (nicht am Prompt raten, am Bild messen):
```
uv run pytest tests/test_projection_schwarzplan.py -q     # 6 Tests
# und die Überlappungen zählen, Muster siehe unten
```

---

## 3. Die Lehre dieser Session — bitte ernst nehmen

Drei Fehler an einem Abend, alle derselben Art: **etwas gebaut, das plausibel
war, und den Erfolg nicht am Ergebnis geprüft.**

- Ein Ausweichverfahren, das 78 s kostete und nichts bewirkte.
- Eine Themenerkennung, deren Zweig nie erreicht wurde.
- Ein goldener Ring, der in zwei Fassungen als **Grau** ankam, weil sichtbar
  = Farbe × Deckkraft ist und die Spitze des Farbverlaufs auf Alpha 19 lag.

Jedes Mal hat erst eine **Messung am gerenderten Ergebnis** es aufgedeckt, nie
das Lesen des Codes. Für diese Session heißt das:

> **Nach jeder Stiländerung am Bild messen, nicht am Prompt.** Ein Zähler im
> Browser (`page.evaluate`) kostet 30 Sekunden und beantwortet die Frage,
> die eine Stunde Nachdenken offen lässt.

Und eine spezifische Falle: **Die offizielle Cytoscape-Doku beschreibt eine
neuere Version als die vendorierte 3.30.2.** `stripe-*` und `pie-hole` stehen
dort und fehlen im Bundle — eine nicht existierende Stil-Eigenschaft wirft
**keinen Fehler**, sie tut nichts. Immer gegen das Bundle prüfen:
```
grep -c "eigenschaft-name" frontend/static/vendor/cytoscape.min.js
```

---

## 4. Umgebung

**Server starten** (Tool 1, Graph, mit dem Replay-Stand von 60 Interviews):
```
cd ~/projekte/kollektivgedaechtnis
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
```

**Adressen** (vServer über Tailscale, `100.75.24.33`):
| | |
|---|---|
| Projektion theme-f | `:8801/projection?theme=f` |
| dasselbe mit Touch | `:8801/projection?theme=f&touch=1` |
| Vergleich (Punkt+Text) | `:8801/projection?theme=e` |
| Operator Tool 1 | `:8801/operator` |
| Tool 2 (Traum) | `:8810/dream`, `:8810/operator` — braucht `config2.toml` |

**Am Bild messen** — dieses Muster hat den ganzen Abend die Fehler gefunden:
```python
# tests/test_zzz_probe.py, danach löschen
def test_p(page, static_server):
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto("http://127.0.0.1:8801/projection?theme=f")
    page.wait_for_function("window.kgReady === true", timeout=90000)
    page.wait_for_timeout(6000)
    r = page.evaluate("""() => {
        const cy = window.kgView.cy;
        const t = cy.nodes('.term');
        const bb = n => n.boundingBox({includeLabels:true, includeNodes:true});
        const ov = (a,b) => !(a.x2<b.x1||b.x2<a.x1||a.y2<b.y1||b.y2<a.y1);
        const k = t.map(bb); let paare=0;
        for (let i=0;i<k.length;i++) for (let j=i+1;j<k.length;j++) if (ov(k[i],k[j])) paare++;
        return { paare, terms: t.length };
    }""")
    print("\nPAARE", r)
    page.screenshot(path="/tmp/shot.png")
```
```
uv run pytest tests/test_zzz_probe.py -q -s
```

**Farben im Screenshot zählen** (belegt, ob eine Farbe wirklich ankommt):
```
/usr/bin/python3 -c "
import numpy as np
from PIL import Image
a=np.asarray(Image.open('/tmp/shot.png').convert('RGB'),dtype=int)
for k,v in {'GOLD':(201,162,39),'ROT':(214,40,40),'BLAU':(29,78,156),'GELB':(244,195,0)}.items():
    print(k, int((np.abs(a-np.array(v)).sum(2)<45).sum()))
"
```

**Testsuite:** zwei Blöcke, wegen Laufzeit.
```
uv run pytest --collect-only -q | tail -1     # Zahl VORHER bestimmen
uv run pytest --ignore=tests/test_prerender.py --ignore=tests/test_projection.py -q   # ~9 min
uv run pytest tests/test_projection.py tests/test_prerender.py -q                     # ~22 min
```
> Ein Hintergrundlauf verifiziert den Commit, auf dem er **gestartet** ist. Eine
> Parallel-Session arbeitet im selben Arbeitsbaum — deshalb pfadgenau committen
> (`git commit -m "…" -- <pfade>`), und `-m` muss vor `--` stehen.

---

## 5. Stand und offene Punkte des Projekts

**🔴 Nur Birk kann das:** OpenRouter-Guthaben stand zuletzt bei **~15 USD**.
Zwei Ausstellungstage kosten ≈ 11. https://openrouter.ai/credits

**Entschieden am 2026-08-30:** mood + tension bleiben · Bildmodell
`google/gemini-3-pro-image` · drei Leitfragen statt fünf · Bildbegriffe stehen
immer an der Wand, auch über dem Dichteregler · Beurteilung von Bildern macht
Birk, kein Modell.

**Weiterhin offen:** Bildsprache endgültig bestätigen (Spec §1) ·
Satz-Bild-Deckung (31 % gemessen, `docs/decisions/satz-bild-deckung.md`) ·
Zitate ja/nein · 40-Bilder-Serie (≈5,55 USD, braucht Birks OK) ·
Datenschutz-Punkte in der Nextcloud-README.

**Vollständiger Kontext des Vortags:** `docs/HANDOFF-2026-08-30.md`
