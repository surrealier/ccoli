from src.llm_client import PriorityLLMClient
from src.runtime_preferences import HardwareProfile, RuntimePreferences


class _FakeClient:
    def __init__(self, provider, model, response, error_code=None, error=""):
        self.provider = provider
        self.model = model
        self.base_url = "http://localhost:11434"
        self._response = response
        self.last_error_code = error_code
        self.last_error = error

    def chat(self, *_args, **_kwargs):
        return self._response


def _preferences(*, accelerators, processor_priority=None):
    return RuntimePreferences(
        llm_priority=["ollama", "api", "ollama_cpu", "other"],
        api_priority=["gemini", "claude", "chatgpt"],
        connection_priority=["wired", "wifi"],
        processor_priority=processor_priority or ["gpu", "cpu"],
        llm_models={
            "ollama": "qwen2.5:0.5b",
            "gemini": "gemini-2.5-flash",
            "claude": "claude-3-5-haiku-latest",
            "chatgpt": "gpt-4o-mini",
        },
        hardware=HardwareProfile(accelerators=list(accelerators)),
        tts_backend="edge_tts",
    )


def _llm_config():
    return {
        "provider": "gemini",
        "base_url": "",
        "model": "gemini-2.5-flash",
        "ollama_model": "qwen2.5:0.5b",
        "api_models": {
            "gemini": "gemini-2.5-flash",
            "claude": "claude-3-5-haiku-latest",
            "chatgpt": "gpt-4o-mini",
        },
        "gemini_api_key": "gem-key",
        "anthropic_api_key": "ant-key",
        "openai_api_key": "open-key",
    }


def test_priority_llm_client_prefers_gpu_ollama_when_available(monkeypatch):
    client = PriorityLLMClient(_llm_config(), _preferences(accelerators=["cuda"]))
    calls = []

    def fake_client_for_candidate(provider, model, api_key=""):
        calls.append((provider, model, api_key))
        if provider == "ollama":
            return _FakeClient(provider, model, "local response")
        raise AssertionError("API fallback should not run when local Ollama succeeds")

    monkeypatch.setattr(client, "_client_for_candidate", fake_client_for_candidate)

    response = client.chat([{"role": "user", "content": "안녕"}])

    assert response == "local response"
    assert calls == [("ollama", "qwen2.5:0.5b", "")]
    assert client.describe_runtime()["active_bucket"] == "ollama"
    assert client.base_url == "http://localhost:11434"


def test_priority_llm_client_falls_back_to_api_before_cpu_ollama(monkeypatch):
    client = PriorityLLMClient(_llm_config(), _preferences(accelerators=[]))
    calls = []

    def fake_client_for_candidate(provider, model, api_key=""):
        calls.append((provider, model, api_key))
        if provider == "gemini":
            return _FakeClient(provider, model, "api response")
        if provider == "ollama":
            return _FakeClient(provider, model, "cpu response")
        return _FakeClient(provider, model, "")

    monkeypatch.setattr(client, "_client_for_candidate", fake_client_for_candidate)

    response = client.chat([{"role": "user", "content": "안녕"}])

    assert response == "api response"
    assert calls[0] == ("gemini", "gemini-2.5-flash", "gem-key")
    assert client.describe_runtime()["active_bucket"] == "api"


def test_priority_llm_client_pins_first_successful_candidate(monkeypatch):
    client = PriorityLLMClient(_llm_config(), _preferences(accelerators=["cuda"]))
    calls = []

    def fake_client_for_candidate(provider, model, api_key=""):
        calls.append((provider, model, api_key))
        if provider == "ollama":
            return _FakeClient(provider, model, "", error_code="provider_error", error="connection refused")
        if provider == "gemini":
            return _FakeClient(provider, model, "api response")
        return _FakeClient(provider, model, "")

    monkeypatch.setattr(client, "_client_for_candidate", fake_client_for_candidate)

    assert client.chat([{"role": "user", "content": "첫 질문"}]) == "api response"
    assert client.chat([{"role": "user", "content": "다음 질문"}]) == "api response"

    assert calls == [
        ("ollama", "qwen2.5:0.5b", ""),
        ("gemini", "gemini-2.5-flash", "gem-key"),
        ("gemini", "gemini-2.5-flash", "gem-key"),
    ]
    assert client.describe_runtime()["active_bucket"] == "api"


def test_priority_llm_client_reselects_after_runtime_reload(monkeypatch):
    client = PriorityLLMClient(_llm_config(), _preferences(accelerators=["cuda"]))
    calls = []

    def fake_client_for_candidate(provider, model, api_key=""):
        calls.append((provider, model, api_key))
        if provider == "ollama":
            return _FakeClient(provider, model, "", error_code="provider_error", error="connection refused")
        if provider == "gemini":
            return _FakeClient(provider, model, "api response")
        return _FakeClient(provider, model, "")

    monkeypatch.setattr(client, "_client_for_candidate", fake_client_for_candidate)

    assert client.chat([{"role": "user", "content": "첫 질문"}]) == "api response"
    client.reload_runtime_preferences(_preferences(accelerators=["cuda"]), _llm_config())
    assert client.chat([{"role": "user", "content": "다시 질문"}]) == "api response"

    assert calls == [
        ("ollama", "qwen2.5:0.5b", ""),
        ("gemini", "gemini-2.5-flash", "gem-key"),
        ("ollama", "qwen2.5:0.5b", ""),
        ("gemini", "gemini-2.5-flash", "gem-key"),
    ]


def test_priority_llm_client_falls_back_when_pinned_provider_later_fails(monkeypatch):
    preferences = _preferences(accelerators=['cuda'])
    preferences.llm_priority = ['api', 'ollama', 'ollama_cpu', 'other']
    config = _llm_config()
    config['anthropic_api_key'] = ''
    config['openai_api_key'] = ''
    client = PriorityLLMClient(config, preferences)
    calls = []

    def fake_client_for_candidate(provider, model, api_key=''):
        calls.append(provider)
        if provider == 'gemini':
            return _FakeClient(provider, model, 'first response' if calls.count('gemini') == 1 else '', error_code='provider_error')
        if provider == 'ollama':
            return _FakeClient(provider, model, 'local fallback')
        return _FakeClient(provider, model, '')

    monkeypatch.setattr(client, '_client_for_candidate', fake_client_for_candidate)

    assert client.chat([{'role': 'user', 'content': 'first'}]) == 'first response'
    assert client.chat([{'role': 'user', 'content': 'second'}]) == 'local fallback'
    assert calls == ['gemini', 'gemini', 'ollama']
    assert client.describe_runtime()['active_provider'] == 'ollama'