from __future__ import annotations

import copy
import logging
import threading
import re
from typing import Any

from .runtime_preferences import (
    API_PRIORITY_ALLOWED,
    CONNECTION_PRIORITY_ALLOWED,
    LLM_PRIORITY_ALLOWED,
    PROCESSOR_PRIORITY_ALLOWED,
    RuntimePreferences,
    normalize_priority_list,
)


log = logging.getLogger(__name__)

_COMMAND_PREFIX_RE = re.compile(r"^\s*@@\s*")
_PRIORITY_KW = "\uc6b0\uc120\uc21c\uc704"
_MODEL_KW = "\ubaa8\ub378"
_API_KW = "api"
_CONNECTION_KW = "\uc5f0\uacb0"
_NETWORK_KW = "\ub124\ud2b8\uc6cc\ud06c"
_PROCESSOR_KW = "\ud504\ub85c\uc138\uc11c"
_STATUS_WORDS = (
    f"{_PRIORITY_KW} \uc0c1\ud0dc",
    f"{_PRIORITY_KW} \ubcf4\uc5ec",
    f"{_PRIORITY_KW} \uc54c\ub824",
    f"\ud604\uc7ac {_PRIORITY_KW}",
)

_MODEL_ALIASES = {
    "ollama_cpu": (
        "ollama cpu",
        "ollama(local, cpu)",
        "ollama local cpu",
        "\ub85c\uceec ollama cpu",
        "\ub85c\uceec \uc62c\ub77c\ub9c8 cpu",
        "\uc62c\ub77c\ub9c8 cpu",
    ),
    "ollama": (
        "ollama(local)",
        "ollama local",
        "\ub85c\uceec ollama",
        "\ub85c\uceec \uc62c\ub77c\ub9c8",
        "ollama",
        "\uc62c\ub77c\ub9c8",
    ),
    "api": (
        "cloud api",
        "\ud074\ub77c\uc6b0\ub4dc api",
        "api",
    ),
    "other": (
        "\uadf8 \uc678",
        "\uae30\ud0c0",
        "other",
    ),
}

_API_ALIASES = {
    "gemini": ("gemini", "\uc81c\ubbf8\ub2c8"),
    "claude": ("claude", "\ud074\ub85c\ub4dc"),
    "chatgpt": ("chatgpt", "chat gpt", "gpt", "\ucc57\uc9c0\ud53c\ud2f0", "\ucc57gpt"),
}

_CONNECTION_ALIASES = {
    "wired": ("wired", "usb", "\uc720\uc120"),
    "wifi": ("wi-fi", "wifi", "\ubb34\uc120"),
}

_PROCESSOR_ALIASES = {
    "gpu": ("gpu", "cuda", "\uac00\uc18d", "\uadf8\ub798\ud53d"),
    "cpu": ("cpu",),
}

_CATEGORY_PATTERNS = {
    "llm": re.compile(r"(\ubaa8\ub378|llm)\s*\uc6b0\uc120\uc21c\uc704", re.IGNORECASE),
    "api": re.compile(r"(api|provider)\s*\uc6b0\uc120\uc21c\uc704", re.IGNORECASE),
    "connection": re.compile(r"(\uc5f0\uacb0|\ub124\ud2b8\uc6cc\ud06c)\s*\uc6b0\uc120\uc21c\uc704", re.IGNORECASE),
    "processor": re.compile(r"(\ud504\ub85c\uc138\uc11c|processor)\s*\uc6b0\uc120\uc21c\uc704", re.IGNORECASE),
}


def _canonical_order_from_aliases(text: str, aliases: dict[str, tuple[str, ...]], default: list[str]) -> list[str]:
    lowered = text.lower()
    matches: list[tuple[int, int, str]] = []
    for canonical, patterns in aliases.items():
        best = None
        for pattern in patterns:
            idx = lowered.find(pattern.lower())
            if idx >= 0:
                candidate = (idx, len(pattern), canonical)
                if best is None or candidate[0] < best[0] or (
                    candidate[0] == best[0] and candidate[1] > best[1]
                ):
                    best = candidate
        if best is not None:
            matches.append(best)

    matches.sort(key=lambda item: (item[0], -item[1]))
    ordered: list[str] = []
    occupied: list[tuple[int, int]] = []
    for start, length, canonical in matches:
        end = start + length
        if any(start < taken_end and end > taken_start for taken_start, taken_end in occupied):
            continue
        occupied.append((start, end))
        ordered.append(canonical)
    return normalize_priority_list(ordered, tuple(aliases.keys()), default)


def _extract_segment(text: str, category: str) -> str:
    pattern = _CATEGORY_PATTERNS[category]
    match = pattern.search(text)
    if not match:
        return ""

    end = len(text)
    for key, other in _CATEGORY_PATTERNS.items():
        if key == category:
            continue
        next_match = other.search(text, match.end())
        if next_match:
            end = min(end, next_match.start())
    return text[match.start():end]


class RuntimeController:
    def __init__(self, config):
        self.config = config
        self.preferences = RuntimePreferences.from_mapping(self.config.config)
        self.llm_client = None
        self.stt_engine = None
        self.agent = None
        self._dialogue_settings_lock = threading.RLock()

    def bind(self, *, llm_client=None, stt_engine=None, agent=None):
        if llm_client is not None:
            self.llm_client = llm_client
        if stt_engine is not None:
            self.stt_engine = stt_engine
        if agent is not None:
            self.agent = agent
        self.refresh_from_config(save=False)

    def refresh_from_config(self, save: bool = False):
        self._ensure_runtime_defaults()
        if save:
            self.config.save()

        self.preferences = RuntimePreferences.from_mapping(self.config.config)

        if self.llm_client and hasattr(self.llm_client, "reload_runtime_preferences"):
            self.llm_client.reload_runtime_preferences(
                self.preferences,
                self.config.get_llm_config(),
            )

        if self.stt_engine and hasattr(self.stt_engine, "set_device_priority"):
            self.stt_engine.set_device_priority(self.preferences.resolved_stt_devices())

        self._apply_dialogue_settings(self._dialogue_settings())

    def _dialogue_settings(self) -> dict[str, Any]:
        values = self.config.get('dialogue', default={}) or {}
        return {
            'language': values.get('language', self.config.get('stt', 'language', default='auto')),
            'short_responses': values.get('short_responses', True),
            'fast_model': values.get('fast_model', ''),
        }

    def _apply_dialogue_settings(self, settings: dict[str, Any]) -> None:
        if self.stt_engine is not None and hasattr(self.stt_engine, 'set_language'):
            self.stt_engine.set_language(settings['language'])
        if self.agent is not None and hasattr(self.agent, 'configure_dialogue'):
            self.agent.configure_dialogue(**settings)

    def update_dialogue(self, changes: dict[str, Any]) -> dict[str, Any]:
        from .dialogue_policy import normalize_language
        with self._dialogue_settings_lock:
            candidate = {**self._dialogue_settings(), **changes}
            candidate['language'] = normalize_language(candidate['language'], allow_auto=True)
            if type(candidate['short_responses']) is not bool:
                raise ValueError('Choose a short or detailed response style')
            model = candidate['fast_model']
            if not isinstance(model, str) or len(model) > 96 or (model and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]*', model)):
                raise ValueError('Choose a supported fast model')
            previous = copy.deepcopy(self.config.config)
            prior_settings = self._dialogue_settings()
            try:
                self._apply_dialogue_settings(candidate)
                self.config.config['dialogue'] = dict(candidate)
                self.config.config.setdefault('stt', {})['language'] = candidate['language']
                self.config.save()
            except Exception:
                self.config.config = previous
                self._apply_dialogue_settings(prior_settings)
                raise
            return dict(candidate)

    def get_connection_priority(self) -> list[str]:
        return list(self.preferences.connection_priority)

    def status_snapshot(self) -> dict[str, Any]:
        llm_status = {}
        if self.llm_client and hasattr(self.llm_client, "describe_runtime"):
            llm_status = self.llm_client.describe_runtime()

        stt_status = {}
        if self.stt_engine is not None:
            stt_status = {
                "configured_devices": list(getattr(self.stt_engine, "device_priority", [])),
                "device_in_use": getattr(self.stt_engine, "device_in_use", None),
            }

        runtime = self.preferences.to_dict()
        runtime["connection_mode"] = self.config.get("connection", "mode", default="auto")
        runtime["llm"] = llm_status
        runtime["stt"] = stt_status
        return runtime

    def handle_text_command(self, text: str) -> str | None:
        if not text:
            return None

        parsed = self._parse_command(text)
        if parsed is None:
            return None

        if parsed["action"] == "status":
            return self._build_status_message()

        updates = parsed["updates"]
        if not updates:
            return self._build_help_message()

        llm_cfg = self.config.config.setdefault("llm", {})
        connection_cfg = self.config.config.setdefault("connection", {})
        runtime_cfg = self.config.config.setdefault("runtime", {})

        changed_parts = []
        if "llm_priority" in updates:
            llm_cfg["priority"] = updates["llm_priority"]
            changed_parts.append(
                f"\ubaa8\ub378 {_PRIORITY_KW}: "
                + " > ".join(self._format_llm_bucket(item) for item in updates["llm_priority"])
            )

        if "api_priority" in updates:
            llm_cfg["api_priority"] = updates["api_priority"]
            changed_parts.append(
                f"API {_PRIORITY_KW}: "
                + " > ".join(item.capitalize() for item in updates["api_priority"])
            )

        if "connection_priority" in updates:
            connection_cfg["priority"] = updates["connection_priority"]
            connection_cfg["mode"] = "auto"
            changed_parts.append(
                f"\uc5f0\uacb0 {_PRIORITY_KW}: "
                + " > ".join(self._format_connection(item) for item in updates["connection_priority"])
            )

        if "processor_priority" in updates:
            runtime_cfg["processor_priority"] = updates["processor_priority"]
            changed_parts.append(
                f"\ud504\ub85c\uc138\uc11c {_PRIORITY_KW}: "
                + " > ".join(item.upper() for item in updates["processor_priority"])
            )

        self.refresh_from_config(save=True)

        response = "\uc6b0\uc120\uc21c\uc704\ub97c \ubc18\uc601\ud588\uc5b4\uc694. " + " / ".join(changed_parts) + "."
        if "processor_priority" in updates and not self.preferences.to_dict()["tts_processor_selectable"]:
            response += " \ucc38\uace0\ub85c \ud604\uc7ac TTS\ub294 Edge TTS\ub77c \ub85c\uceec GPU/CPU \uc120\ud0dd\uc744 \uc9c1\uc811 \uc801\uc6a9\ud558\uc9c0\ub294 \ubabb\ud574\uc694."
        return response

    def _ensure_runtime_defaults(self):
        llm_cfg = self.config.config.setdefault("llm", {})
        connection_cfg = self.config.config.setdefault("connection", {})
        runtime_cfg = self.config.config.setdefault("runtime", {})
        provider = (llm_cfg.get("provider", "ollama") or "ollama").strip().lower()

        llm_cfg["priority"] = normalize_priority_list(
            llm_cfg.get("priority"),
            LLM_PRIORITY_ALLOWED,
            self.preferences.llm_priority if hasattr(self, "preferences") else ["ollama", "api", "ollama_cpu", "other"],
        )
        default_api = [provider] if provider in API_PRIORITY_ALLOWED else []
        default_api.extend(item for item in ("gemini", "claude", "chatgpt") if item not in default_api)
        llm_cfg["api_priority"] = normalize_priority_list(
            llm_cfg.get("api_priority"),
            API_PRIORITY_ALLOWED,
            default_api,
        )
        connection_cfg["priority"] = normalize_priority_list(
            connection_cfg.get("priority"),
            CONNECTION_PRIORITY_ALLOWED,
            ["wired", "wifi"],
        )
        runtime_cfg["processor_priority"] = normalize_priority_list(
            runtime_cfg.get("processor_priority"),
            PROCESSOR_PRIORITY_ALLOWED,
            ["gpu", "cpu"],
        )

    def _parse_command(self, text: str) -> dict[str, Any] | None:
        normalized = _COMMAND_PREFIX_RE.sub("", text.strip())
        lowered = normalized.lower()
        relevant_tokens = (
            _PRIORITY_KW,
            _MODEL_KW,
            _CONNECTION_KW,
            _NETWORK_KW,
            _PROCESSOR_KW,
            "llm",
            "api",
            "priority",
        )
        looks_like_command = (
            _PRIORITY_KW in normalized
            or "priority" in lowered
            or (text.strip().startswith("@@") and any(token.lower() in lowered for token in relevant_tokens))
        )
        if not looks_like_command:
            return None

        if any(keyword in normalized for keyword in _STATUS_WORDS):
            return {"action": "status", "updates": {}}

        updates: dict[str, list[str]] = {}

        llm_segment = _extract_segment(normalized, "llm") or normalized
        if f"{_MODEL_KW} {_PRIORITY_KW}" in normalized or "llm priority" in lowered:
            updates["llm_priority"] = _canonical_order_from_aliases(
                llm_segment,
                _MODEL_ALIASES,
                self.preferences.llm_priority,
            )

        api_segment = _extract_segment(normalized, "api") or normalized
        if f"api {_PRIORITY_KW}" in lowered or "provider priority" in lowered:
            updates["api_priority"] = _canonical_order_from_aliases(
                api_segment,
                _API_ALIASES,
                self.preferences.api_priority,
            )

        connection_segment = _extract_segment(normalized, "connection") or normalized
        if (
            f"{_CONNECTION_KW} {_PRIORITY_KW}" in normalized
            or f"{_NETWORK_KW} {_PRIORITY_KW}" in normalized
            or "connection priority" in lowered
        ):
            updates["connection_priority"] = _canonical_order_from_aliases(
                connection_segment,
                _CONNECTION_ALIASES,
                self.preferences.connection_priority,
            )

        processor_segment = _extract_segment(normalized, "processor") or normalized
        if f"{_PROCESSOR_KW} {_PRIORITY_KW}" in normalized or "processor priority" in lowered:
            updates["processor_priority"] = _canonical_order_from_aliases(
                processor_segment,
                _PROCESSOR_ALIASES,
                self.preferences.processor_priority,
            )

        if not updates and (_PRIORITY_KW in normalized or "priority" in lowered):
            return {"action": "status", "updates": {}}
        if not updates:
            return None
        return {"action": "update", "updates": updates}

    def _build_status_message(self) -> str:
        runtime = self.status_snapshot()
        llm_runtime = runtime.get("llm") or {}
        stt_runtime = runtime.get("stt") or {}

        pieces = [
            "\ud604\uc7ac \uc6b0\uc120\uc21c\uc704 \uc0c1\ud0dc\uc608\uc694.",
            "\ubaa8\ub378: " + " > ".join(self._format_llm_bucket(item) for item in runtime["llm_priority"]),
            "API: " + " > ".join(item.capitalize() for item in runtime["api_priority"]),
            "\uc5f0\uacb0: " + " > ".join(self._format_connection(item) for item in runtime["connection_priority"]),
            "\ud504\ub85c\uc138\uc11c: " + " > ".join(item.upper() for item in runtime["processor_priority"]),
        ]

        active_llm = llm_runtime.get("active_provider")
        active_model = llm_runtime.get("active_model")
        if active_llm and active_model:
            pieces.append(f"\ud604\uc7ac \ud65c\uc131 LLM\uc740 {active_llm}({active_model})\uc774\uc5d0\uc694.")

        stt_device = stt_runtime.get("device_in_use")
        if stt_device:
            pieces.append(f"STT\ub294 \uc9c0\uae08 {stt_device}\ub85c \ub3d9\uc791 \uc911\uc774\uc5d0\uc694.")

        hardware = runtime.get("hardware") or {}
        if hardware.get("platform") == "darwin" and hardware.get("mps_available"):
            pieces.append(
                "macOS에서 MPS는 감지됐지만 현재 STT 백엔드는 CPU/CUDA만 지원해서 STT에는 직접 쓰지 못해요."
            )

        if not runtime.get("tts_processor_selectable", False):
            pieces.append("현재 TTS는 Edge TTS라 로컬 GPU/CPU/MPS 선택을 직접 적용하지는 못해요.")

        return " ".join(pieces)

    @staticmethod
    def _build_help_message() -> str:
        return (
            "\uc6b0\uc120\uc21c\uc704 \uba85\ub839\uc744 \uc774\ud574\ud558\uc9c0 \ubabb\ud588\uc5b4\uc694. \uc608\ub97c \ub4e4\uba74 "
            "@@\ubaa8\ub378 \uc6b0\uc120\uc21c\uc704 ollama > api > ollama cpu > other, "
            "@@\uc5f0\uacb0 \uc6b0\uc120\uc21c\uc704 wired > wifi, "
            "@@\ud504\ub85c\uc138\uc11c \uc6b0\uc120\uc21c\uc704 gpu > cpu, "
            "@@\uc6b0\uc120\uc21c\uc704 \uc0c1\ud0dc \ucc98\ub7fc \ub9d0\ud574 \uc8fc\uc138\uc694."
        )

    @staticmethod
    def _format_llm_bucket(bucket: str) -> str:
        mapping = {
            "ollama": "Ollama(Local)",
            "api": "API",
            "ollama_cpu": "Ollama(Local CPU)",
            "other": "Other",
        }
        return mapping.get(bucket, bucket)

    @staticmethod
    def _format_connection(item: str) -> str:
        return {"wired": "Wired", "wifi": "WiFi"}.get(item, item)
