# Decision — Kamera an die Traumbegriffe koppeln (Birk, 2026-08-31)

Bindend. Schließt Abschnitt 1 des `docs/archiv/HANDOFF-kamera-traumbegriffe.md` ab —
dort standen vier Fragen als „nicht entschieden und gehören Birk". Hier stehen
die Antworten und die Messungen, gegen die sie entschieden wurden.

Umgesetzt in `frontend/static/camera.js` (`focusDream`, `_dreamNodes`,
`_dreamSpread`, `_levelForBox`) und `frontend/static/projection.js`
(`dreamNodes`, `aimCameraAtDream`).

## Die Ausgangslage, gemessen

Fünf Begriffe tragen je Traum `.dream-anchor` / `.dream-neighbour` /
`.dream-recent`, aber die Kamera wusste nichts davon:

```
Netz-Bounding-Box   x = -2013 … 1757   (3769 breit)
Fenster             1920 px, Zoom 0.886  → 58 % der Netzbreite
sichtbar            3 der 5 Traumbegriffe
außerhalb           t133 (x -1875) und t134 (x -1931), beide „recent"
```

Die beiden fehlenden sind kein Zufall: frisch angelegte Knoten landen am
äußersten Rand des Netzes (Netzrand −2013).

## 1. Wann bewegt sich die Kamera? — Zwei Auslöser, nicht drei

**Entschieden: das Portrait zu Interviewbeginn und die neuen Begriffe.**
Beide sieht Tool 1 selbst, beide enden im selben Graph-Push, deshalb genügt
ein Einstieg (`aimCameraAtDream()` in `settle()`).

Birk wollte ursprünglich **drei** Auslöser, der dritte war „wenn das Bild
fertig generiert ist". Der entfällt aus zwei geprüften Gründen:

1. **Er zeigte auf denselben Ausschnitt.** `kg2.weighting.select_required`
   wählt die fünf Begriffe zu Beginn des Zyklus und behält sie bis zum
   fertigen Bild. `in_dream` in `graph.json` zeigt während der ganzen
   Generierung dieselben fünf — ein Schwenk zum Bildende führe dorthin, wo
   die Kamera seit Auslöser 2 längst steht.
2. **Er wäre nur über eine Architekturverletzung erreichbar.** Der Status
   `done` mit `image_path` steht in Tool 2s eigener Datenbank
   (`kg2/store.py`, `finish_dream`). `kg2/graph_client.py` ist der einzige
   Kontakt zwischen den Tools und hat per Konstruktion kein POST/PUT/PATCH;
   `tests/test_dream_contract.py` prüft das am Quelltext. Die Grenze
   existiert, damit Tool 1 weiterläuft, wenn Tool 2 abstürzt.

## 2. Wie eng? — Die fünf PLUS ihre Personen

**Entschieden: `dream.union(dream.neighborhood().nodes('.person'))`.**

Gemessen am Replay-Stand (60 Personen, 110 Begriffe, Fenster 1920×1080):

| Variante | Box | Zoom | Begriffe im Bild |
|---|---|---|---|
| nur die fünf | 1240 × 346 | **1.452** | 11 |
| die fünf + ihre 18 Personen | 1685 × 884 | **1.068** | 35 |
| die fünf + die zuletzt Befragte | 3125 × 767 | 0.576 | 60 |

Die dritte Variante fiel raus, weil diese eine Person am anderen Ende des
Netzes sitzt — der Ausschnitt wäre WEITER als die Ausgangslage (0.886).

Ausschlaggebend für Variante 2 war die Lesbarkeit: 1.452 ist 1,6× enger als
die auf der Wand kalibrierte Ansicht und für Labels wie „Pseudo-Abstimmung
vor Baubeginn" zu wenig Fläche. 1.068 liegt nah an dem, was schon als lesbar
beurteilt wurde. Inhaltlich ist es außerdem die vollständigere Aussage: die
Begriffe sind das Material, die Portraits sind, wer es gesagt hat.

> Vorbehalt zur dritten Variante: „die zuletzt befragte Person" wurde über
> `created_at` bestimmt und lieferte im Replay-Stand `p1` — die Zeitstempel
> sind dort synthetisch (exakt 300 s Abstand, min = max = Median). Die Zahl
> 0.576 ist damit für den Livebetrieb nicht belastbar. Für die Entscheidung
> ohne Belang, weil Variante 2 aus eigenem Recht gewinnt.

## 3. Zwischen zwei Träumen? — Weiterwandern, aber im Traumgebiet, mit wachsendem Radius

**Entschieden: der Rundgang bleibt im Gebiet, und der Ausschnitt weitet sich
über die Haltezeit von 1.0 auf 2.1.** Birks Bild: „inhaltlich zuerst den Traum
erklären, eins zu eins zeigen, und dann immer mehr Kontext geben."

Zwei verworfene Alternativen:

- **Stillstand** widerspricht der Bauentscheidung des automatischen Modus.
  `camera.js` hat eine Atembewegung (`breathAmplitude: 0.06`) allein dafür,
  dass das Bild nie einfriert — vier Minuten Stillstand arbeiten dagegen.
- **Freier Rundgang wie bisher** machte die Kopplung fast wirkungslos: eine
  Fahrt dauert 5,2 s, eine Rast 4,2 s, macht rund 25 Stationen zwischen zwei
  Träumen. Der Ausschnitt wäre nach zehn Sekunden verlassen.

Umsetzung: `_pickTarget()` wählt aus den Knoten des Gebiets statt aus allen
110 Begriffen; `_travelLevel()` misst die Box des Gebiets und teilt sie durch
`_dreamSpread()`. Die Aufweitung ist **linear** und nicht über `easeInOut` —
das hier ist kein Bewegungsabschnitt, den jemand als eine Geste sieht,
sondern ein vier Minuten langes Driften; weiche Enden ließen es
zwischendurch schneller laufen und würden als Bewegung auffallen.

`holdMs: 240000` (vier Minuten) hängt an kg2s `min_interval_s: 240`. Läuft
die Zeit ab, verfällt das Gebiet und die Wand wandert wieder frei — der Rest
des Netzes darf nicht stundenlang unsichtbar bleiben.

## 4. Verhältnis zum Touchscreen — kein Sonderfall

**Entschieden: die Kopplung gilt auf allen Flächen gleich.** Fläche A
(`?touch=1`) bekommt keine Ausnahme.

Das brauchte keine Zeile Code, weil Birks Modell aus Frage 1 es schon
abdeckt: im manuellen Modus wirkt nichts, das Gebiet wird trotzdem gemerkt,
und beim Rückfall in die Automatik fährt die Wand zuerst dorthin. Gemessen
auf `?theme=f&touch=1`:

```
1. Automatik        zoom 1.068   5/5 Begriffe, 18/18 Personen
2. Berührung        mode manual  (Besucher übernimmt)
3. Nahansicht       zoom 2.400   0/5 sichtbar — er schaut woanders hin
4. neuer Traum      zoom 2.400   pan unverändert — die Wand bewegt sich NICHT
                                 Gebiet trotzdem gemerkt: 23 Knoten
5. Rückfall         zoom 1.053   5/5 Begriffe, 18/18 Personen
```

Sollte sich vor Ort zeigen, dass es am Touchscreen zu unruhig ist, ist die
Einschränkung auf B/C eine Einzeilenänderung in `attachTouchAutonomy`.

## Der Fehler, der die Kopplung zunächst wirkungslos machte

Wert festzuhalten, weil er die Fehlerart aus Handoff §4 exakt wiederholt —
gebaut, plausibel, wirkungslos, und **nur am gerenderten Bild** zu sehen.

Die erste Fassung war vollständig und richtig: `focusDream()` lief,
`dreamState` meldete 23 Knoten, ein erzwungener Handover fuhr sauber von
0.886 auf 1.032. Trotzdem stand der Zoom in drei Messpunkten über 40 Sekunden
unverändert auf 0.886.

Ursache, instrumentiert statt geraten (`setMode`, `_startHandover`, `_frame`
mit einer Spur belegt):

```
focusDream n=23 mode=fit
_startHandover zoom=1.000
onGraphChanged h=ja
setMode(fit)            ← hier
_frame (GANZES NETZ!)
```

`setMode()` behandelte einen Moduswechsel und ein Neusetzen auf denselben
Wert gleich: es löschte `this._handover` und framte über `_frame()` das ganze
Netz. `/events` schickt nach jedem `graph` auch ein `state`, und
`projection.html` reicht dessen `camera_mode` ungeprüft durch — meist
derselbe Wert wie eben. Also tötete **jeder Graph-Push** den Handover, den
derselbe Push eine Zeile vorher gestartet hatte.

Die Reparatur trennt zwei Dinge, die vorher eines waren:

- **immer, auch bei gleichem Modus:** `_applyInteractivity()` — die
  Zusicherung, dass keine Besucherhand den Viewport verschiebt oder einen
  Knoten aus der Anordnung zieht. Sie wird bei jedem Aufruf neu behauptet.
- **nur bei echtem Wechsel:** `_handover = null`, `_roam`, `_frame()` — das
  Neuwerfen der Ansicht.

Ein erster Reparaturversuch stieg pauschal früh aus und nahm die Zusicherung
mit; `tests/test_camera.py::test_fit_and_pan_modes_disable_panning_zooming_and_grabbing`
fing das ab. Der Test beschreibt einen echten Schutz und wurde deshalb NICHT
angepasst — die Trennlinie oben ist die Antwort darauf.

## Was der Prerender davon merkt — und warum die Kopplung abschaltbar ist

`sim/prerender.py` schießt Referenzaufnahmen und filmt Sequenzen. Beides
braucht eine DEFINIERTE Ansicht, nicht die, die die Station gerade erzählt:
Ansicht 1 heißt „fit mode, the whole net in frame" und wird darauf geprüft,
dass alle Knoten im Bild sind; eine Sequenz zeigt EINE Bewegung und danach
einen Schweif, der stillstehen muss. Zwei kalte Läufe werden Bild für Bild auf
Gleichheit verglichen.

Die Kopplung brach alle drei Zusagen. Die Reparatur ist eine Zeile —
`_open_projection()` ruft `window.kgView.setDreamCamera(false)` — aber sie
richtig zu finden hat drei Anläufe gekostet, und **das** ist der Teil, der hier
festgehalten gehört.

### Der Weg dahin: zwei falsche Diagnosen

**Falsche Fährte 1: „das gemerkte Gebiet muss weg."** `clearDream()` gebaut,
das `_dream` löscht. Ergebnis: 0.931 → 0.966. Die Zahl BEWEGTE sich, statt grün
zu werden — das Signal, dass die Ursache mehrteilig ist. Nachgelegt: auch den
laufenden Handover verwerfen. Damit war Ansicht 1 grün, die Sequenzen aber
nicht.

**Falsche Fährte 2: „die Aufweitung ist nicht reproduzierbar."** `motion.json`
rundet Knotenpositionen auf drei Nachkommastellen, den Zoom aber nicht — also
schien eine zeitabhängige Zoomberechnung die Erklärung. Die Aufweitung wurde
in 250-ms-Stufen quantisiert. Ergebnis: die Abweichung wurde GRÖSSER. Damit war
die Hypothese widerlegt, und die Quantisierung ist wieder entfernt — sie löste
ein Problem, das es nicht gab.

Auch der dritte Verdacht (der Frühausstieg in `setMode`) fiel, und zwar an der
Messung: ein wiederholtes `setMode('fit')` und ein explizites `_frame()`
liefern bitgleich denselben Zoom (Differenz exakt 0), der Zoom ist über
Sekunden stabil.

### Die tatsächliche Ursache: der Zeitpunkt, nicht der Mechanismus

Gefunden, indem die beiden `motion.json` Frame für Frame verglichen wurden,
statt weiter zu raten:

```
frame   0  t=  0.0  dzoom=9.240e-03  dpan=(1.19, 10.45)  positionen_gleich=True
frame   1  t= 40.0  dzoom=9.228e-03  dpan=(1.19, 10.43)  positionen_gleich=True
frame   4  t=160.0  dzoom=9.167e-03  dpan=(1.18, 10.36)  positionen_gleich=True
```

Drei Aussagen auf einmal: die Abweichung ist **schon in Frame 0** da (also vor
jedem Tick der kontrollierten Uhr), sie **klingt ab** (also konvergieren beide
Läufe gegen dasselbe Ziel), und die **Knotenpositionen sind identisch** (also
liegt es allein an der Kamera). Das ist die Signatur einer laufenden Fahrt, die
in beiden Läufen unterschiedlich weit gekommen ist — kein Rundungsproblem.

`setDreamCamera(false)` stand nach den Wartezeiten in `_open_projection()`. Die
Fahrt startet aber mit dem ERSTEN Graph-Push, also währenddessen. Das
Abschalten fror sie damit nur ein, an einer Stelle, die von der realen Uhr
abhängt. Jetzt steht der Aufruf direkt nach `page.goto()`, sobald `kgView`
existiert — bevor die Kamera überhaupt losfahren kann.

### Warum ein Schalter und nicht ein Aufräumen vor jeder Aufnahme

`aimCameraAtDream()` hängt in `settle()` und läuft damit bei JEDER Migration —
auch bei der, die der Prerender selbst als Trigger auslöst, mitten im Film.
Gemessen: nach einem Dial-Wechsel stand `dream: 23, handover: läuft`, obwohl
unmittelbar davor beides gelöscht war. Ein punktuelles Aufräumen kuriert also
Symptome; „diese Aufnahme erzählt nicht, sie zeigt" ist eine Aussage über den
ganzen Lauf. **Die Wand schaltet nie ab** — nur Werkzeuge.

`clearDream()` bleibt daneben bestehen (es löscht Gebiet und laufende Fahrt)
und wird von `setDreamCamera(false)` benutzt.

### Die Lehre

Zwei geratene Fixes kosteten je zwölf Minuten Testlauf und führten in die
Irre. Die Sonde, die zwei `motion.json` vergleicht, war in zwei Minuten
geschrieben und beantwortete die Frage sofort. Das ist wörtlich, was Abschnitt
4 des Handoffs fordert — und es wurde hier trotzdem erst im dritten Anlauf
befolgt. **Wenn eine Kennzahl sich BEWEGT, statt grün zu werden, ist die
Diagnose unvollständig — nicht der Fix zu schwach.** Beide Male war das der
Moment, an dem die Messung fällig war und stattdessen weitergeraten wurde.

Gegenprobe, dass die Fehlschläge wirklich von dieser Arbeit stammten und nicht
vorbestanden: dieselben Tests gegen `c6347bd` (der Stand davor) laufen grün
durch. Eine frühere Behauptung, der Determinismus-Test sei ohnehin instabil,
war falsch — sie beruhte auf einem Stash, der nur die uncommitteten Änderungen
zurücknahm, während die committeten aktiv blieben.

## Verifikation am gerenderten Bild

Alle Zahlen aus `page.evaluate` gegen den laufenden Server auf `:8801`,
Viewport 1920×1080, `?theme=f`.

```
vorher     3/5 Traumbegriffe im Bild, zoom 0.886
nachher    5/5 Begriffe, 18/18 Personen, zoom 1.068
Aufweitung über 90 s im pan-Modus:
  t= 6s  zoom 1.027  spread 1.089  5/5  18/18   44 Begriffe im Bild
  t=36s  zoom 0.833  spread 1.231  5/5  18/18   58
  t=81s  zoom 0.734  spread 1.441  5/5  18/18   68
Rundgang   6/6 gewählte Ziele lagen im Traumgebiet
tests/test_camera.py  38/38
```

Anmerkung zu `fit` vs. `pan`: `step()` steigt in `fit` aus (`camera.js`,
`if (this._mode !== 'pan') return`). Der Rundgang UND die Aufweitung leben
deshalb im `pan`-Modus; in `fit` fährt die Kamera einmal auf das Traumgebiet
und bleibt dort stehen. Das ist konsistent mit dem, was `fit` bedeutet, aber
es heißt: **wer die wandernde Kamera und den wachsenden Radius auf der Wand
sehen will, muss den Operator auf `pan` stellen.** Vorgabe der Station ist
`fit` (`kg/server.py`, `camera_mode` default).

## Cytoscape-Prüfung gegen das Bundle

Nach Handoff §4 gegen die vendorierte 3.30.2 geprüft, nicht gegen die Doku:
`neighborhood`, `closedNeighborhood`, `union`, `boundingBox` sind alle im
Bundle vorhanden. Verwendet wird `neighborhood()` und nicht
`closedNeighborhood()`, weil das Ergebnis ohnehin mit den Traumknoten
vereinigt wird und `neighborhood()` sichtbar macht, dass hier die PERSONEN
dazukommen und nicht versehentlich weitere Begriffe.
