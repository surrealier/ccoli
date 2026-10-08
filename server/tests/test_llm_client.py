import logging

import requests

from src.llm_client import LLMClient


class _StreamResponse:
    def __init__(self, lines, status_code=200):
        self._lines = lines
        self.status_code = status_code
        self.text = "\n".join(lines)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status={self.status_code}")

    def iter_lines(self, decode_unicode=True):
        for line in self._lines:
            yield line if decode_unicode else line.encode("utf-8")


def test_chat_once_merges_stream_chunks(monkeypatch):
    lines = [
        '{"message":{"content":"안녕"},"done":false}',
        '{"message":{"content":"하세요. 좋은 밤이에요."},"done":true,"done_reason":"stop"}',
    ]

    def fake_post(*args, **kwargs):
        return _StreamResponse(lines)

    monkeypatch.setattr("src.llm_client.requests.post", fake_post)

    client = LLMClient("http://localhost:11434", "qwen3:8b")
    content, done_reason, thinking = client._chat_once(
        messages=[{"role": "user", "content": "인사해줘"}],
        temperature=0.8,
        max_tokens=256,
    )

    assert content == "안녕하세요. 좋은 밤이에요."
    assert done_reason == "stop"
    assert thinking == ""


def test_chat_retries_once_when_done_reason_is_length(monkeypatch):
    calls = []

    def fake_chat_once(messages, temperature, max_tokens, think=True):
        calls.append((max_tokens, think))
        if len(calls) == 1:
            return "안녕하세요. 밤", "length", "생각 중"
        return "안녕하세요. 밤이네요. 오늘은 조금 선선해요.", "stop", ""

    client = LLMClient("http://localhost:11434", "qwen3:8b")
    monkeypatch.setattr(client, "_chat_once", fake_chat_once)
    monkeypatch.setattr(client, "_generate_fallback", lambda *args, **kwargs: "")

    result = client.chat(
        messages=[{"role": "user", "content": "안녕"}],
        temperature=0.8,
        max_tokens=256,
    )

    assert result == "안녕하세요. 밤이네요. 오늘은 조금 선선해요."
    assert calls[0] == (256, False)
    assert calls[1] == (512, False)


def test_chat_uses_generate_fallback_when_stream_is_empty(monkeypatch):
    client = LLMClient("http://localhost:11434", "qwen3:8b")
    monkeypatch.setattr(client, "_chat_once", lambda *args, **kwargs: ("", "", ""))
    monkeypatch.setattr(client, "_generate_fallback", lambda *args, **kwargs: "대체 응답")

    result = client.chat(
        messages=[{"role": "user", "content": "안녕"}],
        temperature=0.8,
        max_tokens=128,
    )

    assert result == "대체 응답"


def test_chat_forces_think_false_even_when_requested(monkeypatch):
    calls = []

    def fake_chat_once(messages, temperature, max_tokens, think=True):
        calls.append((max_tokens, think))
        return "최종 답변", "stop", ""

    client = LLMClient("http://localhost:11434", "qwen3:8b")
    monkeypatch.setattr(client, "_chat_once", fake_chat_once)
    monkeypatch.setattr(client, "_generate_fallback", lambda *args, **kwargs: "")

    result = client.chat(
        messages=[{"role": "user", "content": "질문"}],
        temperature=0.8,
        max_tokens=256,
        think=True,
    )

    assert result == "최종 답변"
    assert calls == [(256, False)]


def test_chat_ignores_client_default_think(monkeypatch):
    calls = []

    def fake_chat_once(messages, temperature, max_tokens, think=True):
        calls.append((max_tokens, think))
        return "응답", "stop", ""

    client = LLMClient("http://localhost:11434", "qwen3:8b", default_think=True)
    monkeypatch.setattr(client, "_chat_once", fake_chat_once)

    result = client.chat(
        messages=[{"role": "user", "content": "질문"}],
        temperature=0.8,
        max_tokens=128,
    )

    assert result == "응답"
    assert calls == [(128, False)]


def test_ollama_connection_failure_logs_warning_not_error(monkeypatch, caplog):
    client = LLMClient("http://localhost:11434", "qwen3:8b")

    def fail_chat_once(*args, **kwargs):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(client, "_chat_once", fail_chat_once)

    with caplog.at_level(logging.WARNING, logger="src.llm_client"):
        result = client.chat([{"role": "user", "content": "안녕"}])

    assert result == ""
    assert client.last_error_code == "provider_error"
    assert "Ollama API error: connection refused" in caplog.text
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


class _JsonResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status={self.status_code}")

    def json(self):
        return self._payload


def test_chatgpt_provider_calls_openai_api(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _JsonResponse({"choices": [{"message": {"content": "OpenAI 응답"}}]})

    monkeypatch.setattr("src.llm_client.requests.post", fake_post)
    client = LLMClient("", "gpt-4o-mini", provider="chatgpt", api_key="sk-test")

    result = client.chat([{"role": "user", "content": "hello"}], temperature=0.3, max_tokens=64)

    assert result == "OpenAI 응답"
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"


def test_gemini_provider_calls_google_api(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _JsonResponse(
            {"candidates": [{"content": {"parts": [{"text": "Gemini 응답"}]}}]}
        )

    monkeypatch.setattr("src.llm_client.requests.post", fake_post)
    client = LLMClient("", "gemini-2.5-flash", provider="gemini", api_key="gem-key")

    result = client.chat([{"role": "user", "content": "안녕"}], temperature=0.4, max_tokens=80)

    assert result == "Gemini 응답"
    assert "generativelanguage.googleapis.com" in captured["url"]
    assert captured["json"]["generationConfig"]["thinkingConfig"]["thinkingBudget"] == 0


def test_gemini_legacy_model_omits_thinking_config(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return _JsonResponse(
            {"candidates": [{"content": {"parts": [{"text": "Gemini 응답"}]}}]}
        )

    monkeypatch.setattr("src.llm_client.requests.post", fake_post)
    client = LLMClient("", "gemini-1.5-flash", provider="gemini", api_key="gem-key")

    result = client.chat([{"role": "user", "content": "안녕"}], temperature=0.4, max_tokens=80)

    assert result == "Gemini 응답"
    assert "thinkingConfig" not in captured["json"]["generationConfig"]


def test_gemini_retries_once_when_response_hits_max_tokens(monkeypatch):
    max_output_tokens = []

    def fake_post(url, json=None, timeout=None):
        max_output_tokens.append(json["generationConfig"]["maxOutputTokens"])
        if len(max_output_tokens) == 1:
            return _JsonResponse(
                {
                    "candidates": [
                        {
                            "finishReason": "MAX_TOKENS",
                            "content": {"parts": [{"text": "콜리 연결됐어요! 콜"}]},
                        }
                    ]
                }
            )
        return _JsonResponse(
            {
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": "콜리 연결됐어요! 아직 일하고 계세요?"}]},
                    }
                ]
            }
        )

    monkeypatch.setattr("src.llm_client.requests.post", fake_post)
    client = LLMClient("", "gemini-2.5-flash", provider="gemini", api_key="gem-key")

    result = client.chat([{"role": "user", "content": "인사해줘"}], temperature=0.4, max_tokens=80)

    assert result == "콜리 연결됐어요! 아직 일하고 계세요?"
    assert max_output_tokens == [80, 384]


def test_claude_provider_calls_anthropic_api(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _JsonResponse({"content": [{"text": "Claude 응답"}]})

    monkeypatch.setattr("src.llm_client.requests.post", fake_post)
    client = LLMClient("", "claude-3-5-haiku-latest", provider="claude", api_key="ant-key")

    result = client.chat([{"role": "user", "content": "안녕"}], temperature=0.2, max_tokens=90)

    assert result == "Claude 응답"
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "ant-key"


def test_gemini_preserves_system_instruction_boundary(monkeypatch):
    captured = {}
    def fake_post(url, json=None, timeout=None):
        captured.update(json)
        return _JsonResponse({'candidates': [{'content': {'parts': [{'text': 'ok'}]}}]})
    monkeypatch.setattr('src.llm_client.requests.post', fake_post)
    client = LLMClient('', 'gemini-2.5-flash-lite', provider='gemini', api_key='test-only')
    assert client.chat([
        {'role': 'system', 'content': 'Policy: verify actions.'},
        {'role': 'user', 'content': 'hello'},
        {'role': 'assistant', 'content': 'hi'},
        {'role': 'user', 'content': 'complete my task'},
    ]) == 'ok'
    assert captured['systemInstruction']['parts'] == [{'text': 'Policy: verify actions.'}]
    assert [m['role'] for m in captured['contents']] == ['user', 'model', 'user']
    assert all('Policy:' not in str(m) for m in captured['contents'])

def test_gemini_38_uses_low_thinking_without_removed_sampling(monkeypatch):
    captured = {}
    def fake_post(url, json=None, timeout=None):
        captured.update(json)
        return _JsonResponse({'candidates': [{'content': {'parts': [
            {'thought': True, 'text': 'internal reasoning'}, {'text': 'hello'}]}}]})
    monkeypatch.setattr('src.llm_client.requests.post', fake_post)
    client = LLMClient('', 'gemini-3.8-flash', provider='gemini', api_key='test')
    assert client.chat([{'role': 'user', 'content': 'hello'}]) == 'hello'
    cfg = captured['generationConfig']
    assert cfg['thinkingConfig'] == {'thinkingLevel': 'low'}
    assert 'temperature' not in cfg
    assert 'thinkingBudget' not in cfg['thinkingConfig']


def test_gpt6_luna_uses_supported_fast_chat_parameters(monkeypatch):
    captured = {}
    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(json)
        return _JsonResponse({'choices': [{'message': {'content': 'hello'}}]})
    monkeypatch.setattr('src.llm_client.requests.post', fake_post)
    client = LLMClient('', 'gpt-6-luna', provider='chatgpt', api_key='test')
    assert client.chat([{'role':'user','content':'hello'}], max_tokens=256) == 'hello'
    assert captured['max_completion_tokens'] == 256
    assert captured['reasoning_effort'] == 'none'
    assert 'max_tokens' not in captured


def test_gpt6_astra_omits_sampling_with_reasoning(monkeypatch):
    captured = {}
    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(json)
        return _JsonResponse({'choices': [{'message': {'content': 'hello'}}]})
    monkeypatch.setattr('src.llm_client.requests.post', fake_post)
    client = LLMClient('', 'gpt-6-astra', provider='chatgpt', api_key='test')
    assert client.chat([{'role':'user','content':'hello'}]) == 'hello'
    assert captured['reasoning_effort'] == 'low'
    assert 'temperature' not in captured


def test_gemini_retries_thought_only_truncation_once(monkeypatch):
    budgets=[]
    def fake_post(url, json=None, timeout=None):
        budgets.append(json['generationConfig']['maxOutputTokens'])
        if len(budgets)==1:
            return _JsonResponse({'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'thought':True,'text':'internal'}]}}]})
        return _JsonResponse({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'answer'}]}}]})
    monkeypatch.setattr('src.llm_client.requests.post',fake_post)
    client=LLMClient('', 'gemini-3.8-flash', provider='gemini', api_key='test')
    assert client.chat([{'role':'user','content':'hello'}],max_tokens=768)=='answer'
    assert budgets==[768,1536]


def test_claude_sonnet_55_uses_low_latency_compatible_payload(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured['url'] = url
        captured['json'] = json
        return _JsonResponse({'content': [
            {'type': 'thinking', 'thinking': 'private', 'text': 'must not speak'},
            {'type': 'text', 'text': 'Claude 응답'},
        ]})

    monkeypatch.setattr('src.llm_client.requests.post', fake_post)
    client = LLMClient('', 'claude-sonnet-5-5', provider='claude', api_key='synthetic-key')
    result = client.chat([{'role': 'user', 'content': '안녕'}], temperature=0.2, max_tokens=90)

    assert result == 'Claude 응답'
    assert captured['url'] == 'https://api.anthropic.com/v1/messages'
    payload = captured['json']
    assert payload['model'] == 'claude-sonnet-5-5'
    assert payload['max_tokens'] == 90
    assert payload['thinking'] == {'type': 'between_tools'}
    assert payload['output_config'] == {'effort': 'low'}
    assert 'temperature' not in payload
