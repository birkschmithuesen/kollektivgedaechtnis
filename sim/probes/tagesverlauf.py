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
    uv run python sim/probes/tagesverlauf.py [zielordner] [optionen]

Optionen:

``--stufe1 <datei.json>``
    Stufe 1 (Satz, Bildbeschreibung, Widerspruch, mood, tension) wird beim
    ersten Lauf dorthin geschrieben und bei jedem weiteren von dort GELESEN
    statt neu erzeugt. Damit vergleicht ein zweiter Lauf wirklich nur das, was
    man verändert hat. Ohne Cache erzeugt Stufe 1 jedes Mal andere Sätze, und
    zwei Bildreihen unterscheiden sich dann in zwei Variablen gleichzeitig —
    aus so einem Vergleich lässt sich nichts ablesen.

``--modell <name>``
    Anderes Bildmodell als das aus der Config (Modellvergleich). Der Prompt
    bleibt Wort für Wort derselbe.

``--ohne-kanaele``
    Lässt mood und tension WEG: der Prompt besteht dann nur aus Motiv,
    Register und Format. Der Radikaltest — er beantwortet, ob die beiden
    festen Skalen überhaupt etwas am Bild bewirken oder nur Text sind.

Schreibt je Traum eine PNG/JPG und eine gleichnamige `.md` mit dem deutschen
Satz, den englischen Bildprompt-Bausteinen und den Werten — die
Reproduzierbarkeits-Regel aus AGENTS.md (Datei + Begleittext).
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kg2.condense import CondenseResult, condense
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


def begleittext(nummer, personen, tageszeit, ergebnis, begriffe, prompt, bildname, cfg, register, bildmodell, mit_kanaelen) -> str:
    """Die `.md` neben dem Bild — Prompt und Parameter, wie AGENTS.md es für
    jede erzeugte Mediendatei verlangt.

    `register` wird DURCHGEREICHT, nicht hier hinterlegt. Bis 2026-08-30 stand
    hier eine zweite, festverdrahtete Fassung des Registertexts — die noch die
    alte Film/Korn-Variante MIT Schriftverbot zeigte, während längst das
    hyperreale Register ohne Schriftverbot gesendet wurde. Der Begleittext ist
    die einzige Stelle, an der Birk am Material prüft, was ein Bild an Anweisung
    bekommen hat; eine Kopie darin kann von der Wahrheit abdriften und tat es.
    """
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
| **Stimmung** (mood = {ergebnis.mood}) | {MOOD_DE[ergebnis.mood] if mit_kanaelen else "— NICHT GESENDET (Radikaltest ohne Kanäle)"} |
| **Spannung** (tension = {ergebnis.tension}) | {TENSION_DE[ergebnis.tension] if mit_kanaelen else "— NICHT GESENDET (Radikaltest ohne Kanäle)"} |
| **Widerspruch im Material** | {(ergebnis.tension_source or "— (kein Widerspruch im Material)") if mit_kanaelen else "— NICHT GESENDET (hängt am Spannungsblock)"} |
| **Register** (fix, ganzer Tag, englisch wie gesendet) | {register} |
| **Format** (fix) | Seitenverhältnis {cfg.image_aspect_ratio}, Querformat, eine einzelne Fotografie. |

## Woraus er entstanden ist

- **{personen} Personen** hatten zu diesem Zeitpunkt ein Interview gegeben
- **{begriffe} Begriffe** standen im Material
- mood **{ergebnis.mood}**/5, tension **{ergebnis.tension}**/5 — vom Modell aus
  dem Material abgeleitet, nicht gesetzt

## Reproduktion

```
condense_model: {cfg.condense_model} (effort {cfg.condense_effort})
image_model:    {bildmodell}
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

    argumente = sys.argv[1:]
    stufe1_datei: Path | None = None
    modell_wahl: str | None = None
    mit_kanaelen = True
    stellungen: list[str] = []
    i = 0
    while i < len(argumente):
        a = argumente[i]
        if a == "--stufe1":
            stufe1_datei = Path(argumente[i + 1])
            i += 2
        elif a == "--modell":
            modell_wahl = argumente[i + 1]
            i += 2
        elif a == "--ohne-kanaele":
            mit_kanaelen = False
            i += 1
        else:
            stellungen.append(a)
            i += 1

    ziel = Path(stellungen[0] if stellungen else "out/tagesverlauf")
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

    # Stufe 1 aus dem Cache, wenn es ihn gibt: Bildvergleiche taugen nur, wenn
    # das Material zwischen zwei Läufen Wort für Wort dasselbe ist.
    gecacht: dict[str, dict] = {}
    if stufe1_datei and stufe1_datei.exists():
        gecacht = json.loads(stufe1_datei.read_text(encoding="utf-8"))
        print(f"Stufe 1 aus {stufe1_datei} ({len(gecacht)} Einträge)")

    bildmodell = modell_wahl or cfg.image_model
    print(f"Bildmodell: {bildmodell}   Kanäle mood/tension: "
          f"{'ja' if mit_kanaelen else 'NEIN (Radikaltest)'}")

    for nummer, (personen, tageszeit) in enumerate(ZEITPUNKTE, 1):
        teilgraph = prefix_graph(graph, personen)
        material = build_material(teilgraph)
        print(f"\n--- {nummer}/5  {personen} Personen ({tageszeit}) "
              f"— {material.term_count} Begriffe")

        try:
            beginn = time.time()
            schluessel = str(personen)
            if schluessel in gecacht:
                ergebnis = CondenseResult(**gecacht[schluessel])
                print(f"    Satz:  {ergebnis.sentence}   [aus Cache]")
            else:
                ergebnis = condense(llm, material)
                print(f"    Satz:  {ergebnis.sentence}")
                gecacht[schluessel] = asdict(ergebnis)
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
                include_channels=mit_kanaelen,
            )
            daten = render_image(
                prompt,
                model=bildmodell,
                api_key=cfg.openrouter_api_key,
                url=cfg.image_url,
                timeout=cfg.image_timeout_s,
                aspect_ratio=cfg.image_aspect_ratio,
            )
            bild = save_image(daten, ziel / f"{nummer}-{personen:02d}personen")
        except Exception as exc:  # ein Ausfall darf die anderen nicht kosten
            log.error("Traum %s fehlgeschlagen: %s", nummer, exc)
            continue

        begleiter = bild.with_suffix(".md")
        begleiter.write_text(
            begleittext(nummer, personen, tageszeit, ergebnis,
                        material.term_count, prompt, bild.name, cfg, register,
                        bildmodell, mit_kanaelen),
            encoding="utf-8",
        )
        fertig.append((nummer, personen, ergebnis, bild))
        print(f"    Bild:  {bild}  ({bild.stat().st_size // 1024} KB)")

    if stufe1_datei:
        stufe1_datei.parent.mkdir(parents=True, exist_ok=True)
        stufe1_datei.write_text(
            json.dumps(gecacht, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nStufe 1 gesichert -> {stufe1_datei}")

    print(f"\n{len(fertig)} von {len(ZEITPUNKTE)} gerendert -> {ziel.resolve()}")
    for nummer, personen, ergebnis, bild in fertig:
        print(f"  {nummer}. {personen:2d} Personen  mood={ergebnis.mood} "
              f"tension={ergebnis.tension}  {bild.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
