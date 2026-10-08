"""
Configuration management module
- Provides settings by combining config.yaml and environment variables
- Manages global settings with a singleton pattern
- Supplies defaults and merges runtime overrides
"""
import copy
import logging
import os
from pathlib import Path
from typing import Any, Dict

import yaml

from src.robot_mode import normalize_display_type
from src.runtime_preferences import (
    DEFAULT_API_MODELS,
    DEFAULT_CONNECTION_PRIORITY,
    DEFAULT_LLM_PRIORITY,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_PROCESSOR_PRIORITY,
    build_default_api_priority,
    normalize_priority_list,
    resolve_llm_models,
)

log = logging.getLogger("config_loader")

_SECRET_ENV_PATHS: dict[str, tuple[str, ...]] = {
    "WEATHER_API_KEY": ("weather", "api_key"),
    "OPENAI_API_KEY": ("llm", "openai_api_key"),
    "ANTHROPIC_API_KEY": ("llm", "anthropic_api_key"),
    "GEMINI_API_KEY": ("llm", "gemini_api_key"),
    "TAVILY_API_KEY": ("integrations", "search", "api_key"),
    "SLACK_BOT_TOKEN": ("integrations", "notify-slack", "api_key"),
    "GOOGLE_MAPS_API_KEY": ("integrations", "maps", "api_key"),
    "GOOGLE_CLIENT_ID": ("integrations", "calendar-google", "fields", "client_id"),
    "GOOGLE_CLIENT_SECRET": ("integrations", "calendar-google", "fields", "client_secret"),
    "GOOGLE_REFRESH_TOKEN": ("integrations", "calendar-google", "fields", "refresh_token"),
    "TELEGRAM_BOT_TOKEN": ("telegram", "bot_token"),
    "WEB_AUTH_TOKEN": ("web", "auth_token"),
}


def _nested_value(data: dict, path: tuple[str, ...]) -> tuple[bool, Any]:
    node: Any = data
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return False, None
        node = node[key]
    return True, node


def _restore_nested_value(data: dict, original: dict, path: tuple[str, ...]) -> None:
    present, value = _nested_value(original, path)
    node = data
    for key in path[:-1]:
        if not isinstance(node.get(key), dict):
            if not present:
                return
            node[key] = {}
        node = node[key]
    if present:
        node[path[-1]] = copy.deepcopy(value)
    else:
        node.pop(path[-1], None)


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        raw_items = value.replace("\n", ",").split(",")
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = [value]

    items: list[str] = []
    for item in raw_items:
        normalized = str(item).strip()
        if normalized and normalized not in items:
            items.append(normalized)
    return items


class Config:
    """
    Configuration manager class
    Loads config.yaml and .env and provides merged settings.
    Environment variables have higher priority.
    """

    DEFAULT_CONFIG = {
        "server": {
            "host": "0.0.0.0",
            "port": 5001,
        },
        "stt": {
            "model_size": "turbo",
            "device": "cuda",
            "language": "ko",
        },
        "llm": {
            "provider": "ollama",
            "base_url": "http://localhost:11434",
            "model": DEFAULT_OLLAMA_MODEL,
            "ollama_model": DEFAULT_OLLAMA_MODEL,
            "api_models": {
                "gemini": DEFAULT_API_MODELS["gemini"],
                "claude": DEFAULT_API_MODELS["claude"],
                "chatgpt": DEFAULT_API_MODELS["chatgpt"],
            },
            "priority": list(DEFAULT_LLM_PRIORITY),
            "api_priority": build_default_api_priority("ollama"),
            "think": False,
            "auto_start": True,
            "start_command": "ollama serve",
            "startup_timeout": 10.0,
        },
        "tts": {
            "backend": "edge_tts",
            "voice": "ko-KR-SunHiNeural",
            "model": "gemini-3.8-flash-lite-tts",
            "gemini_voice": "Kore",
        },
        "assistant": {
            "name": "ccoli",
            "personality": "cheerful",
            "proactive": True,
            "proactive_interval": 1800,
        },
        "agent": {"enabled": False, "state_path": ""},
        "features": {
            "robot_mode_enabled": False,
        },
        "robot": {
            "controller": "legacy_direct",
            "transport": "local",
            "companion": {
                "transport": "uart",
                "baudrate": 115200,
                "tx_pin": 26,
                "rx_pin": 32,
            },
            "servo": {
                "count": 2,
                "pin_pitch": 26,
                "pin_tilt": 32,
                "angle_min": 0,
                "angle_max": 180,
                "default_angle": 90,
            },
            "display": {
                "type": "ssd1306",
                "width": 128,
                "height": 64,
                "i2c_scl": 21,
                "i2c_sda": 25,
                "i2c_addr": "0x3C",
            },
            "idle": {
                "blink_interval_min": 3000,
                "blink_interval_max": 5000,
                "gaze_interval": 8000,
            },
            "emotion": {
                "default": "neutral",
                "decay_to_neutral": True,
                "decay_interval": 30,
                "persist_sec": 900,
            },
        },
        "weather": {
            "api_key": "",
            "lat": 37.5665,
            "lon": 126.9780,
        },
        "context": {
            "max_history": 20,
            "backup_interval": 10,
            "auto_save": True,
        },
        "emotion": {
            "enabled": True,
            "decay_to_neutral": True,
            "decay_interval": 300,
        },
        "memory": {
            "refresh_interval": 5,
            "memory_dir": "memory",
        },
        "logging": {
            "level": "INFO",
            "save_to_file": True,
            "log_dir": "logs",
        },
        "connection": {
            "mode": "auto",
            "priority": list(DEFAULT_CONNECTION_PRIORITY),
            "socket_timeout": 0.5,
            "serial_port": "auto",
            "serial_baudrate": 115200,
            "serial_scan_interval": 1.0,
            "serial_initial_idle_timeout_s": 5.0,
        },
        "queue": {
            "stt_maxsize": 4,
            "tts_maxsize": 2,
            "command_maxsize": 10,
        },
        "audio": {
            "max_seconds": 12,
        },
        "integrations": {
            "weather": {"enabled": True},
            "search": {"enabled": True},
            "calendar-google": {"enabled": True},
            "notify-slack": {"enabled": True},
            "maps": {"enabled": True},
        },
        "voice_id": {
            "enabled": False,
            "threshold": 0.72,
        },
        "telegram": {
            "enabled": False,
            "bot_token": "",
            "allowed_chat_ids": [],
            "min_interval_sec": 0.5,
            "poll_interval_sec": 1.0,
            "long_poll_timeout_sec": 20.0,
        },
        "web": {
            "enabled": True,
            "host": "0.0.0.0",
            "port": 8005,
            "auth_token": "",
            "log_tail_lines": 200,
        },
        "runtime": {
            "processor_priority": list(DEFAULT_PROCESSOR_PRIORITY),
        },
    }

    def __init__(self, config_file: str = "config.yaml"):
        self.config_file = config_file
        self.config = copy.deepcopy(self.DEFAULT_CONFIG)
        self._yaml_config: dict = {}
        self._env_secret_paths: set[tuple[str, ...]] = set()

        self._load_yaml()
        self._load_env()
        self._apply_runtime_defaults()

        log.info("Configuration loaded successfully")

    def _load_yaml(self):
        """Load config.yaml file."""
        try:
            if Path(self.config_file).exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    yaml_config = yaml.safe_load(f)
                    if yaml_config:
                        if not isinstance(yaml_config, dict):
                            raise ValueError("config.yaml must contain a mapping")
                        self._yaml_config = copy.deepcopy(yaml_config)
                        self._merge_config(self.config, yaml_config)
                        log.info("Loaded config from %s", self.config_file)
            else:
                log.warning("%s not found, using defaults", self.config_file)
        except Exception as exc:
            log.error("Failed to load %s: %s", self.config_file, exc)

    def _load_env(self):
        """Load environment variables (supports .env file)."""
        try:
            try:
                from dotenv import load_dotenv

                load_dotenv()
                log.info("Loaded .env file")
            except ImportError:
                pass

            self._env_secret_paths = {
                path for env_key, path in _SECRET_ENV_PATHS.items() if env_key in os.environ
            }

            if "WEATHER_API_KEY" in os.environ:
                self.config["weather"]["api_key"] = os.environ["WEATHER_API_KEY"]

            if "LLM_PROVIDER" in os.environ:
                self.config["llm"]["provider"] = os.environ["LLM_PROVIDER"]

            if "LLM_MODEL" in os.environ:
                self.config["llm"]["model"] = os.environ["LLM_MODEL"]

            if "OLLAMA_MODEL" in os.environ:
                self.config.setdefault("llm", {})["ollama_model"] = os.environ["OLLAMA_MODEL"]

            if "GEMINI_MODEL" in os.environ:
                self.config.setdefault("llm", {}).setdefault("api_models", {})["gemini"] = os.environ["GEMINI_MODEL"]

            if "CLAUDE_MODEL" in os.environ:
                self.config.setdefault("llm", {}).setdefault("api_models", {})["claude"] = os.environ["CLAUDE_MODEL"]

            if "CHATGPT_MODEL" in os.environ:
                self.config.setdefault("llm", {}).setdefault("api_models", {})["chatgpt"] = os.environ["CHATGPT_MODEL"]

            if "OPENAI_API_KEY" in os.environ:
                self.config["llm"]["openai_api_key"] = os.environ["OPENAI_API_KEY"]

            if "ANTHROPIC_API_KEY" in os.environ:
                self.config["llm"]["anthropic_api_key"] = os.environ["ANTHROPIC_API_KEY"]

            if "GEMINI_API_KEY" in os.environ:
                self.config["llm"]["gemini_api_key"] = os.environ["GEMINI_API_KEY"]

            if "TAVILY_API_KEY" in os.environ:
                self.config.setdefault("integrations", {}).setdefault("search", {})["api_key"] = os.environ["TAVILY_API_KEY"]
            if "SLACK_BOT_TOKEN" in os.environ:
                self.config.setdefault("integrations", {}).setdefault("notify-slack", {})["api_key"] = os.environ["SLACK_BOT_TOKEN"]
            if "GOOGLE_MAPS_API_KEY" in os.environ:
                self.config.setdefault("integrations", {}).setdefault("maps", {})["api_key"] = os.environ["GOOGLE_MAPS_API_KEY"]
            for env_key, field in (
                ("GOOGLE_CLIENT_ID", "client_id"),
                ("GOOGLE_CLIENT_SECRET", "client_secret"),
                ("GOOGLE_REFRESH_TOKEN", "refresh_token"),
                ("GOOGLE_CALENDAR_ID", "calendar_id"),
                ("GOOGLE_CALENDAR_TIME_ZONE", "time_zone"),
            ):
                if env_key in os.environ:
                    self.config.setdefault("integrations", {}).setdefault("calendar-google", {}).setdefault("fields", {})[
                        field
                    ] = os.environ[env_key]
            if "TELEGRAM_ENABLED" in os.environ:
                self.config.setdefault("telegram", {})["enabled"] = _coerce_bool(os.environ["TELEGRAM_ENABLED"])
            if "TELEGRAM_BOT_TOKEN" in os.environ:
                self.config.setdefault("telegram", {})["bot_token"] = os.environ["TELEGRAM_BOT_TOKEN"]
            if "TELEGRAM_ALLOWED_CHAT_IDS" in os.environ:
                self.config.setdefault("telegram", {})["allowed_chat_ids"] = _normalize_string_list(
                    os.environ["TELEGRAM_ALLOWED_CHAT_IDS"]
                )
            if "TELEGRAM_MIN_INTERVAL_SEC" in os.environ:
                self.config.setdefault("telegram", {})["min_interval_sec"] = float(os.environ["TELEGRAM_MIN_INTERVAL_SEC"])
            if "TELEGRAM_POLL_INTERVAL_SEC" in os.environ:
                self.config.setdefault("telegram", {})["poll_interval_sec"] = float(
                    os.environ["TELEGRAM_POLL_INTERVAL_SEC"]
                )
            if "TELEGRAM_LONG_POLL_TIMEOUT_SEC" in os.environ:
                self.config.setdefault("telegram", {})["long_poll_timeout_sec"] = float(
                    os.environ["TELEGRAM_LONG_POLL_TIMEOUT_SEC"]
                )
            if "VOICE_ID_ENABLED" in os.environ:
                self.config.setdefault("voice_id", {})["enabled"] = os.environ["VOICE_ID_ENABLED"].lower() in {"1", "true", "yes", "on"}
            if "VOICE_ID_THRESHOLD" in os.environ:
                self.config.setdefault("voice_id", {})["threshold"] = float(os.environ["VOICE_ID_THRESHOLD"])

            if "SERVER_PORT" in os.environ:
                self.config["server"]["port"] = int(os.environ["SERVER_PORT"])

            if "SERIAL_PORT" in os.environ:
                self.config.setdefault("connection", {})["serial_port"] = os.environ["SERIAL_PORT"]

            if "SERIAL_BAUDRATE" in os.environ:
                self.config.setdefault("connection", {})["serial_baudrate"] = int(os.environ["SERIAL_BAUDRATE"])

            if "STT_MODEL_SIZE" in os.environ:
                self.config.setdefault("stt", {})["model_size"] = os.environ["STT_MODEL_SIZE"]

            if "STT_DEVICE" in os.environ:
                self.config.setdefault("stt", {})["device"] = os.environ["STT_DEVICE"]
            elif "DEVICE" in os.environ:
                self.config.setdefault("stt", {})["device"] = os.environ["DEVICE"]

            if "STT_LANGUAGE" in os.environ:
                self.config.setdefault("stt", {})["language"] = os.environ["STT_LANGUAGE"]

            if "TTS_VOICE" in os.environ:
                self.config.setdefault("tts", {})["voice"] = os.environ["TTS_VOICE"]

            if "TTS_MODEL" in os.environ:
                self.config.setdefault("tts", {})["model"] = os.environ["TTS_MODEL"]

            if "TTS_GEMINI_VOICE" in os.environ:
                self.config.setdefault("tts", {})["gemini_voice"] = os.environ["TTS_GEMINI_VOICE"]
            if "TTS_BACKEND" in os.environ:
                self.config.setdefault("tts", {})["backend"] = os.environ["TTS_BACKEND"]

            if "WEB_HOST" in os.environ:
                self.config.setdefault("web", {})["host"] = os.environ["WEB_HOST"]
            if "WEB_PORT" in os.environ:
                self.config.setdefault("web", {})["port"] = int(os.environ["WEB_PORT"])
            if "WEB_AUTH_TOKEN" in os.environ:
                self.config.setdefault("web", {})["auth_token"] = os.environ["WEB_AUTH_TOKEN"]

            if "AGENT_ENABLED" in os.environ:
                self.config.setdefault("agent", {})["enabled"] = _coerce_bool(os.environ["AGENT_ENABLED"])
            if "AGENT_STATE_PATH" in os.environ:
                self.config.setdefault("agent", {})["state_path"] = os.environ["AGENT_STATE_PATH"]

            if "MEMORY_DIR" in os.environ:
                self.config.setdefault("memory", {})["memory_dir"] = os.environ["MEMORY_DIR"]

            if "MEMORY_REFRESH_INTERVAL" in os.environ:
                self.config.setdefault("memory", {})["refresh_interval"] = int(os.environ["MEMORY_REFRESH_INTERVAL"])

            if "ASSISTANT_NAME" in os.environ:
                self.config["assistant"]["name"] = os.environ["ASSISTANT_NAME"]

            if "LOG_LEVEL" in os.environ:
                self.config["logging"]["level"] = os.environ["LOG_LEVEL"]

            if "LLM_PRIORITY" in os.environ:
                self.config.setdefault("llm", {})["priority"] = os.environ["LLM_PRIORITY"]

            if "LLM_API_PRIORITY" in os.environ:
                self.config.setdefault("llm", {})["api_priority"] = os.environ["LLM_API_PRIORITY"]

            if "CONNECTION_PRIORITY" in os.environ:
                self.config.setdefault("connection", {})["priority"] = os.environ["CONNECTION_PRIORITY"]

            if "PROCESSOR_PRIORITY" in os.environ:
                self.config.setdefault("runtime", {})["processor_priority"] = os.environ["PROCESSOR_PRIORITY"]

        except Exception as exc:
            log.error("Failed to load environment variables: %s", exc)

    def _apply_runtime_defaults(self):
        llm_cfg = self.config.setdefault("llm", {})
        provider = (llm_cfg.get("provider", "ollama") or "ollama").strip().lower()

        llm_models = resolve_llm_models(llm_cfg)
        llm_cfg["ollama_model"] = llm_models["ollama"]
        api_models = llm_cfg.setdefault("api_models", {})
        api_models["gemini"] = llm_models["gemini"]
        api_models["claude"] = llm_models["claude"]
        api_models["chatgpt"] = llm_models["chatgpt"]

        llm_cfg["priority"] = normalize_priority_list(
            llm_cfg.get("priority"),
            ("ollama", "api", "ollama_cpu", "other"),
            DEFAULT_LLM_PRIORITY,
        )
        llm_cfg["api_priority"] = normalize_priority_list(
            llm_cfg.get("api_priority"),
            ("gemini", "claude", "chatgpt"),
            build_default_api_priority(provider),
        )

        tts_cfg = self.config.setdefault("tts", {})
        tts_cfg["backend"] = (tts_cfg.get("backend") or "edge_tts").strip().lower()

        features_cfg = self.config.setdefault("features", {})
        features_cfg["robot_mode_enabled"] = _coerce_bool(features_cfg.get("robot_mode_enabled"), False)

        robot_cfg = self.config.setdefault("robot", {})
        controller = str(robot_cfg.get("controller", "legacy_direct") or "legacy_direct").strip().lower()
        if controller not in {"legacy_direct", "companion_uart"}:
            controller = "legacy_direct"
        robot_cfg["controller"] = controller
        # transport is derived from controller, never read back from the merged
        # config: the defaults always seed "local", so honoring an existing value
        # would pin a companion_uart build to the legacy local transport.
        # Keep this in sync with src/robot_mode._normalize_robot_config.
        robot_cfg["transport"] = "companion" if controller == "companion_uart" else "local"

        companion_cfg = robot_cfg.setdefault("companion", {})
        companion_cfg["transport"] = "uart"
        try:
            companion_cfg["baudrate"] = int(companion_cfg.get("baudrate", 115200) or 115200)
        except (TypeError, ValueError):
            companion_cfg["baudrate"] = 115200
        for pin_key, default_pin in (("tx_pin", 26), ("rx_pin", 32)):
            try:
                companion_cfg[pin_key] = int(companion_cfg.get(pin_key, default_pin))
            except (TypeError, ValueError):
                companion_cfg[pin_key] = default_pin

        servo_cfg = robot_cfg.setdefault("servo", {})
        try:
            servo_count = int(servo_cfg.get("count", 2) or 2)
        except (TypeError, ValueError):
            servo_count = 2
        servo_cfg["count"] = min(4, max(1, servo_count))

        display_cfg = robot_cfg.setdefault("display", {})
        display_cfg["type"] = normalize_display_type(display_cfg.get("type"), controller)

        robot_emotion_cfg = robot_cfg.setdefault("emotion", {})
        try:
            robot_emotion_cfg["persist_sec"] = int(robot_emotion_cfg.get("persist_sec", 900) or 900)
        except (TypeError, ValueError):
            robot_emotion_cfg["persist_sec"] = 900

        connection_cfg = self.config.setdefault("connection", {})
        connection_cfg["priority"] = normalize_priority_list(
            connection_cfg.get("priority"),
            ("wired", "wifi"),
            DEFAULT_CONNECTION_PRIORITY,
        )

        runtime_cfg = self.config.setdefault("runtime", {})
        runtime_cfg["processor_priority"] = normalize_priority_list(
            runtime_cfg.get("processor_priority"),
            ("gpu", "cpu"),
            DEFAULT_PROCESSOR_PRIORITY,
        )

        telegram_cfg = self.config.setdefault("telegram", {})
        telegram_cfg["enabled"] = _coerce_bool(telegram_cfg.get("enabled"), False)
        telegram_cfg["bot_token"] = str(telegram_cfg.get("bot_token", "") or "").strip()
        telegram_cfg["allowed_chat_ids"] = _normalize_string_list(telegram_cfg.get("allowed_chat_ids"))
        telegram_cfg["min_interval_sec"] = _coerce_float(telegram_cfg.get("min_interval_sec"), 0.5)
        telegram_cfg["poll_interval_sec"] = _coerce_float(telegram_cfg.get("poll_interval_sec"), 1.0)
        telegram_cfg["long_poll_timeout_sec"] = _coerce_float(telegram_cfg.get("long_poll_timeout_sec"), 20.0)

    def _merge_config(self, base: Dict, override: Dict):
        """Recursively merge dictionaries."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value

    def get(self, *keys, default=None) -> Any:
        """
        Get a value using nested keys.
        e.g. config.get("server", "port") -> 5001
        """
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def get_server_config(self) -> Dict:
        return self.config.get("server", {})

    def get_stt_config(self) -> Dict:
        return self.config.get("stt", {})

    def get_llm_config(self) -> Dict:
        return self.config.get("llm", {})

    def get_tts_config(self) -> Dict:
        return self.config.get("tts", {})

    def get_assistant_config(self) -> Dict:
        return self.config.get("assistant", {})

    def get_features_config(self) -> Dict:
        return self.config.get("features", {})

    def get_robot_config(self) -> Dict:
        return self.config.get("robot", {})

    def get_weather_config(self) -> Dict:
        return self.config.get("weather", {})

    def get_context_config(self) -> Dict:
        return self.config.get("context", {})

    def get_emotion_config(self) -> Dict:
        return self.config.get("emotion", {})

    def get_logging_config(self) -> Dict:
        return self.config.get("logging", {})

    def get_voice_id_config(self) -> Dict:
        return self.config.get("voice_id", {})

    def get_telegram_config(self) -> Dict:
        return self.config.get("telegram", {})

    def save(self, config_file: str = None):
        file_path = config_file or self.config_file
        try:
            saved = copy.deepcopy(self.config)
            for path in self._env_secret_paths:
                _restore_nested_value(saved, self._yaml_config, path)
            with open(file_path, "w", encoding="utf-8") as f:
                yaml.dump(saved, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            if file_path == self.config_file:
                self._yaml_config = saved
            log.info("Configuration saved to %s", file_path)
        except Exception as exc:
            log.error("Failed to save config to %s: %s", file_path, exc)


_config = None


def get_config(config_file: str = "config.yaml") -> Config:
    """Return singleton Config instance."""
    global _config
    if _config is None:
        _config = Config(config_file)
    return _config
