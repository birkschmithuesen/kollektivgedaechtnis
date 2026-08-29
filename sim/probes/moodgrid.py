"""Render a small grid of dreams that differ ONLY in mood/tension.

Ad-hoc probe, written 2026-08-29 for the moment Birk needed to SEE whether
the two new analysis channels actually change the picture. Not part of the
station: `sim/dream_register.py` is the maintained tool for register choices.

One fixed sentence, one fixed register, one fixed format — the only thing
that moves between the frames is the pair (mood, tension). If two images at
different mood levels look the same, the channel is decoration.
"""

from __future__ import annotations

import logging
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kg2.config import load_dream_config
from kg2.imagegen import build_image_prompt, render_image, save_image

log = logging.getLogger("moodgrid")

# From the real 30-person calibration run, translated for stage 2.
SENTENCE_EN = (
    "A thousand adhesive dots burst open the asphalt yard and the empty "
    "village house stands in the crack full of afternoon light."
)

# Corners plus the centre: cold/coherent, cold/impossible, warm/coherent,
# warm/impossible, and the middle of both scales.
CASES = [
    (1, 1, "kalt-ruhig"),
    (5, 1, "warm-ruhig"),
    (3, 3, "mitte-mitte"),
    (1, 5, "kalt-unmoeglich"),
    (5, 5, "warm-unmoeglich"),
]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "out/moodgrid")
    out.mkdir(parents=True, exist_ok=True)

    cfg = load_dream_config(None)
    register = tomllib.loads(
        Path(__file__).resolve().parents[2] / "config2.example.toml".read_text(encoding="utf-8")
    )["visual_register"]

    print(f"Satz: {SENTENCE_EN}\n")
    done = []
    for mood, tension, name in CASES:
        prompt = build_image_prompt(
            SENTENCE_EN,
            mood=mood,
            tension=tension,
            register=register,
            aspect_ratio=cfg.image_aspect_ratio,
        )
        try:
            data = render_image(
                prompt,
                model=cfg.image_model,
                api_key=cfg.openrouter_api_key,
                url=cfg.image_url,
                timeout=cfg.image_timeout_s,
            )
            target = save_image(data, out / f"mood{mood}-tension{tension}-{name}")
        except Exception as exc:  # a failed render must not lose the others
            log.error("%s failed: %s", name, exc)
            continue
        done.append((mood, tension, name, target))
        print(f"  mood={mood} tension={tension} ({name}) -> {target.resolve()}")

    print(f"\n{len(done)} von {len(CASES)} gerendert.")


if __name__ == "__main__":
    main()
