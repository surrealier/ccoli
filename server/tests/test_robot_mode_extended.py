"""Extended Robot mode tests — actions, clamping, invalid JSON, mode switch."""
from src.robot_mode import RobotMode


class _FakeLLM:
    def __init__(self, outputs):
        self.outputs = outputs

    def chat(self, *args, **kwargs):
        return self.outputs.pop(0)


def test_servo_set_action():
    llm = _FakeLLM(["서보 45도로", '{"action":"SERVO_SET","servo":0,"angle":45}'])
    robot = RobotMode([], llm)
    refined, action = robot.process_with_llm("서보 45도", current_angle=90)
    assert action["action"] == "SERVO_SET"
    assert action["angle"] == 45


def test_noop_action():
    llm = _FakeLLM(["불명확", '{"action":"NOOP"}'])
    robot = RobotMode([], llm)
    _, action = robot.process_with_llm("음", current_angle=90)
    assert action["action"] == "NOOP"


def test_angle_clamped_high():
    llm = _FakeLLM(["200도", '{"action":"SERVO_SET","servo":0,"angle":200}'])
    robot = RobotMode([], llm)
    _, action = robot.process_with_llm("200도", current_angle=90)
    assert action["angle"] == 180


def test_angle_clamped_negative():
    llm = _FakeLLM(["마이너스", '{"action":"SERVO_SET","servo":0,"angle":-30}'])
    robot = RobotMode([], llm)
    _, action = robot.process_with_llm("마이너스", current_angle=90)
    assert action["angle"] == 0


def test_invalid_json_falls_back_to_noop():
    llm = _FakeLLM(["돌려", "이해할 수 없는 명령입니다"])
    robot = RobotMode([], llm)
    _, action = robot.process_with_llm("돌려", current_angle=90)
    assert action["action"] == "NOOP"


def test_refine_stt():
    llm = _FakeLLM(["정리된 텍스트입니다"])
    robot = RobotMode([], llm)
    # input must be >= 2 chars, output must be <= 3x input length
    assert robot._refine_stt("원본 텍스트") == "정리된 텍스트입니다"


def test_multiple_actions_config():
    cfg = [{"name": "s1", "action": "SERVO_SET"}, {"name": "s2", "action": "SERVO_SET"}]
    llm = _FakeLLM(["서보 이동", '{"action":"SERVO_SET","servo":1,"angle":90}'])
    robot = RobotMode(cfg, llm)
    _, action = robot.process_with_llm("이동", current_angle=90)
    assert len(robot.actions_config) == 2
    assert action["servo"] == 1


def test_switch_mode_action():
    llm = _FakeLLM(["에이전트 전환", '{"action":"SWITCH_MODE","mode":"agent"}'])
    robot = RobotMode([], llm)
    _, action = robot.process_with_llm("모드 전환", current_angle=90)
    assert action["action"] == "SWITCH_MODE"
    assert action["mode"] == "agent"
