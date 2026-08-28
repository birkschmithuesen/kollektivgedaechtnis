"""Spec §10's values, produced by the simulation and not guessed.

The same discipline Tool 1's density values were produced under (T1§14.4 and
run-19c): run it, read the output, write the answer into `docs/operations.md`.

Four sub-commands (`questions` and `contradiction` were retired 2026-08-28
along with the guiding-question prompt slot and the contradiction clause —
see kg2/condense.py):

* `terms`  — the gliding single-mention formula's two constants
              (`kg2.weighting.SINGLE_MENTION_BUDGET`,
              `SHARED_TERMS_SATURATION`): several N/X combinations per graph
              size, sentences printed alongside how many shared/single-mention
              terms actually made it into the prompt. BIRK PICKS.
* `mood`   — whether stage 1's `mood`/`tension` scale (kg2/condense.py) is
              actually used across its 1-5 range on built extremes, and
              whether real material varies it at all.
* `quotes` — a side-by-side with/without quotes in the material (spec §5.1's
              revised default is without), so the cost of leaving them out is
              visible before it is final.
* `floor`  — arithmetic, no LLM. The floor is a question about the day's
              cadence, not about the model.

**This module recommends nothing** (standing rule, 2026-08-25). Reading the
sentences cold is the point.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kg2.condense import condense
from kg2.weighting import build_material, select_marginal

FIXTURE = Path(__file__).resolve().parent / "data" / "graph-19c.json"

#: Empty morning, mid-morning, afternoon, end of the day.
SIZES = (3, 10, 30, 60)

#: Candidate values for kg2.weighting.SINGLE_MENTION_BUDGET (N) and
#: SHARED_TERMS_SATURATION (X). Not a claim that these are the right ones —
#: a starting spread around the module's provisional defaults (20, 25).
TERMS_N = (10, 20, 30)
TERMS_X = (15, 25, 40)

#: Four BUILT extremes, not drawn from real interviews — deliberate (task
#: brief, 2026-08-28): this tests whether the 1-5 scale is used at all, not
#: what any real person said. Terms are invented outright and are each said
#: by every synthetic person, so every one of them is "shared" and nothing
#: about the gliding single-mention formula interferes with the reading.
SYNTHETIC_CASES: dict[str, list[str]] = {
    "eindeutig positiv, einig": [
        "Gemeinsam gepflegte Gärten",
        "Nachbarschaftshilfe beim Umbau",
        "Frisch renovierte Fassaden",
        "Kinderlachen im Innenhof",
        "Vertrauen in die Bauverwaltung",
        "Sonnige, offene Dachterrassen",
    ],
    "eher positiv, leichte Spannung": [
        "Neue Balkone für alle Wohnungen",
        "Steigende Mieten nach der Sanierung",
        "Mehr Grün auf dem Hof",
        "Lange Wartezeiten für Fördermittel",
        "Freundliche neue Nachbarschaft",
    ],
    "eher negativ, leichte Hoffnung": [
        "Rissige Fassaden seit Jahren",
        "Erste Zusagen für Fördergelder",
        "Leerstehende Erdgeschosse",
        "Ein neuer Nachbarschaftsverein",
        "Unklare Zuständigkeiten im Amt",
    ],
    "eindeutig negativ, zerstritten": [
        "Drohende Zwangsräumungen",
        "Schimmel in den Wänden",
        "Offener Streit zwischen Eigentümern",
        "Abgesperrte, verrottende Baustellen",
        "Tiefes Misstrauen gegenüber der Verwaltung",
        "Abgesagte Sanierungsversprechen",
    ],
}


def prefix_graph(graph: dict, persons: int) -> dict:
    """The graph as it stood after the first `persons` interviews.

    Derived from the real run-19c artefact rather than invented: the first N
    persons by creation time, the edges that touch them, the terms that survive,
    and mentions recomputed for the smaller graph.

    Honest about its one limitation: Tool 1's merge judge renames a node when it
    absorbs a label, and this reconstruction carries the FINAL labels back into
    an earlier state. So the terms are what those interviews really produced;
    their wording is the wording they ended the day with. For calibrating a
    threshold and a question that is the right trade — the alternative is 60
    live LLM runs per candidate.
    """
    people = sorted(
        (n for n in graph["nodes"] if n.get("type") == "person"),
        key=lambda n: (n.get("created_at", 0.0), n["id"]),
    )[:persons]
    kept = {n["id"] for n in people}

    edges = [e for e in graph["edges"] if e["source"] in kept]
    counts: dict[str, int] = {}
    for edge in edges:
        counts[edge["target"]] = counts.get(edge["target"], 0) + 1

    terms = [
        {**n, "mentions": counts[n["id"]]}
        for n in graph["nodes"]
        if n.get("type") == "term" and n["id"] in counts
    ]

    return {
        "version": graph["version"],
        "generated_at": graph["generated_at"],
        "min_mentions": graph["min_mentions"],
        "nodes": list(people) + terms,
        "edges": edges,
        "quotes": [q for q in graph["quotes"] if q.get("person_id") in kept],
    }


def _synthetic_graph(terms: list[str], persons: int = 6) -> dict:
    """Every synthetic person "mentions" every term, so each term is shared —
    the gliding single-mention formula (kg2.weighting) never trims this
    down and the mood/tension reading is not confused by missing detail."""
    person_nodes = [
        {"id": f"sp{i}", "type": "person", "created_at": float(i), "hidden": False}
        for i in range(persons)
    ]
    term_nodes = [
        {"id": f"st{i}", "type": "term", "label": label, "created_at": 1000.0 + i,
         "hidden": False}
        for i, label in enumerate(terms)
    ]
    edges = [
        {"id": f"se{i}-{j}", "source": f"sp{i}", "target": f"st{j}"}
        for i in range(persons)
        for j in range(len(terms))
    ]
    return {
        "version": 1, "generated_at": 1000.0, "min_mentions": 1,
        "nodes": person_nodes + term_nodes, "edges": edges, "quotes": [],
    }


def floor_table(interview_count: int, day_seconds: float, floors) -> list[dict]:
    """How many dreams each candidate floor would have produced.

    No model involved: at an even cadence, a floor only binds when it is longer
    than the gap between interviews, and then it merges whole runs of them into
    one dream. `cadence_s` is reported because it, not the floor, is what
    decides the answer — a table that hid it would read as a fact about the
    floor when it is a fact about the day.
    """
    rows = []
    cadence = day_seconds / interview_count if interview_count else 0.0
    for floor in floors:
        if not interview_count:
            rows.append({"min_interval_s": floor, "cadence_s": cadence,
                         "dreams": 0, "collapsed": 0, "per_dream": 0.0})
            continue
        dreams = 0
        last: float | None = None
        for index in range(interview_count):
            at = index * cadence
            if last is None or at - last >= floor:
                dreams += 1
                last = at
        rows.append(
            {
                "min_interval_s": floor,
                "cadence_s": cadence,
                "dreams": dreams,
                "collapsed": interview_count - dreams,
                "per_dream": round(interview_count / dreams, 2) if dreams else 0.0,
            }
        )
    return rows


def _llm(cfg):
    from kg.llm import LLMClient  # pure wrapper — permitted by spec §3

    return LLMClient(
        model=cfg.condense_model,
        effort=cfg.condense_effort,
        max_tokens=cfg.condense_max_tokens,
        api_key=cfg.anthropic_api_key,
    )


def run_terms(graph: dict, cfg) -> None:
    llm = _llm(cfg)
    print(
        "Vier Graphgrößen, je mehrere N/X-Kombinationen (Einmal-Nennungs-Budget "
        "/ Sättigung der geteilten Begriffe, kg2.weighting.SINGLE_MENTION_BUDGET "
        "/ SHARED_TERMS_SATURATION). Geteilte Begriffe sind IMMER alle drin.\n"
    )
    for size in SIZES:
        material = build_material(prefix_graph(graph, size))
        print(
            f"=== {size} Menschen, {len(material.shared)} geteilte, "
            f"{len(material.marginal)} einmalige Begriffe verfügbar"
        )
        for n in TERMS_N:
            for x in TERMS_X:
                selected = select_marginal(material, budget=n, saturation=x)
                try:
                    result = condense(
                        llm, material, single_mention_budget=n, shared_terms_saturation=x
                    )
                    print(
                        f"  N={n:>2} X={x:>2}: {len(material.shared)} geteilte + "
                        f"{len(selected)} einmalige im Prompt — {result.sentence}"
                    )
                except Exception as exc:
                    print(f"  N={n:>2} X={x:>2}: FEHLER — {exc}")
        print()
    print("Gewählte N/X als SINGLE_MENTION_BUDGET/SHARED_TERMS_SATURATION in kg2/weighting.py eintragen.")


def run_mood(graph: dict, cfg) -> None:
    llm = _llm(cfg)
    print(
        "Vier gebaute Extreme (frei erfundenes Material, keine echten "
        "Interviews), je dreimal durch Stufe 1 geschickt. Prüft, ob das "
        "1-5-Spektrum überhaupt ausgeschöpft wird.\n"
    )
    for label, terms in SYNTHETIC_CASES.items():
        material = build_material(_synthetic_graph(terms))
        print(f"=== {label}")
        for _ in range(3):
            try:
                result = condense(llm, material)
                print(f"  mood={result.mood} tension={result.tension} — {result.sentence}")
            except Exception as exc:
                print(f"  FEHLER — {exc}")
        print()

    print(
        "Zur Einordnung: derselbe reale Graph in vier Größen. Bekäme er immer "
        "denselben Wert, wäre die Skala zwar korrekt, aber am echten Material "
        "nutzlos.\n"
    )
    for size in SIZES:
        material = build_material(prefix_graph(graph, size))
        try:
            result = condense(llm, material)
            print(f"  {size:>2} Menschen: mood={result.mood} tension={result.tension} — {result.sentence}")
        except Exception as exc:
            print(f"  {size:>2} Menschen: FEHLER — {exc}")


def run_quotes(graph: dict, cfg) -> None:
    llm = _llm(cfg)
    print(
        "Je Graphgröße ein Satzpaar: ohne Zitate (Standard seit 2026-08-28) und "
        "mit Zitaten (include_quotes=True) im selben Material.\n"
    )
    for size in SIZES:
        material = build_material(prefix_graph(graph, size))
        print(f"=== {size} Menschen, {len(material.quotes)} Zitate verfügbar")
        for include_quotes in (False, True):
            label = "mit Zitaten " if include_quotes else "ohne Zitate"
            try:
                result = condense(llm, material, include_quotes=include_quotes)
                print(f"  {label}: {result.sentence}")
            except Exception as exc:
                print(f"  {label}: FEHLER — {exc}")
        print()


def run_floor(args) -> None:
    rows = floor_table(args.interviews, args.hours * 3600, tuple(args.floors))
    print(
        f"{args.interviews} Interviews über {args.hours} h "
        f"= alle {rows[0]['cadence_s']:.0f} s eines.\n"
    )
    print(f"{'min_interval_s':>15} {'Träume':>8} {'zusammengefasst':>16} {'Interviews/Traum':>18}")
    for row in rows:
        print(
            f"{row['min_interval_s']:>15} {row['dreams']:>8} "
            f"{row['collapsed']:>16} {row['per_dream']:>18}"
        )
    print(
        "\nEin Boden unterhalb der Taktung greift nie. Gewählten Wert als "
        "`min_interval_s` in config2.toml eintragen."
    )


def main() -> None:
    from kg2.config import load_dream_config

    parser = argparse.ArgumentParser(prog="sim.dream_calibrate")
    parser.add_argument("mode", choices=("terms", "mood", "quotes", "floor"))
    parser.add_argument("--graph", default=str(FIXTURE))
    parser.add_argument("--config", default=None)
    parser.add_argument("--interviews", type=int, default=60)
    parser.add_argument("--hours", type=float, default=8.0)
    parser.add_argument("--floors", type=int, nargs="+", default=[120, 240, 360, 480, 900])
    args = parser.parse_args()

    if args.mode == "floor":
        run_floor(args)
        return

    cfg = load_dream_config(Path(args.config) if args.config else None)
    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    if args.mode == "terms":
        run_terms(graph, cfg)
    elif args.mode == "mood":
        run_mood(graph, cfg)
    else:
        run_quotes(graph, cfg)


if __name__ == "__main__":
    main()
