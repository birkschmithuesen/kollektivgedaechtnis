"""Seed a Store with a realistic-density interview graph, no simulation involved.

Birk's 2026-08-14 decision (Task 20 brief): the pre-render comparison series
must NOT depend on Tasks 18/19 (the simulation replay engine, which do not
exist yet). This module writes state directly through `kg.store.Store` +
`kg.photos.make_portrait` + PIL — no LLM, no embeddings, no `kg.pipeline`.
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from kg.config import Config
from kg.photos import make_portrait
from kg.store import Store

# 100 realistic long German term labels drawn from the conference's actual
# subject matter (Bauwende / Stadt der Zukunft). Their LENGTH DISTRIBUTION is
# the point of this series — what will or will not fit on a whiteboard. Do
# not shorten, translate, invent replacements, or reorder: list order IS the
# Zipf popularity ranking used by `_weights()` below.
TERM_LABELS = [
    "Betonspritzen mit Drohnen",
    "Genossenschaftliches Wohnen",
    "Photovoltaik-Fassaden",
    "Kreislaufgerechte Bauteilkataloge",
    "Rückbaubare Verbindungen statt Kleber",
    "Graue Energie im Bestand halten",
    "Lehmbau im urbanen Maßstab",
    "Holz-Hybrid-Hochhäuser",
    "Bodenpreisbremse für Erbbaurecht",
    "Kommunale Bodenbevorratung",
    "Umbau statt Abriss",
    "Materialpässe für jedes Gebäude",
    "Urban Mining aus Abrissmasse",
    "Recyclingbeton mit Rezyklatanteil",
    "Carbonbeton statt Stahlbewehrung",
    "Suffizienz als Planungsgrundlage",
    "Gemeinschaftsflächen statt Quadratmeter",
    "Cluster-Wohnungen für Wahlfamilien",
    "Mietshäuser-Syndikat als Modell",
    "Baugruppen ohne Eigenkapital",
    "Sozialer Wohnungsbau in Serie",
    "Serielle Sanierung von Plattenbauten",
    "Wärmepumpen im Bestandsquartier",
    "Kalte Nahwärmenetze",
    "Abwasserwärme aus dem Kanal",
    "Agri-Photovoltaik am Stadtrand",
    "Balkonkraftwerke ohne Anmeldung",
    "Quartiersspeicher statt Hausbatterie",
    "Lastmanagement über Nachbarschaften",
    "Energiegenossenschaften auf dem Dach",
    "Schwammstadt gegen Starkregen",
    "Entsiegelung von Parkplätzen",
    "Baumrigolen im Straßenraum",
    "Fassadenbegrünung gegen Hitzeinseln",
    "Kühle Erdgeschosse für alle",
    "Trinkbrunnen im öffentlichen Raum",
    "Superblocks nach Barceloner Vorbild",
    "Autofreie Innenstadt bis 2035",
    "Parkraum in Nachbarschaftsgärten",
    "Lastenräder im Wirtschaftsverkehr",
    "Mikrodepots für die letzte Meile",
    "Straßenbahn statt Stadtautobahn",
    "Nachtbusse für Schichtarbeitende",
    "Barrierefreiheit von Anfang an",
    "Blindenleitsysteme mitdenken",
    "Sitzbänke ohne Liegesperren",
    "Öffentliche Toiletten als Grundversorgung",
    "Nutzungsoffene Erdgeschosszonen",
    "Zwischennutzung als Dauerlösung",
    "Leerstandsmelder für Kommunen",
    "Konzeptvergabe statt Höchstgebot",
    "Erbbaurecht für gemeinwohlorientierte Träger",
    "Bodenwertzuwachs abschöpfen",
    "Mietendeckel neu gedacht",
    "Wohnungstausch statt Umzugsstau",
    "Kleinteilige Nachverdichtung",
    "Aufstockung von Supermärkten",
    "Dachgeschossausbau ohne Verdrängung",
    "Milieuschutz mit Zähnen",
    "Vorkaufsrecht für Kommunen",
    "Genossenschaftsanteile finanzierbar machen",
    "Bürgschaftsfonds für Baugruppen",
    "Planungsrecht entschlacken",
    "Gebäudetyp E für Experimente",
    "Normen als Innovationsbremse",
    "Brandschutz im Holzbau klären",
    "Typengenehmigung bundesweit",
    "Digitale Bauakte für Kommunen",
    "BIM für kleine Büros",
    "Offene Bauteilbörsen im Netz",
    "Handwerk als Engpass",
    "Ausbildungsoffensive im Bauhandwerk",
    "Vorfertigung in regionalen Werken",
    "Robotik auf der Baustelle",
    "3D-Druck mit lokalem Aushub",
    "Strohballen als Dämmstoff",
    "Hanfkalk im Wohnungsbau",
    "Pilzmyzel als Dämmung",
    "Seegras statt Mineralwolle",
    "Schafwolle im Dachaufbau",
    "Wiederverwendung von Fensterelementen",
    "Stahlträger aus dem Rückbau",
    "Ziegel wiederverwenden statt schreddern",
    "Schadstoffkataster vor dem Rückbau",
    "Reparaturcafés im Quartier",
    "Nachbarschaftswerkstätten",
    "Gemeinschaftsküchen im Wohnblock",
    "Kita im Erdgeschoss",
    "Pflege-WGs im Quartier",
    "Mehrgenerationenhäuser",
    "Wohnen für Hilfe",
    "Obdachlosigkeit durch Housing First beenden",
    "Beteiligung ohne Beteiligungstheater",
    "Zufallsbürgerräte für Bauleitplanung",
    "Planungszellen in der Kommune",
    "Klimacheck für jeden Bebauungsplan",
    "CO2-Budget pro Quadratmeter",
    "Lebenszyklusanalyse verpflichtend",
    "Abrissmoratorium für Bestandsbauten",
    "Bauwende als Generationenprojekt",
]

# A fixed epoch (2026-08-01 00:00:00 UTC-ish, arbitrary but constant) so
# started_at/stopped_at are deterministic and never touch time.time().
_EPOCH_BASE = 1785542400.0
_INTERVIEW_SPACING_S = 240.0
_INTERVIEW_DURATION_S = 165.0

_MIN_TERMS_PER_PERSON = 4
_MAX_TERMS_PER_PERSON = 6
_ZIPF_EXPONENT = 0.85


def _weights() -> list[float]:
    """Zipf-like popularity: list order IS the ranking (spec-mandated shape)."""
    return [1.0 / (i + 1) ** _ZIPF_EXPONENT for i in range(len(TERM_LABELS))]


def _draw_terms_for_person(rng: random.Random, weights: list[float]) -> list[str]:
    """4-6 distinct labels, weighted-without-replacement via rejection sampling.

    `random.Random.choices` draws with replacement, so duplicates within one
    person are drawn and rejected rather than avoided by construction — the
    weights of the remaining labels don't need re-normalising this way.
    """
    target = rng.randint(_MIN_TERMS_PER_PERSON, _MAX_TERMS_PER_PERSON)
    chosen: list[str] = []
    seen: set[str] = set()
    # TERM_LABELS has 100 entries and target is at most 6, so this loop
    # terminates quickly in practice; the population is large relative to
    # what's being drawn.
    while len(chosen) < target:
        label = rng.choices(TERM_LABELS, weights=weights, k=1)[0]
        if label in seen:
            continue
        seen.add(label)
        chosen.append(label)
    return chosen


# Muted grey (Birk's 3rd review made it one flat colour; his 2026-08-15 colour
# correction took the blue cast out of it). The old #3A3A42 was the last tinted
# value left once the themes went to pure black and pure white, and on a pure
# black ground it would have read as the one blue thing on the wall. #3B3B3B is
# the NEUTRAL grey of the same relative luminance, so the disc is exactly as
# bright as it was and carries exactly as little information.
_PLACEHOLDER_FILL = (0x3B, 0x3B, 0x3B)


def _write_placeholder_photo(dest: Path) -> Path:
    """A flat, uniform placeholder — deliberately NOT information.

    Birk's third pre-render review (2026-08-14): the previous per-person hue
    gradient plus face ellipse read as data, but the colours meant nothing —
    misleading, and fighting the term text. Every person now gets the exact
    same muted, desaturated `_PLACEHOLDER_FILL`: visible against the #000000
    ground, sitting inside the golden ring (the ring, not the fill, is the
    concept's carrier). Real photographs will bring their own structure once
    they arrive through this same `make_portrait` path — the placeholder must
    not pretend to have any.

    A pure function of `dest`: it takes no rng, because the colour stopped
    depending on one. The DRAW that used to happen here still happens, in
    `person_specs` — see the comment there.
    """
    width, height = 900, 1200
    image = Image.new("RGB", (width, height), _PLACEHOLDER_FILL)
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, format="JPEG", quality=90)
    return dest


@dataclass(frozen=True)
class PersonSpec:
    """One seeded interview, decided before anything is written.

    Split out of `seed_graph` on 2026-08-15 for the fifth pre-render round's
    `seq-new-person` sequence, which has to drop the (N+1)th person into a
    graph that is already settled and on screen — the arrival is the whole
    transition being filmed, so it cannot come from re-seeding the database.
    Person N's draw depends on every draw before it, so the plan is computed
    for the whole run and the caller picks the entry it wants.
    """

    index: int
    started_at: float
    stopped_at: float
    terms: tuple[str, ...]


def person_specs(persons: int = 50, seed: int = 20260814) -> list[PersonSpec]:
    """The deterministic plan for `persons` seeded interviews.

    Walks `random.Random(seed)` in EXACTLY the order `seed_graph` used to walk
    it: one throwaway value per person, then that person's term draw. Any
    other order silently reshuffles the graph's shape.
    """
    rng = random.Random(seed)
    weights = _weights()
    specs: list[PersonSpec] = []
    for index in range(persons):
        started_at = _EPOCH_BASE + index * _INTERVIEW_SPACING_S
        # The placeholder photo's draw. It is taken and thrown away: the
        # colour stopped depending on it at Birk's third review, but this is
        # the Nth value in the sequence and every term drawn after it depends
        # on that sequence staying put. Dropping it would reshuffle every
        # downstream pick and silently change the seeded graph's shape (75
        # terms / 25 mentioned once, at persons=50, seed=20260814).
        rng.random()
        specs.append(
            PersonSpec(
                index=index,
                started_at=started_at,
                stopped_at=started_at + _INTERVIEW_DURATION_S,
                terms=tuple(_draw_terms_for_person(rng, weights)),
            )
        )
    return specs


def write_person(store: Store, cfg: Config, spec: PersonSpec):
    """Write one planned interview — photo, portrait, person row, edges.

    Takes no rng: every random decision was already made in `person_specs`,
    which is what lets a single person be added to a running store later
    without replaying the seed.
    """
    src = cfg.photo_dir / f"person-{spec.index:03d}.jpg"
    _write_placeholder_photo(src)
    dest = cfg.portrait_dir / f"person-{spec.index:03d}.png"
    make_portrait(src, dest, size=cfg.portrait_size)

    person = store.create_person(
        started_at=spec.started_at,
        photo_path=str(src),
        portrait_path=str(dest),
    )
    # "spoken" is a real kg.session.Transition reason; the state machine emits
    # only text/spoken/timeout/new_photo, so seeded rows must not invent a
    # fifth value.
    store.close_person(person.id, stopped_at=spec.stopped_at, reason="spoken")
    store.set_person_status(person.id, "done")

    for label in spec.terms:
        term = store.get_or_create_term(label, created_at=spec.started_at)
        store.add_edge(person.id, term.id, created_at=spec.started_at)
    return person


def seed_graph(data_dir: Path, persons: int = 50, seed: int = 20260814) -> Path:
    """Populate a fresh Store at `Config(data_dir).db_path` and return that path.

    Deterministic for a given (persons, seed): a single `random.Random(seed)`
    drives every random choice in a fixed call order, never the
    module-level `random` functions and never `time.time()`.
    """
    data_dir = Path(data_dir)
    cfg = Config(data_dir=data_dir)
    store = Store.open(cfg.db_path)

    try:
        with store.transaction():
            for spec in person_specs(persons, seed):
                write_person(store, cfg, spec)
            store.set_setting("min_mentions", "1")
    finally:
        store.close()

    return cfg.db_path


def main() -> None:
    parser = argparse.ArgumentParser(prog="sim.seed_graph")
    parser.add_argument("--out", default="out/prerender-state")
    parser.add_argument("--persons", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260814)
    args = parser.parse_args()
    db_path = seed_graph(Path(args.out), persons=args.persons, seed=args.seed)
    print(db_path)


if __name__ == "__main__":
    main()
