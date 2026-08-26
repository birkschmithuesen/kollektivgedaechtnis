# Simulationswerkzeuge

Alles hier ist Werkzeug zum **Anschauen und Kalibrieren**, nichts davon läuft am
Ausstellungstag. Kein Werkzeug hier ruft ein LLM auf — die Extraktion ist in
`out/sim19c/sim.db` bereits geschehen, diese Skripte spielen ihr Ergebnis nach.

## Den Aufbau Interview für Interview mitverfolgen

Startet eine **leere** Wand und lädt auf Zuruf je ein Interview nach. Nach
Schritt N enthält der Graph exakt die ersten N Interviews — jeder Knoten, der
erscheint, erscheint wegen des gerade hinzugefügten Interviews.

```bash
uv run python -m sim.step_server \
  --source-db out/sim19c/sim.db \
  --data-dir /tmp/kg-walk \
  --host 127.0.0.1 --port 8802 \
  --portraits 'sim/data/portraits/*.jpg'
```

```bash
curl -XPOST http://127.0.0.1:8802/step      # ein Interview weiter
curl       http://127.0.0.1:8802/progress   # wo stehen wir
curl -XPOST http://127.0.0.1:8802/reset     # zurück auf leer
```

`/step` liefert zurück, was das Interview verändert hat: `new_terms` (neue
Knoten) getrennt von `joined_terms` (Begriffe, die eine weitere Stimme bekommen
haben). Auf der Wand sind das zwei verschiedene Ereignisse.

Wandern die Begriffe zusammen? Erst ab ~20 Interviews wird „geteilt (ab 2)"
interessant; bei 8 Interviews gibt es typischerweise genau einen geteilten
Begriff, und die Wand sieht bei Dichte 2 leer aus. Das ist der Bestand, kein
Defekt.

## Interviews als Markdown lesen

```bash
uv run python sim/export_interviews_md.py \
  --db out/sim19c/sim.db --out <zielordner>
```

Eine Datei je Interview: **Transkript wörtlich** (mit „ähm", ungeglättet — das
ist, was der Extraktor gesehen hat), die extrahierten Begriffe samt Reichweite,
die behaltenen Zitate. Dazu `00-uebersicht.md` als Index.

Wörtlich ist Absicht: Ein Begriff, der falsch aussieht, muss bis zu dem Satz
zurückverfolgbar sein, aus dem er stammt.

## Portraits für den echten Look

Personenknoten brauchen Gesichter, um die Wand beurteilen zu können. 16
einzelne Portraits wären 16 Bildmodell-Aufrufe; ein 4×4-Kontaktbogen ist
**einer**.

```bash
uv run python sim/cut_portrait_sheet.py sim/data/portrait-sheet.png \
  --out sim/data/portraits
```

Das Skript **misst die Trennstege**, bevor es schneidet, und verweigert die
Arbeit, wenn das Raster nicht passt — ein um zwanzig Pixel verschobener Bogen
ergäbe sonst 16 Portraits mit dem Ohr des Nachbarn am Rand. Prüfen ohne
Schneiden:

```bash
uv run python sim/cut_portrait_sheet.py <bogen.png> --check
```

Neuen Bogen erzeugen: ein Bildmodell mit einem Prompt für ein sauberes 4×4-Raster
aus Passbildern vor einheitlichem Hintergrund, dann obiges Skript darüber.

## Was diese Werkzeuge NICHT prüfen

Sie spielen ein aufgezeichnetes Ergebnis nach. Damit ist **weder Extraktion noch
Merging** getestet — ein Schritt, der richtig aussieht, beweist nur, dass das
gespeicherte Ergebnis korrekt kopiert wurde. Für die echte Kette braucht es den
Replay mit LLM (`sim/replay.py`) oder die Ende-zu-Ende-Tests.
