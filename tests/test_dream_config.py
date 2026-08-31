from pathlib import Path

import pytest

from kg2.config import DreamConfig, load_dream_config


def test_load_reads_toml_and_resolves_paths(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config2.toml"
    cfg_file.write_text(
        """
        data_dir = "dream-state"
        tool1_url = "http://192.168.1.10:8800"
        poll_interval_s = 5.0
        min_interval_s = 240
        visual_register = "malerisch, atmosphaerisch, weich"
        server_host = "0.0.0.0"
        server_port = 8810
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    cfg = load_dream_config(cfg_file)

    assert isinstance(cfg, DreamConfig)
    assert cfg.data_dir == (tmp_path / "dream-state").resolve()
    assert cfg.db_path == (tmp_path / "dream-state" / "dreams.sqlite3").resolve()
    assert cfg.image_dir == (tmp_path / "dream-state" / "images").resolve()
    assert cfg.tool1_url == "http://192.168.1.10:8800"
    assert cfg.graph_url == "http://192.168.1.10:8800/graph.json"
    assert cfg.poll_interval_s == 5.0
    assert cfg.min_interval_s == 240
    assert cfg.visual_register == "malerisch, atmosphaerisch, weich"
    assert cfg.server_host == "0.0.0.0"
    assert cfg.server_port == 8810
    assert cfg.anthropic_api_key == "sk-test"
    assert cfg.openrouter_api_key == "sk-or-test"


def test_defaults_are_the_spec_values(tmp_path, monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    cfg_file = tmp_path / "config2.toml"
    cfg_file.write_text('data_dir = "dream-state"\n', encoding="utf-8")

    cfg = load_dream_config(cfg_file)

    # Spec §4.1 / §5.1 / §10 — the calibration START values, not final ones.
    assert cfg.poll_interval_s == 5.0
    assert cfg.min_interval_s == 240
    # Spec §5.1 / §5.2 — one model to reason about, one credential each.
    assert cfg.condense_model == "claude-opus-5"
    assert cfg.image_model == "google/gemini-3-pro-image"
    # Spec §3.1: the documented default stays localhost here too.
    assert cfg.server_host == "127.0.0.1"
    # Deliberately NOT 8800: both processes must be runnable on one box during
    # development without a port clash.
    assert cfg.server_port == 8810
    assert cfg.anthropic_api_key is None
    assert cfg.openrouter_api_key is None


def test_directories_are_created(tmp_path):
    cfg_file = tmp_path / "config2.toml"
    cfg_file.write_text('data_dir = "dream-state"\n', encoding="utf-8")

    cfg = load_dream_config(cfg_file)

    assert cfg.data_dir.is_dir()
    assert cfg.image_dir.is_dir()


def test_a_trailing_slash_on_tool1_url_does_not_double_up(tmp_path):
    cfg_file = tmp_path / "config2.toml"
    cfg_file.write_text(
        'data_dir = "d"\ntool1_url = "http://10.0.0.2:8800/"\n', encoding="utf-8"
    )

    assert load_dream_config(cfg_file).graph_url == "http://10.0.0.2:8800/graph.json"


def test_the_example_config_carries_no_credentials():
    """Same rule as Tool 1 (spec §2): keys come from the environment only."""
    text = Path("config2.example.toml").read_text(encoding="utf-8")

    # No assignment of a key-shaped field, and no key-shaped literal anywhere.
    assignments = [
        line.split("=")[0].strip()
        for line in text.splitlines()
        if "=" in line and not line.strip().startswith("#")
    ]
    assert "anthropic_api_key" not in assignments
    assert "openrouter_api_key" not in assignments
    for forbidden in ("sk-ant-", "sk-or-v1-"):
        assert forbidden not in text


def test_the_image_route_defaults_to_openrouter(tmp_path, monkeypatch):
    """Fallback-Regel: ohne neue Schlüssel rendert Stufe 2 wie bisher."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    cfg_file = tmp_path / "config2.toml"
    cfg_file.write_text('data_dir = "dream-state"\n', encoding="utf-8")

    cfg = load_dream_config(cfg_file)

    assert cfg.image_api_mode == "openrouter"
    assert cfg.image_url == "https://openrouter.ai/api/v1/chat/completions"
    assert cfg.image_api_key == "sk-or-test"


def test_the_image_route_can_be_switched_to_black_forest_labs(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("BFL_API_KEY", "bfl-key")
    cfg_file = tmp_path / "config2.toml"
    cfg_file.write_text(
        """
        data_dir = "dream-state"
        image_api_mode = "bfl"
        image_model = "flux-pro-1.1"
        image_url = "https://api.eu.bfl.ai/v1"
        image_api_key_env = "BFL_API_KEY"
        image_width = 1344
        image_height = 768
        """,
        encoding="utf-8",
    )

    cfg = load_dream_config(cfg_file)

    assert cfg.image_api_mode == "bfl"
    assert cfg.image_api_key == "bfl-key"
    assert (cfg.image_width, cfg.image_height) == (1344, 768)
    # Der Schlüssel steht nie in der Datei, nur der Name seiner Variablen.
    assert "bfl-key" not in cfg_file.read_text(encoding="utf-8")


def test_the_example_config_loads(tmp_path, monkeypatch):
    """A template that does not parse is a 9 a.m. failure, so it is tested."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    target = tmp_path / "config2.toml"
    target.write_text(
        Path("config2.example.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )

    cfg = load_dream_config(target)

    assert cfg.tool1_url.startswith("http://")
    assert cfg.visual_register


def test_a_config_with_the_removed_question_keys_still_starts(tmp_path):
    """Auf dem Ausstellungsrechner liegt eine `config2.toml`, die noch
    `guiding_question` (und die beiden Anzeige-Startwerte dazu) enthält — die
    drei Schlüssel sind am 2026-08-31 ersatzlos entfallen. Ein Startfehler am
    Ausstellungsmorgen wegen Zeilen, die nichts mehr tun, wäre die teuerste
    denkbare Art, diese Entfernung zu melden: `load_dream_config` überliest
    unbekannte Schlüssel, statt sie an DreamConfig durchzureichen, wo sie ein
    unerwartetes Argument wären."""
    cfg_file = tmp_path / "config2.toml"
    cfg_file.write_text(
        """
        data_dir = "dream-state"
        min_interval_s = 300
        guiding_question = "Wie wollen wir in zehn Jahren zusammen wohnen und bauen?"
        default_question_visible = true
        default_question_seconds = 0
        """,
        encoding="utf-8",
    )

    cfg = load_dream_config(cfg_file)

    # Die Datei wird geladen, der Rest der Datei wirkt weiterhin ...
    assert cfg.min_interval_s == 300
    # ... und die alten Schlüssel hinterlassen nichts, auch keinen stillen
    # Rest, den irgendwer später wieder anzeigen könnte.
    assert not hasattr(cfg, "guiding_question")
    assert not hasattr(cfg, "default_question_visible")
    assert not hasattr(cfg, "default_question_seconds")


# --- Stufe 1 auf einen zweiten Anbieter umschalten (2026-08-31) ------------

def test_condense_default_bleibt_anthropic():
    """Fallback-Regel: unveraenderte Config verhaelt sich wie vorher."""
    from kg2.config import DreamConfig
    f = DreamConfig.__dataclass_fields__
    assert f["condense_api_mode"].default == "anthropic"
    assert f["condense_url"].default == ""
    assert f["condense_api_key_env"].default == ""
    assert f["condense_reasoning_effort"].default == ""


def test_condense_api_key_faellt_auf_anthropic_zurueck():
    from kg2.config import DreamConfig
    from pathlib import Path
    c = DreamConfig(data_dir=Path("/tmp"), anthropic_api_key="anthropic-key")
    assert c.condense_api_key == "anthropic-key"


def test_condense_api_key_env_gewinnt(monkeypatch):
    from kg2.config import DreamConfig
    from pathlib import Path
    monkeypatch.setenv("MEIN_EU_KEY", "eu-key")
    c = DreamConfig(
        data_dir=Path("/tmp"),
        anthropic_api_key="anthropic-key",
        condense_api_key_env="MEIN_EU_KEY",
    )
    assert c.condense_api_key == "eu-key"


def test_condense_schalter_kommen_aus_der_toml(tmp_path):
    """Ohne Eintrag in _FIELD_NAMES waeren die Felder stumm wirkungslos."""
    from kg2.config import load_dream_config
    cfg = tmp_path / "c.toml"
    cfg.write_text(
        'data_dir = "d"\n'
        'condense_api_mode = "chat_completions"\n'
        'condense_url = "https://api.infomaniak.com/2/ai/110416/openai/v1/chat/completions"\n'
        'condense_api_key_env = "HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY"\n'
        'condense_reasoning_effort = "none"\n'
        'condense_model = "moonshotai/Kimi-K2.6"\n',
        encoding="utf-8",
    )
    c = load_dream_config(cfg)
    assert c.condense_api_mode == "chat_completions"
    assert c.condense_reasoning_effort == "none"
    assert c.condense_model == "moonshotai/Kimi-K2.6"
    assert "infomaniak" in c.condense_url
