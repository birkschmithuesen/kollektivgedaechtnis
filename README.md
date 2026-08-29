# Kollektivgedächtnis

Zwei Werkzeuge für eine Ausstellungsstation auf dem Festival **NEW bauhaus**
(Weimarhalle, 2.–3. September 2026).

Besucherinnen und Besucher werden in einer Fotobox interviewt. Was sie sagen,
wird laufend transkribiert; ein Sprachmodell zieht daraus konkrete Begriffe.
Über den Tag wächst daraus ein Beziehungsgraph an die Wand — und auf einem
zweiten Schirm ein „Traum": ein Satz und ein Bild, die den ganzen Graphen zu
diesem Zeitpunkt verdichten.

| | |
|---|---|
| **Tool 1 — Kollektivgedächtnis** (`kg/`) | Aufnahme, Extraktion, Graph, Projektion, Operator-Oberfläche |
| **Tool 2 — Kollektivtraum** (`kg2/`) | liest `graph.json`, verdichtet ihn zu Satz + Bild, zeigt beides auf Screen B |

Die beiden hängen **nicht** voneinander ab. Tool 2 kennt Tool 1 ausschließlich
über einen lesenden HTTP-Aufruf auf `graph.json`. Fällt Tool 2 aus, bleibt die
Wand unberührt; fällt Tool 1 aus, zeigt Screen B seinen letzten Traum weiter.

## Wie es läuft

```
Foto (Telegram) ──► Personenknoten erscheint sofort
                         │
Mikrofon ──► STT ──► Transkript ──► „Interview beendet“
                         │
                         ▼
               Begriffsextraktion (LLM)
               Merge-Entscheidung (LLM + Embeddings)
                         │
                         ▼
                   graph.json ──────────────┐
                         │                  │
                         ▼                  ▼
              Wand (Screen A)      Kollektivtraum (Screen B)
              cytoscape,              Satz  (LLM, deutsch + englisch)
              Touchscreen             Bild  (Bildmodell, 16:9)
                                      Verlaufsstreifen des Tages
```

Ein Traum entsteht, **wenn ein Interview fertig verarbeitet ist** — nicht nach
der Uhr, nie während der Stille.

## Schnellstart

Voraussetzung: Python ≥ 3.12 und [uv](https://docs.astral.sh/uv/).

```bash
uv sync

# Tool 1, ohne externe Dienste:
cp config.example.toml config.toml
uv run python -m kg --no-telegram --no-stt        # http://127.0.0.1:8800

# Tool 2, ohne Ausstellungsrechner und ohne Modelle:
cp config2.example.toml config2.toml
uv run python -m kg2 --no-watch                   # http://127.0.0.1:8810
```

Im Betrieb starten beide über ihr jeweiliges Skript
(`scripts/start.sh`, `scripts/start-dream.sh`), das auch die Browser-Fenster
öffnet und jeden Teil nach einem Absturz neu hochfährt. Der vollständige
Ablauf für einen Ausstellungstag steht in **[`docs/operations.md`](docs/operations.md)**.

Geheimnisse stehen **nie** in einer Konfigurationsdatei, sondern
ausschließlich in der Prozess-Umgebung:

```bash
export ANTHROPIC_API_KEY=...      # Extraktion, Merge, Traum-Satz
export OPENROUTER_API_KEY=...     # Embeddings und Bildmodell
export KG_TELEGRAM_TOKEN=...      # Foto-Auslöser
```

## Tests

```bash
uv run pytest                     # ~740 Tests, ohne Netz, ohne Kosten (~20 min)
uv run pytest -m e2e tests/e2e    # Ende-zu-Ende, ECHTE Aufrufe — kostet Geld
```

Die E2E-Tests sind aus der Standardsuite deselektiert, damit kein gewöhnlicher
Lauf Geld kostet; `-m e2e` ist der bewusste Weg hinein. Ohne Schlüssel
überspringen sie sich, statt grün zu werden.

## Dokumentation

| Was | Wo |
|---|---|
| Runbook für den Ausstellungstag, kalibrierte Werte | [`docs/operations.md`](docs/operations.md) |
| Spec Tool 1 | [`docs/superpowers/specs/2026-08-12-kollektivgedaechtnis-design.md`](docs/superpowers/specs/2026-08-12-kollektivgedaechtnis-design.md) |
| Spec Tool 2 | [`docs/superpowers/specs/2026-08-25-kollektivtraum-design.md`](docs/superpowers/specs/2026-08-25-kollektivtraum-design.md) |
| Verträge zu externen Diensten (STT, Bildmodell) | [`docs/stt-contract.md`](docs/stt-contract.md), [`docs/dream-image-contract.md`](docs/dream-image-contract.md) |
| Stand, Entscheidungen, Offenes | `docs/HANDOFF-*.md` (jüngstes zuerst) |

Die Verträge sind die **Autorität**: erst am echten Endpunkt geprüft, dann
dagegen programmiert. Weicht die Wirklichkeit ab, wird der Code angepasst —
nicht das Dokument der Bequemlichkeit halber der Annahme angeglichen.

## Simulation

Die Station lässt sich vollständig ohne Publikum betreiben. `sim/` enthält
60 **synthetische** Interviews (von einem Sprachmodell erzeugt, keine realen
Aussagen) und 16 **generierte** Portraits (keine realen Personen) — damit sind
Wand und Traum reproduzierbar prüfbar, offline und kostenlos.

```bash
uv run python -m sim.seed_graph --help        # Graph ohne Modellaufrufe füllen
uv run python -m sim.dream_calibrate --help   # Kalibrierläufe für Tool 2
```

## Lizenz

[MIT](LICENSE) — Copyright (c) 2026 Birk Schmithüsen.

Das gilt auch für das Material unter `sim/`: die 60 Interviews sind von einem
Sprachmodell erzeugt, die 16 Portraits von einem Bildmodell — es sind keine
realen Personen und keine realen Aussagen darin.
