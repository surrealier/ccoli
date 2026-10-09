"""Conversation preferences affect STT, chat and TTS without shared language state."""
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from src.runtime_controller import RuntimeController
from web.app import create_app
from web.auth import configure


class FakeConfig:
    def __init__(self):
        self.config = {'stt': {'language': 'ko'}, 'dialogue': {'language': 'ko', 'short_responses': True, 'fast_model': ''}, 'web': {'auth_token': ''}}
        self.saves = 0
    def get(self, *keys, default=None):
        value = self.config
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value
    def save(self):
        self.saves += 1


class FakeSTT:
    language = 'ko'
    device_priority = ['cpu']
    device_in_use = 'cpu'
    def set_device_priority(self, _devices):
        pass
    def set_language(self, language):
        self.language = language


class FakeAgent:
    def __init__(self):
        self.settings = {'language': 'ko', 'short_responses': True, 'fast_model': ''}
        self.emotion_system = SimpleNamespace(current_emotion='neutral')
        self.calls = []
    def configure_dialogue(self, **changes):
        self.settings.update(changes)
        return self.describe_dialogue()
    def describe_dialogue(self):
        return {**self.settings, 'supported_languages': ['auto', 'ko', 'en', 'zh', 'ja', 'es']}
    def generate_response(self, text, speaker_id='web_user', language=None):
        self.calls.append((text, speaker_id, language))
        return 'Hola.', 'none'


def make_client(monkeypatch):
    cfg, stt, agent = FakeConfig(), FakeSTT(), FakeAgent()
    runtime = RuntimeController(cfg)
    runtime.bind(stt_engine=stt, agent=agent)
    agent.runtime_controller = runtime
    app = create_app(lambda: agent, lambda: None, lambda: 'agent', lambda: {})
    from web.routes import api_dialogue
    monkeypatch.setattr(api_dialogue, 'get_config', lambda: cfg)
    configure('')
    return TestClient(app), cfg, stt, agent


def test_language_preference_applies_to_stt_and_agent_and_is_saved(monkeypatch):
    client, cfg, stt, agent = make_client(monkeypatch)
    response = client.patch('/api/dialogue/', json={'language': 'ja', 'short_responses': False})
    assert response.status_code == 200
    assert stt.language == 'ja'
    assert agent.settings['language'] == 'ja'
    assert agent.settings['short_responses'] is False
    assert cfg.config['stt']['language'] == 'ja'
    assert cfg.saves == 1
    assert client.get('/api/dialogue/').json()['language'] == 'ja'


@pytest.mark.parametrize('body', [{'language': 'fr'}, {'language': True}, {'short_responses': 'true'}, {'fast_model': 'unsafe model\n'}, {'unrecognized': True}])
def test_invalid_preferences_do_not_change_or_save_runtime(monkeypatch, body):
    client, cfg, stt, agent = make_client(monkeypatch)
    assert client.patch('/api/dialogue/', json=body).status_code == 422
    assert stt.language == 'ko'
    assert agent.settings['language'] == 'ko'
    assert cfg.saves == 0


def test_each_web_chat_has_its_own_language(monkeypatch):
    client, cfg, stt, agent = make_client(monkeypatch)
    for language, text in [('es','Hola'),('en','Hello'),('zh','你好'),('ja','こんにちは')]:
        response = client.post('/api/chat/', json={'text':text,'speaker_id':language,'language':language})
        assert response.status_code == 200
        assert agent.calls[-1] == (text,language,language)
    assert stt.language == 'ko'
    assert cfg.saves == 0
    assert client.post('/api/chat/', json={'text':'hello','language':'fr'}).status_code == 422


def test_dialogue_preferences_require_authentication(monkeypatch):
    client, cfg, stt, agent = make_client(monkeypatch)
    configure('synthetic-token')
    try:
        assert client.patch('/api/dialogue/', json={'language':'es'}).status_code == 401
        assert client.get('/api/dialogue/').status_code == 401
        assert cfg.saves == 0
    finally:
        configure('')


@pytest.mark.parametrize('model', ['/model', '.model', '-model', 'model/path'])
def test_fast_model_validation_matches_model_client(monkeypatch, model):
    client, cfg, stt, agent = make_client(monkeypatch)
    assert client.patch('/api/dialogue/', json={'fast_model':model}).status_code == 422
    assert cfg.saves == 0


def test_save_failure_restores_runtime_and_returns_sanitized_error(monkeypatch):
    client, cfg, stt, agent = make_client(monkeypatch)
    def fail():
        raise OSError('synthetic-secret-settings-path')
    monkeypatch.setattr(cfg, 'save', fail)
    response = client.patch('/api/dialogue/', json={'language':'es','fast_model':'gemini-3.5-flash-lite'})
    assert response.status_code == 503
    assert 'synthetic-secret' not in response.text
    assert stt.language == 'ko'
    assert agent.settings == {'language':'ko','short_responses':True,'fast_model':''}
    assert cfg.config['dialogue'] == agent.settings
    assert cfg.config['stt']['language'] == 'ko'
