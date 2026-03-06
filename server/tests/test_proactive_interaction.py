"""Tests for proactive_interaction.ProactiveInteraction class."""
import time
from datetime import datetime, timedelta
from unittest.mock import patch

from proactive_interaction import ProactiveInteraction


def _make_pi(**kwargs):
    return ProactiveInteraction(enabled=True, interval=60, **kwargs)


def test_disabled_never_triggers():
    pi = _make_pi()
    pi.enabled = False
    pi.last_interaction = 0
    pi.last_proactive = 0
    assert pi.should_trigger() is False


def test_trigger_after_interval_elapsed():
    pi = _make_pi()
    now = time.time()
    pi.last_interaction = now - 120  # 2 min ago, interval=60
    pi.last_proactive = now - 120
    with patch("proactive_interaction.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 3, 6, 14, 0)  # 14시 = active
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert pi.should_trigger() is True


def test_no_trigger_within_interval():
    pi = _make_pi()
    # last interaction just happened
    pi.last_interaction = time.time()
    assert pi.should_trigger() is False


def test_get_proactive_message_returns_string():
    pi = _make_pi()
    pi.last_interaction = time.time() - 120
    pi.last_proactive = time.time() - 120
    with patch("proactive_interaction.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 3, 6, 14, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        msg = pi.get_proactive_message()
        assert isinstance(msg, str)
        assert len(msg) > 0


def test_get_proactive_message_none_when_not_triggered():
    pi = _make_pi()
    pi.last_interaction = time.time()  # just now
    msg = pi.get_proactive_message()
    assert msg is None


def test_sleep_mode_blocks_trigger():
    pi = _make_pi()
    pi.last_interaction = time.time() - 120
    pi.last_proactive = time.time() - 120
    pi.enter_sleep_mode()
    assert pi.sleep_mode is True
    with patch("proactive_interaction.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 3, 6, 14, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert pi.should_trigger() is False


def test_wake_up_clears_sleep():
    pi = _make_pi()
    pi.enter_sleep_mode()
    result = pi.wake_up()
    assert pi.sleep_mode is False
    assert "일어났" in result


def test_wake_up_when_already_awake():
    pi = _make_pi()
    result = pi.wake_up()
    assert "이미" in result


def test_pause_temporarily():
    pi = _make_pi()
    result = pi.pause_temporarily(hours=2)
    assert pi.sleep_mode is True
    assert "2시간" in result


def test_birthday_reminder_match():
    pi = _make_pi()
    today_str = datetime.now().strftime("%m월 %d일")
    memories = [f"엄마 생일 {today_str}"]
    result = pi.check_birthday_reminder(memories)
    assert result is not None and "특별한 날" in result


def test_birthday_reminder_no_match():
    pi = _make_pi()
    result = pi.check_birthday_reminder(["아무 메모"])
    assert result is None


def test_enable_disable():
    pi = _make_pi()
    pi.disable()
    assert pi.enabled is False
    pi.enable()
    assert pi.enabled is True


def test_set_interval():
    pi = _make_pi()
    pi.set_interval(300)
    assert pi.interval == 300


def test_get_stats_structure():
    pi = _make_pi()
    stats = pi.get_stats()
    assert "enabled" in stats
    assert "interval" in stats
    assert "sleep_mode" in stats


def test_time_greeting_returns_list_for_valid_hour():
    pi = _make_pi()
    greetings = pi._get_time_greeting(8)  # morning
    assert isinstance(greetings, list) and len(greetings) > 0


def test_update_interaction_resets_timer():
    pi = _make_pi()
    old = pi.last_interaction
    time.sleep(0.01)
    pi.update_interaction()
    assert pi.last_interaction > old
