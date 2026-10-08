"""Tests for the curl/bootstrap shell installer."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "install.sh"

# install.sh is the POSIX bootstrap; Windows users go through
# `python3 scripts/install.py` instead. Under Git Bash the script would also
# report POSIX paths (/c/...) that can never match Python's WindowsPath, so the
# assertions below only describe the platforms the shell installer targets.
pytestmark = [
    pytest.mark.skipif(sys.platform == "win32", reason="install.sh targets POSIX hosts"),
    pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not available"),
]


def _run_bootstrap(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(env)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=str(ROOT),
        env=merged,
        check=False,
        capture_output=True,
        text=True,
    )


def test_bootstrap_dry_run_prefers_local_repo_in_auto_mode():
    # VIRTUAL_ENV is pinned so the expected command is stable: install.sh only
    # appends --user outside a venv/conda, which would otherwise make this test
    # depend on where the suite happens to run (green in a venv, red in Docker).
    result = _run_bootstrap(
        {
            "CCOLI_DRY_RUN": "1",
            "CCOLI_INSTALL_SOURCE": "auto",
            "CCOLI_PYTHON": sys.executable,
            "VIRTUAL_ENV": "/tmp/fake-venv",
        }
    )

    assert result.returncode == 0
    assert f"INSTALL_CMD={sys.executable} -m pip install -e {ROOT}" in result.stdout
    assert "NEXT_CMD=ccoli setup" in result.stdout
    assert f"USER_BIN={Path.home() / '.local' / 'bin'}" in result.stdout


def test_bootstrap_dry_run_can_force_remote_git_install():
    result = _run_bootstrap(
        {
            "CCOLI_DRY_RUN": "1",
            "CCOLI_INSTALL_SOURCE": "remote",
            "CCOLI_GIT_URL": "https://example.com/demo.git",
            "CCOLI_GIT_REF": "stable",
            "CCOLI_PYTHON": sys.executable,
        }
    )

    assert result.returncode == 0
    assert "git+https://example.com/demo.git@stable" in result.stdout
    assert f"FALLBACK_NEXT_CMD={sys.executable} -m ccoli setup" in result.stdout


def test_bootstrap_dry_run_skips_user_install_inside_conda():
    result = _run_bootstrap(
        {
            "CCOLI_DRY_RUN": "1",
            "CCOLI_INSTALL_SOURCE": "auto",
            "CCOLI_PYTHON": sys.executable,
            "CONDA_PREFIX": "/tmp/fake-conda-env",
        }
    )

    assert result.returncode == 0
    assert f"INSTALL_CMD={sys.executable} -m pip install -e {ROOT}" in result.stdout


def test_bootstrap_dry_run_uses_user_install_outside_env():
    result = _run_bootstrap(
        {
            "CCOLI_DRY_RUN": "1",
            "CCOLI_INSTALL_SOURCE": "auto",
            "CCOLI_PYTHON": sys.executable,
            "VIRTUAL_ENV": "",
            "CONDA_PREFIX": "",
        }
    )

    assert result.returncode == 0
    assert f"INSTALL_CMD={sys.executable} -m pip install --user -e {ROOT}" in result.stdout
