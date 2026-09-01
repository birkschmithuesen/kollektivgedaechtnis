# Handoff: Alternativ-Foto-Cache für das laufende Interview

**Stand 2026-09-01.** Branch `mikrofonschalter/interview-signal` im Repo
`kollektivgedaechtnis`. Vorbereitet, **nicht gebaut** — auf Birks Ansage:
„Musst du jetzt aber nicht bauen den cache. Nur soweit vorbereiten."

---

## Der Auftrag, wörtlich

> „Wenn während eines laufenden Interviews ein zweites Foto gemacht wird,
> soll das in einen alternativ Foto cache für das laufende Interview."

Anlass war eine Rückfrage zu meiner Formulierung „zweites Foto → neuer
Besucher". Das beschrieb das *heutige* Verhalten, nicht das gewünschte.

## Was heute passiert (Code gelesen, nicht vermutet)

`kg/session.py`, `SessionTracker.photo(at)` kennt drei Fälle:

| Situation | Übergang | Wirkung |
|---|---|---|
| kein Interview offen | `opened/photo` | neue Person |
| offen, **ohne** Porträt (per Schalter eröffnet) | `portrait/late_photo` | Porträt wird nachgetragen, **selbe** Person |
| offen, **mit** Porträt | `closed/new_photo` + `opened/photo` | Interview endet, **neue** Person |

Der dritte Fall ist der, den Birk geändert haben will. Heute ist ein zweites
Foto der Anfang des nächsten Besuchs — künftig soll es eine weitere Aufnahme
**derselben** Person sein.

Der zweite Fall (`late_photo`) ist frisch gebaut und getestet (33 Tests in
`tests/test_mic_switch.py`, plus Mutationsprobe). Er bleibt, wie er ist.

## Was vorbereitet ist

Nur eine Markierung: Der Docstring von `SessionTracker.photo()` benennt die
offene Entscheidung, zitiert den Auftrag und verweist hierher. **Kein
Verhalten geändert** — und das ist Absicht: Ohne Cache, in den das zweite
Bild fällt, wäre das Foto schlicht verloren. Das wäre schlechter als der
heutige Stand, bei dem es wenigstens eine eigene Person bekommt.

## Drei Entscheidungen VOR dem Bauen

Die kosten hinterher deutlich mehr als vorher. Alle drei brauchen Birk.

### 1. Wie fängt dann der nächste Besuch an?

**Das ist die wichtigste Frage.** Fällt jedes Foto während eines offenen
Interviews in den Cache, gibt es keinen Weg mehr, per Foto ein neues
Interview zu eröffnen. Übrig bleiben:

* der Mikrofonschalter (`mic_switch`, seit 2026-09-01),
* die gesprochene Schlussphrase (`stop_intent`),
* der Timeout (`timeout_s`, Vorgabe in `config.toml`).

Das ist eine Entscheidung über den **Ablauf an der Station**, keine
Implementierungsfrage: Wenn ein Gast geht ohne etwas zu sagen und ohne den
Schalter zu betätigen, hängt sein Interview bis zum Timeout — und das Foto
des nächsten Gastes landet in *seinem* Cache. Denkbare Auswege:

* Cache nur, solange das Interview **jung** ist (z.B. erste 60 s), danach
  wieder `new_photo`.
* Cache nur bei ausdrücklicher Bedienung im Operator („weitere Aufnahme").
* Kürzerer Timeout, damit ein verwaistes Interview schneller zufällt.

### 2. Wo liegen die Bilder, und wie lange?

`person.photo_path` und `person.portrait_path` halten je **genau einen**
Pfad (`kg/store.py`, `create_person`, `set_person_portrait`). Ein Cache
braucht also eine eigene Tabelle — etwa `person_photo(person_id, photo_path,
portrait_path, taken_at, chosen)` — oder eine Liste am Datensatz.

**Und eine Löschregel.** Bei einer Arbeit über Datenschutz und Überwachung
ist ein wachsender Haufen nicht ausgewählter Porträts kein Nebenaspekt,
sondern ein Widerspruch zur Aussage der Arbeit. Vorschlag zur Diskussion:
verworfene Aufnahmen werden beim Schließen des Interviews gelöscht, nur die
gewählte bleibt. Falls sie länger leben sollen, gehört das ausdrücklich
entschieden und dokumentiert — nicht als Nebenwirkung „vergessen".

Siehe auch `kg/photos.py` (Zuschnitt, Ablage) und `kg/export.py`
(`_portrait_url`, liefert bei fehlendem Pfad `None`).

### 3. Wer wählt aus?

Operator-Ansicht, automatisch (letzte Aufnahme gewinnt), oder der Gast
selbst? Danach richtet sich, ob es überhaupt eine Oberfläche braucht.
Die Operator-Seite liegt in `frontend/operator.html` +
`frontend/static/operator.js`.

## Wenn gebaut wird: worauf zu achten ist

* **`late_photo` nicht mit dem Cache vermischen.** Der Fall „Interview per
  Schalter eröffnet, Porträt wird nachgereicht" ist etwas anderes als „schon
  ein Porträt da, weitere Aufnahme". Beide Wege brauchen eigene Tests. Eine
  Mutationsprobe dazu existiert und ist dokumentiert — Nachreich-Zweig
  entfernen lässt 5 Tests rot werden, während die zwei
  `new_photo`-Absicherungen absichtlich grün bleiben.
* **Die Wand verträgt Personen ohne Bild** (`--person-blank` in
  `theme-f.css`, seit `cf3de55`) — ein Cache-Bild, das noch nicht gewählt
  ist, muss also nicht sofort erscheinen.
* **Nach einem Neustart** liest `Core.__init__` aus der Datenbank nach, ob
  die offene Person schon ein Porträt hat (`open_without_portrait`). Kommt
  eine Cache-Tabelle dazu, gehört sie in dieselbe Wiederherstellung.
* Die volle Suite lag am 2026-09-01 bei **1108 grün** (ohne
  `test_prerender.py`, das Playwright braucht).

## Verwandte Stellen

| Datei | Was |
|---|---|
| `kg/session.py` | `SessionTracker.photo()` — hier steht die Markierung |
| `kg/core.py` | `_open`, `_portrait`, `on_photo`, `open_without_portrait` |
| `kg/store.py` | `create_person`, `set_person_portrait` |
| `kg/photos.py` | Zuschnitt und Ablage der Bilder |
| `tests/test_mic_switch.py` | 33 Tests zu Schalter, `late_photo`, `new_photo` |
| `docs/stt-contract.md` | Vertrag STT-Server ↔ Core |
