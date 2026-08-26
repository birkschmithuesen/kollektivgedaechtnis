"""Spec §10's four values, produced by the simulation and not guessed.

The same discipline Tool 1's density values were produced under (T1§14.4, run
19c): run it, read the output, write the answer into `docs/operations.md`.

Three sub-commands, because the three values need different evidence:

* `questions`    — 4 wordings × 4 graph sizes, sentences printed. BIRK PICKS.
* `contradiction`— each size with and without the clause, side by side. The
                   threshold is where the clause stops inventing an opposition.
* `floor`        — arithmetic, no LLM. The floor is a question about the day's
                   cadence, not about the model.

**This module recommends nothing** (standing rule, 2026-08-25). Reading the
sentences cold is the point.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kg2.condense import condense
from kg2.weighting import build_material, contradiction_enabled

FIXTURE = Path(__file__).resolve().parent / "data" / "graph-19c.json"

#: Empty morning, mid-morning, afternoon, end of the day.
SIZES = (3, 10, 30, 60)

#: Candidate wordings. Every one must carry all three interview themes — future
#: of building, AI in building, new forms of living together (spec §10,
#: brainstorm §7). A question naming one material or one technology cannot, and
#: is therefore not a candidate.
#:
#: Order is arbitrary and means nothing. None is marked.
QUESTIONS = (
    "Wie leben und bauen wir in zehn Jahren?",
    "Wie wollen wir in zehn Jahren zusammen wohnen und bauen?",
    "Was soll in zehn Jahren anders sein an dem Ort, an dem Sie leben?",
    "Wer baut in zehn Jahren unsere Häuser, und wer entscheidet darüber?",
)


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


def run_questions(graph: dict, cfg) -> None:
    llm = _llm(cfg)
    print("Vier Formulierungen, vier Graphgrößen. Nur die Frage ändert sich.\n")
    for question in QUESTIONS:
        print(f"=== {question}")
        for size in SIZES:
            material = build_material(prefix_graph(graph, size))
            enabled = contradiction_enabled(material, cfg.contradiction_min_persons)
            try:
                result = condense(llm, material, question, enabled)
                print(f"  {size:>2} Menschen: {result.sentence}")
            except Exception as exc:
                print(f"  {size:>2} Menschen: FEHLER — {exc}")
        print()
    # No recommendation (standing rule): reading them cold is the point.
    print("Gewählte Formulierung als `guiding_question` in config2.toml eintragen.")


def run_contradiction(graph: dict, cfg) -> None:
    llm = _llm(cfg)
    print(
        "Jede Größe zweimal: einmal mit der Widerspruchs-Anweisung, einmal ohne.\n"
        "Gesucht ist die Größe, ab der der Widerspruch im Material WIRKLICH da "
        "ist statt erfunden zu werden.\n"
    )
    for size in SIZES:
        material = build_material(prefix_graph(graph, size))
        print(f"=== {size} Menschen, {material.term_count} Begriffe")
        for enabled in (False, True):
            label = "mit Widerspruch " if enabled else "ohne Widerspruch"
            try:
                result = condense(llm, material, QUESTIONS[0], enabled)
                print(f"  {label}: {result.sentence}")
            except Exception as exc:
                print(f"  {label}: FEHLER — {exc}")
        print()
    print("Gewählte Schwelle als `contradiction_min_persons` in config2.toml eintragen.")


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
    parser.add_argument("mode", choices=("questions", "contradiction", "floor"))
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
    if args.mode == "questions":
        run_questions(graph, cfg)
    else:
        run_contradiction(graph, cfg)


if __name__ == "__main__":
    main()
