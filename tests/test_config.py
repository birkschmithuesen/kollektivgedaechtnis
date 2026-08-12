from pathlib import Path

from kg.config import Config, load_config


def test_load_config_reads_toml_and_resolves_paths(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
        data_dir = "state"
        stt_url = "http://127.0.0.1:5051"
        interview_timeout_s = 900
        terms_per_interview = 5
        stop_phrases = ["Interview beendet", "Aufnahme beenden"]
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("KG_TELEGRAM_TOKEN", "123:abc")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    cfg = load_config(cfg_file)

    assert isinstance(cfg, Config)
    assert cfg.data_dir == (tmp_path / "state").resolve()
    assert cfg.db_path == (tmp_path / "state" / "kg.db").resolve()
    assert cfg.graph_json_path == (tmp_path / "state" / "graph.json").resolve()
    assert cfg.photo_dir == (tmp_path / "state" / "photos").resolve()
    assert cfg.stt_url == "http://127.0.0.1:5051"
    assert cfg.interview_timeout_s == 900
    assert cfg.terms_per_interview == 5
    assert cfg.stop_phrases == ["Interview beendet", "Aufnahme beenden"]
    assert cfg.anthropic_api_key == "sk-test"
    assert cfg.telegram_token == "123:abc"
    assert cfg.openrouter_api_key == "sk-or-test"


def test_defaults_apply_when_keys_missing(tmp_path, monkeypatch):
    # Must not depend on what happens to be exported in the shell.
    for name in ("ANTHROPIC_API_KEY", "KG_TELEGRAM_TOKEN", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('data_dir = "state"\n', encoding="utf-8")

    cfg = load_config(cfg_file)

    assert cfg.llm_model == "claude-opus-5"
    assert cfg.llm_effort == "high"
    assert cfg.default_min_mentions == 1
    assert cfg.tail_seconds == 120
    assert cfg.merge_neighbours == 5
    assert cfg.anthropic_api_key is None
    assert cfg.openrouter_api_key is None
    # Embeddings come from OpenRouter, never from a local model (spec 6.2).
    assert cfg.embedding_url == "https://openrouter.ai/api/v1/embeddings"
    assert cfg.embedding_model == "openai/text-embedding-3-small"


def test_data_dir_is_created(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('data_dir = "state"\n', encoding="utf-8")

    cfg = load_config(cfg_file)

    assert cfg.data_dir.is_dir()
    assert cfg.photo_dir.is_dir()
    assert cfg.portrait_dir.is_dir()


def test_embedding_cache_lives_outside_the_run_directory(tmp_path):
    """The cache must survive `rm -rf out/` between simulation runs (spec 6.2)."""
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('data_dir = "state"\n', encoding="utf-8")

    cfg = load_config(cfg_file)

    assert cfg.embedding_cache_path == (tmp_path / "state" / "embeddings.sqlite3").resolve()
