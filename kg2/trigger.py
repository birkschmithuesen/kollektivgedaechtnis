"""When a dream is due. Pure functions over a graph payload — no I/O, no store.

This module exists because of one race (spec §4.1), and it is worth stating in
full because getting it wrong is invisible until an exhibition day.

Tool 1 publishes `graph.json` twice per interview:

  1. at the photo (`kg/core.py:156`) — the person node exists, **with no
     edges**. The interview has not been transcribed, let alone extracted.
  2. after the pipeline (`kg/core.py:198`) — the person now has edges to their
     terms. Seconds to tens of seconds later.

A dream triggered by (1) would condense a graph the interviewee has contributed
nothing to yet — and because screens A and B stand side by side, the visitor
would watch their own interview *not* arrive. So the only signal Tool 2 trusts
is structural: **a person node that has at least one edge**.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass


def absorbed_persons(graph: dict | None) -> set[str]:
    """Person ids whose interview Tool 1 has finished processing.

    „Has at least one edge" is the whole test. It is a property of the data, so
    it needs no access to Tool 1's internals, survives a Tool 1 restart, and
    cannot drift out of step with the pipeline the way a timer would.

    Hidden persons are excluded: the operator pulled them from the wall (T1§8)
    and spec §5.1 already excludes them from the dream's material, so letting
    one trigger a dream it is not in would be incoherent.

    `kg2.graph_client.fetch_graph` only validates that `version`, `nodes` and
    `edges` are present — never their value types. A payload can therefore
    reach here with `nodes` or `edges` being the wrong shape entirely (a
    string, a dict, a list of non-dicts). This function must degrade to „no
    one absorbed" rather than raise, so a corrupted poll reads as silence
    instead of crashing the watcher loop.
    """
    if not isinstance(graph, dict):
        return set()
    nodes = graph.get("nodes", ())
    edges = graph.get("edges", ())
    if not isinstance(nodes, Iterable) or isinstance(nodes, (str, bytes, dict)):
        nodes = ()
    if not isinstance(edges, Iterable) or isinstance(edges, (str, bytes, dict)):
        edges = ()
    # `.get("id")` rather than `node["id"]`: a person-typed dict with no `id`
    # is exactly the malformed shape this function promises to survive, and a
    # KeyError here would crash the watcher on a payload the client waved
    # through. The `isinstance(..., str)` check does double duty: a Tool 1
    # node id is always a string, so anything else is not a real id AND is
    # dropped before it ever reaches a set — an unhashable id (a list, say)
    # would otherwise blow up the set/comprehension below, and a hashable but
    # non-string one (an int) would make `sorted()` in kg2.cycle crash by
    # mixing types.
    persons = {
        node.get("id")
        for node in nodes
        if isinstance(node, dict)
        and node.get("type") == "person"
        and not node.get("hidden")
        and isinstance(node.get("id"), str)
    }
    # Same reasoning for the edge's `source`: `edge.get("source")` rather than
    # `edge["source"]` avoids a KeyError on a missing key, and the isinstance
    # check keeps a non-string (unhashable or not) out of the set on the same
    # grounds as `persons` above.
    with_edges = {
        edge.get("source") for edge in edges if isinstance(edge, dict)
        and isinstance(edge.get("source"), str)
    }
    return persons & with_edges


@dataclass(frozen=True)
class TriggerState:
    """What the watcher remembers between polls.

    `seen_persons` only ever grows (see `with_absorbed`). That monotonicity is
    what makes hiding and unhiding a person afterwards a no-op rather than a
    second dream on the same material.
    """

    seen_persons: frozenset[str] = frozenset()
    last_started_at: float | None = None

    def with_dream_started(self, at: float | None) -> "TriggerState":
        """Adopt the floor stamp. Done whatever the cycle's outcome is — a
        failed dream must still space out its retry (spec §8)."""
        return TriggerState(self.seen_persons, at)

    def with_absorbed(self, ids: Iterable[str]) -> "TriggerState":
        """Consume material. Done ONLY after a dream actually succeeded, so a
        failure retries the same interviews at the next trigger (spec §8)."""
        return TriggerState(self.seen_persons | frozenset(ids), self.last_started_at)


@dataclass(frozen=True)
class Decision:
    fire: bool
    reason: str
    #: What a SUCCESSFUL dream would consume. Adopted by the caller only then.
    absorbed: frozenset[str] = frozenset()
    #: The floor stamp to adopt regardless of outcome. None when not firing.
    started_at: float | None = None


def evaluate(
    state: TriggerState,
    graph: dict | None,
    now: float,
    min_interval_s: float,
    force: bool = False,
) -> Decision:
    """Is a dream due? Pure; the caller owns the state and the side effects.

    `force` is the operator's „Dream now" (spec §7): it ignores the floor and
    ignores silence, because its whole purpose is to demonstrate the station on
    demand.
    """
    absorbed = frozenset(absorbed_persons(graph))

    if force:
        return Decision(True, "forced", absorbed, now)

    fresh = absorbed - state.seen_persons
    if not fresh:
        # Either silence, or a person node that is still only a photo. Both are
        # correctly nothing: no new material has been said.
        return Decision(False, "nothing new")

    if state.last_started_at is not None and now - state.last_started_at < min_interval_s:
        # THE FLOOR IS A DELAY, NOT A DROP. `state` is returned untouched and no
        # `absorbed` is reported, so the same fresh persons are still fresh at
        # the next poll and the dream fires the moment the floor expires. Folding
        # them in here would swallow the interview silently and forever — and
        # nothing on screen would ever say so.
        return Decision(False, "floor")

    # Everything absorbed so far, not just `fresh`: the dream is of the whole
    # graph, so several interviews inside the floor collapse into one (spec §4.1)
    # and there is nothing to queue.
    return Decision(True, "absorbed", absorbed, now)


def resume_state(dreams: Sequence) -> TriggerState:
    """Rebuild the watcher's memory from the store after a restart (spec §8).

    Takes rows, not a store, so it stays pure and testable.

    * A `done` dream consumed its material — discarded or not. Discard removes
      it from the SCREEN (spec §7); re-dreaming the same graph would only
      reproduce whatever was discarded.
    * A `failed` or `running` dream consumed nothing, so its persons stay fresh
      and are retried — but it did START, so it still counts for the floor.
    """
    seen: set[str] = set()
    last: float | None = None
    for dream in dreams:
        last = dream.created_at if last is None else max(last, dream.created_at)
        if dream.status == "done":
            seen |= set(dream.absorbed_persons)
    return TriggerState(frozenset(seen), last)
