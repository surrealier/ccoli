from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Mapping, Sequence


log = logging.getLogger(__name__)

LLM_PRIORITY_ALLOWED = ("ollama", "api", "ollama_cpu", "other")
API_PRIORITY_ALLOWED = ("gemini", "claude", "chatgpt")
CONNECTION_PRIORITY_ALLOWED = ("wired", "wifi")
PROCESSOR_PRIORITY_ALLOWED = ("gpu", "cpu")

DEFAULT_OLLAMA_MODEL = "qwen3.5:4b"
DEFAULT_API_MODELS = {
    "gemini": "gemini-3.8-flash",
    "claude": "claude-sonnet-5-5",
    "chatgpt": "gpt-6-luna",
}
DEFAULT_LLM_PRIORITY = ["ollama", "api", "ollama_cpu", "other"]
DEFAULT_API_PRIORITY = ["gemini", "claude", "chatgpt"]
DEFAULT_CONNECTION_PRIORITY = ["wired", "wifi"]
DEFAULT_PROCESSOR_PRIORITY = ["gpu", "cpu"]


def normalize_priority_list(value, allowed: Sequence[str], default: Sequence[str]) -> list[str]:
    allowed_set = {item.lower() for item in allowed}
    normalized: list[str] = []

    if isinstance(value, str):
        raw_items = [
            item.strip().lower()
            for item in value.replace(">", ",").replace("|", ",").split(",")
            if item.strip()
        ]
    elif isinstance(value, Sequence):
        raw_items = [str(item).strip().lower() for item in value if str(item).strip()]
    else:
        raw_items = []

    for item in raw_items:
        if item in allowed_set and item not in normalized:
            normalized.append(item)

    for item in default:
        lowered = str(item).lower()
        if lowered in allowed_set and lowered not in normalized:
            normalized.append(lowered)

    return normalized


def build_default_api_priority(current_provider: str | None = None) -> list[str]:
    provider = (current_provider or "").strip().lower()
    ordered = []
    if provider in API_PRIORITY_ALLOWED:
        ordered.append(provider)
    for item in DEFAULT_API_PRIORITY:
        if item not in ordered:
            ordered.append(item)
    return ordered


def resolve_llm_models(llm_config: Mapping) -> dict[str, str]:
    provider = (llm_config.get("provider", "ollama") or "ollama").strip().lower()
    legacy_model = (llm_config.get("model") or "").strip()
    api_models_cfg = llm_config.get("api_models") or {}
    api_models_cfg = api_models_cfg if isinstance(api_models_cfg, Mapping) else {}

    models = {
        "ollama": (llm_config.get("ollama_model") or "").strip(),
        "gemini": (api_models_cfg.get("gemini") or "").strip(),
        "claude": (api_models_cfg.get("claude") or "").strip(),
        "chatgpt": (api_models_cfg.get("chatgpt") or "").strip(),
    }

    if provider == "ollama" and legacy_model and not models["ollama"]:
        models["ollama"] = legacy_model

    for api_provider, default_model in DEFAULT_API_MODELS.items():
        if provider == api_provider and legacy_model and not models[api_provider]:
            models[api_provider] = legacy_model
        if not models[api_provider]:
            models[api_provider] = default_model

    if not models["ollama"]:
        models["ollama"] = DEFAULT_OLLAMA_MODEL

    return models


@dataclass
class HardwareProfile:
    accelerators: list[str] = field(default_factory=list)
    platform: str = field(default_factory=lambda: sys.platform)

    @classmethod
    def detect(cls) -> "HardwareProfile":
        force_cpu = os.getenv("CCOLI_FORCE_CPU", "").strip().lower() in {"1", "true", "yes", "on"}
        if force_cpu:
            return cls(accelerators=[], platform=sys.platform)

        accelerators: list[str] = []

        force_gpu = os.getenv("CCOLI_FORCE_GPU", "").strip().lower() in {"1", "true", "yes", "on"}
        if force_gpu:
            accelerators.append("forced")

        try:
            import torch

            if getattr(torch, "cuda", None) and torch.cuda.is_available():
                accelerators.append("cuda")

            backends = getattr(torch, "backends", None)
            mps_backend = getattr(backends, "mps", None)
            if mps_backend and mps_backend.is_available():
                accelerators.append("mps")
        except Exception:
            pass

        try:
            import onnxruntime as ort

            provider_map = {
                "CUDAExecutionProvider": "cuda",
                "ROCMExecutionProvider": "rocm",
                "DmlExecutionProvider": "directml",
                "OpenVINOExecutionProvider": "openvino",
                "CoreMLExecutionProvider": "coreml",
            }
            for provider in ort.get_available_providers():
                mapped = provider_map.get(provider)
                if mapped:
                    accelerators.append(mapped)
        except Exception:
            pass

        if shutil.which("nvidia-smi"):
            try:
                result = subprocess.run(
                    ["nvidia-smi", "-L"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=2.0,
                )
                if result.returncode == 0 and result.stdout.strip():
                    accelerators.append("cuda")
            except Exception:
                pass

        deduped: list[str] = []
        for accelerator in accelerators:
            if accelerator not in deduped:
                deduped.append(accelerator)
        return cls(accelerators=deduped, platform=sys.platform)

    @property
    def gpu_available(self) -> bool:
        return bool(self.accelerators)

    @property
    def cuda_available(self) -> bool:
        return "cuda" in self.accelerators

    @property
    def mps_available(self) -> bool:
        return "mps" in self.accelerators

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "accelerators": list(self.accelerators),
            "gpu_available": self.gpu_available,
            "cuda_available": self.cuda_available,
            "mps_available": self.mps_available,
        }


@dataclass
class RuntimePreferences:
    llm_priority: list[str]
    api_priority: list[str]
    connection_priority: list[str]
    processor_priority: list[str]
    llm_models: dict[str, str]
    hardware: HardwareProfile = field(default_factory=HardwareProfile.detect)
    tts_backend: str = "edge_tts"

    @classmethod
    def from_mapping(cls, config: Mapping) -> "RuntimePreferences":
        llm_cfg = config.get("llm") or {}
        connection_cfg = config.get("connection") or {}
        runtime_cfg = config.get("runtime") or {}
        llm_provider = (llm_cfg.get("provider", "ollama") or "ollama").strip().lower()

        llm_priority = normalize_priority_list(
            llm_cfg.get("priority"),
            LLM_PRIORITY_ALLOWED,
            DEFAULT_LLM_PRIORITY,
        )
        api_priority = normalize_priority_list(
            llm_cfg.get("api_priority"),
            API_PRIORITY_ALLOWED,
            build_default_api_priority(llm_provider),
        )
        connection_priority = normalize_priority_list(
            connection_cfg.get("priority"),
            CONNECTION_PRIORITY_ALLOWED,
            DEFAULT_CONNECTION_PRIORITY,
        )
        processor_priority = normalize_priority_list(
            runtime_cfg.get("processor_priority"),
            PROCESSOR_PRIORITY_ALLOWED,
            DEFAULT_PROCESSOR_PRIORITY,
        )

        tts_cfg = config.get("tts") or {}
        tts_backend = (tts_cfg.get("backend") or "edge_tts").strip().lower()
        llm_models = resolve_llm_models(llm_cfg)
        return cls(
            llm_priority=llm_priority,
            api_priority=api_priority,
            connection_priority=connection_priority,
            processor_priority=processor_priority,
            llm_models=llm_models,
            hardware=HardwareProfile.detect(),
            tts_backend=tts_backend or "edge_tts",
        )

    def resolved_stt_devices(self) -> list[str]:
        devices: list[str] = []
        for item in self.processor_priority:
            if item == "gpu" and self.hardware.cuda_available and "cuda" not in devices:
                devices.append("cuda")
            if item == "cpu" and "cpu" not in devices:
                devices.append("cpu")

        if "cpu" not in devices:
            devices.append("cpu")
        return devices

    def gpu_bucket_enabled(self) -> bool:
        return "gpu" in self.processor_priority and self.hardware.gpu_available

    @staticmethod
    def stt_supported_devices() -> list[str]:
        return ["cuda", "cpu"]

    def audio_runtime_notes(self) -> list[str]:
        notes: list[str] = []

        if self.hardware.platform == "darwin":
            if self.hardware.mps_available:
                notes.append(
                    "macOS MPS was detected, but the current STT backend "
                    "uses faster-whisper with CPU/CUDA only, so STT stays on CPU."
                )
            else:
                notes.append(
                    "On macOS the current STT backend uses CPU in this project "
                    "because the faster-whisper path does not use MPS here."
                )

        if self.tts_backend == "gemini_tts":
            notes.append(
                "Gemini TTS is a remote model; local GPU, CPU, and MPS selection does not apply."
            )
        if self.tts_backend in {"edge_tts", "edge-tts"}:
            notes.append(
                "Current TTS backend is Edge TTS, so it does not use local GPU, CPU, or MPS selection."
            )

        return notes

    def to_dict(self) -> dict:
        return {
            "llm_priority": list(self.llm_priority),
            "api_priority": list(self.api_priority),
            "connection_priority": list(self.connection_priority),
            "processor_priority": list(self.processor_priority),
            "llm_models": dict(self.llm_models),
            "hardware": self.hardware.to_dict(),
            "stt_supported_devices": self.stt_supported_devices(),
            "stt_mps_supported": False,
            "tts_backend": self.tts_backend,
            "tts_mps_supported": False,
            "tts_processor_selectable": self.tts_backend not in {"edge_tts", "edge-tts", "gemini_tts"},
            "audio_runtime_notes": self.audio_runtime_notes(),
        }
