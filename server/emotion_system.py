# ============================================================
# emotion_system.py — 감정 상태 분석 및 표현 시스템
# ============================================================
# 역할:
# - 대화 텍스트에서 즉각 반응(AFFECT)을 추출
# - 관계(RELATION), 기분 잔상(MOOD), 바디 상태(BODY)를 함께 관리
# - 감정이 한 턴마다 바로 neutral로 리셋되지 않도록 지속형 상태를 유지
# ============================================================
import copy
import logging
import random
from typing import Dict, Tuple

log = logging.getLogger("emotion_system")


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


class EmotionSystem:
    """
    감정 상태 시스템
    - 즉각 반응보다 lingering mood를 우선 보존합니다.
    - 기본 사용자 기준 RELATION 상태를 유지합니다.
    - sleep/fatigue 같은 BODY 상태가 idle 감정에도 영향을 줍니다.
    """

    EMOTIONS = ["happy", "sad", "excited", "sleepy", "angry", "neutral"]
    NON_NEUTRAL_EMOTIONS = [emotion for emotion in EMOTIONS if emotion != "neutral"]
    DOMINANT_THRESHOLD = 0.18

    EMOTION_COLORS = {
        "happy": (255, 200, 0),
        "sad": (0, 100, 255),
        "excited": (255, 50, 200),
        "sleepy": (100, 100, 150),
        "angry": (255, 0, 0),
        "neutral": (100, 255, 100),
    }

    EMOTION_PATTERNS = {
        "happy": ("pulse", "medium"),
        "sad": ("slow_fade", "slow"),
        "excited": ("rainbow", "fast"),
        "sleepy": ("breathing", "slow"),
        "angry": ("blink", "fast"),
        "neutral": ("solid", "none"),
    }

    EMOTION_SERVO_ACTIONS = {
        "happy": "NOD",
        "sad": "SHAKE_SLOW",
        "excited": "WIGGLE_FAST",
        "sleepy": "DRIFT",
        "angry": "SHAKE_SHARP",
        "neutral": "CENTER",
    }

    EMOTION_KEYWORDS = {
        "happy": ["행복", "기쁘", "좋아", "웃", "즐거", "신나", "재밌", "굿", "최고", "좋다", "고마", "반갑"],
        "sad": ["슬프", "우울", "힘들", "아프", "외로", "쓸쓸", "답답", "안타깝", "아쉽"],
        "excited": ["와", "대박", "짱", "신난다", "흥분", "놀라", "멋지", "환상", "완전"],
        "sleepy": ["피곤", "졸려", "자고", "잠", "쉬고", "휴식", "지쳐", "잔다", "잘게"],
        "angry": ["화", "짜증", "싫", "귀찮", "답답", "속상", "빡", "열받", "미워", "별로"],
        "neutral": [],
    }

    APOLOGY_KEYWORDS = ["미안", "죄송", "사과", "잘못했", "용서"]
    WAKE_KEYWORDS = ["일어", "깨워", "굿모닝", "아침", "wake"]

    DEFAULT_SOUL = {
        "playfulness": 0.60,
        "sensitivity": 0.68,
        "forgiveness": 0.34,
        "curiosity": 0.55,
        "sleep_rhythm": 0.50,
    }

    DEFAULT_RELATION = {
        "affection": 0.50,
        "trust": 0.50,
        "grudge": 0.00,
        "comfort": 0.50,
    }

    DEFAULT_BODY = {
        "sleep_mode": False,
        "fatigue": 0.15,
    }

    def __init__(self, soul_profile: Dict | None = None):
        self.current_emotion = "neutral"
        self.emotion_history = []
        self.max_history = 10

        self.soul_profile = copy.deepcopy(self.DEFAULT_SOUL)
        if soul_profile:
            for key, value in soul_profile.items():
                if key in self.soul_profile:
                    self.soul_profile[key] = _clamp01(value)

        self.relations: dict[str, dict[str, float]] = {"default": copy.deepcopy(self.DEFAULT_RELATION)}
        self.body_state = copy.deepcopy(self.DEFAULT_BODY)
        self.mood_weights = {emotion: 0.0 for emotion in self.NON_NEUTRAL_EMOTIONS}

    def analyze_emotion(self, text: str, speaker_id: str = "default") -> str:
        """
        텍스트에서 감정을 분석하고 내부 lingering mood를 갱신합니다.
        Returns: dominant emotion string
        """
        relation = self._relation_for(speaker_id)
        if not text:
            return self._recompute_current_emotion()

        text_lower = text.lower()
        self._passive_decay()
        self._update_body_bias(text_lower)

        scores = {emotion: 0 for emotion in self.EMOTIONS}
        for emotion, keywords in self.EMOTION_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    scores[emotion] += 1

        apology_detected = any(keyword in text_lower for keyword in self.APOLOGY_KEYWORDS)
        max_score = max(scores.values())

        if max_score > 0:
            detected_emotion = max(scores, key=scores.get)
            self._apply_detected_emotion(detected_emotion, max_score, relation)
        elif apology_detected:
            self._apply_apology(relation)
        else:
            self._apply_idle_bias(relation)

        dominant = self._recompute_current_emotion()
        log.info("Emotion detected: %s", dominant)
        return dominant

    def _relation_for(self, speaker_id: str) -> dict[str, float]:
        relation = self.relations.get(speaker_id)
        if relation is None:
            relation = copy.deepcopy(self.DEFAULT_RELATION)
            self.relations[speaker_id] = relation
        return relation

    def _apply_emotion_delta(self, emotion: str, delta: float):
        if emotion not in self.mood_weights:
            return
        self.mood_weights[emotion] = _clamp01(self.mood_weights[emotion] + delta)

    def _soften_emotion(self, emotion: str, amount: float):
        if emotion not in self.mood_weights:
            return
        self.mood_weights[emotion] = _clamp01(self.mood_weights[emotion] - amount)

    def _apply_detected_emotion(self, emotion: str, score: int, relation: dict[str, float]):
        sensitivity = self.soul_profile["sensitivity"]
        forgiveness = self.soul_profile["forgiveness"]
        playfulness = self.soul_profile["playfulness"]

        if emotion == "angry":
            self._apply_emotion_delta("angry", 0.42 + (score * 0.10) + (relation["grudge"] * 0.18))
            self._apply_emotion_delta("sad", 0.10 * sensitivity)
            relation["grudge"] = _clamp01(relation["grudge"] + (0.18 * sensitivity))
            relation["trust"] = _clamp01(relation["trust"] - (0.06 * sensitivity))
            relation["comfort"] = _clamp01(relation["comfort"] - 0.04)
            return

        if emotion == "sad":
            self._apply_emotion_delta("sad", 0.34 + (score * 0.08))
            self._soften_emotion("angry", 0.05 + (forgiveness * 0.03))
            relation["comfort"] = _clamp01(relation["comfort"] - 0.03)
            return

        if emotion == "happy":
            self._apply_emotion_delta("happy", 0.30 + (score * 0.08) + (playfulness * 0.04))
            self._soften_emotion("sad", 0.10 + (forgiveness * 0.05))
            self._soften_emotion("angry", 0.09 + (forgiveness * 0.05))
            relation["affection"] = _clamp01(relation["affection"] + 0.06)
            relation["trust"] = _clamp01(relation["trust"] + 0.04)
            relation["grudge"] = _clamp01(relation["grudge"] - (0.05 + forgiveness * 0.05))
            return

        if emotion == "excited":
            self._apply_emotion_delta("excited", 0.34 + (score * 0.09))
            self._apply_emotion_delta("happy", 0.12)
            self._soften_emotion("sleepy", 0.08)
            self.body_state["fatigue"] = _clamp01(self.body_state["fatigue"] - 0.05)
            relation["affection"] = _clamp01(relation["affection"] + 0.03)
            return

        if emotion == "sleepy":
            self._apply_emotion_delta("sleepy", 0.28 + (score * 0.08) + (self.body_state["fatigue"] * 0.12))
            self.body_state["fatigue"] = _clamp01(self.body_state["fatigue"] + 0.18)
            return

    def _apply_apology(self, relation: dict[str, float]):
        forgiveness = self.soul_profile["forgiveness"]
        soften = 0.10 + (forgiveness * 0.12)
        current_anger = self.mood_weights.get("angry", 0.0)

        self._soften_emotion("angry", soften)
        self._soften_emotion("sad", soften * 0.35)

        # Apology softens the edge, but a lingering sulk remains for a while.
        if current_anger > 0.22 or relation["grudge"] > 0.10:
            self._apply_emotion_delta("sad", 0.08)

        relation["grudge"] = _clamp01(relation["grudge"] - (0.03 + forgiveness * 0.05))
        relation["trust"] = _clamp01(relation["trust"] + 0.02)

    def _apply_idle_bias(self, relation: dict[str, float]):
        if self.body_state["sleep_mode"] or self.body_state["fatigue"] >= 0.72:
            self._apply_emotion_delta("sleepy", 0.08 + (self.body_state["fatigue"] * 0.05))
        if relation["grudge"] >= 0.18:
            self._apply_emotion_delta("sad", 0.05 + (relation["grudge"] * 0.04))

    def _update_body_bias(self, text_lower: str):
        if any(keyword in text_lower for keyword in self.WAKE_KEYWORDS):
            self.body_state["sleep_mode"] = False
            self.body_state["fatigue"] = _clamp01(self.body_state["fatigue"] - 0.35)
            return

        if any(keyword in text_lower for keyword in self.EMOTION_KEYWORDS["sleepy"]):
            self.body_state["fatigue"] = _clamp01(self.body_state["fatigue"] + 0.12)

    def _passive_decay(self):
        forgiveness = self.soul_profile["forgiveness"]
        decay_factor = 0.96 + (forgiveness * 0.01)
        for emotion in self.NON_NEUTRAL_EMOTIONS:
            self.mood_weights[emotion] *= decay_factor

        default_relation = self._relation_for("default")
        default_relation["grudge"] = _clamp01(default_relation["grudge"] - (0.002 + forgiveness * 0.002))
        self.body_state["fatigue"] = _clamp01(self.body_state["fatigue"] - 0.002)

    def _recompute_current_emotion(self) -> str:
        sleepy_bias = 0.0
        if self.body_state["sleep_mode"]:
            sleepy_bias += 0.22
        sleepy_bias += self.body_state["fatigue"] * 0.22

        dominant = "neutral"
        dominant_score = self.DOMINANT_THRESHOLD

        for emotion in self.NON_NEUTRAL_EMOTIONS:
            score = self.mood_weights.get(emotion, 0.0)
            if emotion == "sleepy":
                score += sleepy_bias
            if score > dominant_score:
                dominant = emotion
                dominant_score = score

        self._update_emotion(dominant)
        return self.current_emotion

    def _update_emotion(self, new_emotion: str):
        if new_emotion != self.current_emotion:
            self.emotion_history.append(self.current_emotion)
            if len(self.emotion_history) > self.max_history:
                self.emotion_history.pop(0)
            self.current_emotion = new_emotion

    def get_led_color(self, emotion: str = None) -> Tuple[int, int, int]:
        emotion = emotion or self.current_emotion
        return self.EMOTION_COLORS.get(emotion, self.EMOTION_COLORS["neutral"])

    def get_led_pattern(self, emotion: str = None) -> Dict:
        emotion = emotion or self.current_emotion
        pattern, speed = self.EMOTION_PATTERNS.get(emotion, self.EMOTION_PATTERNS["neutral"])
        rgb = self.get_led_color(emotion)
        return {
            "pattern": pattern,
            "speed": speed,
            "color": {"r": rgb[0], "g": rgb[1], "b": rgb[2]},
        }

    def get_servo_action(self, emotion: str = None) -> str:
        emotion = emotion or self.current_emotion
        return self.EMOTION_SERVO_ACTIONS.get(emotion, "CENTER")

    def get_state_snapshot(self, speaker_id: str = "default") -> Dict:
        relation = self._relation_for(speaker_id)
        return {
            "current_emotion": self.current_emotion,
            "mood": {emotion: round(self.mood_weights.get(emotion, 0.0), 4) for emotion in self.NON_NEUTRAL_EMOTIONS},
            "relation": {key: round(value, 4) for key, value in relation.items()},
            "body": {
                "sleep_mode": bool(self.body_state["sleep_mode"]),
                "fatigue": round(self.body_state["fatigue"], 4),
            },
            "soul": {key: round(value, 4) for key, value in self.soul_profile.items()},
        }

    def register_emotion_signal(self, emotion: str, *, speaker_id: str = "default", intensity: float = 0.28) -> str:
        relation = self._relation_for(speaker_id)
        self._passive_decay()
        intensity = _clamp01(intensity)

        if emotion == "angry":
            self._apply_emotion_delta("angry", 0.18 + intensity * 0.35)
            relation["grudge"] = _clamp01(relation["grudge"] + intensity * 0.06)
        elif emotion == "sad":
            self._apply_emotion_delta("sad", 0.16 + intensity * 0.28)
        elif emotion == "happy":
            self._apply_emotion_delta("happy", 0.14 + intensity * 0.25)
            self._soften_emotion("angry", 0.05 + intensity * 0.06)
            self._soften_emotion("sad", 0.04 + intensity * 0.05)
        elif emotion == "excited":
            self._apply_emotion_delta("excited", 0.15 + intensity * 0.30)
            self._apply_emotion_delta("happy", 0.08)
        elif emotion == "sleepy":
            self._apply_emotion_delta("sleepy", 0.15 + intensity * 0.25)
            self.body_state["fatigue"] = _clamp01(self.body_state["fatigue"] + 0.08)
        elif emotion == "neutral":
            self._soften_emotion("angry", 0.04 + intensity * 0.05)
            self._soften_emotion("sad", 0.03 + intensity * 0.05)

        return self._recompute_current_emotion()

    def get_emotion_command(self, emotion: str = None) -> Dict:
        emotion = emotion or self.current_emotion
        return {
            "action": "EMOTION",
            "emotion": emotion,
            "led": self.get_led_pattern(emotion),
            "servo_action": self.get_servo_action(emotion),
            "emotion_state": self.get_state_snapshot(),
        }

    def set_emotion(self, emotion: str):
        if emotion not in self.EMOTIONS:
            log.warning("Invalid emotion: %s", emotion)
            return

        for key in self.NON_NEUTRAL_EMOTIONS:
            self.mood_weights[key] = 0.0

        if emotion != "neutral":
            self.mood_weights[emotion] = 1.0
        self._update_emotion(emotion)
        log.info("Emotion manually set to: %s", emotion)

    def set_body_state(self, *, sleep_mode: bool | None = None, fatigue: float | None = None):
        if sleep_mode is not None:
            self.body_state["sleep_mode"] = bool(sleep_mode)
        if fatigue is not None:
            self.body_state["fatigue"] = _clamp01(fatigue)
        self._recompute_current_emotion()

    def get_random_emotion(self, exclude_current: bool = True) -> str:
        emotions = self.EMOTIONS.copy()
        if exclude_current and self.current_emotion in emotions:
            emotions.remove(self.current_emotion)
        return random.choice(emotions)

    def decay_to_neutral(self, probability: float = 0.1):
        """
        시간이 지나면 mood/grudge/fatigue가 완만하게 줄어듭니다.
        probability=1.0이면 적극적으로 한 단계 큰 감쇠를 적용합니다.
        """
        if self.current_emotion == "neutral" and self._relation_for("default")["grudge"] <= 0.0:
            return False
        if random.random() >= probability:
            return False

        forgiveness = self.soul_profile["forgiveness"]
        decay_factor = 0.10 if probability >= 1.0 else max(0.55, 0.82 - (forgiveness * 0.10))
        for emotion in self.NON_NEUTRAL_EMOTIONS:
            self.mood_weights[emotion] *= decay_factor

        default_relation = self._relation_for("default")
        default_relation["grudge"] = _clamp01(default_relation["grudge"] - (0.08 + forgiveness * 0.10))
        self.body_state["fatigue"] = _clamp01(self.body_state["fatigue"] - 0.05)
        self._recompute_current_emotion()
        log.info("Emotion decayed toward neutral")
        return True
