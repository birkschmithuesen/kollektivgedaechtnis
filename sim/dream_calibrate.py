"""Spec §10's values, produced by the simulation and not guessed.

The same discipline Tool 1's density values were produced under (T1§14.4 and
run-19c): run it, read the output, write the answer into `docs/operations.md`.

Six sub-commands (`questions` and `contradiction` were retired 2026-08-28
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
* `tension`— the `mood` run above (2026-08-28) confounded the two axes: its
              four cases moved sentiment and disagreement together
              (positive+unified, negative+conflicted), so a low tension on the
              "negative, conflicted" case could not be told apart from
              tension simply tracking mood. This run decouples the axes —
              four cases crossing positive/negative sentiment with
              unified/contradictory content — and asks the actual question:
              does tension react to contradiction, or does it just ride along
              with mood? See `TENSION_CASES` below and the task brief,
              `.task-tension-kalibrierung.md` (2026-08-28).
* `quotes` — a side-by-side with/without quotes in the material (spec §5.1's
              revised default is without), so the cost of leaving them out is
              visible before it is final.
* `recency`— a side-by-side with/without the „Zuletzt gesagt" block
              (`kg2.weighting.RECENT_TERMS`, added 2026-08-29, task brief
              `.task-recency.md`): does the block actually pull newer terms
              into the sentence, or does the weighted block drown it out
              regardless?
* `floor`  — arithmetic, no LLM. The floor is a question about the day's
              cadence, not about the model.

**This module recommends nothing** (standing rule, 2026-08-25). Reading the
sentences cold is the point.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from kg2.condense import condense
from kg2.weighting import RECENT_TERMS, build_material, select_marginal, select_recent

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


@dataclass(frozen=True)
class TensionCase:
    """One cell of the 2x2 grid that decouples sentiment from disagreement.

    `mood_axis` and `tension_axis` are the case's INTENDED position on each
    axis — not a prediction of what stage 1 will return, which is exactly
    what this run checks.
    """

    label: str
    mood_axis: str  # "positiv" | "negativ"
    tension_axis: str  # "einig" | "zerstritten"
    terms: list[str]


#: The 2x2 grid the old `mood` run's fourth case (`SYNTHETIC_CASES`,
#: "eindeutig negativ, zerstritten") conflated: it moved sentiment and
#: disagreement together, so its low tension reading could not be told apart
#: from tension simply tracking mood. Built fresh here so the two axes vary
#: independently (task brief, 2026-08-28):
#:
#: * A (positiv, einig) — optimistic terms that reinforce each other.
#: * B (positiv, zerstritten) — the case that was missing entirely: three
#:   pairs of optimistic terms, each pair mutually exclusive (both cannot be
#:   true of the same yard/house at once).
#: * C (negativ, einig) — the OLD "zerstritten" case, kept verbatim and
#:   relabelled as what it actually is: uniformly negative terms that all
#:   point the same direction, no real contradiction among them.
#: * D (negativ, zerstritten) — three pairs of negative terms, each pair
#:   mutually exclusive, mirroring B's construction on the negative side.
#:
#: Every pair in B and D is said by the SAME synthetic persons as every other
#: term (`_synthetic_graph` below), so both sides of a contradiction are
#: mentioned equally often — a 5-vs-1 "contradiction" would not be one.
TENSION_CASES: tuple[TensionCase, ...] = (
    TensionCase(
        "positiv, einig (A)",
        "positiv",
        "einig",
        [
            "Gemeinsam sanierte Fassaden",
            "Neue Spielplätze für alle Kinder",
            "Vertrauensvolle Zusammenarbeit mit der Verwaltung",
            "Blühende Gemeinschaftsgärten",
            "Stabile, bezahlbare Mieten",
            "Offene Nachbarschaftstreffen",
        ],
    ),
    TensionCase(
        "positiv, zerstritten (B)",
        "positiv",
        "zerstritten",
        [
            "Glänzende Neubauten ersetzen jedes alte Haus",
            "Jedes historische Haus bleibt für immer erhalten",
            "Hohe Wohntürme schaffen Platz für alle",
            "Niedrige Häuser bewahren die vertraute Höhe",
            "Autofreie Höfe schenken den Kindern die Straße zurück",
            "Ein eigener Parkplatz sichert jeder Familie ihre Mobilität",
        ],
    ),
    TensionCase(
        "negativ, einig (C)",
        "negativ",
        "einig",
        [
            "Drohende Zwangsräumungen",
            "Schimmel in den Wänden",
            "Offener Streit zwischen Eigentümern",
            "Abgesperrte, verrottende Baustellen",
            "Tiefes Misstrauen gegenüber der Verwaltung",
            "Abgesagte Sanierungsversprechen",
        ],
    ),
    TensionCase(
        "negativ, zerstritten (D)",
        "negativ",
        "zerstritten",
        [
            "Die Bagger reißen jedes marode Haus sofort ab",
            "Jedes marode Haus verrottet einfach ungenutzt weiter",
            "Die Mieten steigen jeden Monat unaufhaltsam weiter",
            "Die Wohnungen stehen inzwischen komplett leer",
            "Jede Beschwerde wird im Amt sofort abgewiesen",
            "Niemand im Amt ist überhaupt noch erreichbar",
        ],
    ),
)


@dataclass(frozen=True)
class TensionRun:
    """One `condense` call's outcome, tagged with the case it came from."""

    case: str
    mood_axis: str
    tension_axis: str
    mood: int
    tension: int


def tension_axis_summary(runs: Iterable[TensionRun]) -> dict:
    """The actual question (task brief): does `tension` react to
    contradiction, or does it just ride along with `mood`? Arithmetic only,
    no LLM — kept separate from `run_tension` so it can be unit-tested on
    hand-built runs.
    """
    runs = list(runs)

    def avg(values: list[int]) -> float:
        return sum(values) / len(values) if values else 0.0

    einig = [r.tension for r in runs if r.tension_axis == "einig"]
    zerstritten = [r.tension for r in runs if r.tension_axis == "zerstritten"]
    positiv = [r.tension for r in runs if r.mood_axis == "positiv"]
    negativ = [r.tension for r in runs if r.mood_axis == "negativ"]

    spread: dict[str, tuple[int, int]] = {}
    for case in dict.fromkeys(r.case for r in runs):
        values = [r.tension for r in runs if r.case == case]
        spread[case] = (min(values), max(values))

    return {
        "einig_avg": avg(einig),
        "zerstritten_avg": avg(zerstritten),
        "tension_axis_gap": avg(zerstritten) - avg(einig),
        "positiv_avg": avg(positiv),
        "negativ_avg": avg(negativ),
        "mood_axis_gap": avg(negativ) - avg(positiv),
        "spread_per_case": spread,
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


def run_tension(graph: dict, cfg) -> None:
    """Decoupled from `run_mood` (task brief, 2026-08-28): that run's four
    cases moved sentiment and disagreement together, so a low `tension` on
    its "negative, conflicted" case could not be told apart from `tension`
    simply tracking `mood`. This run crosses the two axes independently
    (`TENSION_CASES`) and answers the actual question with numbers, not a
    recommendation (standing rule, see module docstring).
    """
    llm = _llm(cfg)
    print(
        "Vier gebaute Fälle, Stimmung und Widersprüchlichkeit unabhängig "
        "voneinander (2x2), je dreimal durch Stufe 1 geschickt. Prüft, ob "
        "`tension` auf Widerspruch reagiert oder nur mit `mood` mitläuft.\n"
    )

    runs: list[TensionRun] = []
    for case in TENSION_CASES:
        material = build_material(_synthetic_graph(case.terms))
        print(f"=== {case.label}")
        for _ in range(3):
            try:
                result = condense(llm, material)
                print(f"  mood={result.mood} tension={result.tension} — {result.sentence}")
                runs.append(
                    TensionRun(
                        case=case.label,
                        mood_axis=case.mood_axis,
                        tension_axis=case.tension_axis,
                        mood=result.mood,
                        tension=result.tension,
                    )
                )
            except Exception as exc:
                print(f"  FEHLER — {exc}")
        print()

    if runs:
        summary = tension_axis_summary(runs)
        print("=== Auswertung: reagiert tension auf Widerspruch oder auf Stimmung?\n")
        print(
            f"  tension, einige Fälle (A+C):        {summary['einig_avg']:.2f}\n"
            f"  tension, zerstrittene Fälle (B+D):   {summary['zerstritten_avg']:.2f}\n"
            f"  Differenz (zerstritten − einig):     {summary['tension_axis_gap']:+.2f}\n"
        )
        print(
            f"  tension, positive Fälle (A+B):       {summary['positiv_avg']:.2f}\n"
            f"  tension, negative Fälle (C+D):        {summary['negativ_avg']:.2f}\n"
            f"  Differenz (negativ − positiv):        {summary['mood_axis_gap']:+.2f}\n"
        )
        print("  Streuung je Fall über die drei Wiederholungen (min–max):")
        for label, (low, high) in summary["spread_per_case"].items():
            print(f"    {label}: {low}–{high}")
        print()

    print(
        "Zur Einordnung: derselbe reale Graph in vier Größen, je dreimal "
        "(Vorbefund docs/operations.md: tension eng bei 3/4/4/4, mood bei "
        "3/2/3/2).\n"
    )
    for size in SIZES:
        material = build_material(prefix_graph(graph, size))
        print(f"=== {size} Menschen")
        for _ in range(3):
            try:
                result = condense(llm, material)
                print(f"  mood={result.mood} tension={result.tension} — {result.sentence}")
            except Exception as exc:
                print(f"  FEHLER — {exc}")
        print()


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


def run_recency(graph: dict, cfg) -> None:
    """Side-by-side with/without the „Zuletzt gesagt" block — analogous to
    `run_quotes` above. `recent_terms=0` switches the block off entirely
    (kg2/weighting.py::render_material); `RECENT_TERMS` is the module
    default. The question is not "does the sentence change" (it almost always
    will, stage 1 is not deterministic) but whether the RECENT terms printed
    below actually turn up in the "mit" sentence and not in the "ohne" one."""
    llm = _llm(cfg)
    print(
        "Je Graphgröße ein Satzpaar: ohne Aktualitätsblock und mit „Zuletzt "
        "gesagt' (kg2.weighting.RECENT_TERMS jüngste Begriffe, aus geteilten "
        "und einmaligen) im selben Material.\n"
    )
    for size in SIZES:
        material = build_material(prefix_graph(graph, size))
        recent = select_recent(material)
        print(
            f"=== {size} Menschen, jüngste Begriffe: "
            + (", ".join(w.label for w in recent) if recent else "keine")
        )
        for recent_terms in (0, RECENT_TERMS):
            label = "mit Aktualitätsblock " if recent_terms else "ohne Aktualitätsblock"
            try:
                result = condense(llm, material, recent_terms=recent_terms)
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
    parser.add_argument("mode", choices=("terms", "mood", "tension", "quotes", "recency", "floor"))
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
    elif args.mode == "tension":
        run_tension(graph, cfg)
    elif args.mode == "quotes":
        run_quotes(graph, cfg)
    else:
        run_recency(graph, cfg)


if __name__ == "__main__":
    main()
