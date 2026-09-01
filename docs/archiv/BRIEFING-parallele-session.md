# Kurzbriefing für die parallel laufende Session

**Stand 2026-09-01, von der EU-Umstellungs-Session.**

Du arbeitest in `kg-app` auf `master`, ich auf dem Branch
**`mikrofonschalter/interview-signal`** (gepusht). Diese Notiz und die beiden
Handoffs liegen dort — lesbar **ohne** Branch-Wechsel:

```
git show origin/mikrofonschalter/interview-signal:docs/BRIEFING-parallele-session.md
git show origin/mikrofonschalter/interview-signal:docs/HANDOFF-session-2026-09-01.md
git show origin/mikrofonschalter/interview-signal:docs/HANDOFF-alternativ-foto-cache.md
```

* `HANDOFF-session-2026-09-01.md` — Gesamtstand, was steht, was offen ist
* `HANDOFF-alternativ-foto-cache.md` — die nächste Aufgabe

---

## Was du wissen musst, in Kürze

**Die Station läuft jetzt vollständig über EU/Schweiz.** LLM (Verdichtung,
Wake-Word, Traumsatz) und Embeddings über Infomaniak Genf, Bilder über Black
Forest Labs (`api.eu.bfl.ai`), STT über Infomaniak Whisper. Anthropic und
OpenRouter bleiben als Rückfallwege in den Configs.

**Zwei Dinge betreffen dich direkt:**

1. **Der Embedding-Wechsel ändert die Nachbarschaften.** bge statt
   `text-embedding-3-small`, gemessen an 108 echten Merge-Paaren aus Lauf 19c:
   69/108 statt 66/108 in den Top-12. `merge_neighbours = 12` bleibt richtig.
   Wenn dir Begriffs-Zusammenführungen anders vorkommen als früher — das ist
   der Grund, kein Fehler. Details: `docs/embedding-vergleich-2026-08-31.md`.

2. **Eine Person kann jetzt ohne Porträtfoto existieren.** Der
   Mikrofonschalter eröffnet und schließt Interviews (`POST
   /api/interview_switch` in `kg/server.py`); wer kein Foto von sich will,
   soll trotzdem teilnehmen können. `photo_path` und `portrait_path` sind dann
   `None`.

   Auf der Wand war so ein Knoten in theme-f **unsichtbar** (247 von 28392
   Pixeln nicht schwarz, und die kamen von der Kante). Behoben mit
   `--person-blank: #6E6656` — keine neue Farbe, sondern die vorhandene
   `--term-ring-idle`. **Wenn du an der Projektion arbeitest: rechne mit
   `portrait === null`.**

---

## Berührungspunkte

Bisher gab es keine Konflikte: deine Arbeit lag in `camera.js`,
`projection.html`, `photos.py`, QR-Code; meine in `session.py`, `core.py`,
`server.py`. `master` lief während meiner Session fünfmal weiter, ich habe vor
jedem Push rebased und die volle Suite gefahren (zuletzt **1130 grün**, ohne
`test_prerender.py`).

**Wo wir uns treffen werden:**

* **`kg/server.py`** — du hast dort gerade uncommittete Änderungen
  (Foto-über-Netz), ich habe `POST /api/interview_switch` ergänzt. Beim
  nächsten Rebase aufeinander achten.
* **`frontend/static/projection.js`** — ich habe `PERSON_BLANK` ergänzt und in
  `render()` das Nachziehen des Porträts eingebaut: `toCytoscape` setzte
  `portrait` nur beim Anlegen, ein nachgereichtes Bild wäre bis zum
  Seitenneuladen unsichtbar geblieben.
* **`kg/photos.py`** — dein Gesichtsausschnitt (`c4974fc`), von mir nicht
  angefasst. Wenn der Alternativ-Foto-Cache kommt, treffen wir uns dort.

**Zwei Regeln, die ich mir teuer erkauft habe:**

* **Nie im geteilten Arbeitsverzeichnis den Branch wechseln.** Ich habe das
  einmal getan und dir den Boden weggezogen — nichts ging verloren, aber der
  richtige Weg ist ein `git worktree` (es gibt bereits drei).
* **Zum Testen eigenen Port und eigenes `data_dir`.** 8800 (dein Core) und
  8899 sind belegt; ich habe 8853/8854 mit `mktemp -d` benutzt.

---

## Die nächste Aufgabe, falls sie bei dir landet

Birk will, dass ein **zweites Foto während eines laufenden Interviews** in
einen Alternativ-Cache derselben Person fällt, statt einen neuen Besuch zu
beginnen (heute: `closed/new_photo` + `opened/photo`).

**Vorbereitet, bewusst nicht gebaut** — ohne Cache wäre das Foto sonst
verloren, und das ist schlechter als der jetzige Stand. Die Markierung sitzt
im Docstring von `SessionTracker.photo()`.

Drei Entscheidungen brauchen Birk, bevor gebaut wird. Die wichtigste: **Wie
fängt dann der nächste Besuch an?** Fällt jedes Foto in den Cache, eröffnet
kein Foto mehr ein Interview — übrig blieben Schalter, Schlussphrase und
Timeout. Ein Gast, der wortlos geht, lässt sein Interview bis zum Timeout
offen, und das Foto des nächsten landet in seinem Cache. Das ist eine Frage an
den Ablauf der Station, keine an den Code. Ausführlich im Handoff.
