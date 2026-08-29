# Spec: Anzeigeregler der Wand — von `min_mentions` auf eine Begriffs-Obergrenze

**Status:** Entwurf, 2026-08-29. Entschieden von Birk im Gespräch, Messung
liegt vor (siehe §2). Umzusetzen in **Tool 1** (`kg/`, `frontend/`).
**Betrifft NICHT Tool 2** — die Entkopplung ist Teil der Entscheidung, §5.

---

## 1. Was heute da ist und warum es nicht reicht

Die Wand hat einen Regler `min_mentions` („zeige nur Begriffe, die mindestens
N Menschen genannt haben", Werte 1/2/3). Er liegt im Operator-Panel, wird als
Zahl in `graph.json` mitgeschickt (`kg/export.py:51`) und **im Browser**
angewendet (`frontend/static/graph-model.js:8`) — die Datenbank enthält immer
alle Begriffe, gefiltert wird nur die Anzeige.

Der Zweck des Reglers ist **Lesbarkeit**: Bei zu vielen Begriffen überlappen
die Beschriftungen und die Schrift wird zu klein. Aber „ab wie vielen
Nennungen" ist dafür eine **indirekte** Größe. Die direkte wäre: *wie viele
Begriffe passen auf die Wand?*

## 2. Die Messung (gemacht am 2026-08-29, `wall_legibility_probe.py`)

Echtes Frontend, `out/sim19c/sim.db` (60 Personen, 163 Begriffe), Chromium
1920 × 1080, gemessen an Cytoscapes eigenen Label-Boxen.

**Der heutige Regler:**

| `min_mentions` | Begriffe | Schrift px | Label-Kollisionen | Labels auf Portraits |
|---|---|---|---|---|
| 1 (Standard) | **163** | 16,1 | **56** | **51** |
| 2 | 49 | **4,0** | 0 | 0 |
| 3 | 26 | 11,5 | 0 | 0 |
| 4 | 16 | 16,8 | 0 | 0 |

Drei Befunde:

1. **Der Standardwert produziert eine unlesbare Wand.** Bei 60 Personen und
   `min_mentions=1` überlappen 56 Label-Paare, 51 Labels liegen auf
   Portraits. Am Ausstellungstag tritt das ab etwa 40 Interviews ein.
2. **Der Regler springt zu grob.** Ein Klick von 1 auf 2 wirft 114 von 163
   Begriffen weg — zwei Drittel der Wand.
3. **Er tut nicht verlässlich, wofür er da ist.** Bei `min_mentions=2` sind es
   weniger Begriffe, aber die Schrift ist mit **4 px kleiner** als bei 163
   Begriffen (16 px): Die Kamera zoomt heraus, weil die verbliebenen Begriffe
   weit gestreut liegen. Weniger Begriffe ≠ bessere Lesbarkeit.

**Die vorgeschlagene Regel** (Obergrenze, stärkste Begriffe zuerst; gemessen
mit denselben 60 Personen):

| Obergrenze | Schrift px | Label-Kollisionen | Labels auf Portraits | Fläche |
|---|---|---|---|---|
| 20 | 16,5 | 1 | 4 | 8,9 % |
| 26 | 13,0 | 2 | 9 | 8,7 % |
| 32 | 14,7 | 2 | 3 | 11,9 % |
| 40 | 14,3 | 1 | 7 | 14,6 % |
| 49 | 12,4 | 5 | 7 | 15,1 % |
| 60 | 10,3 | 1 | 2 | 15,5 % |

Der Unterschied zum heutigen Regler ist deutlich: **Über den ganzen Bereich
bleiben die Kollisionen einstellig** (1–5 statt 56), weil die Kamera bei einer
gedeckelten, dichteren Auswahl nicht so weit herauszoomen muss. Die Schrift
sinkt gleichmäßig von 16,5 px auf 10,3 px, statt zu springen.

**Umrechnung auf die Wand** (65″, 16:9 → 144 cm Bildbreite, 1920 px):

| Schrift px | Versalhöhe | lesbar bis ca. |
|---|---|---|
| 10,3 | 5,4 mm | 1,4 m |
| 12,4 | 6,5 mm | 1,6 m |
| 14,3 | 7,5 mm | 1,9 m |
| 16,5 | 8,7 mm | 2,2 m |

⚠️ Diese Umrechnung ist **eine Abschätzung** (Faustregel ~1 mm Versalhöhe pro
2,5 m Lesedistanz) und setzt eine 65″-Fläche voraus. Die tatsächliche
Projektionsgröße vor Ort ist nicht dokumentiert — `docs/operations.md` hält
ausdrücklich fest, dass Beamer, Wand und Raumtiefe **vor Ort** eingestellt
werden (Entscheidung D4). Der Regler muss deshalb ein Regler bleiben und darf
keine feste Zahl werden.

## 3. Die neue Regel

> **Alle Begriffe ab 2 Nennungen kommen auf die Wand. Der Rest wird mit
> Einmal-Nennungen aufgefüllt, bis die Obergrenze erreicht ist — die jüngsten
> zuerst. Was darüber hinausgeht, wird ausgeblendet.**

Das ist **dieselbe Regel wie in Tool 2** (`kg2/weighting.py`, seit 2026-08-28)
— dort mit einem gleitenden Budget statt einer festen Obergrenze, weil der
Traum kein Platzproblem hat.

Warum „jüngste zuerst" und nicht „häufigste": Bei den Einmal-Nennungen ist die
Häufigkeit definitionsgemäß gleich (alle 1×), es braucht also ein zweites
Kriterium. Die Aktualität sorgt dafür, dass die gerade interviewte Person
ihren Begriff auf der Wand findet, während sie noch davorsteht.

Wenn die geteilten Begriffe allein die Obergrenze überschreiten (bei 60
Personen sind es 49): **dann wird auch bei den geteilten gekappt**, häufigste
zuerst. Das unterscheidet die Wand von Tool 2, und der Grund ist der
physikalische Platz — anders als beim Traum gibt es hier keine Alternative.

## 4. Der Regler selbst

`min_mentions` wird ersetzt durch **„Begriffe auf der Wand"** — eine
Obergrenze. Vorschlag für die Stufen: **20 / 32 / 45 / alle**, mit **32** als
Startwert (mittlere Dichte, 14,7 px Schrift, 2 Kollisionen).

Offen und vor Ort zu entscheiden: die genauen Stufenwerte. Die Messung deckt
20–60 ab; darüber wurde nicht gemessen, weil 163 Begriffe bereits als
unlesbar belegt sind.

Der alte Wert `min_mentions` in `graph.json`, `settings` und der Config wird
**nicht stillschweigend umgedeutet** — er verschwindet, und die neue Größe
bekommt einen eigenen Namen (Vorschlag `max_terms`). Ein Bestandsstand mit
`min_mentions=2` in der Datenbank darf nicht als „max_terms=2" gelesen werden.

## 5. Was ausdrücklich NICHT gekoppelt wird

Tool 2 liest weiterhin **alle** Begriffe aus `graph.json` und filtert selbst.
Der Anzeigeregler der Wand hat **keinen** Einfluss auf den Trauminhalt.

Begründung (Birk + Gegenargument, beide festgehalten):

- **Für die Kopplung spräche:** Was man sieht, ist das, was ins Bild geht.
  Nachvollziehbarkeit im Raum.
- **Dagegen — und das gab den Ausschlag:** Der Regler löst ein
  Lesbarkeitsproblem. Wäre er gekoppelt, würde ein Operator, der wegen der
  Schriftgröße nachjustiert, unabsichtlich ändern, woraus die Bilder
  entstehen. Zwei Ausstellungstage mit unterschiedlicher Reglerstellung wären
  nicht mehr vergleichbar, obwohl die Menschen dasselbe gesagt haben.

Stattdessen folgen beide **derselben Regel** mit eigenen Grenzen. Inhaltlich
einig, technisch entkoppelt.

Ausgeblendete Begriffe bleiben in der Datenbank und im Export. **Nichts wird
gelöscht** — Löschungen entscheidet Birk.

## 6. Was zu bauen ist

1. `kg/store.py` / `kg/export.py` — die Auswahl serverseitig berechnen oder
   die nötigen Daten (Nennungszahl, `created_at`) exportieren, damit das
   Frontend sie anwenden kann. Heute filtert der Browser
   (`frontend/static/graph-model.js:8`); ob das so bleibt, ist eine
   Implementierungsentscheidung — die Wand darf beim Umschalten nur nicht
   flackern.
2. `frontend/static/operator.js` — Regler umbauen, Beschriftung,
   Live-Vorschau der Begriffszahl.
3. `frontend/static/projection.js` — der Anzeigepfad.
4. `kg/config.py`, `config.example.toml` — `default_min_mentions` →
   `default_max_terms`.
5. `docs/operations.md` — Reglerbeschreibung ersetzen, die Messtabellen aus §2
   aufnehmen, die Entkopplung aus §5 festhalten.

**Bestandsdaten:** Keine Migration, die löscht. Eine Datenbank mit gesetztem
`min_mentions` startet mit dem neuen Standardwert.

## 7. Offene Punkte für die Umsetzung

- **Flackern beim Übergang.** Wenn ein Begriff die Obergrenze verlässt,
  verschwindet er von der Wand; kommt eine Nennung dazu, kehrt er zurück. Bei
  Begriffen an der Grenze kann das hin- und herspringen. Eine Hysterese (ein
  ausgeblendeter Begriff kehrt erst zurück, wenn er deutlich über der Grenze
  liegt) oder eine Mindeststandzeit wäre zu prüfen. **Messen, nicht raten.**
- **Der Zoom-Effekt aus §2, Befund 3** ist nicht verstanden: Warum wird die
  Schrift bei *weniger* Begriffen kleiner? Vermutung: Die Kamera rahmt alle
  sichtbaren Knoten ein, und verstreute Begriffe zwingen zu mehr Abstand. Falls
  das stimmt, hilft die Obergrenze doppelt — sie hält die Auswahl auch
  räumlich dichter. **Vor dem Bauen verifizieren.**
- Die Stufenwerte des Reglers (§4) vor Ort am echten Beamer festlegen.
