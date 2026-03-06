"""Tests for info_services.InfoServices class."""
import time
from datetime import datetime
from unittest.mock import patch

from info_services import InfoServices


def test_get_current_time_structure():
    svc = InfoServices()
    result = svc.get_current_time()
    assert result["type"] == "time"
    assert "datetime" in result
    assert "weekday" in result


def test_get_current_date_structure():
    svc = InfoServices()
    result = svc.get_current_date()
    assert result["type"] == "date"
    assert "date" in result and "weekday" in result


def test_get_day_of_week():
    svc = InfoServices()
    result = svc.get_day_of_week()
    assert result["type"] == "weekday"
    assert result["weekday"].endswith("요일")


def test_set_timer_and_check():
    svc = InfoServices()
    result = svc.set_timer(1, label="테스트")
    assert result["type"] == "timer_set"
    assert result["label"] == "테스트"
    assert len(svc.timers) == 1

    # not expired yet
    assert svc.check_timers() == []

    # force expire
    svc.timers[0]["end_time"] = time.time() - 1
    expired = svc.check_timers()
    assert len(expired) == 1
    assert len(svc.timers) == 0


def test_set_alarm():
    svc = InfoServices()
    result = svc.set_alarm(23, 59, label="밤알람")
    assert result["type"] == "alarm_set"
    assert result["label"] == "밤알람"
    assert len(svc.alarms) == 1


def test_check_alarms_triggered():
    svc = InfoServices()
    svc.set_alarm(0, 0)
    # force alarm time to past
    svc.alarms[0]["time"] = datetime(2020, 1, 1)
    triggered = svc.check_alarms()
    assert len(triggered) == 1
    assert len(svc.alarms) == 0


def test_get_active_timers_and_alarms():
    svc = InfoServices()
    svc.set_timer(300)
    svc.set_alarm(12, 0)
    assert svc.get_active_timers()["type"] == "timers"
    assert svc.get_active_alarms()["type"] == "alarms"


def test_cancel_all_timers_and_alarms():
    svc = InfoServices()
    svc.set_timer(60)
    svc.set_timer(120)
    result = svc.cancel_all_timers()
    assert result["count"] == 2
    assert len(svc.timers) == 0

    svc.set_alarm(8, 0)
    result = svc.cancel_all_alarms()
    assert result["count"] == 1
    assert len(svc.alarms) == 0


def test_get_weather_returns_none_without_key():
    svc = InfoServices()
    assert svc.get_weather() is None


def test_process_info_request_time():
    svc = InfoServices()
    result = svc.process_info_request("지금 몇 시야?")
    assert result is not None and result["type"] == "time"


def test_process_info_request_date():
    svc = InfoServices()
    result = svc.process_info_request("오늘 며칠이야?")
    assert result is not None and result["type"] == "date"


def test_process_info_request_weekday():
    svc = InfoServices()
    result = svc.process_info_request("무슨 요일이야?")
    assert result is not None and result["type"] == "weekday"


def test_process_info_request_timer_set():
    svc = InfoServices()
    result = svc.process_info_request("타이머 5분 설정해줘")
    assert result is not None and result["type"] == "timer_set"
    assert result["duration_sec"] == 300


def test_process_info_request_timer_no_duration():
    svc = InfoServices()
    result = svc.process_info_request("타이머 설정해줘")
    assert result is not None and result["type"] == "timer_error"


def test_process_info_request_timer_check():
    svc = InfoServices()
    svc.set_timer(60)
    result = svc.process_info_request("타이머 얼마나 남았어?")
    assert result is not None and result["type"] == "timers"


def test_process_info_request_timer_cancel():
    svc = InfoServices()
    svc.set_timer(60)
    result = svc.process_info_request("타이머 취소해줘")
    assert result is not None and result["type"] == "timers_cancelled"


def test_process_info_request_unrecognized():
    svc = InfoServices()
    result = svc.process_info_request("안녕하세요")
    assert result is None
