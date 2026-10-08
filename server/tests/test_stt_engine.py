import numpy as np

import src.stt_engine as stt_engine_module
from src.stt_engine import STTEngine


class FakeSegment:
    def __init__(self, text):
        self.text = text


class FakeModel:
    def transcribe(self, pcm_f32, **kwargs):
        return [FakeSegment("테스트")], {"language": "ko"}


def test_safe_transcribe_with_fake_model():
    engine = STTEngine(model_size="tiny", device="cpu", language="ko")
    engine.model = FakeModel()
    pcm = np.zeros(16000, dtype=np.float32)

    segments, info = engine.safe_transcribe(pcm)
    assert segments[0].text == "테스트"
    assert info["language"] == "ko"


def test_load_model_on_cuda_runs_runtime_preflight(monkeypatch):
    calls = []

    def fake_ensure():
        calls.append("ensure")

    def fake_preload():
        calls.append("preload")

    class DummyWhisperModel:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    monkeypatch.setattr(STTEngine, "_ensure_cuda_runtime_paths", staticmethod(fake_ensure))
    monkeypatch.setattr(STTEngine, "_preload_cuda_runtime", staticmethod(fake_preload))
    monkeypatch.setattr(stt_engine_module, "WhisperModel", DummyWhisperModel)

    engine = STTEngine(model_size="tiny", device="cuda", language="ko")
    engine.load_model("cuda")

    assert calls == ["ensure", "preload"]
    assert engine.device_in_use == "cuda"


def test_safe_transcribe_cuda_runtime_error_with_cuda_index_falls_back_to_cpu(monkeypatch):
    class RuntimeErrorModel:
        def transcribe(self, pcm_f32, **kwargs):
            raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")

    class CpuModel:
        def transcribe(self, pcm_f32, **kwargs):
            return [FakeSegment("복구")], {"language": "ko"}

    engine = STTEngine(model_size="tiny", device="cuda", language="ko")
    engine.model = RuntimeErrorModel()
    engine.device_in_use = "cuda:0"

    loaded = []

    def fake_load_model(device):
        loaded.append(device)
        engine.model = CpuModel()
        engine.device_in_use = device

    monkeypatch.setattr(engine, "load_model", fake_load_model)

    segments, info = engine.safe_transcribe(np.zeros(800, dtype=np.float32))
    assert loaded == ["cpu"]
    assert segments[0].text == "복구"
    assert info["language"] == "ko"


def test_stt_latency_defaults_reach_inference(monkeypatch):
    monkeypatch.delenv("STT_CPU_THREADS", raising=False)
    monkeypatch.delenv("STT_BEAM_SIZE", raising=False)
    seen = {}

    class CaptureModel:
        def __init__(self, *args, **kwargs):
            seen.update(kwargs)

        def transcribe(self, pcm, **kwargs):
            seen.update(kwargs)
            return iter([FakeSegment("확인")]), {}

    monkeypatch.setattr(stt_engine_module, "WhisperModel", CaptureModel)
    engine = STTEngine("turbo", "cpu")
    engine.safe_transcribe(np.zeros(16000, dtype=np.float32))
    assert seen["cpu_threads"] == 4
    assert seen["beam_size"] == 1
    assert seen["compute_type"] == "int8"


def test_stt_env_overrides_reach_inference(monkeypatch):
    monkeypatch.setenv("STT_CPU_THREADS", "6")
    monkeypatch.setenv("STT_BEAM_SIZE", "3")
    seen = {}

    class CaptureModel:
        def __init__(self, *args, **kwargs):
            seen.update(kwargs)

        def transcribe(self, pcm, **kwargs):
            seen.update(kwargs)
            return iter([FakeSegment("확인")]), {}

    monkeypatch.setattr(stt_engine_module, "WhisperModel", CaptureModel)
    STTEngine("turbo", "cpu").safe_transcribe(np.zeros(16000, dtype=np.float32))
    assert seen["cpu_threads"] == 6
    assert seen["beam_size"] == 3


def test_stt_invalid_latency_env_fails_before_model_load(monkeypatch):
    import pytest

    for name, value in [("STT_CPU_THREADS", "0"), ("STT_CPU_THREADS", "65"),
                        ("STT_BEAM_SIZE", "0"), ("STT_BEAM_SIZE", "11"),
                        ("STT_BEAM_SIZE", "fast"), ("STT_CPU_THREADS", "1.5")]:
        monkeypatch.delenv("STT_CPU_THREADS", raising=False)
        monkeypatch.delenv("STT_BEAM_SIZE", raising=False)
        monkeypatch.setenv(name, value)
        with pytest.raises(ValueError, match=name):
            STTEngine("turbo", "cpu")
