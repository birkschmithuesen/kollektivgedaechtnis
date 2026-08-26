"""One dream: condense -> render -> persist (spec §5).

Where reproducibility (§5.3) and the failure policy (§8) meet.

The order below is the design, not an implementation detail:

1. The row is written BEFORE the first cloud call, so a crash or a kill leaves
   a `running` row — visibly incomplete, which is the honest record — instead
   of no trace that a dream was ever attempted.
2. Stage 1's prompt and sentence are stored as soon as they exist.
3. Stage 2's prompt is stored BEFORE the render, so a failed render still
   leaves the prompt that failed. That is the one worth reading.
4. Only then does the row become `done` and reach the screen.

This function NEVER raises. The watcher must not be one exception away from a
dead poll loop, and the display is protected for free: `visible_dreams()` only
ever returns `done` rows, so a failure needs nothing undone — the current image
simply stays up (§8).
"""

from __future__ import annotations

import logging

from kg2.condense import condense as _condense
from kg2.imagegen import build_image_prompt, render_image as _render_image, save_image
from kg2.models import Dream
from kg2.trigger import absorbed_persons
from kg2.weighting import build_material, contradiction_enabled

log = logging.getLogger(__name__)


def run_dream(
    store,
    cfg,
    llm,
    graph: dict,
    now: float,
    *,
    condense_fn=_condense,
    render_fn=_render_image,
    on_sentence=None,
) -> Dream | None:
    """Run one full cycle. Returns the finished Dream, or None if it failed."""
    material = build_material(graph)
    contradiction = contradiction_enabled(material, cfg.contradiction_min_persons)

    dream = store.create_dream(
        created_at=now,
        graph_generated_at=material.generated_at,
        person_count=material.person_count,
        term_count=material.term_count,
        edge_count=material.edge_count,
        contradiction=contradiction,
        guiding_question=cfg.guiding_question,
        absorbed_persons=sorted(absorbed_persons(graph)),
    )

    try:
        result = condense_fn(llm, material, cfg.guiding_question, contradiction)
        store.set_stage1(
            dream.id,
            prompt=result.prompt,
            sentence=result.sentence,
            model=cfg.condense_model,
        )
        _announce(on_sentence, result.sentence)

        image_prompt = build_image_prompt(
            result.sentence, cfg.visual_register, cfg.image_aspect_ratio
        )
        store.set_stage2_prompt(dream.id, prompt=image_prompt, model=cfg.image_model)

        data = render_fn(
            image_prompt,
            model=cfg.image_model,
            api_key=cfg.openrouter_api_key,
            url=cfg.image_url,
            timeout=cfg.image_timeout_s,
        )
        filename = f"{dream.id}.png"
        save_image(data, cfg.image_dir / filename)
        store.finish_dream(dream.id, image_path=filename)
    except BaseException as exc:
        # BaseException, not Exception: a KeyboardInterrupt during the shutdown
        # of an exhibition day must still close the row honestly rather than
        # leave it stuck at `running` forever. The dream is abandoned either
        # way — spec §8 — and the current image stays up.
        log.error("dream %s failed: %s", dream.id, exc)
        store.fail_dream(dream.id, f"{type(exc).__name__}: {exc}")
        return None

    return store.get_dream(dream.id)


def _announce(on_sentence, sentence: str) -> None:
    """Tell the display the sentence exists, before the image does (spec §6).

    This is what the typewriter variant is built on: it builds the sentence up
    word by word WHILE stage 2 runs, then settles into the baseline's fixed line
    when the image arrives. A failure here is swallowed on purpose — the
    typewriter is decoration and must never cost an image.
    """
    if on_sentence is None:
        return
    try:
        on_sentence(sentence)
    except Exception as exc:
        log.warning("could not announce the sentence: %s", exc)
