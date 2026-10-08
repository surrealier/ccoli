import base64
import io
import wave

import numpy as np
import pytest

from src.agent_mode import AgentMode
from src.integrations.gemini_tts import GeminiTTS


class _Response:
    status_code = 200

    def __init__(self, audio: bytes, mime: str):
        self.audio = audio
        self.mime = mime

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "candidates": [{
                "content": {"parts": [{
                    "inlineData": {
                        "mimeType": self.mime,
                        "data": base64.b64encode(self.audio).decode("ascii"),
                    }
                }]}
            }]
        }


def test_gemini_tts_requests_latest_model_and_resamples_actual_24k(monkeypatch):
    sent = {}

    def fake_post(url, *, headers, json, timeout):
        sent.update(url=url, headers=headers, body=json, timeout=timeout)
        samples = np.ones(2400, dtype="<i2") * 1000
        return _Response(samples.tobytes(), "audio/l16; rate=24000; channels=1")

    monkeypatch.setattr("src.integrations.gemini_tts.requests.post", fake_post)
    result = GeminiTTS("synthetic-key").synthesize("준비됐어요.")

    assert "gemini-3.8-flash-lite-tts:generateContent" in sent["url"]
    assert sent["headers"]["x-goog-api-key"] == "synthetic-key"
    assert sent["body"]["contents"][0]["parts"][0]["text"] == "준비됐어요."
    assert sent["body"]["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert 3198 <= len(result) <= 3202


def test_gemini_tts_decodes_default_wav_response(monkeypatch):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes((np.ones(2400, dtype="<i2") * 1200).tobytes())

    monkeypatch.setattr(
        "src.integrations.gemini_tts.requests.post",
        lambda *args, **kwargs: _Response(stream.getvalue(), "audio/wav"),
    )
    assert len(GeminiTTS("synthetic-key").synthesize("시험")) == 3200


def test_agent_mode_can_select_gemini_tts_and_falls_back_to_edge():
    class _FakeGemini:
        def __init__(self):
            self.result = b"gemini-pcm"
            self.calls = []

        def synthesize(self, text):
            self.calls.append(text)
            return self.result

    agent = AgentMode.__new__(AgentMode)
    agent.tts_backend = "gemini_tts"
    agent.gemini_tts = _FakeGemini()
    agent._edge_text_to_audio = lambda *args, **kwargs: b"edge-pcm"

    assert agent.text_to_audio("첫 응답") == b"gemini-pcm"
    agent.gemini_tts.result = b""
    assert agent.text_to_audio("복구 응답") == b"edge-pcm"
    assert agent.gemini_tts.calls == ["첫 응답", "복구 응답"]


def test_agent_mode_default_edge_never_calls_gemini():
    agent = AgentMode.__new__(AgentMode)
    agent.tts_backend = "edge_tts"
    agent.gemini_tts = None
    agent._edge_text_to_audio = lambda *args, **kwargs: b"edge-pcm"
    assert agent.text_to_audio("빠른 응답") == b"edge-pcm"


def test_gemini_tts_failure_falls_back_without_logging_private_text(caplog):
    class _Failure:
        def synthesize(self, text):
            raise RuntimeError("private response leaked")

    agent = AgentMode.__new__(AgentMode)
    agent.tts_backend = "gemini_tts"
    agent.gemini_tts = _Failure()
    agent._edge_text_to_audio = lambda *args, **kwargs: b"edge-pcm"

    with caplog.at_level("WARNING", logger="src.agent_mode"):
        assert agent.text_to_audio("private response leaked") == b"edge-pcm"
    assert "private response leaked" not in caplog.text


def test_gemini_tts_rejects_corrupt_base64(monkeypatch):
    class _CorruptResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{
                "inlineData": {"mimeType": "audio/l16; rate=24000; channels=1", "data": "%%%"}
            }]}}]}

    monkeypatch.setattr(
        "src.integrations.gemini_tts.requests.post",
        lambda *args, **kwargs: _CorruptResponse(),
    )
    with pytest.raises(ValueError, match="Invalid TTS audio encoding"):
        GeminiTTS("synthetic-key").synthesize("시험")
