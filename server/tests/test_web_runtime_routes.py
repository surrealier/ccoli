from fastapi.testclient import TestClient

from web.app import create_app
from web.auth import configure


class _FakeEmotion:
    current_emotion = "neutral"
    emotion_history = ["neutral"]


class _FakeProactive:
    def get_stats(self):
        return {"count": 1}


class _FakeInfoServices:
    def get_active_timers(self):
        return []

    def get_active_alarms(self):
        return []


class _FakeRuntimeController:
    def handle_text_command(self, text):
        if text == "우선순위 상태":
            return "현재 우선순위 상태예요."
        return None

    def status_snapshot(self):
        return {
            "llm_priority": ["ollama", "api", "ollama_cpu", "other"],
            "api_priority": ["gemini", "claude", "chatgpt"],
            "connection_priority": ["wired", "wifi"],
            "processor_priority": ["gpu", "cpu"],
            "audio_runtime_notes": ["Current TTS backend is Edge TTS."],
            "stt": {
                "configured_devices": ["cpu"],
                "device_in_use": "cpu",
            },
            "llm": {
                "configured_provider": "gemini",
                "active_provider": "gemini",
                "active_model": "gemini-2.5-flash",
                "active_bucket": "api",
                "active_processor": "cpu",
                "last_error_code": None,
            },
        }


class _FakeAgent:
    def __init__(self):
        self.runtime_controller = _FakeRuntimeController()
        self.emotion_system = _FakeEmotion()
        self.proactive = _FakeProactive()
        self.info_services = _FakeInfoServices()
        self.conversation_count = 3
        self.generate_calls = []

    def generate_response(self, text, speaker_id="web_user"):
        self.generate_calls.append((text, speaker_id))
        return "일반 응답", "none"


def _client(dashboard_state=None):
    configure("")
    agent = _FakeAgent()
    state = dashboard_state or {
        "warmup": {
            "stt_ready": True,
            "tts_ready": True,
            "updated_at": "2026-03-24T01:00:00+00:00",
        },
        "connection": {
            "connected": True,
            "current_transport": "wired",
            "current_endpoint": "/dev/cu.usbserial-test",
            "last_transport": "wired",
            "last_endpoint": "/dev/cu.usbserial-test",
            "last_connected_at": "2026-03-24T01:01:00+00:00",
            "last_disconnected_at": None,
        },
        "last_checks": {},
    }
    app = create_app(lambda: agent, lambda: None, lambda: "agent", lambda: state)
    return TestClient(app), agent, state


def test_api_chat_handles_runtime_priority_command():
    client, agent, _state = _client()

    response = client.post("/api/chat/", json={"text": "우선순위 상태"})

    assert response.status_code == 200
    assert response.json()["intent"] == "runtime_config"
    assert "현재 우선순위 상태예요." in response.json()["response"]
    assert agent.generate_calls == []


def test_api_status_exposes_runtime_snapshot():
    client, _agent, _state = _client()

    response = client.get("/api/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime"]["llm_priority"] == ["ollama", "api", "ollama_cpu", "other"]
    assert payload["runtime"]["connection_priority"] == ["wired", "wifi"]


def test_api_diagnostics_exposes_normalized_runtime_data():
    client, _agent, _state = _client()

    response = client.get("/api/diagnostics/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "agent"
    assert payload["runtime"]["warmup"]["stt_ready"] is True
    assert payload["runtime"]["llm"]["active_provider"] == "gemini"
    assert payload["stt"]["model_size"] == "turbo"
    assert payload["stt"]["device_in_use"] == "cpu"
    assert payload["connection"]["connected"] is True
    assert payload["connection"]["current_transport"] == "wired"


def test_api_diagnostics_check_records_results_and_reflects_connection_changes():
    dashboard_state = {
        "warmup": {"stt_ready": True, "tts_ready": False, "updated_at": "2026-03-24T01:00:00+00:00"},
        "connection": {
            "connected": True,
            "current_transport": "wired",
            "current_endpoint": "/dev/cu.usbserial-test",
            "last_transport": "wired",
            "last_endpoint": "/dev/cu.usbserial-test",
            "last_connected_at": "2026-03-24T01:01:00+00:00",
            "last_disconnected_at": None,
        },
        "last_checks": {},
    }
    client, _agent, state = _client(dashboard_state)

    initial = client.post("/api/diagnostics/check", json={"target": "connection"})
    assert initial.status_code == 200
    assert initial.json()["ok"] is True
    assert state["last_checks"]["connection"]["ok"] is True

    state["connection"].update(
        {
            "connected": False,
            "current_transport": None,
            "current_endpoint": None,
            "last_disconnected_at": "2026-03-24T01:02:00+00:00",
        }
    )

    changed = client.post("/api/diagnostics/check", json={"target": "connection"})
    assert changed.status_code == 200
    assert changed.json()["ok"] is False
    assert "No active device connection" in changed.json()["summary"]


def test_api_diagnostics_check_supports_stt_and_llm_targets():
    client, _agent, state = _client()

    stt_result = client.post("/api/diagnostics/check", json={"target": "stt"})
    llm_result = client.post("/api/diagnostics/check", json={"target": "llm"})

    assert stt_result.status_code == 200
    assert stt_result.json()["target"] == "stt"
    assert stt_result.json()["ok"] is True
    assert llm_result.status_code == 200
    assert llm_result.json()["target"] == "llm"
    assert llm_result.json()["ok"] is True
    assert set(state["last_checks"].keys()) >= {"stt", "llm"}
