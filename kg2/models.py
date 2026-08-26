"""Plain data carriers. Persistence lives in kg2.store.

Same shape and the same rule as `kg.models` (spec §3 permits reusing Tool 1's
dataclass shapes), but a separate file: Tool 2's store must never import Tool
1's, and sharing a module would be the first step towards it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Dream:
    """One dream, and everything needed to explain it afterwards (spec §5.3)."""

    id: str
    created_at: float
    graph_generated_at: float | None = None
    person_count: int = 0
    term_count: int = 0
    edge_count: int = 0
    contradiction: bool = False
    guiding_question: str = ""
    # The person ids this dream condensed. Persisted because a restart has no
    # other way to know which interviews have already been dreamt — without it
    # the watcher would either fire once for all 40 or never fire again.
    absorbed_persons: list[str] = field(default_factory=list)
    stage1_prompt: str | None = None
    sentence: str | None = None
    stage2_prompt: str | None = None
    condense_model: str | None = None
    image_model: str | None = None
    image_path: str | None = None
    status: str = "running"  # running | done | failed
    error: str | None = None
    discarded: bool = False
