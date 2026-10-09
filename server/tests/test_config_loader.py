"""Tests for config_loader.Config class."""
import os
import tempfile
from pathlib import Path

import yaml

from config_loader import Config


def _write_yaml(path, data):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)


def test_defaults_when_no_yaml_exists(tmp_path):
    cfg = Config(config_file=str(tmp_path / "missing.yaml"))
    assert cfg.get("server", "port") == 5001
    assert cfg.get("stt", "language") == "auto"
    assert cfg.get("features", "robot_mode_enabled") is False
    assert cfg.get("robot", "controller") == "legacy_direct"
    assert cfg.get("robot", "servo", "count") == 2
    assert cfg.get("connection", "mode") == "auto"
    assert cfg.get("connection", "serial_baudrate") == 115200
    assert cfg.get("llm", "priority") == ["ollama", "api", "ollama_cpu", "other"]
    assert cfg.get("llm", "api_priority") == ["gemini", "claude", "chatgpt"]
    assert cfg.get("connection", "priority") == ["wired", "wifi"]
    assert cfg.get("runtime", "processor_priority") == ["gpu", "cpu"]


def test_load_yaml_overrides_defaults(tmp_path):
    yaml_path = tmp_path / "config.yaml"
    _write_yaml(yaml_path, {"server": {"port": 9999}})
    cfg = Config(config_file=str(yaml_path))
    assert cfg.get("server", "port") == 9999
    # non-overridden default preserved
    assert cfg.get("server", "host") == "0.0.0.0"


def test_env_overrides_yaml(tmp_path, monkeypatch):
    yaml_path = tmp_path / "config.yaml"
    _write_yaml(yaml_path, {"server": {"port": 8000}})
    monkeypatch.setenv("SERVER_PORT", "7777")
    cfg = Config(config_file=str(yaml_path))
    assert cfg.get("server", "port") == 7777


def test_env_serial_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("SERIAL_PORT", "/dev/cu.usbserial-test")
    monkeypatch.setenv("SERIAL_BAUDRATE", "1500000")
    cfg = Config(config_file=str(tmp_path / "missing.yaml"))
    assert cfg.get("connection", "serial_port") == "/dev/cu.usbserial-test"
    assert cfg.get("connection", "serial_baudrate") == 1500000


def test_merge_config_deep():
    cfg = Config.__new__(Config)
    base = {"a": {"b": 1, "c": 2}}
    cfg._merge_config(base, {"a": {"b": 99}})
    assert base == {"a": {"b": 99, "c": 2}}


def test_get_returns_default_for_missing_key(tmp_path):
    cfg = Config(config_file=str(tmp_path / "missing.yaml"))
    assert cfg.get("nonexistent", "key", default="fallback") == "fallback"


def test_section_getters(tmp_path):
    cfg = Config(config_file=str(tmp_path / "missing.yaml"))
    assert "port" in cfg.get_server_config()
    assert "model_size" in cfg.get_stt_config()
    assert "provider" in cfg.get_llm_config()
    assert "voice" in cfg.get_tts_config()
    assert "name" in cfg.get_assistant_config()
    assert "robot_mode_enabled" in cfg.get_features_config()
    assert "controller" in cfg.get_robot_config()
    assert "api_key" in cfg.get_weather_config()
    assert "max_history" in cfg.get_context_config()
    assert "enabled" in cfg.get_emotion_config()
    assert "level" in cfg.get_logging_config()
    assert "enabled" in cfg.get_voice_id_config()


def test_save_and_reload(tmp_path):
    yaml_path = tmp_path / "config.yaml"
    cfg = Config(config_file=str(yaml_path))
    cfg.config["server"]["port"] = 1234
    cfg.save()

    cfg2 = Config(config_file=str(yaml_path))
    assert cfg2.get("server", "port") == 1234


def test_env_weather_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("WEATHER_API_KEY", "test-key-123")
    cfg = Config(config_file=str(tmp_path / "missing.yaml"))
    assert cfg.get("weather", "api_key") == "test-key-123"


def test_env_voice_id_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICE_ID_ENABLED", "true")
    cfg = Config(config_file=str(tmp_path / "missing.yaml"))
    assert cfg.get("voice_id", "enabled") is True


def test_robot_controller_normalized_from_yaml(tmp_path):
    yaml_path = tmp_path / "config.yaml"
    _write_yaml(
        yaml_path,
        {
            "features": {"robot_mode_enabled": "yes"},
            "robot": {
                "controller": "COMPANION_UART",
                "servo": {"count": 9},
                "emotion": {"persist_sec": "1200"},
            },
        },
    )
    cfg = Config(config_file=str(yaml_path))
    assert cfg.get("features", "robot_mode_enabled") is True
    assert cfg.get("robot", "controller") == "companion_uart"
    assert cfg.get("robot", "transport") == "companion"
    assert cfg.get("robot", "servo", "count") == 4
    assert cfg.get("robot", "emotion", "persist_sec") == 1200
