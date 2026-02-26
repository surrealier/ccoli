from src.integrations import (
    GoogleCalendarIntegration,
    MapsIntegration,
    NotifyIntegration,
    SearchIntegration,
)


def test_search_integration_requires_query_and_key():
    s = SearchIntegration(api_key="")
    assert s.execute("search.query", {"query": "날씨"}).ok is False


def test_calendar_integration_basic_actions():
    cal = GoogleCalendarIntegration("id", "secret", "refresh")
    assert cal.execute("calendar.list").ok is True
    assert cal.execute("calendar.create", {"title": "회의"}).ok is True


def test_notify_integration_send_validation():
    n = NotifyIntegration("token")
    assert n.execute("notify.send", {"channel": "", "text": "hi"}).ok is False
    assert n.execute("notify.send", {"channel": "#general", "text": "hi"}).ok is True


def test_maps_integration_validation():
    m = MapsIntegration("key")
    assert m.execute("maps.route", {"origin": "", "destination": "강남"}).ok is False
    res = m.execute("maps.route", {"origin": "서울역", "destination": "강남"})
    assert res.ok is True
    assert "서울역" in res.data["summary"]
