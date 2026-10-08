"""NFR §6.1 — Security tests: credential masking, log leak prevention."""
import logging
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ccoli.cli import _mask_secret, _upsert_env_var, _configure_llm
from config_loader import Config


# ── _mask_secret ─────────────────────────────────────────────

def test_mask_hides_middle():
    # 'sk-1234567890' len=14 → first3 + 8 stars + last3
    r = _mask_secret("sk-1234567890")
    assert r[:3] == "sk-"
    assert r[-3:] == "890"
    assert "*" in r


def test_mask_short_fully_masked():
    assert _mask_secret("abc") == "***"


# ── Config save / load ───────────────────────────────────────

def test_config_save_writes_yaml(tmp_path):
    p = tmp_path / "config.yaml"
    cfg = Config(config_file=str(p))
    cfg.config["weather"]["api_key"] = "test-key-123"
    cfg.save()
    content = p.read_text()
    assert "test-key-123" in content  # local file stores actual value


# ── _upsert_env_var log safety ───────────────────────────────

def test_upsert_env_var_no_log_leak(tmp_path, caplog):
    p = tmp_path / ".env"
    with caplog.at_level(logging.DEBUG):
        _upsert_env_var(p, "SECRET_KEY", "super-secret-value-xyz")
    assert "super-secret-value-xyz" not in caplog.text
    assert "SECRET_KEY=super-secret-value-xyz" in p.read_text()


# ── _configure_llm output masking ────────────────────────────

def test_configure_llm_no_raw_key_in_stdout(tmp_path, capsys):
    # _configure_llm expects root/server/config.yaml and root/server/.env
    (tmp_path / "server").mkdir()
    (tmp_path / "server" / "config.yaml").write_text("{}")
    _configure_llm(tmp_path, "gemini", "gemini-1.5-flash", None, "secret-api-key-456")
    out = capsys.readouterr().out
    # stdout should mention the env file update but NOT the raw key
    assert "secret-api-key-456" not in out


# ── .gitignore guards .env ───────────────────────────────────

def test_gitignore_excludes_env():
    gi = Path(__file__).resolve().parents[2] / ".gitignore"
    if gi.exists():
        content = gi.read_text()
        assert ".env" in content


# ── Config loading log safety ────────────────────────────────

def test_config_load_no_credential_in_log(tmp_path, caplog, monkeypatch):
    monkeypatch.setenv("WEATHER_API_KEY", "secret-weather-key-999")
    p = tmp_path / "config.yaml"
    with caplog.at_level(logging.DEBUG):
        Config(config_file=str(p))
    assert "secret-weather-key-999" not in caplog.text


def test_authenticated_config_api_masks_nested_credential_fields(tmp_path, monkeypatch):
    import config_loader
    from fastapi.testclient import TestClient
    from web.app import create_app
    from web.auth import configure

    path = tmp_path / "config.yaml"
    path.write_text(
        "telegram:\n  bot_token: synthetic-telegram-token\n"
        "integrations:\n  calendar-google:\n    fields:\n"
        "      client_secret: synthetic-google-secret\n"
        "      refresh_token: synthetic-google-refresh\n",
        encoding="utf-8",
    )
    cfg = Config(config_file=str(path))
    monkeypatch.setattr(config_loader, "_config", cfg)
    configure("synthetic-auth-token")
    try:
        app = create_app(lambda: object(), lambda: None, lambda: "agent")
        with TestClient(app) as client:
            response = client.get("/api/config/", headers={"X-Auth-Token": "synthetic-auth-token"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["telegram"]["bot_token"] == "***"
        fields = payload["integrations"]["calendar-google"]["fields"]
        assert fields["client_secret"] == "***"
        assert fields["refresh_token"] == "***"
        assert "synthetic-google-" not in response.text
        assert "synthetic-telegram-" not in response.text
    finally:
        configure("")


def test_authenticated_config_patch_never_persists_env_dashboard_token(tmp_path, monkeypatch):
    import config_loader
    from fastapi.testclient import TestClient
    from web.app import create_app
    from web.auth import configure

    path = tmp_path / "config.yaml"
    path.write_text("llm:\n  model: previous-model\n", encoding="utf-8")
    monkeypatch.setenv("WEB_AUTH_TOKEN", "synthetic-env-auth-token")
    cfg = Config(config_file=str(path))
    monkeypatch.setattr(config_loader, "_config", cfg)
    configure(cfg.get("web", "auth_token"))
    try:
        app = create_app(lambda: object(), lambda: None, lambda: "agent")
        with TestClient(app) as client:
            response = client.patch(
                "/api/config/",
                headers={"X-Auth-Token": "synthetic-env-auth-token"},
                json={"section": "llm", "key": "model", "value": "edited-model"},
            )
        assert response.status_code == 200
        saved = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert saved["llm"]["model"] == "edited-model"
        assert "auth_token" not in saved["web"]
        assert "synthetic-env-auth-token" not in path.read_text(encoding="utf-8")
    finally:
        configure("")
