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
        guiding_question = "Wie leben und bauen wir in zehn Jahren?"
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
    assert cfg.guiding_question == "Wie leben und bauen wir in zehn Jahren?"
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


def test_the_example_config_loads(tmp_path, monkeypatch):
    """A template that does not parse is a 9 a.m. failure, so it is tested."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    target = tmp_path / "config2.toml"
    target.write_text(
        Path("config2.example.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )

    cfg = load_dream_config(target)

    assert cfg.tool1_url.startswith("http://")
    assert cfg.guiding_question
    assert cfg.visual_register
