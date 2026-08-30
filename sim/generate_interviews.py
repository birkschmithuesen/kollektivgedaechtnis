"""Synthetic interview corpus (spec 9). STT is out of scope: this starts from text.

Deterministic by construction — no random seeds — so two runs over the same
corpus are comparable.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from kg.extraction import GUIDING_QUESTIONS as QUESTIONS  # noqa: F401  (re-exported)

# NOT redefined here: the corpus must be generated from the SAME guiding
# questions the extraction prompt names, otherwise the simulation tests the
# wrong text genre (spec 9). Three since 2026-08-30 — see kg/extraction.py for
# why these three and not the original five.

# Sonnet, not the Opus default used for real extraction/merge-judge calls:
# writing synthetic spoken German does not need Opus-level reasoning, and 60
# calls on Opus is a materially large slice of the weekly budget for a
# fixture set (Birk's decision, 2026-08-19).
DEFAULT_GENERATION_MODEL = "claude-sonnet-5"

SPEAKER_TYPES = [
    "sehr knapp, zwei Sätze, fast unwillig",
    "ausschweifend, fünf Minuten, mit zwei Abschweifungen",
    "Fachjargon, Planerin oder Ingenieur, sehr präzise",
    "Alltagssprache, keine Fachbegriffe, sehr bildhaft",
    "unentschlossen, wägt ab, widerspricht sich einmal",
    "klare Position, pointiert, leicht polemisch",
]

# Deliberate overlaps: the same idea in deliberately different words (spec 9).
PLANTED = [
    {
        "concept": "Roboter auf der Baustelle",
        "phrasings": [
            "Maschinen, die den Beton selber aufsprühen, so Drohnen halt",
            "3D-Drucker, die das Haus direkt auf dem Grundstück ausdrucken",
            "Roboterarme, die auf der Baustelle mauern",
        ],
    },
    {
        "concept": "Genossenschaftliches Wohnen",
        "phrasings": [
            "wenn die Leute das Haus zusammen besitzen, so als Verein",
            "Baugruppen, die gemeinsam bauen und dann gemeinsam drin wohnen",
            "wo nicht ein Investor gehört, sondern denen, die drin wohnen",
        ],
    },
    {
        "concept": "Recycling-Beton",
        "phrasings": [
            "den alten Bauschutt einfach wieder neu anmischen",
            "Beton aus Abbruchmaterial, also wirklich aus dem alten Haus",
            "Material aus dem Rückbau nochmal verwenden statt neu zu kaufen",
        ],
    },
    {
        "concept": "Ländlicher Leerstand",
        "phrasings": [
            "die ganzen leeren Häuser in den Dörfern, wo keiner mehr wohnt",
            "auf dem Land stehen ganze Straßen leer",
            "die Ortskerne draußen sterben aus, da ist alles frei",
        ],
    },
    {
        "concept": "Bodenversiegelung",
        "phrasings": [
            "dass alles zubetoniert wird, jeder Parkplatz asphaltiert",
            "der Boden kriegt keine Luft mehr, überall Beton drauf",
            "wir pflastern die Landschaft einfach zu",
        ],
    },
]


@dataclass(frozen=True)
class InterviewSpec:
    index: int
    question_index: int
    speaker_type: str
    planted_concept: str | None = None
    planted_phrasing: str | None = None


def plan_corpus(count: int = 60) -> list[InterviewSpec]:
    """Deterministic assignment — index arithmetic, no randomness."""
    specs: list[InterviewSpec] = []
    planted_position = 0
    for index in range(count):
        concept = phrasing = None
        if index % 3 == 0:  # ~1/3 carry a planted overlap
            group = PLANTED[planted_position % len(PLANTED)]
            concept = group["concept"]
            phrasing = group["phrasings"][
                (planted_position // len(PLANTED)) % len(group["phrasings"])
            ]
            planted_position += 1
        specs.append(
            InterviewSpec(
                index=index,
                question_index=index % len(QUESTIONS),
                speaker_type=SPEAKER_TYPES[index % len(SPEAKER_TYPES)],
                planted_concept=concept,
                planted_phrasing=phrasing,
            )
        )
    return specs


def build_generation_prompt(spec: InterviewSpec) -> str:
    lines = [
        "Schreibe das Transkript EINER Interviewantwort auf einer Architektur- und "
        "Baukultur-Konferenz, so wie eine automatische Spracherkennung es liefern "
        "würde: gesprochene Sprache, Füllwörter („also“, „ähm“, „ne“), abgebrochene "
        "Sätze, Wiederholungen, kleine Abschweifungen, keine Absätze, keine "
        "Anführungszeichen, kein Sprecherlabel.",
        "",
        f"Gestellte Frage: {QUESTIONS[spec.question_index]}",
        f"Sprechertyp: {spec.speaker_type}",
    ]
    if spec.planted_phrasing:
        lines += [
            "",
            "Die Person soll dabei — beiläufig, in eigenen Worten, ohne Fachbegriff — "
            f"genau diesen Gedanken äußern: „{spec.planted_phrasing}“. Verwende NICHT "
            f"den Ausdruck „{spec.planted_concept}“.",
        ]
    lines += ["", "Gib nur das Transkript aus, sonst nichts."]
    return "\n".join(lines)


def write_expectations(plan: list[InterviewSpec], path: Path) -> dict:
    groups: dict[str, dict] = {}
    for spec in plan:
        if not spec.planted_concept:
            continue
        group = groups.setdefault(
            spec.planted_concept, {"concept": spec.planted_concept, "interviews": [], "phrasings": []}
        )
        group["interviews"].append(spec.index)
        group["phrasings"].append(spec.planted_phrasing)
    document = {
        "note": "Erwartete Zusammenfassungen. Ohne diese Datei ist 'gutes Ergebnis' nicht falsifizierbar.",
        "expected_merges": [groups[key] for key in sorted(groups)],
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return document


def main() -> None:
    from kg.config import load_config
    from kg.llm import LLMClient
    from pydantic import BaseModel

    class Transcript(BaseModel):
        text: str

    parser = argparse.ArgumentParser(prog="sim.generate_interviews")
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--out", default="sim/data")
    parser.add_argument(
        "--model",
        default=DEFAULT_GENERATION_MODEL,
        help="Model used to generate the synthetic corpus (kept separate from "
        "cfg.llm_model, which stays on Opus for real extraction/merge-judge calls).",
    )
    args = parser.parse_args()

    cfg = load_config()
    llm = LLMClient(
        model=args.model, effort="medium", max_tokens=4000, api_key=cfg.anthropic_api_key
    )
    out = Path(args.out)
    (out / "interviews").mkdir(parents=True, exist_ok=True)

    plan = plan_corpus(args.count)
    for spec in plan:
        target = out / "interviews" / f"{spec.index:03d}.json"
        if target.exists():
            continue  # generation is resumable and never rewrites a committed fixture
        result = llm.parse(
            system="Du erzeugst realistische deutsche Interviewtranskripte.",
            user=build_generation_prompt(spec),
            output_model=Transcript,
        )
        payload = asdict(spec) | {"model": args.model, "text": result.text}
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {target}")

    write_expectations(plan, out / "expectations.yaml")


if __name__ == "__main__":
    main()
