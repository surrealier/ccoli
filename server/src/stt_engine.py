"""
Whisper 기반 음성 인식(STT) 엔진 모듈
- faster-whisper를 사용한 한국어 음성 인식
- GPU/CPU 자동 폴백 및 스레드 안전 처리
"""

import logging
import os
import sys
import threading
import ctypes
from pathlib import Path
from typing import Sequence

import numpy as np
from faster_whisper import WhisperModel


log = logging.getLogger(__name__)
_CUDA_DLL_PATHS_ADDED = False


class STTEngine:
    """
    음성 인식 엔진 클래스
    - Whisper 모델 로딩 및 관리
    - 스레드 안전한 음성 인식 처리
    """
    def __init__(
        self,
        model_size: str,
        device: str,
        language: str = "ko",
        device_priority: Sequence[str] | None = None,
    ):
        """
        STT 엔진 초기화
        - model_size: Whisper 모델 크기 (tiny, base, small, medium, large)
        - device: 실행 디바이스 (cuda, cpu)
        - language: 인식 언어 (기본값: 한국어)
        """
        self.cpu_threads = self._positive_env_int("STT_CPU_THREADS", 4, 64)
        self.beam_size = self._positive_env_int("STT_BEAM_SIZE", 1, 10)
        self.model_size = model_size
        self.device = device
        self.language = language
        self.model_lock = threading.Lock()  # 모델 접근 동기화를 위한 락
        self.model = None
        self.device_in_use = None
        self.device_priority = self._normalize_device_priority(device_priority or [device, "cpu"])

    @staticmethod
    def _positive_env_int(name: str, default: int, maximum: int) -> int:
        raw = os.environ.get(name, str(default))
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError(f"{name} must be an integer from 1 to {maximum}") from exc
        if not 1 <= value <= maximum:
            raise ValueError(f"{name} must be an integer from 1 to {maximum}")
        return value

    @staticmethod
    def _normalize_device_priority(devices: Sequence[str]) -> list[str]:
        normalized: list[str] = []
        for item in devices:
            value = str(item).strip().lower()
            if not value or value in normalized:
                continue
            normalized.append(value)
        if "cpu" not in normalized:
            normalized.append("cpu")
        return normalized

    def set_device_priority(self, devices: Sequence[str]):
        normalized = self._normalize_device_priority(devices)
        if normalized == self.device_priority:
            return

        self.device_priority = normalized
        self.device = normalized[0]
        if self.device_in_use not in normalized:
            self.model = None
            self.device_in_use = None

    def load_model(self, device: str):
        """
        Whisper 모델을 지정된 디바이스에 로드
        - GPU 사용 시 float16, CPU 사용 시 int8 정밀도 사용
        """
        if str(device).startswith("cuda"):
            self._ensure_cuda_runtime_paths()
            self._preload_cuda_runtime()

        log.info("Loading STT model: %s on %s...", self.model_size, device)
        model = WhisperModel(
            self.model_size,
            device=device,
            compute_type=("int8" if device == "cpu" else "float16"),
            cpu_threads=self.cpu_threads,
            num_workers=1,
        )
        self.model = model
        self.device_in_use = device
        log.info("STT model loaded on %s", device)

    @staticmethod
    def _ensure_cuda_runtime_paths():
        global _CUDA_DLL_PATHS_ADDED
        if _CUDA_DLL_PATHS_ADDED or os.name != "nt":
            return

        prefixes = []
        conda_prefix = os.environ.get("CONDA_PREFIX")
        if conda_prefix:
            prefixes.append(Path(conda_prefix))

        venv_prefix = os.environ.get("VIRTUAL_ENV")
        if venv_prefix:
            prefixes.append(Path(venv_prefix))

        try:
            exe_parent = Path(sys.executable).resolve().parent
            # conda env: <env>/python.exe
            if (exe_parent / "Lib").exists():
                prefixes.append(exe_parent)
            # venv on Windows: <env>/Scripts/python.exe
            if (exe_parent.parent / "Lib").exists():
                prefixes.append(exe_parent.parent)
            # fallback (기존 동작 유지)
            prefixes.append(exe_parent.parent)
        except Exception:
            pass

        cuda_env = os.environ.get("CUDA_PATH") or os.environ.get("CUDA_HOME")
        if cuda_env:
            prefixes.append(Path(cuda_env))

        seen = set()
        added = []
        for prefix in prefixes:
            for rel in (
                Path("Lib/site-packages/nvidia/cublas/bin"),
                Path("Lib/site-packages/nvidia/cudnn/bin"),
                Path("Lib/site-packages/nvidia/cuda_runtime/bin"),
                Path("Library/bin"),
                Path("bin"),
            ):
                dll_dir = (prefix / rel).resolve()
                if not dll_dir.exists():
                    continue
                key = str(dll_dir).lower()
                if key in seen:
                    continue
                seen.add(key)

                try:
                    os.add_dll_directory(str(dll_dir))
                except Exception:
                    pass
                if str(dll_dir) not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = f"{dll_dir};{os.environ.get('PATH', '')}"
                added.append(str(dll_dir))

        _CUDA_DLL_PATHS_ADDED = True
        if added:
            log.info("Registered CUDA runtime paths: %s", " | ".join(added))
        else:
            log.warning(
                "No CUDA runtime directories detected in environment prefixes: %s",
                ", ".join(str(p) for p in prefixes) or "(none)",
            )

    @staticmethod
    def _preload_cuda_runtime():
        """
        Windows에서 ctranslate2가 의존하는 CUDA DLL을 미리 로드해
        PATH/검색 경로 문제가 있으면 조기에 명확하게 로그를 남긴다.
        """
        if os.name != "nt":
            return

        required = ("cublas64_12.dll",)
        cudnn_candidates = (
            "cudnn64_9.dll",
            "cudnn_ops64_9.dll",
            "cudnn_cnn64_9.dll",
            "cudnn64_8.dll",
        )

        missing = []
        for dll in required:
            try:
                ctypes.WinDLL(dll)
            except OSError:
                missing.append(dll)

        cudnn_loaded = False
        for dll in cudnn_candidates:
            try:
                ctypes.WinDLL(dll)
                cudnn_loaded = True
                break
            except OSError:
                continue
        if not cudnn_loaded:
            missing.append("cudnn64_9.dll")

        if missing:
            log.error(
                "Missing CUDA runtime DLLs on PATH: %s (VIRTUAL_ENV=%s, CONDA_PREFIX=%s)",
                ", ".join(missing),
                os.environ.get("VIRTUAL_ENV"),
                os.environ.get("CONDA_PREFIX"),
            )

    @staticmethod
    def _is_cuda_runtime_error(msg: str) -> bool:
        lowered = msg.lower()
        signatures = (
            "cublas",
            "cudnn",
            "cuda",
            "cudart",
            "curand",
            "cufft",
            "cusparse",
            "dll is not found",
            "cannot be loaded",
        )
        return any(sig in lowered for sig in signatures)

    def ensure_model(self):
        """
        모델이 로드되지 않은 경우 자동 로드
        - GPU 로드 실패 시 CPU로 자동 폴백
        """
        if self.model is None:
            last_exc = None
            for device in self.device_priority:
                try:
                    self.load_model(device)
                    self.device = device
                    return
                except Exception as exc:
                    last_exc = exc
                    log.warning("STT init failed on %s -> trying next fallback: %s", device, exc)
            if last_exc is not None:
                raise last_exc

    def safe_transcribe(self, pcm_f32: np.ndarray):
        """
        스레드 안전한 음성 인식 수행
        - VAD 필터링 및 한국어 최적화 파라미터 적용
        - CUDA 런타임 오류 시 CPU로 자동 전환
        """
        self.ensure_model()
        # 연속 메모리 배열로 변환 (성능 최적화)
        pcm_f32 = np.ascontiguousarray(pcm_f32, dtype=np.float32)

        def _run():
            # Whisper 음성 인식 실행 (한국어 최적화 설정)
            segments, info = self.model.transcribe(
                pcm_f32,
                language=self.language,
                beam_size=self.beam_size,                        # 빔 서치 크기
                temperature=0.0,                    # 결정적 출력을 위한 온도 설정
                condition_on_previous_text=False,   # 이전 텍스트 조건부 비활성화
                repetition_penalty=1.15,            # 반복 억제
                no_repeat_ngram_size=3,            # N-gram 반복 방지
                log_prob_threshold=-1.2,           # 로그 확률 임계값
                no_speech_threshold=0.6,           # 무음 감지 임계값
                compression_ratio_threshold=2.4,    # 압축 비율 임계값
                vad_filter=True,                   # VAD 필터 활성화
                vad_parameters=dict(
                    threshold=0.5,                 # VAD 임계값
                    min_speech_duration_ms=200,    # 최소 음성 지속 시간
                    min_silence_duration_ms=150,   # 최소 침묵 지속 시간
                    speech_pad_ms=120,             # 음성 패딩
                ),
                suppress_blank=True,               # 빈 출력 억제
            )
            return list(segments), info

        # 스레드 안전 실행
        with self.model_lock:
            try:
                return _run()
            except RuntimeError as exc:
                msg = str(exc)
                if str(self.device_in_use).startswith("cuda") and self._is_cuda_runtime_error(msg):
                    log.error("CUDA runtime missing/broken -> switching to next fallback now. reason=%s", msg)
                    if "cublas64_12.dll" in msg:
                        log.error(
                            "Detected CUDA 12 runtime mismatch. "
                            "Install CUDA 12 cublas/cudnn runtime for ctranslate2>=4."
                        )
                    current = str(self.device_in_use or "").lower()
                    for device in self.device_priority:
                        normalized_device = str(device).lower()
                        if (
                            normalized_device == current
                            or (current.startswith("cuda") and normalized_device.startswith("cuda"))
                        ):
                            continue
                        self.load_model(device)
                        self.device = device
                        return _run()
                    raise
                raise
