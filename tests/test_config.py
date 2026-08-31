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
    assert cfg.default_max_terms == 32
    # Run 19c: 5 was too narrow — in 7 of 8 near-misses the concept's own node
    # sat at rank 7-56 in the candidate pool and never reached the judge.
    assert cfg.merge_neighbours == 12
    assert cfg.anthropic_api_key is None
    assert cfg.openrouter_api_key is None
    # Embeddings come from OpenRouter, never from a local model (spec 6.2).
    assert cfg.embedding_url == "https://openrouter.ai/api/v1/embeddings"
    assert cfg.embedding_model == "openai/text-embedding-3-small"
    # The bot's name, spoken in front of a stop phrase (Birk, 2026-08-30).
    assert cfg.wake_word == "Utopia"


def test_the_llm_gate_behind_the_wake_word_is_on_by_default_and_runs_cheap(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('data_dir = "state"\n', encoding="utf-8")

    cfg = load_config(cfg_file)

    assert cfg.wake_word_llm is True
    # Deliberately NOT the pipeline's model: one boolean does not need Opus.
    assert cfg.wake_word_llm_model != cfg.llm_model
    # Hard and short — this sits on the hot path of a running recording.
    assert 0 < cfg.wake_word_llm_timeout_s <= 10


def test_the_llm_gate_can_be_switched_off(tmp_path):
    """Off means exactly today's behaviour: mechanics only, never a call."""
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('data_dir = "state"\nwake_word_llm = false\n', encoding="utf-8")

    assert load_config(cfg_file).wake_word_llm is False


def test_the_wake_word_is_configurable_because_the_bot_can_be_renamed(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('data_dir = "state"\nwake_word = "Ada"\n', encoding="utf-8")

    assert load_config(cfg_file).wake_word == "Ada"


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


# --- der zweite LLM-Weg: Umschaltung ausschließlich über Konfiguration -----


def test_an_unchanged_config_stays_on_the_anthropic_route(tmp_path, monkeypatch):
    """Die Fallback-Regel als Test: ohne neue Schlüssel in der config.toml
    verhält sich die Station wie vor dem EU-Umbau."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anthropic")
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('data_dir = "state"\n', encoding="utf-8")

    cfg = load_config(cfg_file)

    assert cfg.llm_api_mode == "anthropic"
    assert cfg.llm_url == ""
    assert cfg.llm_api_key_env == ""
    assert cfg.llm_reasoning_effort == ""
    # Ohne eigene Env-Variable ist der Schlüssel weiter der von Anthropic.
    assert cfg.llm_api_key == "sk-anthropic"
    assert cfg.wake_word_llm_api_mode == "anthropic"
    assert cfg.wake_word_llm_api_key == "sk-anthropic"


def test_the_llm_route_switches_to_a_chat_completions_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anthropic")
    monkeypatch.setenv("HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY", "sk-infomaniak")
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
        data_dir = "state"
        llm_api_mode = "chat_completions"
        llm_model = "moonshotai/Kimi-K2.6"
        llm_url = "https://api.infomaniak.com/2/ai/110416/openai/v1/chat/completions"
        llm_api_key_env = "HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY"
        llm_reasoning_effort = "none"
        """,
        encoding="utf-8",
    )

    cfg = load_config(cfg_file)

    assert cfg.llm_api_mode == "chat_completions"
    assert cfg.llm_reasoning_effort == "none"
    # Der Schlüssel steht NIE in der Datei, nur der Name seiner Env-Variablen.
    assert "sk-infomaniak" not in cfg_file.read_text(encoding="utf-8")
    assert cfg.llm_api_key == "sk-infomaniak"


def test_the_wake_word_route_switches_independently_of_the_pipeline(tmp_path, monkeypatch):
    """Zwei getrennte Schalter, weil es zwei getrennte Modelle sind: eines
    verdichtet ein Interview, das andere entscheidet ein Ja/Nein im heißen
    Pfad. Wer nur einen umstellt, muss das genau so bekommen."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY", "sk-infomaniak")
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
        data_dir = "state"
        wake_word_llm_api_mode = "chat_completions"
        wake_word_llm_model = "google/gemma-4-31B-it"
        wake_word_llm_url = "https://api.infomaniak.com/2/ai/110416/openai/v1/chat/completions"
        wake_word_llm_api_key_env = "HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY"
        """,
        encoding="utf-8",
    )

    cfg = load_config(cfg_file)

    assert cfg.llm_api_mode == "anthropic"
    assert cfg.wake_word_llm_api_mode == "chat_completions"
    assert cfg.wake_word_llm_api_key == "sk-infomaniak"
    assert cfg.wake_word_llm_model == "google/gemma-4-31B-it"


def test_the_embedding_endpoint_switches_the_same_way(tmp_path, monkeypatch):
    """Der Embedder war schon immer OpenAI-kompatibel — nötig war nur, dass
    Modell, URL und Schlüssel gemeinsam woandershin zeigen können."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or")
    monkeypatch.setenv("HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY", "sk-infomaniak")
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('data_dir = "state"\n', encoding="utf-8")
    assert load_config(cfg_file).embedding_api_key == "sk-or"

    cfg_file.write_text(
        """
        data_dir = "state"
        embedding_model = "bge_multilingual_gemma2"
        embedding_url = "https://api.infomaniak.com/2/ai/110416/openai/v1/embeddings"
        embedding_api_key_env = "HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY"
        """,
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)

    assert cfg.embedding_model == "bge_multilingual_gemma2"
    assert cfg.embedding_url.startswith("https://api.infomaniak.com/")
    assert cfg.embedding_api_key == "sk-infomaniak"


def test_a_missing_key_env_variable_reads_as_no_key_not_as_a_crash(tmp_path, monkeypatch):
    """Fehlt die Variable, muss der Fehler beim Aufruf mit klarer Meldung
    kommen (kg.llm), nicht schon beim Laden der Konfiguration."""
    monkeypatch.delenv("GIBT_ES_NICHT", raising=False)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        'data_dir = "state"\nllm_api_key_env = "GIBT_ES_NICHT"\n', encoding="utf-8"
    )

    assert load_config(cfg_file).llm_api_key is None
