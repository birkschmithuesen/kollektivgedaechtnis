"""Tool 2's own configuration. Secrets come from the environment, never here.

Deliberately a SEPARATE file from Tool 1's `config.toml`, not a section inside
it: Tool 2 runs on its own machine (spec §9), so a shared file would describe a
sharing that does not exist.

Two kinds of value live here and they must not be confused:

* `visual_register` is set in the morning and is **never** runtime-adjustable
  (spec §7). A register that wanders mid-day destroys exactly the
  comparability the history strip exists for.
* the `default_*` fields only SEED the store on a fresh database. After that the
  operator UI owns them and a restart must restore the operator's value, not the
  file's — the same `set_setting_default` discipline Tool 1 uses for
  `default_min_mentions`.

**`guiding_question` ist am 2026-08-31 ersatzlos entfallen**, mit ihm
`default_question_visible` und `default_question_seconds`. Seit dem
2026-08-28 erreichte die Frage kein Modell mehr (`kg2/condense.py`) und
steuerte nur noch eine Überschrift auf dem Schirm — eine Anzeige ohne
Funktion, die zudem eine vierte Frage zeigte, die den Gästen nie gestellt
wurde: gefragt wird nach `kg.extraction.GUIDING_QUESTIONS` in Tool 1, und die
sind andere. Birk an der Station: „Ja, ganz weg." Ein `guiding_question` in
einer bestehenden `config2.toml` ist damit ein unbekannter Schlüssel — und
`load_dream_config` überliest unbekannte Schlüssel seit jeher (siehe
`_FIELD_NAMES` unten), der Start scheitert daran also nicht.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

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
    # Zweiter Renderpfad (2026-08-31): "openrouter" ist der Default und damit
    # der gemessene Weg von vorher, "bfl" spricht Black Forest Labs' EU-Endpunkt
    # an. Im bfl-Modus ist `image_url` die BASIS ("https://api.eu.bfl.ai/v1")
    # und `image_model` der Endpunkt darunter ("flux-pro-1.1") — dort ist das
    # Modell der Pfad, nicht ein Feld im Body.
    #
    # Dritter Modus "bfl_proxy" (2026-08-31): derselbe Anbieter, aber über den
    # lokalen Loopback-Broker. `image_url` ist dann die Proxy-Adresse
    # ("http://127.0.0.1:8791/render"), `image_model` der BFL-Endpunktname,
    # und `image_api_key_env` bleibt LEER — der Schlüssel liegt ausschließlich
    # im Proxy (uid bflproxy), nie im Stationsprozess.
    #
    # Auf dem vServer ist "bfl_proxy" der einzige funktionierende BFL-Weg: uid
    # birk hat per nftables keinen Egress zu bfl.ai, und BFL verlangt eine
    # Wildcard-Freigabe (`delivery.*.bfl.ai`), die nftables nicht leisten kann.
    # Begründung und Messungen: ~/.hermes/profiles/birk/docs/
    # bfl-wildcard-egress-loesungsweg.md. Auf einer Maschine ohne diesen Filter
    # funktioniert "bfl" direkt — beide bleiben deshalb erhalten.
    image_api_mode: str = "openrouter"
    # Nur der NAME der Umgebungsvariablen, nie der Schlüssel selbst. Leer =
    # OPENROUTER_API_KEY wie bisher; für BFL: "BFL_API_KEY".
    image_api_key_env: str = ""
    # Nur im bfl-Modus benutzt: dort reist die Bildgröße als Pixel, nicht als
    # Seitenverhältnis. 1344x768 ist 16:9 in Vielfachen von 32, was die
    # flux-Modelle erwarten; `image_aspect_ratio` bleibt der OpenRouter-Weg.
    image_width: int = 1344
    image_height: int = 768

    # -- display start values, owned by the operator UI afterwards (spec §7)
    default_fade_ms: int = 1200  # spec §6: cross-fade, default 1.2 s
    default_strip_ratio: float = 0.22
    # 40 gleichzeitige Träume erwiesen sich als zu viel (Birk, 2026-08-26, an
    # den gerenderten Vergleichen aus sim.dream_prerender): der Streifen zeigt
    # ab hier nur noch die N NEUESTEN, der Rest bleibt in dreams.sqlite3.
    default_strip_max: int = 10
    default_typewriter: bool = False  # spec §6: Birk decides visually on site

    # -- Tool 2's own server ------------------------------------------------
    server_host: str = "127.0.0.1"
    server_port: int = 8810

    anthropic_api_key: str | None = None
    openrouter_api_key: str | None = None

    @property
    def image_api_key(self) -> str | None:
        """Der Schlüssel für Stufe 2. Ohne `image_api_key_env` wie bisher der
        von OpenRouter; sonst der Inhalt genau dieser Variablen. Fehlt sie,
        ist das Ergebnis `None` und der Fehler fällt beim Rendern mit klarer
        Meldung (kg2.imagegen) — nicht schon beim Laden der Konfiguration,
        damit `kg2 --no-watch` ohne jeden Schlüssel startet.
        """
        if self.image_api_key_env:
            return os.environ.get(self.image_api_key_env)
        return self.openrouter_api_key

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
    "visual_register",
    "condense_model",
    "condense_effort",
    "condense_max_tokens",
    "image_model",
    "image_url",
    "image_aspect_ratio",
    "image_timeout_s",
    "image_api_mode",
    "image_api_key_env",
    "image_width",
    "image_height",
    "default_fade_ms",
    "default_strip_ratio",
    "default_strip_max",
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

    # Nur bekannte Schlüssel, alles andere wird überlesen statt zu werfen. Das
    # ist der Grund, warum eine schon vorhandene config2.toml vom
    # Ausstellungsrechner mit dem am 2026-08-31 entfallenen `guiding_question`
    # weiterhin startet: der Schlüssel landet gar nicht erst in kwargs, wo er
    # ein unerwartetes Argument für DreamConfig wäre. Ein Startfehler am
    # Ausstellungsmorgen wegen einer Zeile, die nichts mehr tut, wäre die
    # teuerste denkbare Art, diese Entfernung zu melden.
    kwargs = {k: v for k, v in raw.items() if k in _FIELD_NAMES}
    return DreamConfig(
        data_dir=data_dir,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY"),
        **kwargs,
    )
