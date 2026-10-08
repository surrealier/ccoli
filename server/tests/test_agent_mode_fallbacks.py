from src.agent_mode import AgentMode


class _FakeEmotion:
    def analyze_emotion(self, _text, speaker_id="default"):
        return "neutral"

    def set_body_state(self, *, sleep_mode=None, fatigue=None):
        return None


class _FakeMemory:
    def build_system_prompt(self):
        return "system prompt"

    def after_turn(self, _history):
        return None


class _FakeScheduler:
    def process_schedule_request(self, _text):
        return None


class _FakeInfoServices:
    def process_info_request(self, _text):
        return None


class _FakeProactive:
    def __init__(self):
        self.sleep_mode = False
        self.sleep_until = None

    def update_interaction(self):
        return None


class _FakeLLM:
    def __init__(self, raw="", error_code=None, error=""):
        self.provider = "gemini"
        self.raw = raw
        self.last_error_code = error_code
        self.last_error = error

    def chat(self, _messages, **_kwargs):
        return self.raw


def _make_agent(llm):
    agent = AgentMode.__new__(AgentMode)
    agent.llm = llm
    agent.proactive = _FakeProactive()
    agent.scheduler = _FakeScheduler()
    agent.emotion_system = _FakeEmotion()
    agent.memory = _FakeMemory()
    agent.info_services = _FakeInfoServices()
    agent.integrations = object()
    agent.conversation_history = []
    agent.user_histories = {}
    agent.max_history = 20
    agent.conversation_count = 0
    agent._resolve_info_data = lambda _text: None
    return agent


def test_generate_response_returns_configuration_hint_when_api_key_missing():
    llm = _FakeLLM(raw="", error_code="missing_api_key", error="GEMINI_API_KEY is missing")
    agent = _make_agent(llm)

    response, intent = agent.generate_response("오랜만이야")

    assert intent == "none"
    assert "Gemini" in response
    assert "API" in response
    assert "못 알아들" not in response


def test_generate_response_keeps_generic_fallback_when_no_llm_error_is_present():
    llm = _FakeLLM(raw="", error_code=None, error="")
    agent = _make_agent(llm)

    response, intent = agent.generate_response("오랜만이야")

    assert intent == "none"
    assert response == "잘 이해하지 못했어요. 한 번만 다시 말씀해 주세요."

def test_integration_debug_payload_is_not_logged(caplog):
    from src.integrations.base import IntegrationErrorCode, IntegrationResult

    class FailingRegistry:
        def execute(self, provider, intent, params):
            return IntegrationResult.failure(
                IntegrationErrorCode.HTTP_5XX,
                '연결 오류',
                {'secret': 'PRIVATE_API_KEY', 'request': 'private calendar item'},
            )

    agent = _make_agent(_FakeLLM())
    agent.integrations = FailingRegistry()
    caplog.set_level('WARNING', logger='src.agent_mode')
    response = agent._integration_or_error('calendar-google', 'calendar.list', {}, '일정')
    assert response['code'] == 'HTTP_5XX'
    assert 'PRIVATE_API_KEY' not in caplog.text
    assert 'private calendar item' not in caplog.text