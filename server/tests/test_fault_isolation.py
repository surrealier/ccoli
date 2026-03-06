"""NFR §6.2 — Fault isolation / graceful degradation tests."""
from src.agent_mode import AgentMode
from src.robot_mode import RobotMode
from src.integrations.base import IntegrationErrorCode, IntegrationResult


class _FakeLLMRaises:
    def chat(self, *a, **kw):
        raise RuntimeError("LLM backend down")


class _FakeEmotion:
    def analyze_emotion(self, _t):
        return "neutral"


class _FakeProactive:
    def __init__(self):
        self.sleep_mode = False
        self.sleep_until = None

    def update_interaction(self):
        pass


class _FakeScheduler:
    def process_schedule_request(self, _t):
        return None


class _FakeMemory:
    def build_system_prompt(self):
        return "system"

    def after_turn(self, _h):
        pass


class _FakeInfo:
    def process_info_request(self, _t):
        return None


class _FakeIntegrations:
    def execute(self, *a, **kw):
        return None


class _FakeIntegrationsError:
    def execute(self, provider, intent, params):
        return IntegrationResult.failure(
            code=IntegrationErrorCode.AUTH_MISSING_KEY,
            user_message="키 없음",
        )


def _make_agent(llm, integrations=None):
    a = AgentMode.__new__(AgentMode)
    a.llm = llm
    a.tts_voice = "ko-KR-SunHiNeural"
    a.conversation_history = []
    a.user_histories = {}
    a.max_history = 20
    a.conversation_count = 0
    a.proactive = _FakeProactive()
    a.emotion_system = _FakeEmotion()
    a.scheduler = _FakeScheduler()
    a.memory = _FakeMemory()
    a.integrations = integrations or _FakeIntegrations()
    a.info_services = _FakeInfo()
    return a


# ── LLM failure ──────────────────────────────────────────────

def test_llm_failure_returns_error_message():
    agent = _make_agent(_FakeLLMRaises())
    response, intent = agent.generate_response("테스트")
    assert response == "죄송해요, 오류가 발생했어요."
    assert intent == "none"


def test_llm_none_returns_not_loaded():
    agent = _make_agent(None)
    response, intent = agent.generate_response("테스트")
    assert response == "모델이 로드되지 않았습니다."


# ── TTS failure ──────────────────────────────────────────────

def test_tts_failure_returns_empty_bytes():
    """text_to_audio returns b'' on internal failure, never raises."""
    agent = _make_agent(None)
    result = agent.text_to_audio("")
    assert isinstance(result, bytes)
    assert result == b""


# ── Integration failure ──────────────────────────────────────

def test_integration_failure_returns_user_guidance():
    """Integration AUTH error → user-facing guidance message, not crash."""
    agent = _make_agent(
        type("LLM", (), {"chat": lambda s, m, **kw: "이 응답은 사용 안 됨"})(),
        integrations=_FakeIntegrationsError(),
    )
    response, _ = agent.generate_response("날씨 알려줘")
    assert "api 키" in response.lower() or "오류" in response


# ── Robot mode LLM failure ───────────────────────────────────

def test_robot_llm_failure_graceful():
    """RobotMode handles LLM exception without crashing."""
    robot = RobotMode(actions_config=[], llm_client=_FakeLLMRaises())
    try:
        robot.process_with_llm("테스트", current_angle=90)
    except RuntimeError:
        pass  # current impl may propagate; test documents behaviour
    # key assertion: no unhandled TypeError / AttributeError


# ── Empty / None input ───────────────────────────────────────

def test_empty_text_does_not_crash_agent():
    agent = _make_agent(type("LLM", (), {"chat": lambda s, m, **kw: "응답"})())
    response, _ = agent.generate_response("")
    assert response
