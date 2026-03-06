"""
로봇 모드 처리 모듈
- 음성 명령을 서보 모터 제어 명령으로 변환
- LLM 기반 명령 해석 및 모드 전환 의도 분류
"""
import json
import logging
import re

from .utils import clamp

log = logging.getLogger(__name__)

SERVO_MIN = 0
SERVO_MAX = 180
DEFAULT_ANGLE_CENTER = 90

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


class RobotMode:
    """로봇 모드 메인 클래스 - 음성 명령을 로봇 동작으로 변환"""
    def __init__(self, actions_config, llm_client=None):
        self.actions_config = actions_config
        self.llm = llm_client

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
        return {
            "action": "ROBOT_EMOTION",
            "emotion": emotion,
            "face": mapping["face"],
            "servo_action": mapping["action"],
            "led_color": mapping["led"],
            "display_text": text[:20] if text else "",
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
            return "", "neutral", self.build_robot_payload("neutral")

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
            clean_text, emotion, payload = self.process_emotion_response(response)
            if not clean_text:
                clean_text = response
            return clean_text, emotion, payload
        except Exception as exc:
            log.error("Emotion response failed: %s", exc)
            return user_text, "neutral", self.build_robot_payload("neutral")
