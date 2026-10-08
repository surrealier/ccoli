"""
로봇 모드 처리 모듈
- 음성 명령을 서보 모터 제어 명령으로 변환
- LLM 기반 명령 해석 및 모드 전환 의도 분류
"""
import copy
import json
import logging
import re

from emotion_system import EmotionSystem
from .utils import clamp

log = logging.getLogger(__name__)

SERVO_MIN = 0
SERVO_MAX = 180
DEFAULT_ANGLE_CENTER = 90
ROBOT_CONTROLLER_LEGACY_DIRECT = "legacy_direct"
ROBOT_CONTROLLER_COMPANION_UART = "companion_uart"

# robot.display.type <-> DISPLAY_TYPE in
# arduino/atom_echo_m5stack_esp32_ino/config.h. The firmware picks the pin map
# from that macro, so the two must describe the same panel or the server will
# report a display the device is not driving.
DISPLAY_TYPE_TO_FIRMWARE = {
    "none": 0,
    "ssd1306": 1,
    "st7789v2_240x280": 2,
}

EMOTION_MAP = {
    "neutral": {"face": "neutral", "action": "none", "led": [255, 255, 255]},
    "happy": {"face": "happy", "action": "bounce_happy", "led": [255, 200, 0]},
    "sad": {"face": "sad", "action": "droop_sad", "led": [0, 100, 255]},
    "angry": {"face": "angry", "action": "shake_angry", "led": [255, 0, 0]},
    "surprised": {"face": "surprised", "action": "startle", "led": [255, 255, 255]},
    "sleepy": {"face": "sleepy", "action": "sleep_drift", "led": [80, 0, 120]},
    "love": {"face": "love", "action": "nod_yes", "led": [255, 100, 150]},
    "curious": {"face": "curious", "action": "tilt_curious", "led": [0, 200, 100]},
    "excited": {"face": "excited", "action": "dance", "led": [255, 50, 200]},
    "confused": {"face": "confused", "action": "wiggle", "led": [255, 150, 0]},
}

DEFAULT_ROBOT_CONFIG = {
    "controller": ROBOT_CONTROLLER_LEGACY_DIRECT,
    "transport": "local",
    "companion": {
        "transport": "uart",
        "baudrate": 115200,
        "tx_pin": 26,
        "rx_pin": 32,
    },
    "servo": {
        "count": 2,
    },
    # display.type is intentionally absent: seeding it here would mask the
    # controller-derived default the same way robot.transport used to be masked.
    "display": {},
    "emotion": {
        "persist_sec": 900,
    },
}


def _deep_merge(base: dict, override: dict | None) -> dict:
    if not override:
        return base

    for key, value in override.items():
        if isinstance(base.get(key), dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def normalize_display_type(value, controller: str) -> str:
    """Resolve robot.display.type, defaulting to what each controller can drive.

    The companion board owns the SPI panel; the Atom Echo alone ships with
    DISPLAY_TYPE 0 because an on-board display would take the servo pins.
    """
    display_type = str(value or "").strip().lower()
    if display_type in DISPLAY_TYPE_TO_FIRMWARE:
        return display_type
    if display_type:
        log.warning("Unknown robot.display.type %r; falling back to controller default", display_type)
    return "st7789v2_240x280" if controller == ROBOT_CONTROLLER_COMPANION_UART else "none"


def _normalize_robot_config(robot_config: dict | None) -> dict:
    merged = copy.deepcopy(DEFAULT_ROBOT_CONFIG)
    _deep_merge(merged, robot_config)

    controller = str(merged.get("controller") or ROBOT_CONTROLLER_LEGACY_DIRECT).strip().lower()
    if controller not in {ROBOT_CONTROLLER_LEGACY_DIRECT, ROBOT_CONTROLLER_COMPANION_UART}:
        controller = ROBOT_CONTROLLER_LEGACY_DIRECT
    merged["controller"] = controller
    merged["transport"] = "companion" if controller == ROBOT_CONTROLLER_COMPANION_UART else "local"

    servo_cfg = merged.setdefault("servo", {})
    try:
        servo_count = int(servo_cfg.get("count", 2) or 2)
    except (TypeError, ValueError):
        servo_count = 2
    servo_cfg["count"] = min(4, max(1, servo_count))

    display_cfg = merged.setdefault("display", {})
    display_cfg["type"] = normalize_display_type(display_cfg.get("type"), controller)

    emotion_cfg = merged.setdefault("emotion", {})
    try:
        emotion_cfg["persist_sec"] = int(emotion_cfg.get("persist_sec", 900) or 900)
    except (TypeError, ValueError):
        emotion_cfg["persist_sec"] = 900

    companion_cfg = merged.setdefault("companion", {})
    companion_cfg["transport"] = "uart"
    return merged


class RobotMode:
    """로봇 모드 메인 클래스 - 음성 명령을 로봇 동작으로 변환"""
    def __init__(self, actions_config, llm_client=None, robot_config: dict | None = None, emotion_system=None):
        self.actions_config = actions_config
        self.llm = llm_client
        self.robot_config = _normalize_robot_config(robot_config)
        self.emotion_system = emotion_system or EmotionSystem()

    @property
    def controller_type(self) -> str:
        return self.robot_config.get("controller", ROBOT_CONTROLLER_LEGACY_DIRECT)

    def uses_companion_controller(self) -> bool:
        return self.controller_type == ROBOT_CONTROLLER_COMPANION_UART

    def process_with_llm(self, text: str, current_angle: int) -> tuple[str, dict]:
        """LLM 기반 명령 처리. Returns (refined_text, action_dict).
        action_dict에 "action": "SWITCH_MODE" 가 포함될 수 있음."""
        if not self.llm or not (text or "").strip():
            return text or "", {"action": "NOOP"}

        try:
            refined_text = self._refine_stt(text)
            action = self._determine_action(refined_text, current_angle)
            return refined_text, action
        except Exception as exc:
            log.error("LLM processing failed: %s", exc)
            return text, {"action": "NOOP"}

    def _refine_stt(self, text: str) -> str:
        """음성인식 결과 정제"""
        if not text or len(text) < 2:
            return text

        system_prompt = (
            "당신은 음성인식 결과를 정제하는 전문가입니다.\n"
            "로봇 제어 명령어 맥락을 고려하여 오타나 불명확한 부분을 수정하세요.\n"
            "정제된 텍스트만 출력하세요. 설명 없이 결과만."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"정제: {text}"},
        ]
        refined = self.llm.chat(messages, temperature=0.1, max_tokens=64, think=False)
        if len(refined) > len(text) * 3 or len(refined) < 1:
            return text
        return refined

    def _determine_action(self, text: str, current_angle: int) -> dict:
        """LLM 기반 동작 결정 — 로봇 명령 + 모드 전환 의도 통합 판별"""
        commands_desc = []
        for cmd in self.actions_config:
            name = cmd.get("name", "")
            action = cmd.get("action", "")
            keywords = cmd.get("keywords", [])
            if keywords:
                commands_desc.append(f"- {name}: {', '.join(keywords[:3])} -> {action}")
        commands_text = "\n".join(commands_desc[:10])

        system_prompt = (
            "당신은 로봇 제어 명령을 해석하는 AI입니다.\n"
            "사용자의 음성 명령을 분석하여 적절한 동작을 JSON으로 반환하세요.\n\n"
            f"현재 서보 각도: {current_angle}도 (범위: 0-180)\n\n"
            "사용 가능한 명령:\n"
            f"{commands_text}\n\n"
            "추가 의도:\n"
            "- 사용자가 대화 모드/에이전트 모드로 전환을 원하면: {\"action\": \"SWITCH_MODE\", \"mode\": \"agent\"}\n"
            "- 사용자가 로봇 모드로 전환을 원하면: {\"action\": \"SWITCH_MODE\", \"mode\": \"robot\"}\n\n"
            "응답 형식 (JSON만 출력):\n"
            "{\"action\": \"SERVO_SET\", \"servo\": 0, \"angle\": 90}\n"
            "{\"action\": \"SWITCH_MODE\", \"mode\": \"agent\"}\n"
            "{\"action\": \"NOOP\"}\n\n"
            "규칙:\n"
            "1. 상대 이동(올려/내려)은 현재 각도 기준으로 계산하여 SERVO_SET으로 반환\n"
            "2. 불명확한 명령은 NOOP\n"
            "3. JSON만 출력, 설명 금지"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"명령: {text}"},
        ]
        response = self.llm.chat(messages, temperature=0.1, max_tokens=128, think=False)

        match = re.search(r"\{[^}]+\}", response)
        if match:
            try:
                action_dict = json.loads(match.group(0))
                if "angle" in action_dict:
                    action_dict["angle"] = clamp(action_dict["angle"], SERVO_MIN, SERVO_MAX)
                return action_dict
            except json.JSONDecodeError:
                pass

        return {"action": "NOOP"}

    def build_robot_payload(self, emotion: str, text: str = "") -> dict:
        mapping = EMOTION_MAP.get(emotion, EMOTION_MAP["neutral"])
        display_text = text[:20] if text else ""
        if not self.uses_companion_controller():
            return {
                "action": "ROBOT_EMOTION",
                "emotion": emotion,
                "face": mapping["face"],
                "servo_action": mapping["action"],
                "led_color": mapping["led"],
                "display_text": display_text,
                "meaningful": True,
                "transport": "local",
            }

        speech_text = text[:80] if text else ""
        return {
            "action": "ROBOT_STATE",
            "controller": self.controller_type,
            "transport": self.robot_config.get("companion", {}).get("transport", "uart"),
            "mode": "awake",
            "emotion": emotion,
            "emotion_state": {
                "dominant": emotion,
                "persist_sec": self.robot_config.get("emotion", {}).get("persist_sec", 900),
            },
            "gesture": {
                "id": mapping["action"],
                "intensity": 0.72 if text else 0.35,
            },
            "speech": {
                "tts_active": bool(text),
                "text": speech_text,
            },
            "profile": {
                "servo_count": self.robot_config.get("servo", {}).get("count", 2),
                "display": self.robot_config.get("display", {}).get("type", "st7789v2_240x280"),
            },
            # Keep these fields so legacy firmware can still do a safe local fallback.
            "face": mapping["face"],
            "servo_action": mapping["action"],
            "led_color": mapping["led"],
            "display_text": speech_text[:32],
            "meaningful": True,
        }

    def extract_emotion(self, text: str) -> str:
        match = re.search(r'\[emotion:(\w+)\]', text)
        if match:
            emotion = match.group(1)
            if emotion in EMOTION_MAP:
                return emotion
        return "neutral"

    def process_emotion_response(self, text: str) -> tuple[str, str, dict]:
        emotion = self.extract_emotion(text)
        clean_text = re.sub(r'\[emotion:\w+\]', '', text).strip()
        payload = self.build_robot_payload(emotion, clean_text)
        return clean_text, emotion, payload

    def generate_emotion_response(self, user_text: str) -> tuple[str, str, dict]:
        """LLM에 감정 태그 포함 응답을 요청하고, 감정+페이로드를 반환."""
        if not self.llm or not (user_text or "").strip():
            emotion = self.emotion_system.register_emotion_signal("neutral")
            return "", emotion, self.build_robot_payload(emotion)

        # User-side context can leave a lingering mood before the reply emotion lands.
        self.emotion_system.analyze_emotion(user_text)

        emotions_list = ", ".join(EMOTION_MAP.keys())
        system_prompt = (
            "당신은 감정이 풍부한 로봇 펫 '꼴리'입니다.\n"
            "사용자에게 짧고 귀엽게 대답하세요 (1-2문장).\n"
            "반드시 응답 맨 앞에 감정 태그를 붙이세요.\n\n"
            f"사용 가능한 감정: {emotions_list}\n"
            "형식: [emotion:감정] 응답 텍스트\n"
            "예시: [emotion:happy] 안녕! 만나서 반가워!\n"
            "예시: [emotion:curious] 오, 그게 뭐야? 궁금해!"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]
        try:
            response = self.llm.chat(messages, temperature=0.7, max_tokens=100, think=False)
            clean_text, tagged_emotion, _payload = self.process_emotion_response(response)
            emotion = self.emotion_system.register_emotion_signal(tagged_emotion)
            payload = self.build_robot_payload(emotion, clean_text)
            if not clean_text:
                clean_text = response
            return clean_text, emotion, payload
        except Exception as exc:
            log.error("Emotion response failed: %s", exc)
            emotion = self.emotion_system.register_emotion_signal("neutral")
            return user_text, emotion, self.build_robot_payload(emotion)
