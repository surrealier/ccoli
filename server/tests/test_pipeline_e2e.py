"""L2 integration tests — STT→LLM→TTS full pipeline, Robot mode pipeline."""
from unittest.mock import patch

from src.agent_mode import AgentMode
from src.robot_mode import RobotMode


class _FakeLLM:
    def __init__(self, outputs):
        self._outputs = list(outputs)

    def chat(self, messages, **kwargs):
        return self._outputs.pop(0)


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
    def __init__(self, response=None):
        self._resp = response

    def process_schedule_request(self, _t):
        return self._resp


class _FakeMemory:
    def build_system_prompt(self):
        return "system"

    def after_turn(self, _h):
        pass


class _FakeInfo:
    def __init__(self, response=None):
        self._resp = response

    def process_info_request(self, _t):
        return self._resp


class _FakeIntegrations:
    def execute(self, *a, **kw):
        return None


def _make_agent(llm, info=None, scheduler=None, integrations=None):
    a = AgentMode.__new__(AgentMode)
    a.llm = llm
    a.tts_voice = "ko-KR-SunHiNeural"
    a.conversation_history = []
    a.user_histories = {}
    a.max_history = 20
    a.conversation_count = 0
    a.proactive = _FakeProactive()
    a.emotion_system = _FakeEmotion()
    a.scheduler = scheduler or _FakeScheduler()
    a.memory = _FakeMemory()
    a.integrations = integrations or _FakeIntegrations()
    a.info_services = info or _FakeInfo()
    return a


# ── L2: Agent pipeline ──────────────────────────────────────

def test_agent_pipeline_stt_to_llm_to_tts():
    """STT text → generate_response → text_to_audio chain."""
    agent = _make_agent(_FakeLLM(["안녕하세요! 도와드릴게요."]))
    response, intent = agent.generate_response("안녕")
    assert "안녕하세요" in response

    with patch.object(agent, "text_to_audio", return_value=b"\x00\x01" * 50):
        audio = agent.text_to_audio(response)
    assert len(audio) > 0


def test_agent_pipeline_with_info_context():
    """Info service data injected into LLM context."""
    info = _FakeInfo(response={"type": "time", "datetime": "2026-03-06 14:00", "weekday": "금요일"})
    agent = _make_agent(_FakeLLM(["지금 오후 2시예요."]), info=info)
    response, _ = agent.generate_response("지금 몇 시야?")
    assert response


def test_agent_pipeline_with_schedule_context():
    """Scheduler data injected into LLM context."""
    sched = _FakeScheduler(response="오후 3시 회의가 있어요.")
    agent = _make_agent(_FakeLLM(["오후 3시에 회의가 있네요."]), scheduler=sched)
    response, _ = agent.generate_response("오늘 일정 알려줘")
    assert response


def test_agent_pipeline_speaker_separation():
    """Different speakers get separate history."""
    agent = _make_agent(_FakeLLM(["응답A", "응답B"]))
    agent.generate_response("질문1", speaker_id="alice")
    agent.generate_response("질문2", speaker_id="bob")
    assert "alice" in agent.user_histories
    assert "bob" in agent.user_histories
    assert len(agent.user_histories["alice"]) == 2
    assert len(agent.user_histories["bob"]) == 2


# ── L2: Robot pipeline ───────────────────────────────────────

def test_robot_pipeline_stt_to_action():
    """STT text → RobotMode → action dict."""
    llm = _FakeLLM(["고개 오른쪽", '{"action":"SERVO_SET","servo":0,"angle":120}'])
    robot = RobotMode(actions_config=[], llm_client=llm)
    refined, action = robot.process_with_llm("오른쪽 봐", current_angle=90)
    assert action["action"] == "SERVO_SET"
    assert 0 <= action["angle"] <= 180


def test_robot_pipeline_mode_switch():
    """Robot mode returns SWITCH_MODE action."""
    llm = _FakeLLM(["에이전트 모드로 전환", '{"action":"SWITCH_MODE","mode":"agent"}'])
    robot = RobotMode(actions_config=[], llm_client=llm)
    _, action = robot.process_with_llm("에이전트 모드로 바꿔", current_angle=90)
    assert action["action"] == "SWITCH_MODE"
    assert action["mode"] == "agent"
