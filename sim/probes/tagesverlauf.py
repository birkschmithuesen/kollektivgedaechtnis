"""Fünf Träume eines Tagesverlaufs — Satz und Bild, zum Ansehen nebeneinander.

Ad-hoc-Sonde, 2026-08-29, für Birks Entscheidung zur Bildsprache
(Handoff-Punkt 6). Nicht Teil der Station: `sim/dream_calibrate.py` ist das
gepflegte Kalibrierwerkzeug, `sim/dream_register.py` das für Registerwahlen.

Der Unterschied zu `sim/probes/moodgrid.py`: Dort variieren mood/tension bei
EINEM festen Satz — das zeigt den Bildkanal isoliert. Hier läuft die echte
Kette über wachsendes Material: Stufe 1 verdichtet den Graphen zu einem Satz
und leitet mood/tension selbst ab, Stufe 2 rendert daraus. Das ist, was am
Ausstellungstag tatsächlich passiert.

Fünf Zeitpunkte aus dem realen Lauf 19c (`sim/data/graph-19c.json`), von der
leeren Halle bis zum vollen Tag. Jeder Traum kostet einen Anthropic-Aufruf
(Satz) und ein Bild (≈ 0,139 USD).

    export ANTHROPIC_BASE_URL=http://127.0.0.1:28764 ANTHROPIC_API_KEY=proxy
    uv run python sim/probes/tagesverlauf.py [zielordner]

Schreibt je Traum eine PNG/JPG und eine gleichnamige `.md` mit dem deutschen
Satz, den englischen Bildprompt-Bausteinen und den Werten — die
Reproduzierbarkeits-Regel aus AGENTS.md (Datei + Begleittext).
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kg2.condense import condense
from kg2.config import load_dream_config
from kg2.imagegen import (
    MOOD_LIGHT,
    TENSION_COHERENCE,
    build_image_prompt,
    render_image,
    save_image,
)
from kg2.weighting import build_material
from sim.dream_calibrate import FIXTURE, prefix_graph

log = logging.getLogger("tagesverlauf")

#: Fünf Zeitpunkte eines Ausstellungstags. Nicht gleichmäßig verteilt: die
#: frühen Schritte liegen dichter, weil sich der Graph dort am stärksten
#: verändert — bei 3 Personen entscheidet jedes neue Interview den Satz mit,
#: bei 60 verschiebt es nur noch Gewichte.
ZEITPUNKTE = [
    (3, "früher Vormittag, die ersten drei Gespräche"),
    (10, "später Vormittag"),
    (20, "Mittag"),
    (35, "Nachmittag"),
    (60, "Ende des Tages, alle Interviews"),
]

#: Die deutschen Entsprechungen der fixen englischen Prompt-Bausteine. NUR für
#: die Anzeige — der Prompt selbst bleibt englisch (Googles Doku für dieses
#: Modell verlangt zusammenhängende englische Prosa, kg2/imagegen.py). Hier
#: übersetzt, damit Birk lesen kann, was das Bild an Anweisung bekommen hat,
#: ohne den englischen Block entziffern zu müssen.
MOOD_DE = {
    1: "Das Licht ist kalt und flach, kommt aus keiner bestimmten Richtung, "
       "graublaue Farben im ganzen Bild.",
    2: "Das Licht ist kühl und niedrig, gedämpfte, leicht entsättigte Farben "
       "und weiche graue Schatten.",
    3: "Das Licht ist neutral und gleichmäßig, ausgewogene, gewöhnliche Farben, "
       "ein schlichter, sachlicher Ton.",
    4: "Das Licht ist warm und sanft, weiche goldene Farben, ein mildes, "
       "einladendes Leuchten.",
    5: "Das Licht ist warm und tief, kommt von einer Seite, lange weiche "
       "Schatten, Farben laufen ins Bernsteinfarbene.",
}

TENSION_DE = {
    1: "Alles im Bild gehört zusammen, ein ruhiges, stimmiges Ganzes.",
    2: "Die Szene ist stimmig, mit nur einer leisen Ahnung, dass etwas nicht "
       "ganz am Platz ist.",
    3: "Zwei verschiedene Qualitäten stehen nebeneinander im Bild, jede behält "
       "ihren eigenen Charakter.",
    4: "Zwei klar unvereinbare Qualitäten teilen sich dasselbe Bild, beide "
       "vollständig real, keine dominiert.",
    5: "Das Bild enthält etwas physikalisch Unmögliches, als wären zwei "
       "Wirklichkeiten zu einer verschmolzen.",
}


def begleittext(nummer, personen, tageszeit, ergebnis, begriffe, prompt, bildname, cfg) -> str:
    """Die `.md` neben dem Bild — Prompt und Parameter, wie AGENTS.md es für
    jede erzeugte Mediendatei verlangt."""
    return f"""# Traum {nummer} — {tageszeit}

![{bildname}]({bildname})

## Der Satz auf der Wand

> **{ergebnis.sentence}**

## Was das Bild als Anweisung bekommen hat

Der Bildprompt ist englisch (Googles Doku für dieses Modell verlangt
zusammenhängende englische Prosa). Hier die Bausteine, deutsch:

| Baustein | Inhalt |
|---|---|
| **Motiv** (variabel) | {ergebnis.image_description or ergebnis.sentence_en} |
| **Wörtliche Übersetzung** (nur Archiv) | {ergebnis.sentence_en} |
| **Stimmung** (mood = {ergebnis.mood}) | {MOOD_DE[ergebnis.mood]} |
| **Spannung** (tension = {ergebnis.tension}) | {TENSION_DE[ergebnis.tension]} |
| **Widerspruch im Material** | {ergebnis.tension_source or "— (kein Widerspruch im Material)"} |
| **Register** (fix, ganzer Tag) | Eine Fotografie, auf echtem Film oder echtem Sensor aufgenommen, mit dem Korn, dem Tonwertumfang und den kleinen Unvollkommenheiten einer tatsächlichen Belichtung. Auf Augenhöhe fotografiert, normale Brennweite, natürliche Schärfentiefe. Jede Fläche im Bild ist frei von Schrift, ohne Schilder, Beschriftungen, Lettern. Ein einzelnes fotografisches Bild, ganz und unbeschnitten. |
| **Format** (fix) | Seitenverhältnis {cfg.image_aspect_ratio}, Querformat, eine einzelne Fotografie. |

## Woraus er entstanden ist

- **{personen} Personen** hatten zu diesem Zeitpunkt ein Interview gegeben
- **{begriffe} Begriffe** standen im Material
- mood **{ergebnis.mood}**/5, tension **{ergebnis.tension}**/5 — vom Modell aus
  dem Material abgeleitet, nicht gesetzt

## Reproduktion

```
condense_model: {cfg.condense_model} (effort {cfg.condense_effort})
image_model:    {cfg.image_model}
graph:          sim/data/graph-19c.json, erste {personen} Personen
```

<details>
<summary>Englischer Bildprompt, wortwörtlich wie gesendet</summary>

```
{prompt}
```
</details>
"""


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ziel = Path(sys.argv[1] if len(sys.argv) > 1 else "out/tagesverlauf")
    ziel.mkdir(parents=True, exist_ok=True)

    cfg = load_dream_config(None)
    if not cfg.anthropic_api_key:
        print("ANTHROPIC_API_KEY fehlt (oder ANTHROPIC_BASE_URL für den Proxy)", file=sys.stderr)
        return 1
    if not cfg.openrouter_api_key:
        print("OPENROUTER_API_KEY fehlt", file=sys.stderr)
        return 1

    # Das Register aus der Beispielconfig, nicht aus dem Default der
    # Dataclass — das ist der Wortlaut, der am Ausstellungstag gilt.
    import tomllib

    register = tomllib.loads(
        (Path(__file__).resolve().parents[2] / "config2.example.toml").read_text(
            encoding="utf-8"
        )
    )["visual_register"]

    from kg.llm import LLMClient

    llm = LLMClient(
        model=cfg.condense_model,
        effort=cfg.condense_effort,
        max_tokens=cfg.condense_max_tokens,
        api_key=cfg.anthropic_api_key,
    )

    graph = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fertig = []

    for nummer, (personen, tageszeit) in enumerate(ZEITPUNKTE, 1):
        teilgraph = prefix_graph(graph, personen)
        material = build_material(teilgraph)
        print(f"\n--- {nummer}/5  {personen} Personen ({tageszeit}) "
              f"— {material.term_count} Begriffe")

        try:
            beginn = time.time()
            ergebnis = condense(llm, material)
            print(f"    Satz:  {ergebnis.sentence}")
            print(f"    mood={ergebnis.mood} tension={ergebnis.tension} "
                  f"({time.time() - beginn:.0f}s)")

            prompt = build_image_prompt(
                ergebnis.image_description,
                sentence_en=ergebnis.sentence_en,
                sentence=ergebnis.sentence,
                tension_source=ergebnis.tension_source,
                mood=ergebnis.mood,
                tension=ergebnis.tension,
                register=register,
                aspect_ratio=cfg.image_aspect_ratio,
            )
            daten = render_image(
                prompt,
                model=cfg.image_model,
                api_key=cfg.openrouter_api_key,
                url=cfg.image_url,
                timeout=cfg.image_timeout_s,
            )
            bild = save_image(daten, ziel / f"{nummer}-{personen:02d}personen")
        except Exception as exc:  # ein Ausfall darf die anderen nicht kosten
            log.error("Traum %s fehlgeschlagen: %s", nummer, exc)
            continue

        begleiter = bild.with_suffix(".md")
        begleiter.write_text(
            begleittext(nummer, personen, tageszeit, ergebnis,
                        material.term_count, prompt, bild.name, cfg),
            encoding="utf-8",
        )
        fertig.append((nummer, personen, ergebnis, bild))
        print(f"    Bild:  {bild}  ({bild.stat().st_size // 1024} KB)")

    print(f"\n{len(fertig)} von {len(ZEITPUNKTE)} gerendert -> {ziel.resolve()}")
    for nummer, personen, ergebnis, bild in fertig:
        print(f"  {nummer}. {personen:2d} Personen  mood={ergebnis.mood} "
              f"tension={ergebnis.tension}  {bild.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
