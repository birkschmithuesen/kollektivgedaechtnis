"""Register samples: identical content, one variable (spec §10, brainstorm §10).

**This module recommends nothing.** The register is decided by Birk AT IMAGES,
not in words — that is the whole reason it exists rather than a paragraph in the
spec. The names below are descriptive, the order is alphabetical, and no output
line marks a favourite.

Why fictional content: a sample built on real interview material invites judging
the CONTENT, which is not what is being decided, and it would leave a half-formed
dream of real people's words sitting in a review directory.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path

from kg2.imagegen import build_image_prompt, render_image, save_image

log = logging.getLogger(__name__)

# One sentence, four registers. Invented outright: a courtyard that is both
# poured and planted is exactly the kind of held contradiction stage 1 is
# instructed to produce (spec §5.1), so the samples are judged on the register
# doing the job it will really have to do.
FICTIONAL_SENTENCE = (
    "In einem Hof, der gleichzeitig gegossen und bepflanzt wird, "
    "warten zwei Generationen darauf, dass die jeweils andere zuerst aufgibt."
)

#: Alphabetical, deliberately. Any other order is an implied ranking.
#: „keine Schrift im Bild" is in every one of them, not decoration: the sentence
#: is a separate displayed artefact (spec §5.2) and text inside the picture
#: would compete with it.
REGISTERS: dict[str, str] = {
    "aquarell": (
        "Aquarell auf rauem Papier, laufende Ränder, viel unbemaltes Weiß, "
        "wenige gebrochene Farben, zarte Konturen. Kein Fotorealismus, kein "
        "Architektur-Rendering, keine Schrift im Bild."
    ),
    "malerisch-atmosphaerisch": (
        "Malerisch und atmosphärisch, weiche Übergänge, gedämpfte Farbigkeit, "
        "diffuses Licht, sichtbarer Pinselduktus. Kein Fotorealismus, kein "
        "Architektur-Rendering, keine Schrift im Bild."
    ),
    "radierung": (
        "Radierung, feine Schraffuren in Schwarz auf warmem Papierton, harte "
        "Linien, tiefe Schatten, kein Farbauftrag. Kein Fotorealismus, kein "
        "Architektur-Rendering, keine Schrift im Bild."
    ),
    "siebdruck": (
        "Reduzierter Siebdruck, drei bis vier flache Farbflächen, sichtbarer "
        "Passerversatz, grobes Raster, kräftige Kontraste. Kein Fotorealismus, "
        "kein Architektur-Rendering, keine Schrift im Bild."
    ),
}


@dataclass(frozen=True)
class Sample:
    name: str
    path: Path
    register: str


def render_samples(out_dir, cfg, registers=None, render_fn=render_image) -> list[Sample]:
    """One image per register, same sentence, same aspect ratio.

    A register that fails is logged and skipped: the others already cost real
    money and must not be thrown away with it.

    Existing files are never overwritten — an overwritten sample is a lost
    comparison, and re-running the CLI to add a fifth register must not silently
    remake the first four.
    """
    registers = REGISTERS if registers is None else registers
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    samples: list[Sample] = []
    for name, register in registers.items():
        target = out_dir / f"register-{name}.png"
        if target.exists():
            log.info("%s already exists, left alone", target)
            continue
        prompt = build_image_prompt(FICTIONAL_SENTENCE, register, cfg.image_aspect_ratio)
        try:
            data = render_fn(
                prompt,
                model=cfg.image_model,
                api_key=cfg.openrouter_api_key,
                url=cfg.image_url,
                timeout=cfg.image_timeout_s,
            )
            save_image(data, target)
        except Exception as exc:
            log.error("register %s failed: %s", name, exc)
            continue
        samples.append(Sample(name=name, path=target, register=register))
    return samples


def main() -> None:
    from kg2.config import load_dream_config

    parser = argparse.ArgumentParser(prog="sim.dream_register")
    parser.add_argument("--out", default="out/register1")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_dream_config(Path(args.config) if args.config else None)

    print(f"Ein Satz, {len(REGISTERS)} Register. Nur das Register ändert sich.\n")
    print(f"Satz (frei erfunden): {FICTIONAL_SENTENCE}\n")

    samples = render_samples(Path(args.out), cfg)

    for sample in samples:
        print(sample.path.resolve())
        print(f"    {sample.register}\n")
    # No recommendation, no ranking, no "we suggest". Birk decides at the
    # images (spec §10) and puts the string he picks into config2.toml.
    print(
        f"{len(samples)} von {len(REGISTERS)} Registern gerendert. "
        "Ausgewähltes Register als `visual_register` in config2.toml eintragen."
    )


if __name__ == "__main__":
    main()
