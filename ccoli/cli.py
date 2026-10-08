from __future__ import annotations

import argparse
import getpass
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import yaml

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ImportError:  # pragma: no cover - rich is optional at bootstrap time
    Console = None
    Panel = None
    Table = None


DEFAULT_SERVER_PORT = 5001
DEFAULT_SERVER_IP = "YOUR_SERVER_IP"
DEFAULT_LLM_MODELS = {
    "ollama": "qwen3.5:4b",
    "gemini": "gemini-3.8-flash",
    "claude": "claude-sonnet-5-5",
    "chatgpt": "gpt-6-luna",
}

INTEGRATION_SPECS = {
    "weather": {
        "env_key": "WEATHER_API_KEY",
        "required": ("api_key",),
        "description": "OpenWeather 기반 날씨 조회",
    },
    "search": {
        "env_key": "TAVILY_API_KEY",
        "required": ("api_key",),
        "description": "실시간 검색 조회",
    },
    "calendar-google": {
        "env_key": None,
        "env_keys": {
            "client_id": "GOOGLE_CLIENT_ID",
            "client_secret": "GOOGLE_CLIENT_SECRET",
            "refresh_token": "GOOGLE_REFRESH_TOKEN",
            "calendar_id": "GOOGLE_CALENDAR_ID",
            "time_zone": "GOOGLE_CALENDAR_TIME_ZONE",
        },
        "required": ("client_id", "client_secret", "refresh_token"),
        "description": "Google Calendar 연동",
    },
    "notify-slack": {
        "env_key": "SLACK_BOT_TOKEN",
        "required": ("api_key",),
        "description": "Slack 알림 발송",
    },
    "maps": {
        "env_key": "GOOGLE_MAPS_API_KEY",
        "required": ("api_key",),
        "description": "지도/경로 조회",
    },
}

API_PROVIDERS = ("gemini", "claude", "chatgpt")
CONNECTION_MODES = ("wired", "wifi")
INSTALL_TARGETS = {
    "ollama": {
        "title": "Ollama Local",
        "description": "Run a local LLM with Ollama on this machine.",
        "provider": "ollama",
        "extras": ("runtime",),
    },
    "api": {
        "title": "Cloud API",
        "description": "Use Gemini, Claude, or ChatGPT with an API key.",
        "provider": None,
        "extras": ("runtime",),
    },
    "manual": {
        "title": "Configure Later",
        "description": "Install the runtime now and keep the current LLM config.",
        "provider": None,
        "extras": ("runtime",),
    },
}


@dataclass(frozen=True)
class SetupChoice:
    install_target: str
    provider: str
    model: str
    api_key: Optional[str]
    stt_device: str
    connection_mode: str
    server_port: int
    wifi_ssid: str
    wifi_password: Optional[str]
    server_ip: str
    install_extras: tuple[str, ...]

    @property
    def base_url(self) -> str:
        if self.provider == "ollama":
            return "http://localhost:11434"
        return ""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _server_dir(root: Path) -> Path:
    return root / "server"


def _server_entrypoint(root: Path) -> Path:
    return _server_dir(root) / "server.py"


def _server_config_path(root: Path) -> Path:
    return _server_dir(root) / "config.yaml"


def _server_env_path(root: Path) -> Path:
    return _server_dir(root) / ".env"


def _device_dir(root: Path) -> Path:
    return root / "arduino" / "atom_echo_m5stack_esp32_ino"


def _device_secrets_path(root: Path) -> Path:
    return _device_dir(root) / "device_secrets.h"


def _device_secrets_example_path(root: Path) -> Path:
    return _device_dir(root) / "device_secrets.h.example"


def _escape_cpp_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _extract_cpp_string(contents: str, name: str) -> Optional[str]:
    match = re.search(rf'const\s+char\*\s+{re.escape(name)}\s*=\s*"([^"]*)"\s*;', contents)
    if not match:
        return None
    return match.group(1).strip()


def _extract_cpp_uint16(contents: str, name: str) -> Optional[int]:
    match = re.search(rf"const\s+uint16_t\s+{re.escape(name)}\s*=\s*(\d+)\s*;", contents)
    if not match:
        return None
    return int(match.group(1))


def _extract_server_ip(contents: str) -> Optional[str]:
    extracted = _extract_cpp_string(contents, "SERVER_IP")
    if extracted is None:
        return None
    return extracted or None


def _detect_server_ip(root: Path) -> str:
    for candidate in (_device_secrets_path(root), _device_secrets_example_path(root)):
        if not candidate.exists():
            continue
        content = candidate.read_text(encoding="utf-8")
        detected = _extract_server_ip(content)
        if detected:
            return detected
    return DEFAULT_SERVER_IP


def _detect_device_secret_defaults(root: Path) -> dict[str, object]:
    defaults: dict[str, object] = {
        "connection_mode": "wired",
        "wifi_ssid": "",
        "wifi_password": "",
        "server_ip": "",
        "server_port": DEFAULT_SERVER_PORT,
    }
    for candidate in (_device_secrets_path(root), _device_secrets_example_path(root)):
        if not candidate.exists():
            continue
        content = candidate.read_text(encoding="utf-8")
        connection_mode = _extract_cpp_string(content, "CONNECTION_MODE")
        wifi_ssid = _extract_cpp_string(content, "SSID")
        wifi_password = _extract_cpp_string(content, "PASS")
        server_ip = _extract_cpp_string(content, "SERVER_IP")
        server_port = _extract_cpp_uint16(content, "SERVER_PORT")
        if connection_mode in CONNECTION_MODES:
            defaults["connection_mode"] = connection_mode
        if wifi_ssid is not None:
            defaults["wifi_ssid"] = wifi_ssid
        if wifi_password is not None:
            defaults["wifi_password"] = wifi_password
        if server_ip is not None:
            defaults["server_ip"] = server_ip
        if server_port is not None:
            defaults["server_port"] = server_port
        break
    return defaults


def _setup_connection_defaults(root: Path) -> dict[str, object]:
    defaults = _detect_device_secret_defaults(root)
    config_data = _load_yaml_dict(_server_config_path(root))

    server_cfg = config_data.get("server", {}) if isinstance(config_data.get("server"), dict) else {}
    port = server_cfg.get("port")
    if isinstance(port, int):
        defaults["server_port"] = port

    connection_cfg = config_data.get("connection", {}) if isinstance(config_data.get("connection"), dict) else {}
    connection_mode = str(connection_cfg.get("mode", "")).strip().lower()
    if connection_mode in CONNECTION_MODES:
        defaults["connection_mode"] = connection_mode

    return defaults


def _validate_port(port: int) -> int:
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    return port


def _console() -> Optional["Console"]:
    if Console is None:
        return None
    return Console()


def _print_setup_banner() -> None:
    console = _console()
    message = (
        "Choose how ccoli should install and configure your AI runtime.\n"
        "We keep the base install light, then add only the runtime packages you actually need."
    )
    if console and Panel is not None:
        console.print(Panel.fit(message, title="ccoli Setup", border_style="green"))
        if sys.platform == "darwin":
            console.print(
                "[bold cyan]macOS tip:[/bold cyan] defaulting STT to CPU. "
                "The current STT/TTS path does not use local MPS acceleration."
            )
        return
    print("== ccoli Setup ==")
    print(message)
    if sys.platform == "darwin":
        print("macOS tip: defaulting STT to CPU. The current STT/TTS path does not use local MPS acceleration.")


def _default_stt_device() -> str:
    if sys.platform == "darwin":
        return "cpu"
    return "cuda"


def _prompt_text(message: str, default: Optional[str] = None, secret: bool = False) -> str:
    prompt_suffix = f" [{default}]" if default else ""
    prompt = f"{message}{prompt_suffix}: "
    if secret:
        value = getpass.getpass(prompt)
    else:
        value = input(prompt)
    value = value.strip()
    if value:
        return value
    return default or ""


def _prompt_secret_with_saved_default(message: str, saved_value: Optional[str] = None) -> str:
    prompt_suffix = " [saved]" if saved_value else ""
    value = getpass.getpass(f"{message}{prompt_suffix}: ").strip()
    if value:
        return value
    return saved_value or ""


def _prompt_confirm(message: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        value = input(f"{message} [{hint}]: ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Please enter y or n.")


def _prompt_select(message: str, options: Sequence[tuple[str, str]], default_index: int = 0) -> str:
    console = _console()
    if console and Table is not None:
        table = Table(title=message, show_header=True, header_style="bold green")
        table.add_column("#", style="bold")
        table.add_column("Option")
        table.add_column("Details")
        for idx, (value, label) in enumerate(options, start=1):
            table.add_row(str(idx), value, label)
        console.print(table)
    else:
        print(message)
        for idx, (value, label) in enumerate(options, start=1):
            print(f"  {idx}. {value} - {label}")

    while True:
        raw = _prompt_text("Select", default=str(default_index + 1))
        try:
            selected = int(raw)
        except ValueError:
            print("Please enter the option number.")
            continue
        if 1 <= selected <= len(options):
            return options[selected - 1][0]
        print(f"Please choose a number between 1 and {len(options)}.")


def _prompt_port(message: str, default: int) -> int:
    while True:
        raw = _prompt_text(message, default=str(default))
        try:
            return _validate_port(int(raw))
        except ValueError:
            print("Please enter a valid port between 1 and 65535.")


def _render_setup_summary(choice: SetupChoice, skip_install: bool) -> None:
    console = _console()
    extras = ", ".join(choice.install_extras) or "(none)"
    install_action = "skip pip install" if skip_install else f"pip install -e .[{extras}]"
    if console and Table is not None:
        table = Table(title="Setup Plan", show_header=False, box=None)
        table.add_column("Field", style="bold green")
        table.add_column("Value")
        table.add_row("Install target", choice.install_target)
        table.add_row("Provider", choice.provider)
        table.add_row("Model", choice.model)
        table.add_row("STT device", choice.stt_device)
        table.add_row("Device connection", choice.connection_mode)
        table.add_row("Server port", str(choice.server_port))
        if choice.connection_mode == "wifi":
            table.add_row("Wi-Fi SSID", choice.wifi_ssid)
            table.add_row("Server IP", choice.server_ip)
            table.add_row("Wi-Fi password", "saved to device_secrets.h")
        table.add_row("Python extras", extras)
        table.add_row("Install action", install_action)
        table.add_row("API key", "saved to server/.env" if choice.api_key else "not provided")
        console.print(table)
        return
    print("Setup plan:")
    print(f"- Install target: {choice.install_target}")
    print(f"- Provider: {choice.provider}")
    print(f"- Model: {choice.model}")
    print(f"- STT device: {choice.stt_device}")
    print(f"- Device connection: {choice.connection_mode}")
    print(f"- Server port: {choice.server_port}")
    if choice.connection_mode == "wifi":
        print(f"- Wi-Fi SSID: {choice.wifi_ssid}")
        print(f"- Server IP: {choice.server_ip}")
        print("- Wi-Fi password: saved to device_secrets.h")
    print(f"- Python extras: {extras}")
    print(f"- Install action: {install_action}")
    print(f"- API key: {'saved to server/.env' if choice.api_key else 'not provided'}")


def _build_setup_choice(
    install_target: str,
    provider: Optional[str],
    model: Optional[str],
    api_key: Optional[str],
    stt_device: Optional[str],
    connection_mode: Optional[str],
    wifi_ssid: Optional[str],
    wifi_password: Optional[str],
    server_ip: Optional[str],
    server_port: Optional[int],
) -> SetupChoice:
    normalized_target = (install_target or "").strip().lower()
    if normalized_target not in INSTALL_TARGETS:
        raise ValueError(f"unsupported install target: {install_target}")

    if normalized_target == "manual":
        resolved_provider = (provider or "ollama").strip().lower()
    elif normalized_target == "api":
        resolved_provider = (provider or "").strip().lower()
        if resolved_provider not in API_PROVIDERS:
            raise ValueError("api install target requires provider: gemini, claude, or chatgpt")
    else:
        resolved_provider = "ollama"

    if resolved_provider not in DEFAULT_LLM_MODELS:
        raise ValueError(f"unsupported provider: {resolved_provider}")

    resolved_device = (stt_device or _default_stt_device()).strip().lower()
    if resolved_device not in {"cpu", "cuda"}:
        raise ValueError("stt_device must be `cpu` or `cuda`")

    resolved_model = (model or DEFAULT_LLM_MODELS[resolved_provider]).strip()
    resolved_key = (api_key or "").strip() or None
    resolved_connection_mode = (connection_mode or "wired").strip().lower()
    if resolved_connection_mode not in CONNECTION_MODES:
        raise ValueError(f"connection_mode must be one of: {', '.join(CONNECTION_MODES)}")

    resolved_server_port = _validate_port(int(server_port or DEFAULT_SERVER_PORT))
    resolved_wifi_ssid = (wifi_ssid or "").strip()
    resolved_wifi_password = (wifi_password or "").strip() or None
    resolved_server_ip = (server_ip or "").strip()
    if resolved_connection_mode == "wifi":
        if not resolved_wifi_ssid:
            raise ValueError("wifi_ssid is required when connection_mode is `wifi`")
        if not resolved_wifi_password:
            raise ValueError("wifi_password is required when connection_mode is `wifi`")
        if not resolved_server_ip:
            raise ValueError("server_ip is required when connection_mode is `wifi`")
    else:
        resolved_wifi_ssid = ""
        resolved_wifi_password = None
        resolved_server_ip = ""

    extras = tuple(INSTALL_TARGETS[normalized_target]["extras"])
    return SetupChoice(
        install_target=normalized_target,
        provider=resolved_provider,
        model=resolved_model,
        api_key=resolved_key,
        stt_device=resolved_device,
        connection_mode=resolved_connection_mode,
        server_port=resolved_server_port,
        wifi_ssid=resolved_wifi_ssid,
        wifi_password=resolved_wifi_password,
        server_ip=resolved_server_ip,
        install_extras=extras,
    )


def _prompt_setup_choice(default_target: Optional[str], stt_device: Optional[str]) -> SetupChoice:
    root = _repo_root()
    connection_defaults = _setup_connection_defaults(root)
    _print_setup_banner()
    options = [
        ("ollama", "Local model on your machine via Ollama"),
        ("api", "Gemini / Claude / ChatGPT via API key"),
        ("manual", "Install runtime now and configure LLM later"),
    ]
    target = _prompt_select(
        "Choose your AI path",
        options,
        default_index=0 if default_target in (None, "ollama") else [opt[0] for opt in options].index(default_target),
    )

    provider = None
    if target == "api":
        provider_options = [
            ("gemini", "Google Gemini"),
            ("claude", "Anthropic Claude"),
            ("chatgpt", "OpenAI ChatGPT"),
        ]
        provider = _prompt_select("Choose your cloud provider", provider_options, default_index=0)
    elif target == "manual":
        provider = _prompt_select(
            "Optional default provider",
            [
                ("ollama", "Keep local Ollama as the default"),
                ("gemini", "Prepare for Gemini"),
                ("claude", "Prepare for Claude"),
                ("chatgpt", "Prepare for ChatGPT"),
            ],
            default_index=0,
        )

    resolved_provider = provider or "ollama"
    model = _prompt_text("Model name", default=DEFAULT_LLM_MODELS[resolved_provider])
    api_key = None
    if target == "api":
        api_key = _prompt_text("API key (leave blank to set later)", secret=True)
    device = _prompt_select(
        "Choose STT device",
        [
            ("cpu", "Best default for macOS and general compatibility"),
            ("cuda", "Use NVIDIA CUDA when available"),
        ],
        default_index=0 if (stt_device or _default_stt_device()) == "cpu" else 1,
    )
    default_connection_mode = str(connection_defaults.get("connection_mode", "wired"))
    connection_mode = _prompt_select(
        "Choose device connection",
        [
            ("wired", "USB serial, no Wi-Fi credentials required"),
            ("wifi", "Write Wi-Fi credentials and server IP to device_secrets.h"),
        ],
        default_index=0 if default_connection_mode == "wired" else 1,
    )
    server_port = _prompt_port(
        "Server port",
        int(connection_defaults.get("server_port", DEFAULT_SERVER_PORT)),
    )
    wifi_ssid = None
    wifi_password = None
    server_ip = None
    if connection_mode == "wifi":
        wifi_ssid = _prompt_text(
            "Wi-Fi name (SSID)",
            default=str(connection_defaults.get("wifi_ssid", "")) or None,
        )
        wifi_password = _prompt_secret_with_saved_default(
            "Wi-Fi password",
            saved_value=str(connection_defaults.get("wifi_password", "")) or None,
        )
        server_ip = _prompt_text(
            "Server IP",
            default=str(connection_defaults.get("server_ip", "")) or None,
        )
    return _build_setup_choice(
        target,
        provider,
        model,
        api_key,
        device,
        connection_mode,
        wifi_ssid,
        wifi_password,
        server_ip,
        server_port,
    )


def _editable_install_spec(extras: Sequence[str]) -> str:
    if not extras:
        return "."
    return f".[{','.join(extras)}]"


def _load_yaml_dict(path: Path) -> dict:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _save_yaml_dict(path: Path, data: dict) -> None:
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _upsert_env_var(path: Path, key: str, value: str) -> None:
    lines = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()

    needle = f"{key}="
    replaced = False
    for idx, line in enumerate(lines):
        if line.startswith(needle):
            lines[idx] = f"{key}={value}"
            replaced = True
            break

    if not replaced:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{key}={value}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _mask_secret(value: str) -> str:
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}{'*' * (len(value) - 6)}{value[-3:]}"


def _ollama_health_check(base_url: str, timeout: float = 1.0) -> bool:
    try:
        parsed = urllib.parse.urlparse(base_url)
        scheme = parsed.scheme or "http"
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if scheme == "https" else 80)
        path = parsed.path.rstrip("/")
        url = f"{scheme}://{host}:{port}{path}/api/tags"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def _install_ollama_if_needed() -> bool:
    if shutil.which("ollama"):
        return True

    print("ollama not found; attempting automatic installation...")
    if sys.platform.startswith("linux") or sys.platform == "darwin":
        cmd = "curl -fsSL https://ollama.com/install.sh | sh"
        result = subprocess.run(cmd, shell=True, check=False)
        return result.returncode == 0 and shutil.which("ollama") is not None
    if sys.platform.startswith("win"):
        result = subprocess.run(["winget", "install", "-e", "--id", "Ollama.Ollama"], check=False)
        return result.returncode == 0 and shutil.which("ollama") is not None
    return False


def _ensure_ollama_server(base_url: str, timeout_sec: float = 10.0) -> bool:
    if _ollama_health_check(base_url):
        return True

    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if _ollama_health_check(base_url):
            return True
        time.sleep(0.5)
    return False


def _configure_llm(root: Path, provider: str, model: str, base_url: Optional[str], api_key: Optional[str]) -> Path:
    config_path = _server_config_path(root)
    config_data = _load_yaml_dict(config_path)
    llm_cfg = config_data.setdefault("llm", {})
    if not isinstance(llm_cfg, dict):
        llm_cfg = {}
        config_data["llm"] = llm_cfg

    llm_cfg["provider"] = provider
    llm_cfg["model"] = model
    # A provider choice must also change the runtime route, otherwise a
    # previously configured API or local model can keep winning at startup.
    if provider == "ollama":
        llm_cfg["ollama_model"] = model
        llm_cfg["priority"] = ["ollama", "api", "ollama_cpu", "other"]
    elif provider in {"gemini", "claude", "chatgpt"}:
        api_models = llm_cfg.setdefault("api_models", {})
        if not isinstance(api_models, dict):
            api_models = {}
            llm_cfg["api_models"] = api_models
        api_models[provider] = model
        llm_cfg["priority"] = ["api", "ollama", "ollama_cpu", "other"]
        llm_cfg["api_priority"] = [provider] + [
            item for item in ("gemini", "claude", "chatgpt") if item != provider
        ]

    if provider == "ollama":
        llm_cfg["base_url"] = base_url or llm_cfg.get("base_url", "http://localhost:11434")
        llm_cfg.setdefault("auto_start", True)
        llm_cfg.setdefault("start_command", "ollama serve")
        llm_cfg.setdefault("startup_timeout", 10.0)
    else:
        llm_cfg["base_url"] = base_url or ""

    _save_yaml_dict(config_path, config_data)

    if api_key:
        env_path = _server_env_path(root)
        env_key_map = {
            "gemini": "GEMINI_API_KEY",
            "claude": "ANTHROPIC_API_KEY",
            "chatgpt": "OPENAI_API_KEY",
        }
        env_key = env_key_map.get(provider)
        if env_key:
            _upsert_env_var(env_path, env_key, api_key)
            print(f"updated: {env_path} ({env_key})")

    return config_path


def _apply_setup_choice(root: Path, choice: SetupChoice) -> tuple[Path, Path]:
    config_path = _configure_llm(root, choice.provider, choice.model, choice.base_url, choice.api_key)
    config_data = _load_yaml_dict(config_path)

    server_cfg = config_data.setdefault("server", {})
    if not isinstance(server_cfg, dict):
        server_cfg = {}
        config_data["server"] = server_cfg
    server_cfg["port"] = choice.server_port
    server_cfg.setdefault("host", "0.0.0.0")

    connection_cfg = config_data.setdefault("connection", {})
    if not isinstance(connection_cfg, dict):
        connection_cfg = {}
        config_data["connection"] = connection_cfg
    connection_cfg["mode"] = choice.connection_mode

    stt_cfg = config_data.setdefault("stt", {})
    if not isinstance(stt_cfg, dict):
        stt_cfg = {}
        config_data["stt"] = stt_cfg
    stt_cfg["device"] = choice.stt_device

    setup_cfg = config_data.setdefault("setup", {})
    if not isinstance(setup_cfg, dict):
        setup_cfg = {}
        config_data["setup"] = setup_cfg
    setup_cfg["install_target"] = choice.install_target
    setup_cfg["provider"] = choice.provider
    setup_cfg["python_extras"] = list(choice.install_extras)
    setup_cfg["connection_mode"] = choice.connection_mode
    setup_cfg["server_port"] = choice.server_port

    _save_yaml_dict(config_path, config_data)
    _write_device_secrets(
        root,
        choice.wifi_ssid,
        choice.wifi_password or "",
        choice.server_port,
        connection_mode=choice.connection_mode,
        server_ip=choice.server_ip,
    )
    return config_path, _server_env_path(root)


def _run_pip_install(root: Path, extras: Sequence[str]) -> int:
    spec = _editable_install_spec(extras)
    command = [sys.executable, "-m", "pip", "install", "-e", spec]
    print(f"running: {' '.join(command)}")
    try:
        completed = subprocess.run(command, cwd=str(root), check=False)
    except FileNotFoundError:
        print("error: python/pip is not available in this environment", file=sys.stderr)
        return 1
    return completed.returncode


def _prepare_ollama_model(choice: SetupChoice) -> int:
    if choice.provider != "ollama":
        return 0
    if not _install_ollama_if_needed():
        print("warning: ollama installation was skipped or failed; configure it manually later.", file=sys.stderr)
        return 0
    if not _ensure_ollama_server(choice.base_url):
        print("warning: ollama server did not start automatically; configure it manually later.", file=sys.stderr)
        return 0
    pull = subprocess.run(["ollama", "pull", choice.model], check=False)
    if pull.returncode != 0:
        print(f"warning: failed to pull ollama model `{choice.model}`. You can retry later.", file=sys.stderr)
        return 0
    return 0


def _load_env_vars(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _integration_state(root: Path) -> dict:
    data = _load_yaml_dict(_server_config_path(root))
    integrations = data.setdefault("integrations", {})
    if not isinstance(integrations, dict):
        integrations = {}
        data["integrations"] = integrations
    return data


def _cmd_config_integration_list() -> int:
    root = _repo_root()
    config = _integration_state(root)
    env_values = _load_env_vars(_server_env_path(root))
    status = config.get("integrations", {})
    for name, spec in INTEGRATION_SPECS.items():
        cfg = status.get(name, {}) if isinstance(status.get(name), dict) else {}
        enabled = bool(cfg.get("enabled", False))
        configured = False
        if spec["env_key"]:
            configured = bool(env_values.get(spec["env_key"], "").strip())
        else:
            fields = cfg.get("fields", {}) if isinstance(cfg.get("fields"), dict) else {}
            env_keys = spec.get("env_keys", {})
            configured = all(
                bool((env_values.get(env_keys.get(field, ""), "") or fields.get(field, "")).strip())
                for field in spec["required"]
            )
        print(f"- {name}: enabled={enabled}, configured={configured} ({spec['description']})")
    return 0


def _cmd_config_integration_set(
    provider: str,
    api_key: Optional[str],
    client_id: Optional[str],
    client_secret: Optional[str],
    refresh_token: Optional[str],
    calendar_id: Optional[str] = None,
    time_zone: Optional[str] = None,
) -> int:
    root = _repo_root()
    provider = provider.lower().strip()
    if provider not in INTEGRATION_SPECS:
        print(f"error: unknown provider `{provider}`", file=sys.stderr)
        print(f"supported providers: {', '.join(INTEGRATION_SPECS.keys())}", file=sys.stderr)
        return 2

    spec = INTEGRATION_SPECS[provider]
    config = _integration_state(root)
    integrations = config.setdefault("integrations", {})
    entry = integrations.setdefault(provider, {})
    entry["enabled"] = True
    env_path = _server_env_path(root)

    missing: list[str] = []
    if "api_key" in spec["required"]:
        if not api_key:
            missing.append("--api-key")
        else:
            env_key = spec["env_key"]
            if env_key:
                _upsert_env_var(env_path, env_key, api_key)
                print(f"updated: {env_path} ({env_key}={_mask_secret(api_key)})")
    else:
        fields = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "calendar_id": calendar_id,
            "time_zone": time_zone,
        }
        missing = [f"--{field.replace('_', '-')}" for field in spec["required"] if not fields.get(field)]
        if not missing:
            env_keys = spec.get("env_keys", {})
            for field, value in fields.items():
                if not value:
                    continue
                env_key = env_keys.get(field)
                if env_key:
                    _upsert_env_var(env_path, env_key, value)
                    print(f"updated: {env_path} ({env_key}={_mask_secret(value)})")
            non_secret_fields = {
                field: value
                for field, value in fields.items()
                if value and field in {"calendar_id", "time_zone"}
            }
            if non_secret_fields:
                existing_fields = entry.get("fields", {}) if isinstance(entry.get("fields"), dict) else {}
                entry["fields"] = {**existing_fields, **non_secret_fields}

    if missing:
        print(f"error: missing required options: {', '.join(missing)}", file=sys.stderr)
        return 2

    _save_yaml_dict(_server_config_path(root), config)
    print(f"updated: {_server_config_path(root)}")
    return 0


def _cmd_config_integration_enable(provider: str, enabled: bool) -> int:
    root = _repo_root()
    provider = provider.lower().strip()
    if provider not in INTEGRATION_SPECS:
        print(f"error: unknown provider `{provider}`", file=sys.stderr)
        return 2

    config = _integration_state(root)
    integrations = config.setdefault("integrations", {})
    entry = integrations.setdefault(provider, {})
    entry["enabled"] = enabled
    _save_yaml_dict(_server_config_path(root), config)
    print(f"updated: {_server_config_path(root)}")
    print(f"integration `{provider}` {'enabled' if enabled else 'disabled'}")
    return 0


def _cmd_config_integration_test(provider: str) -> int:
    root = _repo_root()
    provider = provider.lower().strip()
    if provider not in INTEGRATION_SPECS:
        print(f"error: unknown provider `{provider}`", file=sys.stderr)
        return 2

    config = _integration_state(root)
    integrations = config.get("integrations", {})
    entry = integrations.get(provider, {}) if isinstance(integrations, dict) else {}
    if not bool(entry.get("enabled", False)):
        print(f"error: integration `{provider}` is disabled. run `ccoli config integration enable {provider}`", file=sys.stderr)
        return 1

    env_values = _load_env_vars(_server_env_path(root))
    spec = INTEGRATION_SPECS[provider]
    if spec["env_key"]:
        value = env_values.get(spec["env_key"], "")
        if not value.strip():
            print(
                f"error: missing env key `{spec['env_key']}`. run `ccoli config integration set {provider} --api-key ...`",
                file=sys.stderr,
            )
            return 1
        print(f"ok: {provider} integration key detected ({spec['env_key']}={_mask_secret(value)})")
        return 0

    fields = entry.get("fields", {}) if isinstance(entry.get("fields"), dict) else {}
    env_keys = spec.get("env_keys", {})
    missing = [
        field
        for field in spec["required"]
        if not (env_values.get(env_keys.get(field, ""), "") or fields.get(field, "")).strip()
    ]
    if missing:
        missing_env = [env_keys.get(field, field) for field in missing]
        print(f"error: missing calendar OAuth values: {', '.join(missing_env)}", file=sys.stderr)
        return 1
    print(f"ok: {provider} integration OAuth values configured")
    return 0


def _write_device_secrets(
    root: Path,
    ssid: str,
    password: str,
    port: int,
    connection_mode: str = "wifi",
    server_ip: Optional[str] = None,
) -> Path:
    path = _device_secrets_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)

    resolved_server_ip = (server_ip or "").strip()
    if not resolved_server_ip and connection_mode == "wifi":
        detected_ip = _detect_server_ip(root)
        if detected_ip != DEFAULT_SERVER_IP:
            resolved_server_ip = detected_ip
    content = (
        "// Auto-generated by ccoli CLI.\n"
        "// Local credentials only. Do not commit real secrets.\n\n"
        "#ifndef DEVICE_SECRETS_H\n"
        "#define DEVICE_SECRETS_H\n\n"
        "#include <stdint.h>\n\n"
        f'const char* CONNECTION_MODE = "{_escape_cpp_string(connection_mode)}";\n'
        f'const char* SSID = "{_escape_cpp_string(ssid)}";\n'
        f'const char* PASS = "{_escape_cpp_string(password)}";\n'
        f'const char* SERVER_IP = "{_escape_cpp_string(resolved_server_ip)}";\n'
        f"const uint16_t SERVER_PORT = {port};\n\n"
        "#endif  // DEVICE_SECRETS_H\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def _update_server_connection(root: Path, port: int, connection_mode: str = "wifi") -> Path:
    config_path = _server_config_path(root)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    config_data = _load_yaml_dict(config_path)
    server_cfg = config_data.setdefault("server", {})
    if not isinstance(server_cfg, dict):
        server_cfg = {}
        config_data["server"] = server_cfg

    server_cfg["port"] = port
    if "host" not in server_cfg:
        server_cfg["host"] = "0.0.0.0"

    connection_cfg = config_data.setdefault("connection", {})
    if not isinstance(connection_cfg, dict):
        connection_cfg = {}
        config_data["connection"] = connection_cfg
    connection_cfg["mode"] = connection_mode

    _save_yaml_dict(config_path, config_data)
    return config_path




def _voice_profiles_dir(root: Path) -> Path:
    return _server_dir(root) / "data" / "voice_profiles"


def _voice_profile_users(root: Path) -> list[str]:
    meta = _voice_profiles_dir(root) / "profiles.json"
    if not meta.exists():
        return []
    try:
        import json

        data = json.loads(meta.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return sorted(data.keys())
    except Exception:
        return []
    return []


def _voice_profile_delete(root: Path, user: str) -> bool:
    base = _voice_profiles_dir(root)
    meta = base / "profiles.json"
    deleted = False
    if meta.exists():
        try:
            import json

            data = json.loads(meta.read_text(encoding="utf-8"))
            if isinstance(data, dict) and user in data:
                data.pop(user, None)
                meta.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                deleted = True
        except Exception:
            pass
    embed = base / f"{user}.npy"
    if embed.exists():
        embed.unlink()
        deleted = True
    return deleted

def _parse_wifi_config_tokens(tokens: Sequence[str]) -> tuple[str, str, int, str]:
    cleaned = [token.strip() for token in tokens if token and token.strip()]
    if not cleaned:
        raise ValueError("missing wifi configuration tokens")

    lowered = [token.lower() for token in cleaned]
    if "password" not in lowered:
        raise ValueError("keyword `password` is required")

    password_idx = lowered.index("password")
    ssid = " ".join(cleaned[:password_idx]).strip()
    if not ssid:
        raise ValueError("wifi name is missing before `password`")

    tail_tokens = cleaned[password_idx + 1 :]
    if not tail_tokens:
        raise ValueError("password value is missing")

    tail_lowered = [token.lower() for token in tail_tokens]
    connection_mode = "wifi"
    if "mode" in tail_lowered:
        mode_idx = tail_lowered.index("mode")
        if mode_idx + 1 >= len(tail_tokens):
            raise ValueError("mode value is missing")
        connection_mode = tail_tokens[mode_idx + 1].strip().lower()
        if connection_mode not in {"wifi", "wired"}:
            raise ValueError("mode must be one of: wifi, wired")
        tail_tokens = tail_tokens[:mode_idx]
        tail_lowered = [token.lower() for token in tail_tokens]

    port = DEFAULT_SERVER_PORT
    if "port" in tail_lowered:
        port_idx = tail_lowered.index("port")
        password_tokens = tail_tokens[:port_idx]
        port_tokens = tail_tokens[port_idx + 1 :]
        if not port_tokens:
            raise ValueError("port value is missing")
        if len(port_tokens) != 1:
            raise ValueError("port accepts one numeric value")
        try:
            port = _validate_port(int(port_tokens[0]))
        except ValueError as exc:
            raise ValueError("port must be a valid integer between 1 and 65535") from exc
    else:
        password_tokens = tail_tokens

    password = " ".join(password_tokens).strip()
    if not password:
        raise ValueError("password value is missing")

    return ssid, password, port, connection_mode


def _cmd_start(port: Optional[int]) -> int:
    root = _repo_root()
    server_entry = _server_entrypoint(root)
    server_dir = _server_dir(root)

    if not server_entry.exists():
        print(f"error: server entrypoint not found: {server_entry}", file=sys.stderr)
        return 1

    env = os.environ.copy()
    if port is not None:
        env["SERVER_PORT"] = str(_validate_port(port))

    command = [sys.executable, str(server_entry)]
    try:
        completed = subprocess.run(command, cwd=str(server_dir), env=env, check=False)
    except KeyboardInterrupt:
        return 130
    except FileNotFoundError:
        print("error: python executable is not available", file=sys.stderr)
        return 1
    return completed.returncode


def _cmd_config_wifi(tokens: Sequence[str]) -> int:
    try:
        ssid, password, port, connection_mode = _parse_wifi_config_tokens(tokens)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "usage: ccoli config wifi <WiFi Name> password <password> port <port> [mode wifi|wired]",
            file=sys.stderr,
        )
        return 2

    root = _repo_root()
    config_path = _update_server_connection(root, port, connection_mode)
    secrets_path = _write_device_secrets(root, ssid, password, port, connection_mode=connection_mode)

    print(f"updated: {config_path}")
    print(f"updated: {secrets_path}")
    print("note: update SERVER_IP in device_secrets.h if it does not match your server host")
    return 0


def _cmd_config_llm(provider: str, model: Optional[str], base_url: Optional[str], api_key: Optional[str]) -> int:
    provider = provider.lower().strip()
    selected_model = (model or DEFAULT_LLM_MODELS[provider]).strip()
    root = _repo_root()

    if provider == "ollama":
        if not _install_ollama_if_needed():
            print("error: failed to install ollama automatically", file=sys.stderr)
            return 1
        ollama_url = base_url or "http://localhost:11434"
        if not _ensure_ollama_server(ollama_url):
            print("error: failed to start ollama server", file=sys.stderr)
            return 1
        pull = subprocess.run(["ollama", "pull", selected_model], check=False)
        if pull.returncode != 0:
            print(f"error: failed to pull ollama model: {selected_model}", file=sys.stderr)
            return pull.returncode

    config_path = _configure_llm(root, provider, selected_model, base_url, api_key)
    print(f"updated: {config_path}")
    if provider != "ollama" and not api_key:
        print("warning: no API key was provided. Set one in server/.env before running the server.")
    print(f"llm provider set to: {provider} (model={selected_model})")
    return 0


def _cmd_setup(
    install_target: Optional[str],
    provider: Optional[str],
    model: Optional[str],
    api_key: Optional[str],
    stt_device: Optional[str],
    connection_mode: Optional[str],
    wifi_ssid: Optional[str],
    wifi_password: Optional[str],
    server_ip: Optional[str],
    server_port: Optional[int],
    skip_install: bool,
    yes: bool,
) -> int:
    root = _repo_root()

    try:
        if install_target:
            choice = _build_setup_choice(
                install_target,
                provider,
                model,
                api_key,
                stt_device,
                connection_mode,
                wifi_ssid,
                wifi_password,
                server_ip,
                server_port,
            )
        else:
            if not sys.stdin.isatty():
                print(
                    "error: setup needs a TTY unless you pass --install-target and other options explicitly.",
                    file=sys.stderr,
                )
                return 2
            choice = _prompt_setup_choice(default_target=None, stt_device=stt_device)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    _render_setup_summary(choice, skip_install=skip_install)
    if not yes and not _prompt_confirm("Continue with this setup plan?", default=True):
        print("setup cancelled")
        return 1

    if not skip_install:
        install_code = _run_pip_install(root, choice.install_extras)
        if install_code != 0:
            return install_code

    config_path, env_path = _apply_setup_choice(root, choice)
    secrets_path = _device_secrets_path(root)
    if not skip_install:
        _prepare_ollama_model(choice)

    print(f"updated: {config_path}")
    print(f"updated: {secrets_path}")
    if choice.api_key:
        print(f"updated: {env_path}")
    if choice.provider == "ollama":
        print(f"local provider configured: ollama ({choice.model})")
    else:
        if not choice.api_key:
            print("warning: no API key saved yet. Add it to server/.env before starting the server.")
        print(f"cloud provider configured: {choice.provider} ({choice.model})")
    if choice.connection_mode == "wifi":
        print("next: upload the firmware, confirm SERVER_IP in device_secrets.h, then run `ccoli start`.")
    else:
        print("next: run `ccoli start` after flashing the device firmware.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ccoli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="start the ccoli server")
    start_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"override server port for this run (default: {DEFAULT_SERVER_PORT})",
    )

    setup_parser = subparsers.add_parser(
        "setup",
        aliases=["install"],
        help="interactive install/onboarding wizard",
    )
    setup_parser.add_argument(
        "--install-target",
        choices=tuple(INSTALL_TARGETS.keys()),
        default=None,
        help="choose `ollama`, `api`, or `manual` without interactive prompts",
    )
    setup_parser.add_argument(
        "--provider",
        choices=API_PROVIDERS + ("ollama",),
        default=None,
        help="provider override for non-interactive setup",
    )
    setup_parser.add_argument("--model", default=None, help="model name for the selected provider")
    setup_parser.add_argument("--api-key", default=None, help="API key for cloud providers")
    setup_parser.add_argument(
        "--stt-device",
        choices=("cpu", "cuda"),
        default=None,
        help="override STT device selection",
    )
    setup_parser.add_argument(
        "--connection-mode",
        choices=CONNECTION_MODES,
        default=None,
        help="set device connection mode for firmware and server defaults",
    )
    setup_parser.add_argument(
        "--wifi-ssid",
        default=None,
        help="wifi ssid to write into device_secrets.h when using --connection-mode wifi",
    )
    setup_parser.add_argument(
        "--wifi-password",
        default=None,
        help="wifi password to write into device_secrets.h when using --connection-mode wifi",
    )
    setup_parser.add_argument(
        "--server-ip",
        default=None,
        help="server LAN IP/hostname for wifi firmware mode",
    )
    setup_parser.add_argument(
        "--server-port",
        type=int,
        default=None,
        help=f"server/device port to write during setup (default: {DEFAULT_SERVER_PORT})",
    )
    setup_parser.add_argument(
        "--skip-install",
        action="store_true",
        help="only write configuration, skip pip installation",
    )
    setup_parser.add_argument(
        "--yes",
        action="store_true",
        help="skip the final confirmation prompt",
    )

    config_parser = subparsers.add_parser("config", help="configure ccoli project settings")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)

    wifi_parser = config_subparsers.add_parser("wifi", help="set wifi/password/port/mode for ESP32 + server")
    wifi_parser.add_argument(
        "tokens",
        nargs=argparse.REMAINDER,
        help="syntax: <WiFi Name> password <password> port <port> [mode wifi|wired]",
    )

    llm_parser = config_subparsers.add_parser("llm", help="set LLM provider/model/API key")
    llm_parser.add_argument(
        "--provider",
        required=True,
        choices=tuple(DEFAULT_LLM_MODELS.keys()),
        help="llm provider: ollama, gemini, claude, chatgpt",
    )
    llm_parser.add_argument("--model", default=None, help="model name (provider-specific)")
    llm_parser.add_argument("--base-url", default=None, help="base URL (used mainly for ollama)")
    llm_parser.add_argument("--api-key", default=None, help="API key for external providers")

    integration_parser = config_subparsers.add_parser("integration", help="manage feature integrations")
    integration_sub = integration_parser.add_subparsers(dest="integration_command", required=True)

    integration_sub.add_parser("list", help="list integration configuration status")

    set_parser = integration_sub.add_parser("set", help="set provider credentials")
    set_parser.add_argument("provider", choices=tuple(INTEGRATION_SPECS.keys()))
    set_parser.add_argument("--api-key", default=None)
    set_parser.add_argument("--client-id", default=None)
    set_parser.add_argument("--client-secret", default=None)
    set_parser.add_argument("--refresh-token", default=None)
    set_parser.add_argument("--calendar-id", default=None, help="Google Calendar ID, defaults to primary")
    set_parser.add_argument("--time-zone", default=None, help="Calendar event time zone, defaults to Asia/Seoul")

    enable_parser = integration_sub.add_parser("enable", help="enable an integration")
    enable_parser.add_argument("provider", choices=tuple(INTEGRATION_SPECS.keys()))

    disable_parser = integration_sub.add_parser("disable", help="disable an integration")
    disable_parser.add_argument("provider", choices=tuple(INTEGRATION_SPECS.keys()))

    test_parser = integration_sub.add_parser("test", help="validate integration configuration")
    test_parser.add_argument("provider", choices=tuple(INTEGRATION_SPECS.keys()))

    voice_parser = config_subparsers.add_parser("voice-id", help="voice id mode controls")
    voice_sub = voice_parser.add_subparsers(dest="voice_command", required=True)
    voice_sub.add_parser("status")
    voice_sub.add_parser("enable")
    voice_sub.add_parser("disable")
    delete_parser = voice_sub.add_parser("delete")
    delete_parser.add_argument("--user", required=True)
    threshold_parser = voice_sub.add_parser("threshold")
    threshold_parser.add_argument("--value", required=True, type=float)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "start":
        return _cmd_start(args.port)
    if args.command in {"setup", "install"}:
        return _cmd_setup(
            args.install_target,
            args.provider,
            args.model,
            args.api_key,
            args.stt_device,
            args.connection_mode,
            args.wifi_ssid,
            args.wifi_password,
            args.server_ip,
            args.server_port,
            args.skip_install,
            args.yes,
        )
    if args.command == "config" and args.config_command == "wifi":
        return _cmd_config_wifi(args.tokens)
    if args.command == "config" and args.config_command == "llm":
        return _cmd_config_llm(args.provider, args.model, args.base_url, args.api_key)
    if args.command == "config" and args.config_command == "integration":
        if args.integration_command == "list":
            return _cmd_config_integration_list()
        if args.integration_command == "set":
            return _cmd_config_integration_set(
                args.provider,
                args.api_key,
                args.client_id,
                args.client_secret,
                args.refresh_token,
                args.calendar_id,
                args.time_zone,
            )
        if args.integration_command == "enable":
            return _cmd_config_integration_enable(args.provider, True)
        if args.integration_command == "disable":
            return _cmd_config_integration_enable(args.provider, False)
        if args.integration_command == "test":
            return _cmd_config_integration_test(args.provider)
    if args.command == "config" and args.config_command == "voice-id":
        root = _repo_root()
        config = _load_yaml_dict(_server_config_path(root))
        voice_cfg = config.setdefault("voice_id", {})
        if args.voice_command == "status":
            users = _voice_profile_users(root)
            print(f"voice-id enabled={bool(voice_cfg.get('enabled', False))}, threshold={voice_cfg.get('threshold', 0.72)}, users={len(users)}")
            return 0
        if args.voice_command == "enable":
            voice_cfg["enabled"] = True
        elif args.voice_command == "disable":
            voice_cfg["enabled"] = False
        elif args.voice_command == "delete":
            deleted = _voice_profile_delete(root, args.user)
            if deleted:
                print(f"deleted voice profile for user: {args.user}")
            else:
                print(f"no stored voice profile found for user: {args.user}")
        elif args.voice_command == "threshold":
            if args.value <= 0.0 or args.value >= 1.0:
                print("error: threshold must be between 0 and 1", file=sys.stderr)
                return 2
            voice_cfg["threshold"] = args.value
        _save_yaml_dict(_server_config_path(root), config)
        print(f"updated: {_server_config_path(root)}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
