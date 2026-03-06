"""Tests for scheduler.Scheduler class."""
import json
from datetime import datetime, timedelta

from scheduler import Scheduler


def _make_scheduler(tmp_path):
    return Scheduler(schedule_file=str(tmp_path / "schedules.json"))


def test_add_schedule_and_persist(tmp_path):
    s = _make_scheduler(tmp_path)
    dt = datetime.now() + timedelta(hours=1)
    result = s.add_schedule("회의", dt)
    assert "회의" in result
    assert len(s.schedules) == 1

    # verify file written
    data = json.loads((tmp_path / "schedules.json").read_text(encoding="utf-8"))
    assert len(data["schedules"]) == 1


def test_add_schedule_with_reminder(tmp_path):
    s = _make_scheduler(tmp_path)
    dt = datetime.now() + timedelta(hours=1)
    result = s.add_schedule("병원", dt, reminder_before=10)
    assert "10분 전" in result


def test_get_upcoming_schedules(tmp_path):
    s = _make_scheduler(tmp_path)
    s.add_schedule("곧", datetime.now() + timedelta(hours=1))
    s.add_schedule("먼미래", datetime.now() + timedelta(days=30))
    upcoming = s.get_upcoming_schedules(hours=24)
    assert len(upcoming) == 1
    assert upcoming[0]["title"] == "곧"


def test_check_reminders(tmp_path):
    s = _make_scheduler(tmp_path)
    # schedule 5 min from now with 10 min reminder → should trigger now
    dt = datetime.now() + timedelta(minutes=5)
    s.add_schedule("리마인더테스트", dt, reminder_before=10)
    reminders = s.check_reminders()
    assert len(reminders) == 1
    assert reminders[0]["title"] == "리마인더테스트"
    # second call should not re-trigger (reminded=True)
    assert s.check_reminders() == []


def test_complete_schedule(tmp_path):
    s = _make_scheduler(tmp_path)
    s.add_schedule("완료할일", datetime.now() + timedelta(hours=1))
    result = s.complete_schedule(1)
    assert "완료" in result
    assert s.schedules[0]["completed"] is True


def test_complete_schedule_not_found(tmp_path):
    s = _make_scheduler(tmp_path)
    result = s.complete_schedule(999)
    assert "찾을 수 없" in result


def test_delete_schedule(tmp_path):
    s = _make_scheduler(tmp_path)
    s.add_schedule("삭제할일", datetime.now() + timedelta(hours=1))
    result = s.delete_schedule(1)
    assert "삭제" in result
    assert len(s.schedules) == 0


def test_delete_schedule_not_found(tmp_path):
    s = _make_scheduler(tmp_path)
    result = s.delete_schedule(999)
    assert "찾을 수 없" in result


def test_get_today_schedules_empty(tmp_path):
    s = _make_scheduler(tmp_path)
    result = s.get_today_schedules()
    assert "없습니다" in result


def test_get_today_schedules_with_items(tmp_path):
    s = _make_scheduler(tmp_path)
    dt = datetime.now().replace(hour=23, minute=59, second=0, microsecond=0)
    if dt < datetime.now():
        dt += timedelta(days=1)
    s.add_schedule("오늘일정", dt)
    # only shows if schedule date == today
    result = s.get_today_schedules()
    if dt.date() == datetime.now().date():
        assert "오늘일정" in result


def test_parse_and_add_schedule_natural_language(tmp_path):
    s = _make_scheduler(tmp_path)
    result = s.parse_and_add_schedule("내일 오후 3시 회의 있어")
    assert result is not None
    assert len(s.schedules) == 1
    sched_dt = datetime.fromisoformat(s.schedules[0]["datetime"])
    assert sched_dt.hour == 15


def test_parse_and_add_schedule_morning(tmp_path):
    s = _make_scheduler(tmp_path)
    result = s.parse_and_add_schedule("내일 오전 9시 병원 가야해")
    assert result is not None
    sched_dt = datetime.fromisoformat(s.schedules[0]["datetime"])
    assert sched_dt.hour == 9


def test_process_schedule_request_add(tmp_path):
    s = _make_scheduler(tmp_path)
    result = s.process_schedule_request("내일 오후 2시 회의 있어")
    assert result is not None and "등록" in result


def test_process_schedule_request_query_today(tmp_path):
    s = _make_scheduler(tmp_path)
    result = s.process_schedule_request("오늘 일정 뭐 있어?")
    assert result is not None


def test_process_schedule_request_unrecognized(tmp_path):
    s = _make_scheduler(tmp_path)
    result = s.process_schedule_request("안녕하세요")
    assert result is None


def test_load_schedules_from_existing_file(tmp_path):
    path = tmp_path / "schedules.json"
    data = {"schedules": [{"id": 1, "title": "기존", "datetime": (datetime.now() + timedelta(hours=1)).isoformat(), "completed": False, "reminded": False, "reminder_before": 0}]}
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    s = Scheduler(schedule_file=str(path))
    assert len(s.schedules) == 1
    assert s.schedules[0]["title"] == "기존"
