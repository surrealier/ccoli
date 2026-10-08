from config_loader import Config


def test_local_dashboard_environment_overrides(monkeypatch):
    monkeypatch.setenv('WEB_HOST', '127.0.0.1')
    monkeypatch.setenv('WEB_PORT', '8005')
    monkeypatch.setenv('WEB_AUTH_TOKEN', 'test-token-only')
    cfg = Config(config_file='missing.yaml')
    assert cfg.get('web', 'host') == '127.0.0.1'
    assert cfg.get('web', 'port') == 8005
    assert cfg.get('web', 'auth_token') == 'test-token-only'

def test_latest_stt_default_is_turbo():
    from config_loader import Config
    assert Config.DEFAULT_CONFIG['stt']['model_size'] == 'turbo'


def test_project_voice_config_keeps_api_first_after_normal_start():
    from pathlib import Path

    import yaml

    cfg_path = Path(__file__).resolve().parents[1] / "config.yaml"
    llm = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))["llm"]
    assert llm["provider"] == "gemini"
    assert llm["priority"][:2] == ["api", "ollama"]
    assert llm["api_priority"][0] == "gemini"


def test_project_standard_start_enables_agent_with_local_dashboard():
    from pathlib import Path

    import yaml

    cfg_path = Path(__file__).resolve().parents[1] / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert cfg["agent"]["enabled"] is True
    assert cfg["web"]["host"] == "127.0.0.1"
    assert cfg["connection"]["mode"] == "wired"
