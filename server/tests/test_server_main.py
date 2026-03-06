"""Tests for server.py orchestration functions (pure + mock-based)."""
import sys
import unittest.mock as mock

import yaml


# server.py has heavy top-level imports (STTEngine → faster_whisper).
# We pre-mock the unavailable modules so we can import the pure helpers.
_HEAVY = [
    "faster_whisper",
    "faster_whisper.transcribe",
]
for _m in _HEAVY:
    if _m not in sys.modules:
        sys.modules[_m] = mock.MagicMock()

import server as srv  # noqa: E402  (after mocking)


# ── _normalize_start_command (pure) ──────────────────────────

def test_normalize_string():
    assert srv._normalize_start_command("ollama serve") == ["ollama", "serve"]


def test_normalize_list():
    assert srv._normalize_start_command(["a", "b"]) == ["a", "b"]


def test_normalize_none():
    assert srv._normalize_start_command(None) is None


def test_normalize_empty():
    assert srv._normalize_start_command("") is None


# ── _ollama_health_check ─────────────────────────────────────

def test_health_check_success():
    resp = mock.MagicMock()
    resp.status = 200
    cm = mock.MagicMock()
    cm.__enter__ = mock.Mock(return_value=resp)
    cm.__exit__ = mock.Mock(return_value=False)
    with mock.patch("server.urllib.request.urlopen", return_value=cm):
        assert srv._ollama_health_check("http://localhost:11434") is True


def test_health_check_failure():
    with mock.patch("server.urllib.request.urlopen", side_effect=OSError):
        assert srv._ollama_health_check("http://localhost:11434") is False


# ── ensure_ollama_running ────────────────────────────────────

def test_ensure_already_up():
    with mock.patch("server._ollama_health_check", return_value=True):
        assert srv.ensure_ollama_running("http://localhost:11434", {}) is True


def test_ensure_auto_start_disabled():
    with mock.patch("server._ollama_health_check", return_value=False):
        assert srv.ensure_ollama_running("http://localhost:11434", {"auto_start": False}) is False


# ── load_commands_config ─────────────────────────────────────

def test_load_commands_valid(tmp_path):
    p = tmp_path / "cmds.yaml"
    p.write_text(yaml.dump({"commands": [{"name": "nod"}]}))
    srv.load_commands_config(str(p))
    assert srv.ACTIONS_CONFIG == [{"name": "nod"}]


def test_load_commands_missing():
    srv.load_commands_config("/nonexistent/path.yaml")
    assert srv.ACTIONS_CONFIG == []
