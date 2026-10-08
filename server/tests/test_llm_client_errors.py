from src.llm_client import LLMClient


def test_missing_external_api_key_sets_error_state():
    client = LLMClient("", "gemini-1.5-flash", provider="gemini", api_key="")

    result = client.chat([{"role": "user", "content": "hello"}])

    assert result == ""
    assert client.last_error_code == "missing_api_key"
    assert "GEMINI_API_KEY" in client.last_error

def test_provider_error_does_not_expose_request_secret(monkeypatch, caplog):
    secret = 'fake-private-provider-token'
    client = LLMClient('', 'gemini-test', provider='gemini', api_key=secret)
    def fail(*args, **kwargs):
        raise RuntimeError('request failed https://provider/?key=' + secret)
    monkeypatch.setattr(client, '_chat_gemini', fail)
    assert client.chat([{'role': 'user', 'content': 'hello'}]) == ''
    assert client.last_error_code == 'provider_error'
    assert secret not in client.last_error
    assert secret not in caplog.text
