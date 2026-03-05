from src.agent_mode import AgentMode
from src.integrations.base import IntegrationErrorCode, IntegrationResult


class _FakeLLM:
    def __init__(self, response):
        self.response = response
        self.messages = None

    def chat(self, messages, **kwargs):
        self.messages = messages
        return self.response


class _FakeEmotion:
    def analyze_emotion(self, _text):
        return "neutral"


class _FakeProactive:
    def __init__(self):
        self.updated = 0
        self.sleep_mode = False
        self.sleep_until = None

    def update_interaction(self):
        self.updated += 1


class _FakeScheduler:
    def process_schedule_request(self, _text):
        return None


class _FakeMemory:
    def __init__(self):
        self.after_turn_called = 0

    def build_system_prompt(self):
        return "기본 시스템 프롬프트"

    def after_turn(self, _history):
        self.after_turn_called += 1


class _FakeIntegrations:
    def __init__(self, result):
        self.result = result

    def execute(self, provider, intent, params):
        if provider == "search":
            return self.result
        return None


class _FakeInfo:
    def process_info_request(self, _text):
        return None


def _make_agent(fake_llm, integration_result):
    agent = AgentMode.__new__(AgentMode)
    agent.llm = fake_llm
    agent.tts_voice = "ko-KR-SunHiNeural"
    agent.conversation_history = []
    agent.user_histories = {}
    agent.max_history = 20
    agent.conversation_count = 0
    agent.proactive = _FakeProactive()
    agent.emotion_system = _FakeEmotion()
    agent.scheduler = _FakeScheduler()
    agent.memory = _FakeMemory()
    agent.integrations = _FakeIntegrations(integration_result)
    agent.info_services = _FakeInfo()
    return agent


def test_scenario_user_question_to_llm_answer_with_integration_context():
    llm = _FakeLLM("[INTENT:none] 파이썬은 범용 프로그래밍 언어예요.")
    integration_result = IntegrationResult.success({"type": "search", "items": ["python"]})
    agent = _make_agent(llm, integration_result)

    response, intent = agent.generate_response("파이썬 검색해줘", speaker_id="alice")

    assert response == "파이썬은 범용 프로그래밍 언어예요."
    assert intent == "none"
    assert agent.proactive.updated == 1
    assert agent.memory.after_turn_called == 1
    assert "[참고 데이터]" in llm.messages[0]["content"]
    assert len(agent.user_histories["alice"]) == 2


def test_scenario_integration_error_returns_user_guidance_message():
    llm = _FakeLLM("이 응답은 사용되지 않음")
    integration_result = IntegrationResult.failure(
        code=IntegrationErrorCode.AUTH_MISSING_KEY,
        user_message="키가 없어요",
    )
    agent = _make_agent(llm, integration_result)

    response, intent = agent.generate_response("검색해줘")

    assert "api 키" in response.lower()
    assert intent == "none"
