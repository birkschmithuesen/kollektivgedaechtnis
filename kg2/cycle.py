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

This function NEVER raises for an ordinary failure — a bad LLM call, a broken
render, a malformed graph. The watcher must not be one exception away from a
dead poll loop, and the display is protected for free: `visible_dreams()` only
ever returns `done` rows, so a failure needs nothing undone — the current image
simply stays up (§8). The one deliberate exception to "never raises" is
`KeyboardInterrupt`/`SystemExit`: those still close the row (honesty first)
but are then re-raised, because absorbing the operator's own shutdown signal
would be a worse failure than a poll loop that occasionally dies loudly on
purpose.

Building the material (`build_material`, `absorbed_persons`) happens before
any row exists. Those functions are
hardened to degrade rather than raise on the malformed shapes
`kg2.graph_client.fetch_graph` lets through, so a guard around that step is
belt-and-braces, not the primary defence — see the comment at its `except` for
why it deliberately writes no row when it fires.

One more guard sits before step 1 even begins: an empty `Material` (no terms —
an empty graph at 09:00, or a person who is still only a photo) also writes no
row. Stage 1's prompt still ends "Antworte mit genau einem Satz" regardless of
what the material contains, so without this the model invents a dream out of
nothing, and — worse than an ordinary failure — that invented dream would
SUCCEED and take a permanent seat in the day's evidence strip (Finding 2). See
the guard's own comment below for why it applies to a forced „Dream now" just
as much as to an automatic cycle.
"""

from __future__ import annotations

import logging

from kg2.condense import condense as _condense
from kg2.imagegen import build_image_prompt, render_image as _render_image, save_image
from kg2.models import Dream
from kg2.trigger import absorbed_persons
from kg2.weighting import build_material

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
    try:
        material = build_material(graph)
        absorbed = sorted(absorbed_persons(graph))
    except Exception as exc:
        # Belt-and-braces, not the primary defence: build_material and
        # absorbed_persons are themselves hardened to degrade on every
        # malformed shape kg2.graph_client.fetch_graph lets through (wrong
        # types, unhashable ids, non-comparable labels), so this should never
        # fire. If it does anyway — a shape neither of them anticipated —
        # there is nothing yet worth a row: create_dream has not run, and a
        # graph too malformed for the hardened functions is not a dream worth
        # recording. So, unlike the handler below, this path deliberately
        # writes NO row at all. The watcher must still survive the poll, so
        # log and skip the cycle rather than let the exception escape.
        log.error("dream skipped: could not process graph: %s", exc)
        return None

    if material.term_count == 0:
        # Finding 2: "Dream now" on an empty graph — the spec's own use case
        # for the button, someone from the organiser wanting to see how it
        # works at 09:00 — or on a graph with only a photographed-but-not-yet-
        # processed person ("1 Menschen, 0 Begriffe") has nothing for stage 1
        # to condense. Stage 1's prompt does not know that: it still ends
        # "Antworte mit genau einem Satz", so the model answers out of thin
        # air anyway, and a confident sentence-and-image pair lands as
        # dream #1 of a day whose strip is supposed to be evidence of what
        # people actually said. Applies equally to a forced and an automatic
        # cycle: the automatic trigger cannot reach this state today (spec
        # §4.1's `evaluate` only fires on a person node WITH an edge, which
        # means at least one term exists), but that is a property of
        # `kg2.trigger`, not of this function, and this guard must not depend
        # on it staying true. Checked before `create_dream`, so — unlike the
        # ordinary failure path below — this writes NO row at all: there is
        # nothing here worth recording as an attempt, because the cycle never
        # actually started.
        log.info(
            "dream skipped: no material to condense (%d persons, 0 terms)",
            material.person_count,
        )
        return None

    dream = store.create_dream(
        created_at=now,
        graph_generated_at=material.generated_at,
        person_count=material.person_count,
        term_count=material.term_count,
        edge_count=material.edge_count,
        absorbed_persons=absorbed,
    )

    try:
        # Die zuletzt befragte Person verankert den Bildausschnitt
        # (kg2.weighting.select_required). Sie kommt aus `material`, nicht aus
        # `absorbed`: Personen-Ids sind Strings, und `sorted(absorbed)[-1]`
        # liefert „p9" statt „p60" — build_material nimmt den Zeitstempel.
        # Zitate: die woertlichen Saetze der zuletzt Befragten gehen mit in
        # Stufe 1 (Birk, 2026-09-01). `condense_quote_persons=0` schaltet sie
        # ab, ohne dass jemand Code anfassen muss.
        result = condense_fn(
            llm,
            material,
            last_person_id=material.last_person_id,
            include_quotes=cfg.condense_include_quotes and cfg.condense_quote_persons > 0,
            quote_persons=cfg.condense_quote_persons,
        )
        store.set_stage1(
            dream.id,
            prompt=result.prompt,
            sentence=result.sentence,
            sentence_en=result.sentence_en,
            image_description=result.image_description,
            tension_source=result.tension_source,
            mood=result.mood,
            tension=result.tension,
            model=cfg.condense_model,
        )
        _announce(on_sentence, result.sentence)

        # Every field stage 1 produced, not just the motif: build_image_prompt
        # owns the fallback order between them (image_description ->
        # sentence_en -> sentence), so a stage 1 that filled only some of them
        # still yields a prompt here, and this function keeps no opinion about
        # which one won.
        image_prompt = build_image_prompt(
            result.image_description,
            sentence_en=result.sentence_en,
            sentence=result.sentence,
            tension_source=result.tension_source,
            mood=result.mood,
            tension=result.tension,
            register=cfg.visual_register,
            aspect_ratio=cfg.image_aspect_ratio,
        )
        store.set_stage2_prompt(dream.id, prompt=image_prompt, model=cfg.image_model)

        data = render_fn(
            image_prompt,
            model=cfg.image_model,
            api_key=cfg.image_api_key,
            url=cfg.image_url,
            timeout=cfg.image_timeout_s,
            # Welcher Anbieter, entscheidet allein die config2.toml; Default
            # ist unverändert OpenRouter. `width`/`height` benutzt nur der
            # BFL-Weg, im OpenRouter-Weg sind sie folgenlos.
            api_mode=cfg.image_api_mode,
            width=cfg.image_width,
            height=cfg.image_height,
        )
        # No extension here: the real one is decided by the bytes, not
        # assumed (contract document, „Abweichung 3" — PNG or JPEG per call).
        target = save_image(data, cfg.image_dir / dream.id)
        store.finish_dream(dream.id, image_path=target.name)
    except (KeyboardInterrupt, SystemExit):
        # A KeyboardInterrupt during the shutdown of an exhibition day must
        # still close the row honestly rather than leave it stuck at
        # `running` forever — but unlike an ordinary Exception, it must NOT
        # be absorbed: it is the operator's (or the OS's) signal to stop the
        # process, and swallowing it here would leave the watcher running
        # with no way to shut down. So: mark the row failed, then let it keep
        # propagating.
        log.error("dream %s interrupted", dream.id)
        try:
            store.fail_dream(dream.id, "interrupted")
        except Exception as cleanup_exc:
            # Even a broken cleanup must not swallow the interrupt — that
            # would defeat the entire point of this branch.
            log.error(
                "dream %s: could not mark failed during interrupt: %s",
                dream.id, cleanup_exc,
            )
        raise
    except Exception as exc:
        log.error("dream %s failed: %s", dream.id, exc)
        try:
            store.fail_dream(dream.id, f"{type(exc).__name__}: {exc}")
        except Exception as cleanup_exc:
            # The never-raises guarantee has to hold even when closing the
            # row itself fails (a locked DB, a full disk): losing the
            # failure reason is better than taking the watcher down over it.
            log.error("dream %s: could not mark failed: %s", dream.id, cleanup_exc)
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
