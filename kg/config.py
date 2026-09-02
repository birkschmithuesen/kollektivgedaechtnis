"""Configuration loading. Secrets come from the environment, never from the file."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_STOP_PHRASES = [
    "Interview beendet",
    "Interview ist beendet",
    "Aufnahme beenden",
    "Aufnahme ist beendet",
]

# The name the guests address the bot with. Spoken in front of a stop phrase it
# is the sure-fire way to end an interview (Birk, 2026-08-30) — nobody says
# "Utopia" in passing. Configurable because the bot can be renamed; the
# detection never hardcodes it (kg/segmentation.py).
#
# "Utopia", not "Utopie" (Birk, 2026-08-31). On this subject the two are one
# vowel apart and the wrong one is a word guests genuinely use — "wir brauchen
# eine Utopie" must not buy a model call, let alone end a recording. That
# holds because contains_wake_word matches whole tokens: "Utopie", "Utopien"
# and "utopisch" are all different tokens and none of them matches. Verified
# 2026-08-31; the case is pinned in tests/test_segmentation.py.
DEFAULT_WAKE_WORD = "Utopia"

# …and behind that name, when no configured phrase matches, one small model
# decides whether a stop was meant (Birk, 2026-08-30: „Hiermit beende ich das
# Interview." ended nothing). Deliberately not the pipeline's model: one
# boolean per addressed utterance, not the condensation of an interview.
DEFAULT_WAKE_WORD_LLM_MODEL = "claude-sonnet-5"

# Prompt dial for merge aggressiveness (spec 6.2): calibrated in simulation,
# never exposed at runtime.
DEFAULT_MERGE_STYLE = (
    "Fasse nur zusammen, was wirklich dasselbe meint. Verwandte, aber "
    "unterschiedliche Ideen bleiben getrennte Knoten."
)


@dataclass(frozen=True)
class Config:
    data_dir: Path
    stt_url: str = "http://127.0.0.1:5051"
    #: Wie oft die Aufsicht Infomaniaks Whisper durchmisst (Sekunden).
    #: 0,3 s Ton pro Probe -- bei 60 s Takt sind das 18 s Audio je Stunde.
    #: Das ist nichts gegen den Preis, eine Ausstellung lang nicht zu merken,
    #: dass niemand verstanden wird (2026-09-02: 26 Aeusserungen, 0 Transkripte,
    #: eine Viertelstunde Suche).
    stt_probe_takt_s: float = 60.0
    telegram_chat_id: int | None = None
    interview_timeout_s: int = 900
    stop_phrases: list[str] = field(default_factory=lambda: list(DEFAULT_STOP_PHRASES))
    wake_word: str = DEFAULT_WAKE_WORD
    # False = exactly the behaviour before 2026-08-30: mechanics only, never a
    # call. The gate stays the wake word in either case (kg/session.py).
    wake_word_llm: bool = True
    wake_word_llm_model: str = DEFAULT_WAKE_WORD_LLM_MODEL
    # Hard budget for that call. It sits on the hot path of a running
    # recording, so a late answer is dropped rather than waited for.
    wake_word_llm_timeout_s: float = 6.0
    # Eigener Anbieter-Schalter für diesen zweiten Client, unabhängig vom
    # Pipeline-Modell darunter: es sind zwei verschiedene Aufgaben (ein Ja/Nein
    # im heißen Pfad gegen die Verdichtung eines ganzen Interviews), und wer
    # nur eine davon umstellt, soll genau das bekommen. Defaults = Anthropic,
    # also der Weg von vor dem 2026-08-31.
    wake_word_llm_api_mode: str = "anthropic"
    wake_word_llm_url: str = ""
    wake_word_llm_api_key_env: str = ""
    wake_word_llm_reasoning_effort: str = ""
    terms_per_interview: int = 5
    # Run 19c: 5 was too narrow — in 7 of 8 near-misses of run 19b the
    # concept's own node sat at rank 7-56 in the candidate pool and was never
    # shown to the judge. Embeddings are cached, so the widening costs
    # merge-prompt tokens only.
    merge_neighbours: int = 12
    merge_style: str = DEFAULT_MERGE_STYLE
    llm_model: str = "claude-opus-5"
    llm_effort: str = "high"
    llm_max_tokens: int = 16000
    # Der zweite API-Weg (kg/llm.py, 2026-08-31). "anthropic" ist der Default
    # und damit das Verhalten vor dem EU-Umbau; "chat_completions" spricht
    # jeden OpenAI-kompatiblen Endpunkt an. `llm_url` und `llm_api_key_env`
    # gelten nur im zweiten Modus, `llm_reasoning_effort` wird nur gesendet,
    # wenn es gesetzt ist. Der Schlüssel selbst steht NIE in der config.toml —
    # hier steht nur der NAME seiner Umgebungsvariablen.
    llm_api_mode: str = "anthropic"
    llm_url: str = ""
    llm_api_key_env: str = ""
    llm_reasoning_effort: str = ""
    # Embeddings: OpenRouter, OpenAI-compatible endpoint (spec 6.2). Cloud is
    # explicitly fine here; the cache makes re-runs free and offline.
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_url: str = "https://openrouter.ai/api/v1/embeddings"
    # Wie bei `llm_api_key_env`: nur der NAME der Umgebungsvariablen, nie der
    # Schlüssel. Leer = OPENROUTER_API_KEY, also unverändert.
    embedding_api_key_env: str = ""
    # Replaces the old `default_min_mentions` (a threshold on mention count):
    # spec 2026-08-29 found the threshold an indirect proxy for the real
    # constraint, how many term labels fit on the wall before they collide or
    # shrink below reading size. This is a direct cap on term count instead —
    # a different setting, not a reinterpretation, so an existing database's
    # `min_mentions` value is never read as a `max_terms` value (kg/store.py
    # seeds this key fresh via set_setting_default, spec §4/§6).
    default_max_terms: int = 32
    # The mode the wall opens in on a FRESH database. D4 (2026-08-19) opened on
    # the whole net; revised 2026-08-26 (Birk) once the automatic traversal
    # stopped being a sideways slide and became a tour from term to term —
    # surfaces A and C should both be roaming by default, and a station that
    # comes up motionless reads as broken rather than as "fit to screen".
    # Only a default: the operator's live setting is persisted and wins on
    # every restart (spec 7, 10.5).
    default_camera_mode: str = "pan"
    portrait_size: int = 512
    #: Wie lange bei einem AUSFALL DES ANBIETERS weiterversucht wird, in
    #: Sekunden (Birk, 2026-09-01: „die retries wenn keine antwort kommt von
    #: infomaniak muessen auch in den script code rein").
    #:
    #: Anlass: An dem Abend war Infomaniak ZWEIMAL komplett weg, rund 5 und
    #: rund 2 Minuten, HTTP 503 auf allen Pfaden gleichzeitig -- Analyse,
    #: Embeddings und Spracherkennung. Die Wiederholung, die es gab, lief
    #: ohne jede Pause: zwei Versuche gegen einen 503, der nach 0,1 s
    #: zurueckkommt, waren in 0,2 s aufgebraucht. Ein Interview in diesem
    #: Fenster war verloren, und die Person haette als leere Scheibe an der
    #: Wand gestanden.
    #:
    #: 300 s deckt beide gemessenen Ausfaelle mit Reserve. Es blockiert die
    #: Station nicht: die Auswertung laeuft in einem eigenen Thread
    #: (`kg.core`, `asyncio.to_thread`), Wand und Aufnahme laufen weiter.
    #: Gilt NUR fuer Ausfaelle -- eine schlechte Antwort wird weiterhin
    #: sofort und ohne Pause wiederholt.
    #:
    #: 🔴 Das WECKWORT bekommt das ausdruecklich NICHT (kg/stop_intent.py):
    #: dort haengt ein Ja/Nein im heissen Pfad einer laufenden Aufnahme an
    #: einem 6-Sekunden-Budget.
    llm_retry_budget_s: float = 300.0

    server_host: str = "127.0.0.1"
    server_port: int = 8800
    anthropic_api_key: str | None = None
    telegram_token: str | None = None
    openrouter_api_key: str | None = None

    @property
    def llm_api_key(self) -> str | None:
        """Der Schlüssel für den Pipeline-Client.

        Ohne `llm_api_key_env` der Anthropic-Schlüssel wie bisher; mit ihm der
        Inhalt genau dieser Umgebungsvariablen. Fehlt sie, ist das Ergebnis
        `None` und der Fehler fällt beim Aufruf mit klarer Meldung (kg.llm) —
        nicht beim Laden der Konfiguration, damit `kg --no-stt` und die Tests
        ohne jeden Schlüssel starten.
        """
        if self.llm_api_key_env:
            return os.environ.get(self.llm_api_key_env)
        return self.anthropic_api_key

    @property
    def wake_word_llm_api_key(self) -> str | None:
        """Dasselbe für den kleinen Client hinter dem Wake-Word."""
        if self.wake_word_llm_api_key_env:
            return os.environ.get(self.wake_word_llm_api_key_env)
        return self.anthropic_api_key

    @property
    def embedding_api_key(self) -> str | None:
        """Dasselbe für den Embedding-Endpunkt. Leer = OpenRouter wie bisher."""
        if self.embedding_api_key_env:
            return os.environ.get(self.embedding_api_key_env)
        return self.openrouter_api_key

    @property
    def db_path(self) -> Path:
        return self.data_dir / "kg.db"

    @property
    def embedding_cache_path(self) -> Path:
        # Deliberately in data_dir, not in a run directory: simulation runs wipe
        # their own db but must keep the embedding cache (spec 6.2).
        return self.data_dir / "embeddings.sqlite3"

    @property
    def graph_json_path(self) -> Path:
        return self.data_dir / "graph.json"

    @property
    def transcript_log_path(self) -> Path:
        return self.data_dir / "transcript.jsonl"

    @property
    def photo_dir(self) -> Path:
        return self.data_dir / "photos"

    @property
    def portrait_dir(self) -> Path:
        return self.data_dir / "portraits"

    def __post_init__(self) -> None:
        # Directories exist as soon as a Config exists — the server mounts
        # portrait_dir at import time and every task constructs Config directly.
        for directory in (self.data_dir, self.photo_dir, self.portrait_dir):
            directory.mkdir(parents=True, exist_ok=True)


_FIELD_NAMES = {
    "stt_url",
    "stt_probe_takt_s",
    "telegram_chat_id",
    "interview_timeout_s",
    "stop_phrases",
    "wake_word",
    "wake_word_llm",
    "wake_word_llm_model",
    "wake_word_llm_timeout_s",
    "wake_word_llm_api_mode",
    "wake_word_llm_url",
    "wake_word_llm_api_key_env",
    "wake_word_llm_reasoning_effort",
    "terms_per_interview",
    "merge_neighbours",
    "merge_style",
    "llm_model",
    "llm_effort",
    "llm_max_tokens",
    "llm_api_mode",
    "llm_url",
    "llm_api_key_env",
    "llm_reasoning_effort",
    "embedding_model",
    "embedding_url",
    "embedding_api_key_env",
    "default_max_terms",
    "default_camera_mode",
    "portrait_size",
    "llm_retry_budget_s",
    "server_host",
    "server_port",
}


def load_config(path: Path | None = None) -> Config:
    path = Path(path) if path else Path("config.toml")
    raw: dict = {}
    if path.exists():
        raw = tomllib.loads(path.read_text(encoding="utf-8"))

    base = path.parent.resolve()
    data_dir = (base / raw.get("data_dir", "data")).resolve()

    kwargs = {k: v for k, v in raw.items() if k in _FIELD_NAMES}
    return Config(
        data_dir=data_dir,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        telegram_token=os.environ.get("KG_TELEGRAM_TOKEN"),
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY"),
        **kwargs,
    )
