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
| 2 | 49 | 4,0 ⚠️ | 0 | 0 |
| 3 | 26 | 11,5 | 0 | 0 |
| 4 | 16 | 16,8 | 0 | 0 |

⚠️ **Die Schriftgrößen-Spalte dieser Tabelle ist unzuverlässig** (erkannt
2026-08-29 bei der Nachprüfung, §7). Der Messlauf öffnete die Fixture-Datenbank
in place statt über eine Scratch-Kopie und wartete eine feste Zeit statt auf das
Fertig-Signal des Layouts — dadurch konnte eine eingefrorene Kamera-Ansicht aus
einem vorherigen Lauf mitgemessen werden. Die saubere Wiederholung ergibt für
`min_mentions=2` **9,5 px** statt 4,0 px. Die Spalten **Begriffe,
Label-Kollisionen und Labels auf Portraits sind davon nicht betroffen** — sie
zählen den Zustand des Graphen, nicht die Kamera, und tragen den Befund unten.

Zwei Befunde:

1. **Der Standardwert produziert eine unlesbare Wand.** Bei 60 Personen und
   `min_mentions=1` überlappen 56 Label-Paare, 51 Labels liegen auf
   Portraits. Am Ausstellungstag tritt das ab etwa 40 Interviews ein.
   **Das ist der tragende Befund dieser Spec.**
2. **Der Regler springt zu grob.** Ein Klick von 1 auf 2 wirft 114 von 163
   Begriffen weg — zwei Drittel der Wand.

Ein dritter Befund stand hier ursprünglich („weniger Begriffe ergeben kleinere
Schrift, die Kamera zoomt heraus") und ist **widerlegt** — siehe §7. Er wird
bewusst nicht stillschweigend gelöscht: Er war das Argument, das am
plausibelsten klang und am wenigsten geprüft war.

**Die vorgeschlagene Regel** (Obergrenze, stärkste Begriffe zuerst; gemessen
mit denselben 60 Personen). Diese Tabelle ist am 2026-08-29 **sauber
nachgemessen** worden — Scratch-Kopie der Datenbank, Wartezeit auf das
`layoutPending`-Signal statt auf die Uhr:

| Obergrenze | Schrift px | Label-Kollisionen | Labels auf Portraits | Fläche |
|---|---|---|---|---|
| 20 | 17,2 | 0 | 0 | 9,3 % |
| 26 | 15,8 | 0 | 0 | 10,6 % |
| 32 | 13,8 | 0 | 0 | 11,1 % |
| 40 | 12,5 | 0 | 0 | 12,7 % |
| 49 | 10,0 | 0 | 0 | 12,2 % |
| 60 | 7,5 | 0 | 0 | 11,2 % |

Der Unterschied zum heutigen Regler ist eindeutig: **Über den ganzen Bereich
bis 60 Begriffe gibt es keine einzige Kollision** — gegenüber 56 Label-Paaren
und 51 Labels auf Portraits beim Standardwert `min_mentions=1`. Die Schrift
sinkt gleichmäßig und vorhersagbar von 17,2 px auf 7,5 px, statt zu springen.
Die Obergrenze ist damit ein Regler, der genau eine Größe steuert: die
Lesbarkeit.

**Umrechnung auf die Wand** (65″, 16:9 → 144 cm Bildbreite, 1920 px):

| Obergrenze | Schrift px | Versalhöhe | lesbar bis ca. |
|---|---|---|---|
| 20 | 17,2 | 9,0 mm | 2,3 m |
| 26 | 15,8 | 8,3 mm | 2,1 m |
| 32 | 13,8 | 7,2 mm | 1,8 m |
| 40 | 12,5 | 6,6 mm | 1,6 m |
| 49 | 10,0 | 5,2 mm | 1,3 m |
| 60 | 7,5 | 3,9 mm | 1,0 m |

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

- **Flackern beim Übergang — gemessen (2026-08-29).** `sim.dream_calibrate.prefix_graph`
  über die 60 Interviews von Lauf 19c, Auswahlregel bei jedem Schritt neu
  angewendet: **3,5 bis 5,2 Sichtbarkeits-Wechsel pro Interview**, über den
  ganzen getesteten Obergrenzen-Bereich (20/32/45/60) — deutlich über der
  Schwelle "selten" (< 1 pro Interview). Der größte Teil davon ist normale
  Fluktuation durch neue Einmal-Nennungen (Median-Abstand zwischen
  wiederholten Wechseln eines Begriffs: 7 Interviews), aber echtes
  Sofort-Zucken (ein Begriff verschwindet und kehrt im **nächsten** Interview
  zurück) kam mit rund 0,3 Fällen pro Interview trotzdem vor. Eine reine
  Rang-Hysterese (Puffer, wie weit ein Begriff die Grenze unterschreiten muss)
  half kaum (bei Obergrenze 32: 4,42 → 2,80 Wechsel/Schritt selbst mit einem
  Puffer von 15) — der Rang eines Einmal-Begriffs sinkt strukturell mit jedem
  neuen Konkurrenten und erholt sich nie von selbst, das kann ein Puffer nicht
  auffangen. **Gebaut: eine Mindeststandzeit** von 3 Graph-Aktualisierungen
  (`MIN_STAND_REVISIONS`, `frontend/static/projection.js`) — ein einmal
  gezeigter Begriff bleibt mindestens so lange sichtbar, unabhängig vom Rang,
  außer der Operator ändert die Obergrenze selbst (das wirkt sofort, ohne
  Rücksicht auf fremde Standzeiten). Das trifft die Aufgabe direkter als ein
  Rangpuffer, weil es weder das Ersterscheinen verzögert noch veraltete
  Einmal-Nennungen unnötig festhält.
- **Der Zoom-Effekt aus §2, Befund 3 — geklärt, nicht bestätigt (2026-08-29).**
  Die Vermutung (Kamera rahmt alle sichtbaren Knoten ein, verstreute Begriffe
  zwingen zu mehr Abstand) wurde mit einer sauberen, isolierten Messung
  **nicht bestätigt**: `min_mentions=1` (163 Begriffe) settelte bei 3,9 px
  Schrift / Zoom 0,4191, `min_mentions=2` (49 Begriffe) bei 9,5 px / Zoom
  0,6563 — die erwartete Richtung (weniger Begriffe → größere Schrift), nicht
  die in §2 berichtete. Der wahrscheinlichste Grund für die widersprüchliche
  Originalzahl: die Messung lief ohne Scratch-Kopie der Datenbank
  (`sim.prerender._served(db)` ohne `scratch=`) und mit fester Wartezeit statt
  auf das echte Fertig-Signal (`layoutPending === false`) — beides Fallen, in
  die ein Nachbau-Versuch selbst zunächst hineinlief (siehe
  `sim/probes/wall_legibility.py`, jetzt mit Scratch-Kopie). Die Obergrenzen-
  Idee steht trotzdem: Das eigentliche, unabhängig gemessene Problem (163
  Begriffe → 56 Label-Kollisionen, §2 Befund 1) ist davon unberührt.
- Die Stufenwerte des Reglers (§4) vor Ort am echten Beamer festlegen.
