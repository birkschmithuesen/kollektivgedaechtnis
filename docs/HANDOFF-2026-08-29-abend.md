# Handoff 2026-08-29 (Abend) — Bildprompt, Datenablage, öffentliches Repo

Nachfolger von `docs/HANDOFF-2026-08-29.md` (vormittags). Dessen drei Blocker
sind **erledigt** — Stand, Entscheidungen und was offen bleibt stehen hier.

**Repo:** `~/projekte/kollektivgedaechtnis`, Branch `master`.
**Öffentlich** seit heute: `github.com/birkschmithuesen/kollektivgedaechtnis`, MIT.
**Testsuite:** 819 Tests (voller Lauf ~21 min, `test_prerender.py` allein ~12).
**Festival:** NEW bauhaus, 2.–3. September 2026, Weimarhalle — **in vier Tagen.**

---

## 1. Die drei Blocker des Vormittags-Handoffs: erledigt

1. **End-to-End-Test für Tool 2 gebaut und real gefahren.**
   `tests/e2e/test_interview_to_screen_b.py`. Die Kette **Interview → Traum →
   Bild → Screen B** ist erstmals als Ganzes gelaufen: Tool 1 als echter
   uvicorn auf echtem Port, Tool 2 pollt `graph.json` über echtes HTTP, beide
   Cloud-Aufrufe echt. 32 s, ≈ 0,14 USD. Drei Eigenschaften erstmals belegt
   statt angenommen: Dateiendung folgt den Bytes, ein Neustart träumt dasselbe
   Material **nicht** erneut, ein Interview im Mindestabstand wird
   **verzögert statt verworfen**.

2. **Bildvertrag war bereits verifiziert** (seit 2026-08-26, Commit `85cce5b`).
   Offen war nur ein veralteter Kommentar in `config2.example.toml`. Korrigiert.

3. **Gemeinsamer Start dokumentiert:** `scripts/start-dream.sh` als Gegenstück
   zu `scripts/start.sh`, plus Runbook-Abschnitt „Beide Werkzeuge zusammen
   starten". Bewusst **keine** Abhängigkeit: Das Skript prüft `tool1_url`, sagt
   in beiden Richtungen was es findet, **wartet aber nicht** — fällt Tool 1
   aus, kommt Screen B trotzdem hoch. Beide Zweige real geprüft.

---

## 2. Der Bildprompt — fünf Befunde an einem Abend, alle behoben

**Das Muster, das sich durch alle fünf zieht, ist die eigentliche Lehre:**
Jedes Mal steckte der Fehler in einem **Beispiel im Prompt**, nicht im Modell.
Das Modell hat jedes Mal exakt nachgeahmt, was ihm vorgemacht wurde. Wer hier
weiterarbeitet: **prüfe zuerst die Vorbilder im Prompt, bevor du am Modell
oder an den Parametern drehst.**

| # | Befund (Birk, an realen Bildern) | Ursache | Fix |
|---|---|---|---|
| 1 | „Die Tension ist nicht erklärt" — zwei Roboterarme statt des echten Widerspruchs | `TENSION_COHERENCE` nennt keinen Inhalt; das Modell erfindet sich einen | Stufe 1 liefert `tension_source` |
| 2 | „Zu wenig Inhalt im Bild" | Motiv war die 16-Wort-Wandfassung | Stufe 1 liefert `image_description` (3–4 Sätze) |
| 3 | „Der Widerspruch kommt im Bild nicht raus" | Mein Beispiel war selbst abstrakt („decisions are made from above" hat kein Aussehen) | Prompt verlangt **Sichtbares**, mit Positiv- und Negativbeispiel |
| 4 | „Zwei Bilder in einem, links und rechts geteilt" | „beide Seiten gleich groß" liest sich als Diptychon-Auftrag | „EIN EINZIGER ORT, EINE EINZIGE AUFNAHME", trennende Wendungen benannt |
| 5 | „Tafel, aber da steht nichts drauf" → dann „Beschriftung auf Englisch" | Schriftverbot im Register **gegen** mein beschriftetes Positivbeispiel | Verbot raus, dann **Tendenz**: Regelfall ohne Schrift, Ausnahme mit deutschem Wortlaut |

### Was daraus im Code steht

**Stufe 1 (`kg2/condense.py`)** liefert jetzt **vier Texte** statt zwei:
- `sentence` — der deutsche Wandsatz, **16 Wörter, unverändert**. Die
  Lesbarkeitsmessung gilt weiter; er wurde bewusst **nicht** angefasst.
- `sentence_en` — wörtliche Übersetzung, bleibt als ehrliche Entsprechung.
- `image_description` — ausführliche englische Szene, das Bildmotiv.
- `tension_source` — der Widerspruch, **sichtbar** formuliert, darf leer sein.

**Stufe 2 (`kg2/imagegen.py`)**: Motiv-Fallbackkette
`image_description → sentence_en → sentence`. `TENSION_COHERENCE` unverändert;
`TENSION_SOURCE_TEMPLATE` hängt den konkreten Widerspruch als eigenen Satz an.
Bei leerem `tension_source` ist der Prompt **byte-identisch** zu vorher.

**Persistenz** additiv ohne Migration (neue Spalten NULL für Altbestand) —
dasselbe Muster wie bei `sentence_en` am 2026-08-28.

### Register: hyperreal (Birk, korrigiert am 2026-08-29)

Birk hatte am 26.08. „hyperreal von den dreien, unheimlich muss nicht
unbedingt sein" gewählt. **Beim Umbau auf Englisch ging das verloren** —
eingesetzt war die *neutralste* Variante. Daher wirkten die Bilder „ruhig".
Jetzt: extreme Schärfe und Detailtreue (Poren, Fasern, Kratzer, Tiefenschärfe).
Analoges Korn **bewusst entfallen** — es verdeckt genau die Mikrostruktur.

**Merksatz für alle künftigen Register-Änderungen:** Hyperrealismus ist eine
Aussage über **Schärfe**, nicht über Stimmung. Der düstere Ton des alten
Kandidaten kam aus seinen Zusatzwörtern („kühles diffuses Licht, unnatürlich
still"). Stimmung gehört in `mood`, Kohärenz in `tension` — beide aus dem
Material. **Nie ins Register.**

### Gemessene Wirkung (nicht behauptet — an je 5 realen Bildern)

| | vorher | nachher |
|---|---|---|
| Bilder mit Schrift | 5/5 | **2/5**, und dort mit deutschem Wortlaut („HONORAR NEUBAU") |
| Trennwendungen in der Beschreibung | 3 | 1 |
| `mood` über den Tagesverlauf | 3,2,2 | 3,3,2,3,3 (Material identisch!) |

Der `mood`-Sprung war **nicht beabsichtigt**: Sobald Stufe 1 angewiesen ist,
auch die zuversichtliche Seite zu suchen, bewertet sie dasselbe Material
anders. Wer den Wert später kalibriert, muss das wissen.

### Vergleichsbilder (alle mit `.md`-Begleittext: Satz, Prompt-Bausteine deutsch, Werte)

```
out/tagesverlauf/          5 Bilder — der Ausgangsstand (16-Wort-Motiv)
out/tagesverlauf-neu/      3 Bilder — mit Szene + Widerspruch (2 fehlten: Guthaben leer)
out/tagesverlauf-pole/     5 Bilder — beide Pole; hier trat die Zweiteilung auf
out/tagesverlauf-einort/   5 Bilder — ein Ort; hier die leere Tafel
out/tagesverlauf-schrift/  5 Bilder — Schriftverbot aufgehoben; Text wurde englisch
out/tagesverlauf-tendenz/  5 Bilder — AKTUELLER STAND
```

Erzeugt mit `sim/probes/tagesverlauf.py` (fünf Zeitpunkte aus Lauf 19c:
3/10/20/35/60 Personen, 13–163 Begriffe). **≈ 0,70 USD pro Durchlauf.**

---

## 3. Weiteres aus dieser Session

**Repo öffentlich, MIT.** Security-Scan mit `detect-secrets` über Arbeitsstand
**und alle 144 Commits Historie**: nur `sk-test`-Attrappen. Zusätzlich gezielt
auf Telegram-Token, volle Key-Präfixe, PEM geprüft — nichts. Schlüssel kommen
ausschließlich aus `os.environ`; es gibt keinen Pfad in eine Datei.

**Echte Interviewdaten ausgesperrt.** `tests/test_keine_echten_daten_im_repo.py`
(16 Tests) prüft die **Eigenschaft** über `git check-ignore` und den Index —
nicht den Wortlaut von `.gitignore`. Fängt auch `git add -f`, das ein
Ignore-Muster prinzipiell nicht abdeckt. Dabei gefunden: `config.toml` und
`config2.toml` waren **nicht ignoriert** (keine Schlüssel, aber
`telegram_chat_id` und Maschinenadressen). Behoben.

**Ablage echter Daten** (Birk, nach dem KlangNetz-Muster vom 2026-08-04):
Nextcloud `Hermes-Agent/RoboCloud/NewBauhaus-2026-Interviews/`, **neben** dem
Vault, nicht darin — der Vault wandert durch jede Archivierung mit und auf
Mobilgeräte. Transferskript `scripts/sichere-ausstellungstag.sh`
(rsync → rclone copy → **rclone check**), **löscht nie selbst**. Der
Ausstellungsrechner hat bewusst keine Nextcloud-Zugangsdaten.

---

## 4. Was offen ist

### 🔴 Muss Birk tun, vor dem Festival

- **OpenRouter-Guthaben im Auge behalten.** Heute war es bei 59,21/60 USD
  aufgebraucht, dann auf 90 aufgestockt (~30 USD verfügbar). Ein
  Ausstellungstag ≈ 5,55 USD, beide ≈ 11 USD. **Ohne Guthaben erzeugt die
  Station keine Bilder** — sie läuft weiter, produziert Sätze und scheitert
  bei jedem Traum still, das vorherige Bild bleibt stehen (Spec §8, korrektes
  Verhalten). Aufladen: https://openrouter.ai/credits
- **Drei Datenschutz-Punkte** in der Nextcloud-README: Einwilligung der
  Interviewten, Aufbewahrungsdauer, Zugriffskreis. Sind benannt, nicht
  entschieden.

### Inhaltlich offen — Birks Entscheidung am Material

1. **Bildsprache endgültig bestätigen** an `out/tagesverlauf-tendenz/`. Die
   Grundsatzfrage aus Spec §1 bleibt bewusst offen und ist **nicht** still
   zugunsten der Freundlichkeit entschieden worden: Ein durchweg freundliches
   Bild spülte die Kritik weich, ein durchweg düsteres wäre eine Behauptung,
   die das Material nicht deckt. Die Ehrlichkeitsklausel (fehlt eine Seite im
   Material, wird sie **nicht erfunden**) hält beide Richtungen offen.
2. **Leitfrage-Wortlaut** — reine Textentscheidung, steuert nur die Überschrift.
3. **Zitate ja/nein** — Gegenüberstellung in `out/calibrate-quotes.txt`.
4. **40-Bilder-Serie** (≈ 5,55 USD) — braucht Birks OK, **existiert nicht**.
5. **Vergleichsbilder „Weg 2"** — Stimmungstexte vom Modell frei formulieren
   lassen statt fest hinterlegt.

### Vor Ort

6. **Reglerstufe am echten Beamer** (Messung deckt 20–60 ab), **Kamera, Zoom,
   Tempo** (D4).

### Technisch offen, unkritisch

7. **Abgebrochene Sätze** — Erkennung gebaut, Ursache nicht belegt (71 reale
   Aufrufe ohne Reproduktion).
8. **`tension` streut** in einem von vier Fällen.

---

## 5. Arbeitshinweise (haben diese Session Zeit gekostet)

**Ein langer Hintergrundlauf verifiziert den Commit, auf dem er GESTARTET ist.**
Zweimal passiert. Ein 20-Minuten-Lauf sammelt beim Start; jeder Commit während
der Laufzeit ist unsichtbar, das grüne Ergebnis trifft aber danach ein und
liest sich wie Bestätigung. **Der Tell steht im Output selbst:** die Zahlen
gegen `uv run pytest --collect-only -q | tail -1` prüfen. Erwartete Zahl
**vorher** vorhersagen. Lauf mit `git rev-parse --short HEAD` präfixen — eine
Parallel-Session arbeitet im selben Arbeitsbaum.

**Die Testsuite selbst fahren, nicht delegieren.** Claude Codes Bash-Werkzeug
kappt bei ~10 min. Zwei Blöcke funktionieren:
`--ignore=tests/test_prerender.py --ignore=tests/test_projection.py` (~4 min,
758 Tests), dann diese beiden allein (~17 min, 61 Tests).

**Pfadgenau committen** (`git commit -m "…" -- <pfade>`) — Parallel-Session im
selben Arbeitsbaum. Achtung: `-m` muss **vor** `--` stehen.

**Kalibrier- und Renderläufe brauchen:**
```bash
set -a; . ~/.hermes/.env; set +a
export ANTHROPIC_BASE_URL=http://127.0.0.1:28764
export ANTHROPIC_API_KEY=proxy
```
Nur vor dem konkreten Befehl, nicht in die eigene Shell exportieren.

---

## 6. Wo was liegt

| Was | Wo |
|---|---|
| Runbook, kalibrierte Werte, gemeinsamer Start | `docs/operations.md` |
| Spec Kollektivtraum | `docs/superpowers/specs/2026-08-25-kollektivtraum-design.md` |
| Bildvertrag (verifiziert) | `docs/dream-image-contract.md` |
| Bildprompt-Aufbau, fünf Bausteine | Moduldocstring `kg2/imagegen.py` |
| Stufe-1-Prompt (vier Texte) | `_BASE` in `kg2/condense.py` |
| Tagesverlauf-Sonde | `sim/probes/tagesverlauf.py` |
| mood/tension isoliert | `sim/probes/moodgrid.py`, `out/moodgrid/` |
| Registermuster | `out/register1/`, `out/register2-fotoreal/` |
| E2E-Tests | `tests/e2e/`, opt-in `pytest -m e2e tests/e2e` — kostet Geld |
| Startskripte | `scripts/start.sh`, `scripts/start-dream.sh` |
| Datensicherung | `scripts/sichere-ausstellungstag.sh` |
