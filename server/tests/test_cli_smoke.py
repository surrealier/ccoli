"""L4 CLI smoke tests — parser, validation, env helpers, start command."""
import sys
import os
import pytest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ccoli.cli import (
    build_parser,
    _validate_port,
    _mask_secret,
    _upsert_env_var,
    _cmd_start,
)


# ── Parser ───────────────────────────────────────────────────

def test_parser_has_start_and_config():
    p = build_parser()
    choices = p._subparsers._group_actions[0].choices
    assert "start" in choices and "config" in choices


def test_parser_start_with_port():
    args = build_parser().parse_args(["start", "--port", "8080"])
    assert args.port == 8080


def test_parser_start_default_port():
    args = build_parser().parse_args(["start"])
    assert args.port is None


def test_parser_config_llm_provider():
    args = build_parser().parse_args(["config", "llm", "--provider", "gemini"])
    assert args.provider == "gemini"


def test_parser_config_llm_requires_provider():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["config", "llm"])


# ── Validation helpers ───────────────────────────────────────

def test_validate_port_ok():
    assert _validate_port(5001) == 5001


def test_validate_port_zero():
    with pytest.raises(ValueError):
        _validate_port(0)


def test_validate_port_too_high():
    with pytest.raises(ValueError):
        _validate_port(70000)


# ── _mask_secret ─────────────────────────────────────────────

def test_mask_short():
    assert _mask_secret("abc") == "***"


def test_mask_long():
    r = _mask_secret("sk-1234567890")
    assert r.startswith("sk-") and r.endswith("890") and "*" in r


# ── _upsert_env_var ──────────────────────────────────────────

def test_upsert_new_key(tmp_path):
    p = tmp_path / ".env"
    _upsert_env_var(p, "KEY", "val")
    assert "KEY=val" in p.read_text()


def test_upsert_update_existing(tmp_path):
    p = tmp_path / ".env"
    p.write_text("KEY=old\nOTHER=keep\n")
    _upsert_env_var(p, "KEY", "new")
    txt = p.read_text()
    assert "KEY=new" in txt and "OTHER=keep" in txt


# ── _cmd_start ───────────────────────────────────────────────

def test_cmd_start_missing_server(monkeypatch, tmp_path):
    monkeypatch.setattr("ccoli.cli._repo_root", lambda: tmp_path)
    assert _cmd_start(None) == 1
