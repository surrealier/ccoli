"""Tests for emotion_system.EmotionSystem class."""
from emotion_system import EmotionSystem


def test_initial_state():
    es = EmotionSystem()
    assert es.current_emotion == "neutral"
    assert es.emotion_history == []


def test_analyze_emotion_happy_keyword():
    es = EmotionSystem()
    result = es.analyze_emotion("오늘 너무 행복해!")
    assert result == "happy"
    assert es.current_emotion == "happy"


def test_analyze_emotion_no_keyword_keeps_current():
    es = EmotionSystem()
    es.set_emotion("sad")
    result = es.analyze_emotion("안녕하세요")
    assert result == "sad"


def test_analyze_emotion_empty_text():
    es = EmotionSystem()
    assert es.analyze_emotion("") == "neutral"


def test_get_led_color_returns_rgb_tuple():
    es = EmotionSystem()
    color = es.get_led_color("happy")
    assert color == (255, 200, 0)
    assert es.get_led_color("unknown_emotion") == es.EMOTION_COLORS["neutral"]


def test_get_led_pattern_structure():
    es = EmotionSystem()
    pattern = es.get_led_pattern("excited")
    assert pattern["pattern"] == "rainbow"
    assert pattern["speed"] == "fast"
    assert "color" in pattern and "r" in pattern["color"]


def test_get_servo_action():
    es = EmotionSystem()
    assert es.get_servo_action("happy") == "NOD"
    assert es.get_servo_action("angry") == "SHAKE_SHARP"
    assert es.get_servo_action("nonexistent") == "CENTER"


def test_get_emotion_command_structure():
    es = EmotionSystem()
    es.set_emotion("excited")
    cmd = es.get_emotion_command()
    assert cmd["action"] == "EMOTION"
    assert cmd["emotion"] == "excited"
    assert "led" in cmd and "servo_action" in cmd


def test_set_emotion_valid_and_invalid():
    es = EmotionSystem()
    es.set_emotion("angry")
    assert es.current_emotion == "angry"
    es.set_emotion("invalid_emotion")
    assert es.current_emotion == "angry"  # unchanged


def test_emotion_history_tracking():
    es = EmotionSystem()
    es.set_emotion("happy")
    es.set_emotion("sad")
    assert es.emotion_history == ["neutral", "happy"]


def test_decay_to_neutral():
    es = EmotionSystem()
    es.set_emotion("happy")
    # probability=1.0 guarantees decay
    result = es.decay_to_neutral(probability=1.0)
    assert result is True
    assert es.current_emotion == "neutral"


def test_decay_no_change_when_already_neutral():
    es = EmotionSystem()
    result = es.decay_to_neutral(probability=1.0)
    assert result is False


def test_get_random_emotion_excludes_current():
    es = EmotionSystem()
    es.set_emotion("happy")
    for _ in range(20):
        assert es.get_random_emotion(exclude_current=True) != "happy"
