# Plenarsaal: eigene Ansicht, eigenes Bedienfeld — der gewählte Weg

Stand 2026-09-01. Auftrag: `/tmp/brief-plenum.md` (Birk vor Ort).

## Die Entscheidung: EINE Seite, ein Schalter, eine Auflage

Gebaut ist Weg **(a)**, in der Fassung mit der wenigsten Verdopplung:

| Teil | Wie |
|---|---|
| Adresse | `GET /plenum` → Umleitung auf `/projection?plenum=1` |
| Seite | **dieselbe** `frontend/projection.html` |
| Aussehen | `static/plenum.css` — **kein eigenes Theme**, sondern eine Auflage aus ~15 Variablen ÜBER dem geladenen Theme |
| Verhalten | drei `if (istPlenum)`-Stellen in `projection.html` |
| Einstellungen | eigene Schlüssel `plenum_*` in derselben `setting`-Tabelle, im Zustand unter `state.plenum` |
| Bedienfeld | eigene Seite `/operator-plenum`, tabellengetrieben |

### Warum nicht (b), eine eigene Seite

Eine zweite `plenum.html` müsste die Ladereihenfolge der fünf
Cytoscape-Bundles, den Theme-Ladevertrag (`load`-Ereignis vor
`createGraphView`, siehe die Kommentare in `projection.html`), den
SSE-Anschluss und die Zustandsanwendung wörtlich wiederholen. Genau davor
warnen die Kommentare im Bestand mehrfach („keeping one code path avoids a
second page that drifts from this one", `projection.html` beim Zitat-Overlay).
Jede spätere Korrektur an der Wandlogik müsste an zwei Stellen ankommen — und
die zweite fällt aus, weil sie niemand sieht: die Plenarfläche läuft ohne
Bedienung im Saal.

### Warum kein eigenes `theme-p.css`

Ein vollständiges Theme müsste die ~40 gemessenen Werte aus `theme-f.css`
mitkopieren (Personengröße, Ringbreiten, Kantenfarben, die ganze
Begründungslage). Kopierte Messwerte laufen auseinander: wer morgen
`--edge-color` in `theme-f.css` korrigiert, korrigiert im Saal nichts.

`plenum.css` setzt deshalb **nur die Abweichungen** und erbt alles andere aus
dem geladenen Theme. Es ist kein Theme und steht bewusst nicht in
`KNOWN_THEMES` — `?theme=` wählt weiter das Theme, `?plenum=1` legt die
Saal-Auflage darüber. Beide sind kombinierbar (`?theme=e&plenum=1`).

## Warum die Foyer-Ansicht dabei nicht kippen kann

Drei bauliche Gründe, nicht drei Vorsätze:

1. **Ohne `?plenum=1` wird `plenum.css` nie ins Dokument gehängt.** Kein
   `<link>` im Markup, kein `disabled`-Zustand — das Element entsteht nur im
   Plenum-Zweig. Was nicht geladen ist, kann nichts überschreiben.
2. **Die neuen Variablen in `base.css` tragen die heutigen Werte als
   Vorgabe** (`--qr-size: 132px`, `--qr-opacity: 0.7`,
   `--quote-ring: rgba(255,255,255,0.12)`). Der berechnete Wert im Foyer ist
   derselbe wie vorher, geprüft im Browser statt behauptet.
3. **Der Plenarsaal speichert keine Positionen.** `onPositions` wird im
   Plenum-Zweig gar nicht erst übergeben. Sonst schriebe die Saalfläche ihr
   eigenes Layout (andere Schriftgröße → andere Tafelmaße → anderes fcose-
   Ergebnis) in die gemeinsame `position`-Tabelle zurück, und das Foyer
   stünde nach dem nächsten Neuladen anders da. Das ist der eine Weg, auf dem
   diese Änderung das Foyer trotz getrennter Einstellungen hätte verändern
   können.

`tests/test_foyer_unveraendert.py` hält alle drei fest.

## 🔴 „Der weiße Rand soll weg" — der Befund

Birks Satz („der weiße Rand soll weg, das soll uns auf beiden Deck kommen")
benennt kein Element. Statt zu raten, ist gemessen worden: die Wandseite in
1920×1080 im Browser, jedes Element nach heller Kante befragt und das fertige
Bild nach hellen Pixeln gezählt (`min(R,G,B) > 200`).

**Was auf der Fläche überhaupt weiß ist:**

| Kandidat | Messung | Auf welcher Fläche |
|---|---|---|
| **QR-Code, weiße Fläche samt Ruhezone** | 132×132 px, bei 70 % Deckkraft Helligkeit ~178; die Ruhezone ist ein umlaufender weißer Rahmen von 4/37 der Kante (14 px bei 132, 39 px bei 360) | **beide** |
| Zitatkarte, Fläche | 475×64 px, `#f4f1ea` — die 28 360 hellsten Pixel des Bildes liegen alle hier | nur Foyer (erscheint erst auf Fingertipp) |
| Zitatkarte, helle Kante | `box-shadow … 0 0 0 1px rgba(255,255,255,0.12)`, auf Schwarz Helligkeit ~31 | nur Foyer (dito) |
| Bedienknopf „Übersicht" | `border: 1px solid rgba(255,255,255,0.22)` — **das ist die Zeile, die der Auftrag bei base.css:40 der Zitatkarte zugeschrieben hat**; sie gehört dem Touch-Knopf | nur Foyer (`?touch=1`) |
| `#cy` | **kein Rand** — `border: 0px none`, gemessen, damit ausgeschlossen | — |

**Der wahrscheinlichste ist der QR-Code.** Zwei Gründe: Er ist das einzige
weiße Element, das die Saalfläche heute überhaupt zeichnet (die Zitatkarte
erscheint nur auf Berührung, und im Saal berührt niemand etwas), und er ist
zugleich das einzige, das auf **beiden** Flächen steht — was Birks „auf
beiden" erklärt. Die weiße Ruhezone ist dort buchstäblich ein Rand: ein
umlaufender weißer Rahmen um das schwarze Muster.

**Er ist trotzdem stehen geblieben, und das ist eine bewusste Entscheidung.**
Die Ruhezone IST der Code: vier Module Rand sind Vorschrift, und ohne sie
findet kaum ein Leser einen Code auf einer gemusterten Projektion
(`scripts/qr-erzeugen.py`, `tests/test_qr_handyseite.py`). Sie wegzunehmen
hieße, Punkt 5 auf Kosten von Punkt 2 zu erfüllen — und Punkt 2 („der Code
muss aus dem Saal scanbar sein") ist der konkretere und der mit dem Zweck
dahinter. Kleiner als vier Module geht auch nicht: der Code steht bereits auf
dem Minimum.

**Entfernt ist im Saal die haarfeine helle Kante der Zitatkarte**
(`--quote-ring: transparent`) und, in derselben Bildsprache, bekommt die neue
Erklärungstext-Karte gar keine. Im Foyer bleibt beides, wie es ist.

🔴 **Was ich NICHT klären konnte:** ob Birk überhaupt eines dieser Elemente
meint. Ein vierter Kandidat steht in keinem Stylesheet — ein nicht im
Vollbild laufender Browser zeigt seine eigene helle Leiste, und ein Beamer
setzt bei nicht passendem Seitenverhältnis einen eigenen Rahmen. Beides sähe
aus 15 m nach „weißem Rand" aus und wäre kein CSS-Problem. Das ist mit einem
Blick auf seinen Schirm in zehn Sekunden entschieden und mit keiner Messung
von hier aus.

## Getrennte Einstellungen ohne zweiten Zustandsweg

`current_state()` bekommt **einen** zusätzlichen Schlüssel `plenum` mit den
Saalwerten. Die Foyer-Schlüssel daneben bleiben Zeichen für Zeichen, wo sie
waren — `/api/state` und der SSE-Push sind rein additiv erweitert, jeder
bestehende Leser (Foyer-Wand, `/operator`, Spiegel) sieht unverändert seins.

Geschrieben wird über **einen** Endpunkt `POST /api/plenum {key, value}`
gegen die Tabelle `PLENUM_REGLER` in `kg/server.py`. Ein Regler mehr ist dort
eine Zeile, kein Pydantic-Modell plus Route plus Testblock. Die Schranken
stehen an genau einer Stelle, und das Bedienfeld baut seine Regler aus
derselben Tabelle (`/api/plenum/regler`) — die Oberfläche kann damit keinen
Wert anbieten, den der Server ablehnt.
