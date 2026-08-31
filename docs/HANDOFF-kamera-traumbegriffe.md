# Handoff: Kamera an die Traumbegriffe koppeln (+ theme-f fertigstellen)

**Für eine neue Session mit sauberem Kontext.** Repo `~/projekte/kollektivgedaechtnis`,
Branch `master`, öffentlich (MIT). **Festival: NEW bauhaus, 2./3. September 2026,
Weimarhalle — in zwei Tagen.**

> Stand: 2026-08-31 vormittags. Ersetzt den Kamera-Teil von
> `docs/HANDOFF-2026-08-30.md`; jenes Dokument bleibt gültig für alles, was den
> BILDKANAL betrifft (Prompt, Leitfragen, Messsonden).

---

## 1. Die Hauptaufgabe: Kamera an die Traumbegriffe koppeln

**Die Kamera soll den Bildausschnitt zeigen, aus dem gerade das Bild entsteht.**

Fünf Begriffe werden je Traum mechanisch ausgewählt (`kg2.weighting.select_required`)
und tragen im Graphen die Klassen `.dream-anchor` (rot), `.dream-neighbour` (blau),
`.dream-recent` (gelb). Sie sind an der Wand farbig markiert — **aber die Kamera
weiß nichts davon.** Gemessen liegen typischerweise **zwei der fünf außerhalb des
Bildausschnitts**:

```
Netz-Bounding-Box   x = -2019 … 1763   (3782 breit)
Fenster             1920 px, Zoom 0.874
gelbe Begriffe bei  x = -567 und -616  → außerhalb
```

Das ist **kein Fehler, sondern eine ungenutzte Chance**: In `camera.js` steht
ausdrücklich, dass „Fit-all bei 50 Personen unlesbar" ist — die Kamera zeigt
bewusst einen Ausschnitt und wandert. Nur wandert sie nicht dorthin, wo gerade
etwas passiert.

### Was Birk will
Die Kamera soll den Ausschnitt zeigen, der ins Bild eingeht. Das macht die
Station nachvollziehbar: Was an der Wand hängt, ist sichtbar aus DIESEM Teil
des Netzes entstanden.

### Was zuerst zu klären ist — Design, nicht Code
Diese Fragen sind **nicht entschieden und gehören Birk**. Sie sind der Grund,
warum die Session mit sauberem Kontext beginnt:

1. **Wann bewegt sich die Kamera?** Beim Entstehen eines neuen Traums (alle
   ~4 Min) oder kontinuierlich? Ein Sprung mitten im Betrachten stört, ein zu
   langsames Nachführen zeigt den falschen Ausschnitt.
2. **Wie eng?** Nur die fünf Begriffe, oder mit ihren Personen drumherum (dann
   deutlich größerer Ausschnitt)? Die fünf allein können weit auseinanderliegen
   — der Anker ist der meistgenannte Begriff der zuletzt befragten Person, die
   beiden „recent" sind ganz frische Einzelnennungen.
3. **Was passiert zwischen zwei Träumen?** Kamera steht still auf dem letzten
   Ausschnitt, oder wandert weiter wie bisher?
4. **Wie verhält sich das zum Touchscreen?** Dort greift der Besucher selbst ein
   (`?touch=1`). Eine Kamera, die alle vier Minuten wegspringt, während jemand
   zoomt, wäre unbrauchbar. Vermutlich: Kopplung nur auf Fläche B/C — zu
   entscheiden.

### Vorhandene Bausteine (nichts muss neu gebaut werden)
- `frontend/static/camera.js` — `focus(eles, padding)` zeigt bereits auf eine
  **Teilmenge** und lässt den Modus unangetastet. Das ist der Aufhänger.
- `cy.nodes('.in-dream')` liefert alle fünf Knoten.
- `graph.json` trägt je Begriff `in_dream` (bool) und `dream_role`
  (anchor/neighbour/recent) — berechnet in `kg/export.py`.
- Kamera-Modi stehen in `/api/state` (`camera_mode`, `camera_zoom`), steuerbar
  über das Operator-Fenster von Tool 1.

**Architekturgrenze, die halten muss:** Tool 1 (Graph) darf Tool 2 (Traum)
**nicht** kennen — die Kopplung geht nur in eine Richtung, Tool 2 pollt
`graph.json`. `in_dream` funktioniert nur, weil Tool 1 dieselbe mechanische
Auswahl NACHRECHNET, statt sie zu erfragen.

---

## 2. Der eine offene Fehler in theme-f: überlappende Kästchen

**30 überlappende Paare bei 110 Begriffen.** Zwei Ansätze sind **gemessen
gescheitert** — nicht wiederholen:

1. **Eigenes Ausweichverfahren** (`declutterPlates`): kostete **78 Sekunden**
   Ladezeit (theme-e: 8 s) und änderte **nichts** (`before == after` in jedem
   Lauf). Wieder entfernt.
2. **Eigene Zieldichte** (`PLATE_INK_FRACTION` in `settlePlacement`): Der Zweig
   wird **nie erreicht** — mit einem Zähler nachgewiesen, 0 Durchläufe.

**Ursache des zweiten Fehlschlags ist bekannt und der nächste Schritt:**
`settlePlacement` erkennt das Theme über
`cy.nodes('.term')[0].style('text-valign')`. Zu diesem Zeitpunkt tragen die
Knoten **noch keinen berechneten Stil**. Die Erkennung muss an der CSS-Variablen
`--schwarzplan` hängen, wie es in `createGraphView` bereits funktioniert:

```js
const schwarzplan = cssVar('--schwarzplan', '') === 'an';
```

Das ist **eine Zeile** — bewusst nicht mehr um 23:40 blind eingebaut.

---

## 3. Was an theme-f FERTIG ist (alles am Bild verifiziert)

`?theme=f` („Lichtnetz") ist Birks bevorzugte Richtung. Vorlage war sein echtes
Rendering `konzept-livegraph-touchscreen.png` im Vault, aus dem die Werte
**gemessen** wurden: 77,6 % reines Schwarz, hellste Stellen #BEB497, warme
Mitteltöne #836951, **kein Rot, kein Blau, keine gefüllten Kästchen**.

| | Stand |
|---|---|
| Begriffe als **runde Ringe**, nicht gefüllt | ✓ `corner-radius: 18`, Füllung 0.35 |
| **Gold statt Rot** | ✓ gemessen: Gold 34.232 px, Rot 288 (vorher 44.630) |
| **Glow mit runden Ecken** | ✓ `underlay-corner-radius: 28` |
| **Portrait-Fadeout ins Gold** | ✓ durchgehend, ohne Ring dahinter |
| Portraitringe entfernt | ✓ `--ring-width: 0` |
| Kästchen enger | ✓ `--plate-pad: 8` |
| Ladezeit | ✓ 78 s → 1,7 s |

**Der Portrait-Verlauf** (`kg/photos.py`, `ring_glow` + `soft_disc_mask`) war der
zäheste Punkt und brauchte vier Anläufe. Auf der Wand gemessen:

```
d= 6  (204,154,136)  Gesicht
d=14  (192,172,113)  Übergang
d=16  (195,166, 78)  Gold
d=18  (123,100, 32)  Auslauf
```

Das Gewicht steigt **monoton** von 0 (volles Portrait) auf 255 (volles Gold) und
bleibt dort — keine Glockenkurve, deshalb keine dunkle Lücke und kein separater
Ring. Die Goldzone beginnt bei 45 % des Radius und ist damit breiter als die
Alpha-Zone: Das Gold ist voll erreicht, **solange die Scheibe noch deckt**.

---

## 4. Die Lehren dieser Session — bitte ernst nehmen

**Fünf Fehler an einem Abend, alle derselben Art: etwas gebaut, das plausibel
war, und den Erfolg nicht am Ergebnis geprüft.**

1. Ein Ausweichverfahren, das 78 s kostete und nichts bewirkte.
2. Eine Themenerkennung, deren Zweig nie erreicht wurde.
3. Ein Goldring, der in zwei Fassungen als **Grau** ankam — sichtbar ist
   Farbe × Deckkraft, und die Spitze lag auf Alpha 19.
4. Ein Goldring, der korrekt im PNG stand und trotzdem unsichtbar war, weil ein
   **radialer Verlauf am Knoten** (`#1a1a1a → #000000`) präzise darüber lag.
5. **Ein alter Serverprozess hielt den Port**, alle Neustarts liefen ins Leere.
   Zwei Stunden Arbeit waren nicht ausgeliefert, und „HTTP 200" wurde als
   Erfolg gewertet, statt zu prüfen, WELCHER Prozess antwortet.

> **Nach jeder Änderung am gerenderten Bild messen, nicht am Code.** Ein
> `page.evaluate`-Zähler kostet 30 Sekunden und beantwortet die Frage, die eine
> Stunde Nachdenken offen lässt. Und beim Serverstart: `ps -o lstart=` auf die
> PID, die tatsächlich am Port hängt.

**Cytoscape-Falle:** Die offizielle Doku beschreibt eine **neuere Version als die
vendorierte 3.30.2**. `stripe-*` und `pie-hole` stehen dort und fehlen im Bundle
— eine nicht existierende Stil-Eigenschaft wirft **keinen Fehler**, sie tut
nichts. Immer gegen das Bundle prüfen:
```
grep -c "eigenschaft-name" frontend/static/vendor/cytoscape.min.js
```

---

## 5. Umgebung

**Server starten** (Tool 1, Graph, Replay-Stand mit 60 Interviews). **Zuerst den
Port freimachen** — genau das ging gestern schief:
```
cd ~/projekte/kollektivgedaechtnis
ss -tlnp | grep 8801                    # läuft da noch was?
kill <pid>                              # falls ja
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
ps -o lstart= -p $(ss -tlnp | grep ':8801' | grep -oP 'pid=\K[0-9]+')   # PRÜFEN
```

**Adressen** (vServer über Tailscale, `100.75.24.33`):
| | |
|---|---|
| Projektion theme-f | `:8801/projection?theme=f` |
| dasselbe mit Touch | `:8801/projection?theme=f&touch=1` |
| Vergleich (Punkt+Text) | `:8801/projection?theme=e` |
| Operator Tool 1 | `:8801/operator` |
| Tool 2 (Traum) | `:8810/dream`, `:8810/operator` — braucht `config2.toml` |

**Am Bild messen** — dieses Muster hat alle Fehler gefunden:
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

**Farben im Screenshot zählen:**
```
/usr/bin/python3 -c "
import numpy as np
from PIL import Image
a=np.asarray(Image.open('/tmp/shot.png').convert('RGB'),dtype=int)
for k,v in {'GOLD':(201,162,39),'ROT':(214,40,40),'BLAU':(29,78,156),'GELB':(244,195,0)}.items():
    print(k, int((np.abs(a-np.array(v)).sum(2)<45).sum()))
print('schwarz', f'{100*(a.sum(2)<40).mean():.1f}%')
"
```

**Testsuite:** zwei Blöcke wegen Laufzeit.
```
uv run pytest --collect-only -q | tail -1     # Zahl VORHER bestimmen
uv run pytest --ignore=tests/test_prerender.py --ignore=tests/test_projection.py -q   # ~9 min
uv run pytest tests/test_projection.py tests/test_prerender.py -q                     # ~22 min
```
> Ein Hintergrundlauf verifiziert den Commit, auf dem er **gestartet** ist. Eine
> Parallel-Session arbeitet im selben Arbeitsbaum — pfadgenau committen
> (`git commit -m "…" -- <pfade>`), `-m` muss vor `--` stehen.

---

## 6. Stand des Gesamtprojekts

**🔴 Nur Birk:** OpenRouter-Guthaben **14,92 USD**. Zwei Ausstellungstage ≈ 11.
https://openrouter.ai/credits · Datenschutz-Punkte in der Nextcloud-README
(Einwilligung, Aufbewahrung, Zugriffskreis) · Fragen mit Nina abstimmen.

**Erledigt seit dem Handoff vom 30.8.:**
- Replay auf dem Drei-Fragen-Korpus gelaufen → `sim/data/graph-20a.json`
  (60 Personen, 131 Begriffe, 231 Kanten), ersetzt `graph-19c` als Vertragsfixture
- Vier Bildreihen darauf gerendert: `out/neu-3fragen`, `-lang`, `-spitze`,
  `-mechanisch`
- Mechanische Pflichtauswahl mit zwei Reglern (`REQUIRED_TERMS`, `RECENCY_SHARE`)
  plus dritter Achse (Nachbarschaft) und wanderndem Anker
- Werkstatt-Tab im Dream-Operator: zeigt je Traum, WORAUS das Bild entstand
- Bauhaus-Theme mit Farbcodierung der drei Auswahlachsen

**Weiterhin offen:** Bildsprache endgültig bestätigen (Spec §1, gehört Birk) ·
Satz-Bild-Deckung 31 % (`docs/decisions/satz-bild-deckung.md`) · Zitate ja/nein ·
40-Bilder-Serie (≈5,55 USD, braucht Birks OK) · Reglerstufen vor Ort am Beamer.

**Vollständiger Kontext des Bildkanals:** `docs/HANDOFF-2026-08-30.md`
