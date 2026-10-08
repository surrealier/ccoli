"""Tests for the interactive setup/install flow helpers."""
import os
import sys

import yaml


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ccoli.cli import (  # noqa: E402
    DEFAULT_LLM_MODELS,
    _apply_setup_choice,
    _build_setup_choice,
    _cmd_config_integration_set,
    _cmd_config_integration_test,
    _default_stt_device,
    build_parser,
)


def test_parser_has_setup_command():
    parser = build_parser()
    choices = parser._subparsers._group_actions[0].choices
    assert "setup" in choices


def test_parser_setup_accepts_connection_options():
    parser = build_parser()
    args = parser.parse_args(
        [
            "setup",
            "--install-target",
            "api",
            "--provider",
            "gemini",
            "--connection-mode",
            "wifi",
            "--wifi-ssid",
            "OfficeLAN",
            "--wifi-password",
            "secret-pass",
            "--server-ip",
            "192.168.0.20",
            "--server-port",
            "5009",
            "--skip-install",
            "--yes",
        ]
    )

    assert args.connection_mode == "wifi"
    assert args.wifi_ssid == "OfficeLAN"
    assert args.wifi_password == "secret-pass"
    assert args.server_ip == "192.168.0.20"
    assert args.server_port == 5009


def test_default_stt_device_uses_cpu_on_mac(monkeypatch):
    monkeypatch.setattr("ccoli.cli.sys.platform", "darwin")
    assert _default_stt_device() == "cpu"


def test_build_setup_choice_for_ollama():
    choice = _build_setup_choice(
        install_target="ollama",
        provider=None,
        model=None,
        api_key=None,
        stt_device="cpu",
        connection_mode="wired",
        wifi_ssid=None,
        wifi_password=None,
        server_ip=None,
        server_port=None,
    )

    assert choice.install_target == "ollama"
    assert choice.provider == "ollama"
    assert choice.model == DEFAULT_LLM_MODELS["ollama"]
    assert choice.install_extras == ("runtime",)
    assert choice.api_key is None
    assert choice.connection_mode == "wired"
    assert choice.server_port == 5001
    assert choice.wifi_ssid == ""
    assert choice.wifi_password is None
    assert choice.server_ip == ""


def test_build_setup_choice_for_gemini_api():
    choice = _build_setup_choice(
        install_target="api",
        provider="gemini",
        model=None,
        api_key="gemini-secret",
        stt_device="cpu",
        connection_mode="wifi",
        wifi_ssid="OfficeLAN",
        wifi_password="secret-pass",
        server_ip="192.168.0.20",
        server_port=5009,
    )

    assert choice.install_target == "api"
    assert choice.provider == "gemini"
    assert choice.model == DEFAULT_LLM_MODELS["gemini"]
    assert choice.install_extras == ("runtime",)
    assert choice.api_key == "gemini-secret"
    assert choice.connection_mode == "wifi"
    assert choice.wifi_ssid == "OfficeLAN"
    assert choice.wifi_password == "secret-pass"
    assert choice.server_ip == "192.168.0.20"
    assert choice.server_port == 5009


def test_build_setup_choice_requires_wifi_details():
    try:
        _build_setup_choice(
            install_target="api",
            provider="gemini",
            model=None,
            api_key=None,
            stt_device="cpu",
            connection_mode="wifi",
            wifi_ssid=None,
            wifi_password="secret-pass",
            server_ip="192.168.0.20",
            server_port=None,
        )
    except ValueError as exc:
        assert "wifi_ssid" in str(exc)
    else:
        raise AssertionError("expected wifi setup to require ssid")


def test_apply_setup_choice_updates_config_and_env(tmp_path):
    root = tmp_path
    server_dir = root / "server"
    server_dir.mkdir(parents=True)
    (server_dir / "config.yaml").write_text("server:\n  port: 5001\n", encoding="utf-8")

    choice = _build_setup_choice(
        install_target="api",
        provider="gemini",
        model=None,
        api_key="gemini-secret",
        stt_device="cpu",
        connection_mode="wifi",
        wifi_ssid="OfficeLAN",
        wifi_password="secret-pass",
        server_ip="192.168.0.20",
        server_port=5009,
    )

    config_path, env_path = _apply_setup_choice(root, choice)

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config["setup"]["install_target"] == "api"
    assert config["stt"]["device"] == "cpu"
    assert config["llm"]["provider"] == "gemini"
    assert config["llm"]["model"] == DEFAULT_LLM_MODELS["gemini"]
    assert config["llm"]["base_url"] == ""
    assert config["server"]["port"] == 5009
    assert config["connection"]["mode"] == "wifi"
    assert env_path.read_text(encoding="utf-8").strip() == "GEMINI_API_KEY=gemini-secret"

    secrets_path = root / "arduino" / "atom_echo_m5stack_esp32_ino" / "device_secrets.h"
    secrets_text = secrets_path.read_text(encoding="utf-8")
    assert 'CONNECTION_MODE = "wifi"' in secrets_text
    assert 'SSID = "OfficeLAN"' in secrets_text
    assert 'PASS = "secret-pass"' in secrets_text
    assert 'SERVER_IP = "192.168.0.20"' in secrets_text
    assert "SERVER_PORT = 5009" in secrets_text


def test_calendar_integration_set_writes_oauth_to_env(tmp_path, monkeypatch):
    root = tmp_path
    server_dir = root / "server"
    server_dir.mkdir(parents=True)
    (server_dir / "config.yaml").write_text("integrations:\n  calendar-google:\n    enabled: false\n", encoding="utf-8")
    monkeypatch.setattr("ccoli.cli._repo_root", lambda: root)

    result = _cmd_config_integration_set(
        "calendar-google",
        api_key=None,
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        calendar_id="primary",
        time_zone="Asia/Seoul",
    )

    assert result == 0
    config = yaml.safe_load((server_dir / "config.yaml").read_text(encoding="utf-8"))
    entry = config["integrations"]["calendar-google"]
    assert entry["enabled"] is True
    assert entry["fields"] == {"calendar_id": "primary", "time_zone": "Asia/Seoul"}
    env_text = (server_dir / ".env").read_text(encoding="utf-8")
    assert "GOOGLE_CLIENT_ID=client-id" in env_text
    assert "GOOGLE_CLIENT_SECRET=client-secret" in env_text
    assert "GOOGLE_REFRESH_TOKEN=refresh-token" in env_text

    assert _cmd_config_integration_test("calendar-google") == 0


def test_setup_api_defaults_match_runtime_defaults():
    from src.runtime_preferences import DEFAULT_API_MODELS

    for provider, expected in DEFAULT_API_MODELS.items():
        assert DEFAULT_LLM_MODELS[provider] == expected


def test_setup_local_default_matches_verified_runtime_model():
    from src.runtime_preferences import DEFAULT_OLLAMA_MODEL
    assert DEFAULT_LLM_MODELS['ollama'] == DEFAULT_OLLAMA_MODEL == 'qwen3.5:4b'


def test_cli_provider_selection_sets_matching_runtime_priority(tmp_path):
    from ccoli.cli import _configure_llm

    server_dir = tmp_path / "server"
    server_dir.mkdir()
    (server_dir / "config.yaml").write_text(
        "llm:\n  priority: [ollama, api, ollama_cpu, other]\n"
        "  api_priority: [gemini, claude, chatgpt]\n",
        encoding="utf-8",
    )

    path = _configure_llm(tmp_path, "claude", "claude-haiku-4-5-20251001", None, None)
    selected = yaml.safe_load(path.read_text(encoding="utf-8"))["llm"]
    assert selected["priority"][:2] == ["api", "ollama"]
    assert selected["api_priority"][0] == "claude"

    path = _configure_llm(tmp_path, "ollama", "qwen3.5:4b", None, None)
    selected = yaml.safe_load(path.read_text(encoding="utf-8"))["llm"]
    assert selected["priority"][:2] == ["ollama", "api"]


def test_cli_provider_selection_updates_model_table(tmp_path):
    from ccoli.cli import _configure_llm

    server_dir = tmp_path / "server"
    server_dir.mkdir()
    (server_dir / "config.yaml").write_text(
        "llm:\n  ollama_model: old-local\n"
        "  api_models:\n    gemini: old-gemini\n    claude: old-claude\n",
        encoding="utf-8",
    )

    path = _configure_llm(tmp_path, "gemini", "gemini-3.8-flash", None, None)
    selected = yaml.safe_load(path.read_text(encoding="utf-8"))["llm"]
    assert selected["api_models"]["gemini"] == "gemini-3.8-flash"

    path = _configure_llm(tmp_path, "ollama", "qwen3.5:4b", None, None)
    selected = yaml.safe_load(path.read_text(encoding="utf-8"))["llm"]
    assert selected["ollama_model"] == "qwen3.5:4b"
