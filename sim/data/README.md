# `sim/data/` — synthetische Daten. Keine echten Menschen.

**Alles in diesem Verzeichnis ist maschinell erzeugt.** Kein Wort stammt von
einer realen Person, kein Gesicht gehört einem realen Menschen. Das ist keine
Anonymisierung — es gibt nichts zu anonymisieren, weil nie jemand befragt oder
fotografiert wurde.

Diese Datei steht hier, weil die Frage bei einer Installation, die Menschen
interviewt und fotografiert, zuerst gestellt wird. Sie soll am Material
beantwortet sein, nicht in einem Chatverlauf.

| Was | Wie viel | Erzeugt von |
|---|---|---|
| `interviews/*.json` | 60 | Sprachmodell (`claude-sonnet-5`), Feld `model` in jeder Datei |
| `portraits/*.jpg` | 16 | Bildmodell, ein 4×4-Kontaktbogen, zerschnitten von `sim/cut_portrait_sheet.py` |
| `portrait-sheet.png` | 1 | derselbe Kontaktbogen, ungeschnitten |
| `graph-19c.json` | 1 | Replay-Lauf über die 60 Interviews — siehe `graph-19c.provenance.md` |
| `expectations.yaml` | 1 | von Hand, Erwartungswerte für die Simulationsprüfung |

## Woran man das selbst nachprüft

Jede Interviewdatei nennt ihre Herkunft in den eigenen Feldern:

```json
{
  "speaker_type": "sehr knapp, zwei Sätze, fast unwillig",
  "planted_concept": "Roboter auf der Baustelle",
  "planted_phrasing": "Maschinen, die den Beton selber aufsprühen, so Drohnen halt",
  "model": "claude-sonnet-5"
}
```

`speaker_type` und `planted_concept` sind Vorgaben *an* den Generator: Jedes
Interview wurde mit einem zugewiesenen Sprechtyp und einem absichtlich
gepflanzten Begriff erzeugt, damit sich Zusammenführung und Gewichtung gegen
eine bekannte Wahrheit prüfen lassen. Ein echtes Interview hätte diese Felder
nicht — man kann einem Menschen nicht vorher sagen, welchen Begriff er
erwähnen wird.

## Wofür es da ist

Die Station lässt sich damit vollständig ohne Publikum betreiben: Wand und
Traum sind reproduzierbar prüfbar, offline und ohne Kosten. Das ist die
Voraussetzung dafür, dass die Testsuite kein Geld verbrennt und dass sich ein
Kalibrierlauf ein Jahr später wiederholen lässt.

## Echte Daten

Landen **nie** in diesem Repo — es ist öffentlich. Sie bleiben unter `data/`
und `dream-data/`, beide ignoriert, und das ist durch
`tests/test_keine_echten_daten_im_repo.py` abgesichert (auch gegen ein
erzwungenes `git add -f`). Wer echte Ausstellungsdaten sichern will, nimmt ein
**separates privates Repo**.
