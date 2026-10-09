import yaml

from config_loader import Config


def test_env_overrides_support_stt_tts_and_memory(monkeypatch):
    monkeypatch.setenv("STT_DEVICE", "cuda")
    monkeypatch.setenv("STT_LANGUAGE", "ko")
    monkeypatch.setenv("STT_MODEL_SIZE", "medium")
    monkeypatch.setenv("TTS_VOICE", "ko-KR-SunHiNeural")
    monkeypatch.setenv("TTS_BACKEND", "gemini_tts")
    monkeypatch.setenv("TTS_MODEL", "gemini-3.8-flash-lite-tts")
    monkeypatch.setenv("TTS_GEMINI_VOICE", "Kore")
    monkeypatch.setenv("MEMORY_DIR", "../.codex/personal_memory")
    monkeypatch.setenv("MEMORY_REFRESH_INTERVAL", "7")

    cfg = Config(config_file='missing.yaml')

    assert cfg.get("stt", "device") == "cuda"
    assert cfg.get("stt", "language") == "ko"
    assert cfg.get("stt", "model_size") == "medium"
    assert cfg.get("tts", "voice") == "ko-KR-SunHiNeural"
    assert cfg.get("tts", "backend") == "gemini_tts"
    assert cfg.get("tts", "model") == "gemini-3.8-flash-lite-tts"
    assert cfg.get("tts", "gemini_voice") == "Kore"
    assert cfg.get("memory", "memory_dir") == "../.codex/personal_memory"
    assert cfg.get("memory", "refresh_interval") == 7


def test_stt_device_override_takes_precedence_over_legacy_device(monkeypatch):
    monkeypatch.setenv("DEVICE", "cpu")
    monkeypatch.setenv("STT_DEVICE", "cuda")

    cfg = Config(config_file='missing.yaml')

    assert cfg.get("stt", "device") == "cuda"


def test_runtime_priority_env_overrides_are_normalized(monkeypatch):
    monkeypatch.setenv("LLM_PRIORITY", "api > ollama_cpu")
    monkeypatch.setenv("LLM_API_PRIORITY", "claude > gemini")
    monkeypatch.setenv("CONNECTION_PRIORITY", "wifi > wired")
    monkeypatch.setenv("PROCESSOR_PRIORITY", "cpu > gpu")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:1.5b")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")

    cfg = Config(config_file="missing.yaml")

    assert cfg.get("llm", "priority") == ["api", "ollama_cpu", "ollama", "other"]
    assert cfg.get("llm", "api_priority") == ["claude", "gemini", "chatgpt"]
    assert cfg.get("connection", "priority") == ["wifi", "wired"]
    assert cfg.get("runtime", "processor_priority") == ["cpu", "gpu"]
    assert cfg.get("llm", "ollama_model") == "qwen2.5:1.5b"
    assert cfg.get("llm", "api_models", "gemini") == "gemini-2.5-flash"


def test_telegram_env_overrides_are_loaded(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:abc")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "42,-100987654321")
    monkeypatch.setenv("TELEGRAM_MIN_INTERVAL_SEC", "1.5")
    monkeypatch.setenv("TELEGRAM_POLL_INTERVAL_SEC", "2.0")
    monkeypatch.setenv("TELEGRAM_LONG_POLL_TIMEOUT_SEC", "15.0")

    cfg = Config(config_file="missing.yaml")

    assert cfg.get("telegram", "enabled") is True
    assert cfg.get("telegram", "bot_token") == "123456:abc"
    assert cfg.get("telegram", "allowed_chat_ids") == ["42", "-100987654321"]
    assert cfg.get("telegram", "min_interval_sec") == 1.5
    assert cfg.get("telegram", "poll_interval_sec") == 2.0
    assert cfg.get("telegram", "long_poll_timeout_sec") == 15.0


def test_save_does_not_persist_environment_secrets_or_lose_other_edits(tmp_path, monkeypatch):
    env_paths = {
        "WEB_AUTH_TOKEN": ("web", "auth_token"),
        "GEMINI_API_KEY": ("llm", "gemini_api_key"),
        "OPENAI_API_KEY": ("llm", "openai_api_key"),
        "ANTHROPIC_API_KEY": ("llm", "anthropic_api_key"),
        "WEATHER_API_KEY": ("weather", "api_key"),
        "TAVILY_API_KEY": ("integrations", "search", "api_key"),
        "SLACK_BOT_TOKEN": ("integrations", "notify-slack", "api_key"),
        "GOOGLE_MAPS_API_KEY": ("integrations", "maps", "api_key"),
        "GOOGLE_CLIENT_SECRET": ("integrations", "calendar-google", "fields", "client_secret"),
        "GOOGLE_REFRESH_TOKEN": ("integrations", "calendar-google", "fields", "refresh_token"),
        "TELEGRAM_BOT_TOKEN": ("telegram", "bot_token"),
    }
    for env_key in env_paths:
        monkeypatch.setenv(env_key, f"synthetic-env-{env_key}")
    path = tmp_path / "config.yaml"
    path.write_text("llm:\n  model: previous-model\n", encoding="utf-8")

    cfg = Config(config_file=str(path))
    for env_key, keys in env_paths.items():
        assert cfg.get(*keys) == f"synthetic-env-{env_key}"
    cfg.config["llm"]["model"] = "edited-model"
    cfg.config["llm"]["api_priority"] = ["gemini", "claude", "chatgpt"]
    cfg.config["web"]["host"] = "127.0.0.1"
    cfg.save()

    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["llm"]["model"] == "edited-model"
    assert saved["llm"]["api_priority"] == ["gemini", "claude", "chatgpt"]
    assert saved["web"]["host"] == "127.0.0.1"
    for keys in env_paths.values():
        node = saved
        for key in keys[:-1]:
            node = node.get(key, {})
        assert keys[-1] not in node
    assert "synthetic-env-" not in path.read_text(encoding="utf-8")
    reloaded = Config(config_file=str(path))
    assert reloaded.get("llm", "model") == "edited-model"
    assert reloaded.get("llm", "api_priority") == ["gemini", "claude", "chatgpt"]
    assert reloaded.get("web", "host") == "127.0.0.1"


def test_save_preserves_explicit_yaml_secret_while_env_overrides_runtime(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text(
        "web:\n  auth_token: synthetic-file-token\n"
        "llm:\n  gemini_api_key: synthetic-file-key\n  model: old-model\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("WEB_AUTH_TOKEN", "synthetic-env-token")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-env-key")
    cfg = Config(config_file=str(path))
    assert cfg.get("web", "auth_token") == "synthetic-env-token"
    assert cfg.get("llm", "gemini_api_key") == "synthetic-env-key"
    cfg.config["llm"]["model"] = "new-model"
    cfg.save()

    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["web"]["auth_token"] == "synthetic-file-token"
    assert saved["llm"]["gemini_api_key"] == "synthetic-file-key"
    assert saved["llm"]["model"] == "new-model"
    assert "synthetic-env-" not in path.read_text(encoding="utf-8")
    reloaded = Config(config_file=str(path))
    assert reloaded.get("web", "auth_token") == "synthetic-env-token"
    assert reloaded.get("llm", "gemini_api_key") == "synthetic-env-key"


def test_dialogue_defaults_and_explicit_environment_language(tmp_path, monkeypatch):
    monkeypatch.delenv('STT_LANGUAGE', raising=False)
    monkeypatch.delenv('DIALOGUE_LANGUAGE', raising=False)
    cfg = Config(str(tmp_path/'missing.yaml'))
    assert cfg.get('dialogue','language') == 'auto'
    assert cfg.get('stt','language') == 'auto'
    assert cfg.get('dialogue','short_responses') is True
    assert cfg.get('dialogue','fast_model') == ''
    monkeypatch.setenv('STT_LANGUAGE', 'zh')
    cfg = Config(str(tmp_path/'missing.yaml'))
    assert cfg.get('dialogue','language') == 'zh'
    monkeypatch.setenv('DIALOGUE_LANGUAGE', 'es')
    monkeypatch.setenv('DIALOGUE_SHORT_RESPONSES','false')
    monkeypatch.setenv('DIALOGUE_FAST_MODEL','gemini-3.5-flash-lite')
    cfg = Config(str(tmp_path/'missing.yaml'))
    assert cfg.get('dialogue','language') == cfg.get('stt','language') == 'es'
    assert cfg.get('dialogue','short_responses') is False
    assert cfg.get('dialogue','fast_model') == 'gemini-3.5-flash-lite'


def test_config_save_failure_preserves_original_file_and_reports_failure(tmp_path, monkeypatch):
    import os
    import pytest
    path = tmp_path/'config.yaml'
    original = 'stt:\n  language: ko\n'
    path.write_text(original, encoding='utf-8')
    cfg = Config(str(path))
    cfg.config['stt']['language'] = 'es'
    def fail(*_args):
        raise OSError('synthetic-private-path')
    monkeypatch.setattr(os, 'replace', fail)
    with pytest.raises(OSError):
        cfg.save()
    assert path.read_text(encoding='utf-8') == original
    assert not list(tmp_path.glob('.*.tmp'))


def test_legacy_fixed_stt_yaml_remains_explicit_dialogue_choice(tmp_path, monkeypatch):
    monkeypatch.delenv('STT_LANGUAGE', raising=False)
    monkeypatch.delenv('DIALOGUE_LANGUAGE', raising=False)
    path = tmp_path/'config.yaml'
    path.write_text('stt:\n  language: ko\n', encoding='utf-8')
    assert Config(str(path)).get('dialogue','language') == 'ko'
