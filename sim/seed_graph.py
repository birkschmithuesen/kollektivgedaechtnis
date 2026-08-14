"""Seed a Store with a realistic-density interview graph, no simulation involved.

Birk's 2026-08-14 decision (Task 20 brief): the pre-render comparison series
must NOT depend on Tasks 18/19 (the simulation replay engine, which do not
exist yet). This module writes state directly through `kg.store.Store` +
`kg.photos.make_portrait` + PIL — no LLM, no embeddings, no `kg.pipeline`.
"""

from __future__ import annotations

import argparse
import colorsys
import random
from pathlib import Path

from PIL import Image, ImageDraw

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


def _placeholder_photo(rng: random.Random, dest: Path) -> Path:
    """A deterministic, distinguishable non-uniform placeholder — not a real photo.

    Phone-photo aspect (900x1200 portrait), a soft vertical gradient in a
    per-person hue, and a lighter ellipse roughly where a face would sit so
    the crop-and-mask in `make_portrait` has something non-uniform to show.
    """
    width, height = 900, 1200
    hue = rng.random()
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    for y in range(height):
        # Gradient darkens towards the bottom of the frame.
        value = 0.85 - 0.45 * (y / height)
        r, g, b = colorsys.hsv_to_rgb(hue, 0.45, value)
        row_rgb = (int(r * 255), int(g * 255), int(b * 255))
        for x in range(width):
            pixels[x, y] = row_rgb

    face = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(face)
    cx, cy = width * 0.5, height * 0.38
    rx, ry = width * 0.28, height * 0.22
    draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=255)
    lighter = Image.new("RGB", (width, height), (255, 255, 255))
    image = Image.composite(lighter, image, face.point(lambda a: int(a * 0.35)))

    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, format="JPEG", quality=90)
    return dest


def seed_graph(data_dir: Path, persons: int = 50, seed: int = 20260814) -> Path:
    """Populate a fresh Store at `Config(data_dir).db_path` and return that path.

    Deterministic for a given (persons, seed): a single `random.Random(seed)`
    drives every random choice in a fixed call order, never the
    module-level `random` functions and never `time.time()`.
    """
    data_dir = Path(data_dir)
    cfg = Config(data_dir=data_dir)
    store = Store.open(cfg.db_path)
    rng = random.Random(seed)
    weights = _weights()

    try:
        with store.transaction():
            for index in range(persons):
                started_at = _EPOCH_BASE + index * _INTERVIEW_SPACING_S
                stopped_at = started_at + _INTERVIEW_DURATION_S

                src = cfg.photo_dir / f"person-{index:03d}.jpg"
                _placeholder_photo(rng, src)
                dest = cfg.portrait_dir / f"person-{index:03d}.png"
                make_portrait(src, dest, size=cfg.portrait_size)

                person = store.create_person(
                    started_at=started_at,
                    photo_path=str(src),
                    portrait_path=str(dest),
                )
                # "spoken" is a real kg.session.Transition reason; the state
                # machine emits only text/spoken/timeout/new_photo, so seeded
                # rows must not invent a fifth value.
                store.close_person(person.id, stopped_at=stopped_at, reason="spoken")
                store.set_person_status(person.id, "done")

                for label in _draw_terms_for_person(rng, weights):
                    term = store.get_or_create_term(label, created_at=started_at)
                    store.add_edge(person.id, term.id, created_at=started_at)

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
