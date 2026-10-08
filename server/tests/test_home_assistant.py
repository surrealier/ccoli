import threading
import traceback

import pytest
import requests

from src.integrations.home_assistant import HomeAssistantIntegration


SECRET = "test-private-token"


class Response:
    def __init__(self, payload=None, status=200):
        self.status_code = status
        self.payload = payload

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class Session:
    def __init__(self):
        self.calls = []
        self.responses = []
        self.responses_by_url = {}

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = self.responses_by_url.get(url) if url in self.responses_by_url else self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@pytest.fixture
def session(monkeypatch):
    session = Session()
    monkeypatch.setattr(requests, "Session", lambda: session)
    return session


def integration(**kwargs):
    return HomeAssistantIntegration(
        kwargs.get("base_url", "http://home.local:8123/"),
        kwargs.get("token", SECRET),
        kwargs.get("allowed_entities", ["light.study", "switch.fan"]),
    )


def state(entity_id="light.study", value="on"):
    return {"entity_id": entity_id, "state": value, "attributes": {"friendly_name": "Study"}}


def test_missing_configuration_is_inactive(session):
    for kwargs in ({"base_url": ""}, {"token": ""}, {"allowed_entities": []}):
        home = integration(**kwargs)
        assert not home.is_configured()
        assert home.states() == []
        with pytest.raises(RuntimeError):
            home.control("light.study", "turn_on")
    assert session.calls == []


@pytest.mark.parametrize("url", [
    "ftp://home.local", "http:///missing", "http://user:pass@home.local",
    "http://home.local?token=x", "http://home.local#fragment", "http://home.local/api",
    "http://home.local:bad", "http://home.local\\evil", "http://home.local\n",
])
def test_invalid_urls_are_rejected(url):
    with pytest.raises(ValueError):
        integration(base_url=url)


@pytest.mark.parametrize("entities", [
    ["light.*"], ["light.study/../../"], ["lock.front"], ["all"],
    ["light.study?x=y"], [None], "light.study",
])
def test_invalid_allowlists_are_rejected(entities):
    with pytest.raises(ValueError):
        integration(allowed_entities=entities)


def test_states_queries_only_allowlisted_entities_and_limits_fields(session):
    session.responses_by_url = {
        'http://home.local:8123/api/states/light.study': Response(state()),
        'http://home.local:8123/api/states/switch.fan': Response(state("switch.fan", "off")),
    }
    result = integration().states()
    assert result == [
        {"entity_id": "light.study", "state": "on", "name": "Study"},
        {"entity_id": "switch.fan", "state": "off", "name": "Study"},
    ]
    assert sorted(call[1] for call in session.calls) == sorted(session.responses_by_url)
    for method, url, options in session.calls:
        assert method == "GET"
        assert SECRET not in url
        assert options["headers"]["Authorization"] == f"Bearer {SECRET}"
        assert options["timeout"] == 5
        assert options["allow_redirects"] is False

@pytest.mark.parametrize("entity,action,value", [
    ("light.study", "turn_on", "on"), ("switch.fan", "turn_off", "off"),
])
def test_control_verifies_state_after_service_call(session, entity, action, value):
    session.responses = [Response([]), Response(state(entity, value))]
    result = integration().control(entity, action)
    assert result["confirmed"] is True
    assert result["state"] == value
    assert result["entity_id"] == entity
    method, url, options = session.calls[0]
    assert method == "POST"
    assert url == f"http://home.local:8123/api/services/{entity.split('.')[0]}/{action}"
    assert options["json"] == {"entity_id": entity}
    assert options["timeout"] == 5
    assert options["allow_redirects"] is False
    assert session.calls[1][0] == "GET"


@pytest.mark.parametrize("entity,action", [
    ("light.other", "turn_on"), ("lock.front", "unlock"),
    ("light.study", "toggle"), ("light.study", "turn_on/../unlock"),
    (None, "turn_on"), ("light.study", None),
])
def test_disallowed_controls_never_send_http(session, entity, action):
    with pytest.raises(ValueError):
        integration().control(entity, action)
    assert session.calls == []


@pytest.mark.parametrize("response", [
    Response(status=401), Response(status=500), Response(status=302),
    Response(ValueError(SECRET)), requests.Timeout(SECRET),
    Response([]), Response({}), Response(state("light.other")),
    Response({"entity_id": "light.study", "state": None}),
])
def test_state_failures_are_safe_and_do_not_expose_exceptions(session, response):
    session.responses = [response]
    with pytest.raises(RuntimeError) as error:
        integration(allowed_entities=["light.study"]).states()
    assert SECRET not in "".join(traceback.format_exception(error.type, error.value, error.tb))


@pytest.mark.parametrize("value", ["off", "unknown", "unavailable"])
def test_unconfirmed_control_is_not_reported_as_success(session, value):
    session.responses = [Response([]), Response(state(value=value))]
    with pytest.raises(RuntimeError, match="확인"):
        integration().control("light.study", "turn_on")


def test_failed_service_call_does_not_poll_or_retry(session):
    session.responses = [Response(status=401)]
    with pytest.raises(RuntimeError):
        integration().control("light.study", "turn_on")
    assert len(session.calls) == 1


@pytest.mark.parametrize("response", [
    Response(status=307), requests.ConnectionError(SECRET), Response(ValueError(SECRET)),
])
def test_service_failures_are_sanitized_without_retry(session, response):
    session.responses = [response]
    with pytest.raises(RuntimeError) as error:
        integration().control("light.study", "turn_on")
    assert SECRET not in "".join(traceback.format_exception(error.type, error.value, error.tb))
    assert len(session.calls) == 1


def test_allowlist_is_copied_and_implicit_auth_is_disabled(session):
    entities = ["light.study"]
    home = integration(allowed_entities=entities, base_url="https://[::1]:8123")
    entities.append("switch.fan")
    session.responses = [Response(state())]
    assert len(home.states()) == 1
    assert session.trust_env is False
    assert session.calls[0][1] == "https://[::1]:8123/api/states/light.study"


@pytest.mark.parametrize("token", [None, "bad\r\ntoken"])
def test_invalid_tokens_are_rejected_without_echoing_them(token):
    with pytest.raises(ValueError):
        integration(token=token)


def test_state_reads_start_concurrently_and_only_for_allowed_ids(monkeypatch):
    barrier = threading.Barrier(2, timeout=2)
    calls = []

    class CoordinatedSession(Session):
        def request(self, method, url, **kwargs):
            calls.append((method, url))
            barrier.wait()
            entity = url.rsplit('/', 1)[-1]
            return Response(state(entity, 'off'))

    monkeypatch.setattr(requests, 'Session', CoordinatedSession)
    result = integration().states()
    assert [item['entity_id'] for item in result] == ['light.study', 'switch.fan']
    assert sorted(calls) == [
        ('GET', 'http://home.local:8123/api/states/light.study'),
        ('GET', 'http://home.local:8123/api/states/switch.fan'),
    ]


def test_one_failed_allowed_state_read_fails_closed(session):
    session.responses_by_url = {
        'http://home.local:8123/api/states/light.study': Response(state()),
        'http://home.local:8123/api/states/switch.fan': requests.Timeout(SECRET),
    }
    with pytest.raises(RuntimeError) as error:
        integration().states()
    assert SECRET not in str(error.value)
    assert len(session.calls) == 2
    assert all(method == 'GET' for method, _, _ in session.calls)