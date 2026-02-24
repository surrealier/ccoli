from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Sequence

import yaml


DEFAULT_SERVER_PORT = 5001
DEFAULT_SERVER_IP = "YOUR_SERVER_IP"
DEFAULT_LLM_MODELS = {
    "ollama": "qwen3:8b",
    "gemini": "gemini-1.5-flash",
    "claude": "claude-3-5-haiku-latest",
    "chatgpt": "gpt-4o-mini",
}


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


def _extract_server_ip(contents: str) -> Optional[str]:
    match = re.search(r'const\s+char\*\s+SERVER_IP\s*=\s*"([^"]*)"\s*;', contents)
    if not match:
        return None
    extracted = match.group(1).strip()
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


def _validate_port(port: int) -> int:
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    return port


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


def _write_device_secrets(root: Path, ssid: str, password: str, port: int) -> Path:
    path = _device_secrets_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)

    server_ip = _detect_server_ip(root)
    content = (
        "// Auto-generated by ccoli CLI.\n"
        "// Local credentials only. Do not commit real secrets.\n\n"
        "#ifndef DEVICE_SECRETS_H\n"
        "#define DEVICE_SECRETS_H\n\n"
        "#include <stdint.h>\n\n"
        f'const char* SSID = "{_escape_cpp_string(ssid)}";\n'
        f'const char* PASS = "{_escape_cpp_string(password)}";\n'
        f'const char* SERVER_IP = "{_escape_cpp_string(server_ip)}";\n'
        f"const uint16_t SERVER_PORT = {port};\n\n"
        "#endif  // DEVICE_SECRETS_H\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def _update_server_port(root: Path, port: int) -> Path:
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

    _save_yaml_dict(config_path, config_data)
    return config_path


def _parse_wifi_config_tokens(tokens: Sequence[str]) -> tuple[str, str, int]:
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

    return ssid, password, port


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
    except FileNotFoundError:
        print("error: python executable is not available", file=sys.stderr)
        return 1
    return completed.returncode


def _cmd_config_wifi(tokens: Sequence[str]) -> int:
    try:
        ssid, password, port = _parse_wifi_config_tokens(tokens)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "usage: ccoli config wifi <WiFi Name> password <password> port <port>",
            file=sys.stderr,
        )
        return 2

    root = _repo_root()
    config_path = _update_server_port(root, port)
    secrets_path = _write_device_secrets(root, ssid, password, port)

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

    config_parser = subparsers.add_parser("config", help="configure ccoli project settings")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)

    wifi_parser = config_subparsers.add_parser("wifi", help="set wifi/password/port for ESP32 + server")
    wifi_parser.add_argument(
        "tokens",
        nargs=argparse.REMAINDER,
        help="syntax: <WiFi Name> password <password> port <port>",
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

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "start":
        return _cmd_start(args.port)
    if args.command == "config" and args.config_command == "wifi":
        return _cmd_config_wifi(args.tokens)
    if args.command == "config" and args.config_command == "llm":
        return _cmd_config_llm(args.provider, args.model, args.base_url, args.api_key)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
