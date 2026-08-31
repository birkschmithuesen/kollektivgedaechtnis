"""Plain data carriers. Persistence lives in kg.store."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Person:
    """One interviewed visitor. Doubles as the interview record (serial by design)."""

    id: str
    started_at: float
    stopped_at: float | None = None
    stop_reason: str | None = None
    status: str = "open"  # open | closed | processing | done | failed
    transcript: str | None = None
    photo_path: str | None = None
    portrait_path: str | None = None
    hidden: bool = False
    # Wie die Person sich zu Beginn des Interviews selbst vorgestellt hat.
    # None, wenn sie es nicht getan hat — dann steht am Zitat schlicht kein
    # Name, kein Platzhalter (Birk, 2026-08-31).
    name: str | None = None


@dataclass(frozen=True)
class Term:
    id: str
    label: str
    created_at: float
    hidden: bool = False


@dataclass(frozen=True)
class Edge:
    id: str
    person_id: str
    term_id: str
    created_at: float


@dataclass(frozen=True)
class Quote:
    id: str
    person_id: str
    text: str
    created_at: float
