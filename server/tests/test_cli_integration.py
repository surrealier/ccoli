from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ccoli import cli


def test_config_integration_set_and_test(tmp_path, monkeypatch):
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    (server_dir / "config.yaml").write_text("", encoding="utf-8")

    monkeypatch.setattr(cli, "_repo_root", lambda: tmp_path)

    rc = cli.main(["config", "integration", "set", "weather", "--api-key", "secret-key"])
    assert rc == 0

    rc = cli.main(["config", "integration", "test", "weather"])
    assert rc == 0


def test_config_voice_threshold_validation(tmp_path, monkeypatch):
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    (server_dir / "config.yaml").write_text("", encoding="utf-8")
    monkeypatch.setattr(cli, "_repo_root", lambda: tmp_path)

    rc = cli.main(["config", "voice-id", "threshold", "--value", "1.2"])
    assert rc == 2

    rc = cli.main(["config", "voice-id", "threshold", "--value", "0.75"])
    assert rc == 0
