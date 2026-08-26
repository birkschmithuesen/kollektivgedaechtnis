"""Tool 2's own configuration. Secrets come from the environment, never here.

Deliberately a SEPARATE file from Tool 1's `config.toml`, not a section inside
it: Tool 2 runs on its own machine (spec §9), so a shared file would describe a
sharing that does not exist.

Two kinds of value live here and they must not be confused:

* `guiding_question` and `visual_register` are set in the morning and are
  **never** runtime-adjustable (spec §7). Changing the question mid-day destroys
  exactly the comparability the history strip exists for.
* the `default_*` fields only SEED the store on a fresh database. After that the
  operator UI owns them and a restart must restore the operator's value, not the
  file's — the same `set_setting_default` discipline Tool 1 uses for
  `default_min_mentions`.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

# PLACEHOLDER. The wording is decided by Birk at Task 16, from sentences the
# calibration run prints — not chosen here (spec §10, brainstorm §7). It must
# stay wide enough to carry all three interview themes: future of building,
# AI in building, new forms of living together.
DEFAULT_GUIDING_QUESTION = "Wie leben und bauen wir in zehn Jahren?"

# PLACEHOLDER. The register is decided by Birk AT IMAGES at Task 15, not in
# words (spec §10, brainstorm §10). This starting value describes the register
# of the approved rendering kollektivtraum-screen_v2_2026-08-16.png.
# „keine Schrift im Bild" is load-bearing, not decoration: the sentence is a
# separate displayed artefact (spec §5.2) and text rendered inside the image
# would compete with it.
DEFAULT_VISUAL_REGISTER = (
    "Malerisch und atmosphärisch, weiche Übergänge, gedämpfte Farbigkeit, "
    "diffuses Licht, sichtbarer Pinselduktus. Kein Fotorealismus, kein "
    "Architektur-Rendering, keine Schrift im Bild."
)


@dataclass(frozen=True)
class DreamConfig:
    data_dir: Path

    # -- Tool 1, over the network only (spec §2, §9) ------------------------
    tool1_url: str = "http://127.0.0.1:8800"
    poll_interval_s: float = 5.0
    fetch_timeout_s: float = 10.0

    # -- the trigger (spec §4.1, calibrated at Task 16) ---------------------
    min_interval_s: int = 240

    # -- the dream (spec §5, calibrated at Tasks 15/16) ---------------------
    contradiction_min_persons: int = 6
    guiding_question: str = DEFAULT_GUIDING_QUESTION
    visual_register: str = DEFAULT_VISUAL_REGISTER

    # -- stage 1 (spec §5.1) ------------------------------------------------
    condense_model: str = "claude-opus-5"
    condense_effort: str = "high"
    condense_max_tokens: int = 16000

    # -- stage 2 (spec §5.2; the endpoint shape is verified at Task 8) ------
    image_model: str = "google/gemini-3-pro-image"
    image_url: str = "https://openrouter.ai/api/v1/chat/completions"
    image_aspect_ratio: str = "16:9"
    image_timeout_s: float = 180.0

    # -- display start values, owned by the operator UI afterwards (spec §7)
    default_question_visible: bool = True
    default_question_seconds: int = 0  # 0 = permanent
    default_fade_ms: int = 1200  # spec §6: cross-fade, default 1.2 s
    default_strip_ratio: float = 0.22
    default_typewriter: bool = False  # spec §6: Birk decides visually on site

    # -- Tool 2's own server ------------------------------------------------
    server_host: str = "127.0.0.1"
    server_port: int = 8810

    anthropic_api_key: str | None = None
    openrouter_api_key: str | None = None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "dreams.sqlite3"

    @property
    def image_dir(self) -> Path:
        return self.data_dir / "images"

    @property
    def graph_url(self) -> str:
        """The one URL Tool 2 ever calls on Tool 1 (spec §2, §4.1)."""
        return f"{self.tool1_url.rstrip('/')}/graph.json"

    def __post_init__(self) -> None:
        # Directories exist as soon as a DreamConfig exists — the server mounts
        # image_dir at import time, exactly as Tool 1's Config does for
        # portrait_dir.
        for directory in (self.data_dir, self.image_dir):
            directory.mkdir(parents=True, exist_ok=True)


_FIELD_NAMES = {
    "tool1_url",
    "poll_interval_s",
    "fetch_timeout_s",
    "min_interval_s",
    "contradiction_min_persons",
    "guiding_question",
    "visual_register",
    "condense_model",
    "condense_effort",
    "condense_max_tokens",
    "image_model",
    "image_url",
    "image_aspect_ratio",
    "image_timeout_s",
    "default_question_visible",
    "default_question_seconds",
    "default_fade_ms",
    "default_strip_ratio",
    "default_typewriter",
    "server_host",
    "server_port",
}


def load_dream_config(path: Path | None = None) -> DreamConfig:
    path = Path(path) if path else Path("config2.toml")
    raw: dict = {}
    if path.exists():
        raw = tomllib.loads(path.read_text(encoding="utf-8"))

    base = path.parent.resolve()
    data_dir = (base / raw.get("data_dir", "dream-data")).resolve()

    kwargs = {k: v for k, v in raw.items() if k in _FIELD_NAMES}
    return DreamConfig(
        data_dir=data_dir,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY"),
        **kwargs,
    )
