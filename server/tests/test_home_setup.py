from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.integrations.home_assistant import HomeAssistantIntegration
from src.integrations.home_assistant_setup import HomeAssistantSetupService, HomeSetupError
from web.routes import api_home_setup

TOKEN = "home-test-private-token"
BASE = "http://192.0.2.10:18766"
STATES = [
    {"entity_id": "light.desk", "state": "on", "attributes": {"friendly_name": "책상", "secret": TOKEN}},
    {"entity_id": "switch.fan", "state": "off", "attributes": {}},
    {"entity_id": "sensor.private", "state": TOKEN, "attributes": {"friendly_name": TOKEN}},
]


class Reply:
    def __init__(self, data: object, status: int = 200, raw: bytes | None = None) -> None:
        self.status_code = status
        self.raw = raw if raw is not None else json.dumps(data).encode()
        self.headers = {"Content-Length": str(len(self.raw))}
        self.closed = False

    def iter_content(self, chunk_size: int):
        for start in range(0, len(self.raw), chunk_size):
            yield self.raw[start:start + chunk_size]

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def network(monkeypatch):
    session = Mock()
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock(return_value=False)
    session.request.side_effect = [Reply({"message": "API running."}), Reply(STATES)]
    monkeypatch.setattr("src.integrations.home_assistant_setup.requests.Session", Mock(return_value=session))
    # Unit tests inspect fixed HTTP endpoints inline. Separate tests below run
    # the real fixed subprocess and verify its hard deadline/cancellation.
    from src.integrations import home_assistant_setup as setup
    monkeypatch.setattr(setup, "_discover_bounded", lambda base, token, **kwargs: setup._discover_http(base, token))
    return session


def create(tmp_path: Path):
    applied: list[HomeAssistantIntegration | None] = []
    path = tmp_path / "private" / "home.json"
    return HomeAssistantSetupService(path, applied.append), applied, path


def test_default_truthful_status_and_actual_links(tmp_path):
    service, applied, path = create(tmp_path)
    result = service.status()
    assert result["state"] == "unconfigured"
    assert result["base_url"] == "" and not result["verified"] and not result["active"]
    assert not result["token_present"] and result["candidates"] == []
    assert result["links"]["login"] is None
    assert "installation/windows" in result["links"]["installation"]
    assert not path.exists() and applied == []


def test_connect_fixed_endpoints_then_explicit_selection(tmp_path, network):
    service, applied, path = create(tmp_path)
    result = service.connect(BASE + "/", TOKEN)
    assert result["verified"] and not result["active"] and result["token_present"]
    assert result["allowed_entities"] == []
    assert result["candidates"] == [
        {"entity_id": "light.desk", "name": "책상", "state": "on"},
        {"entity_id": "switch.fan", "name": "switch.fan", "state": "off"},
    ]
    assert TOKEN not in json.dumps(result)
    assert result["links"]["token"] == BASE + "/profile/security"
    assert result["links"]["devices"] == BASE + "/config/integrations"
    assert network.trust_env is False
    calls = network.request.call_args_list
    assert [call.args[:2] for call in calls] == [("GET", BASE + "/api/"), ("GET", BASE + "/api/states")]
    assert all(call.kwargs["allow_redirects"] is False and call.kwargs["stream"] is True for call in calls)
    assert json.loads(path.read_text())["token"] == TOKEN
    result = service.select(["light.desk"])
    assert result["active"] and result["allowed_entities"] == ["light.desk"]
    assert applied[-1].is_configured() and applied[-1].allowed_entities == ("light.desk",)
    with pytest.raises(HomeSetupError, match="selection_invalid"):
        service.select(["switch.unknown"])
    with pytest.raises(HomeSetupError, match="selection_invalid"):
        service.select(["light.desk", "light.desk"])
    assert service.select([])["active"] is False and applied[-1] is None


def test_restart_restores_client_but_not_verified_candidates(tmp_path, network):
    service, _, path = create(tmp_path)
    service.connect(BASE, TOKEN)
    service.select(["switch.fan"])
    applied = []
    restored = HomeAssistantSetupService(path, applied.append)
    result = restored.status()
    assert result["active"] and not result["verified"] and result["candidates"] == []
    assert result["state"] == "unverified" and applied[-1].allowed_entities == ("switch.fan",)
    with pytest.raises(HomeSetupError, match="verification_required"):
        restored.select(["switch.fan"])
    network.request.side_effect = [Reply({"message": "API running."}), Reply(STATES)]
    assert restored.connect(BASE)["active"]
    restored.disconnect()
    assert not restored.status()["token_present"] and applied[-1] is None
    assert json.loads(path.read_text())["token"] == ""


@pytest.mark.parametrize("address", ["https://user:pass@example.com", "http://example.com/path", "http://example.com?secret", "file:///tmp", "http://example.com\\secret", "http://example.com:bad"])
def test_invalid_url_never_contacts_network(tmp_path, network, address):
    service, _, _ = create(tmp_path)
    with pytest.raises(HomeSetupError, match="invalid_url"):
        service.connect(address, TOKEN)
    network.request.assert_not_called()


@pytest.mark.parametrize("reply,code", [
    (Reply({}, 302), "redirect_rejected"), (Reply({}, 401), "authentication_failed"),
    (Reply({"message": "Other API"}), "not_home_assistant"),
    (Reply({}, raw=b"x" * (2 * 1024 * 1024 + 1)), "response_too_large"),
    (Reply({}, raw=b"not-json"), "invalid_response"),
])
def test_network_failure_sanitized_and_no_store_commit(tmp_path, network, reply, code):
    service, applied, path = create(tmp_path)
    network.request.side_effect = [reply]
    with pytest.raises(HomeSetupError) as caught:
        service.connect(BASE, TOKEN)
    assert caught.value.code == code and TOKEN not in str(caught.value)
    assert not path.exists() and applied == [] and not service.status()["pending"]


def test_request_exception_never_echoes_token(tmp_path, network):
    service, _, _ = create(tmp_path)
    network.request.side_effect = requests.RequestException(TOKEN)
    with pytest.raises(HomeSetupError) as caught:
        service.connect(BASE, TOKEN)
    assert caught.value.code == "connection_failed" and TOKEN not in str(caught.value)


def test_disconnect_invalidates_slow_connect(tmp_path, network):
    service, applied, _ = create(tmp_path)
    entered, release = threading.Event(), threading.Event()
    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return Reply({"message": "API running."} if args[1].endswith("/api/") else STATES)
    network.request.side_effect = slow
    errors = []
    def connect():
        try:
            service.connect(BASE, TOKEN)
        except HomeSetupError as error:
            errors.append(error.code)
    worker = threading.Thread(target=connect)
    worker.start()
    assert entered.wait(3) and service.status()["pending"]
    service.disconnect()
    release.set()
    worker.join(3)
    assert not worker.is_alive() and errors == ["operation_superseded"]
    assert not service.status()["token_present"] and applied[-1] is None


def test_persistence_failure_restores_runtime_client(tmp_path, network, monkeypatch):
    service, applied, _ = create(tmp_path)
    service.connect(BASE, TOKEN)
    previous = service.status()
    monkeypatch.setattr(service, "_write_settings", Mock(side_effect=OSError(TOKEN)))
    with pytest.raises(HomeSetupError) as caught:
        service.select(["light.desk"])
    assert caught.value.code == "storage_failed" and TOKEN not in str(caught.value)
    assert service.status()["allowed_entities"] == previous["allowed_entities"]
    assert applied[-1] is None


def test_invalid_or_symlink_store_not_activated(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps({"v": 1, "base_url": BASE, "token": TOKEN, "allowed_entities": ["script.private"]}))
    applied = []
    service = HomeAssistantSetupService(path, applied.append)
    assert not service.status()["active"] and not service.status()["token_present"] and applied == []
    target = tmp_path / "link.json"
    target.symlink_to(path)
    service = HomeAssistantSetupService(target, applied.append)
    assert not service.status()["token_present"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    service, _, _ = create(tmp_path)
    monkeypatch.setattr(api_home_setup, "get_agent", lambda: SimpleNamespace(home_setup_service=service))
    app = FastAPI()
    app.include_router(api_home_setup.router)
    from web.auth import require_auth
    app.dependency_overrides[require_auth] = lambda: None
    return TestClient(app), service, app


def test_routes_status_connect_select_disconnect(client, network):
    browser, service, _ = client
    assert browser.get("/api/home-setup/status").status_code == 200
    assert browser.get("/api/home-setup").status_code == 200
    result = browser.post("/api/home-setup/connect", json={"base_url": BASE, "token": TOKEN})
    assert result.status_code == 200 and TOKEN not in result.text
    assert browser.post("/api/home-setup/selection", json={"allowed_entities": ["light.desk"]}).json()["active"]
    assert browser.post("/api/home-setup/disconnect", json={}).json()["state"] == "unconfigured"


@pytest.mark.parametrize("body", [
    '{"base_url":"http://example.com","token":{"secret":"'+TOKEN+'"}}',
    '{"base_url":"http://example.com","token":"'+TOKEN+'","token":"duplicate"}',
    '{"base_url":"http://example.com","token":"'+TOKEN+'","unknown":true}',
    '{"base_url":"http://example.com","token":"'+TOKEN+'",',
    '{"token":"'+TOKEN+'"}',
    '{"base_url":"http://example.com","token":"'+("x"*17000)+'"}',
])
def test_route_invalid_body_never_returns_secret(client, body):
    browser, _, _ = client
    response = browser.post("/api/home-setup/connect", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code in {400, 413}
    assert TOKEN not in response.text and '"input"' not in response.text


def test_routes_require_dashboard_auth(client, monkeypatch):
    browser, _, app = client
    app.dependency_overrides.clear()
    from fastapi import HTTPException
    def deny():
        raise HTTPException(status_code=401, detail="Sign in")
    from web.auth import require_auth
    app.dependency_overrides[require_auth] = deny
    assert browser.get("/api/home-setup").status_code == 401

def test_all_bounded_candidate_ids_persist_and_reload(tmp_path, network):
    # The store must accommodate the maximum valid selection, not just a few
    # short IDs. This is an internal service boundary; HTTP retains its16KiB cap.
    items = [{"entity_id": "light." + str(index) + "_" + "x" * 240,
              "state": "off", "attributes": {}} for index in range(256)]
    network.request.side_effect = [Reply({"message": "API running."}), Reply(items)]
    service, _, path = create(tmp_path)
    service.connect(BASE, TOKEN)
    selected = [item["entity_id"] for item in items]
    assert service.select(selected)["active"]
    restored = HomeAssistantSetupService(path, lambda _: None)
    assert restored.status()["active"]
    assert restored.status()["allowed_entities"] == sorted(selected)


def test_activation_failure_restores_old_client_and_store(tmp_path, network):
    service, _, path = create(tmp_path)
    service.connect(BASE, TOKEN)
    previous = path.read_bytes()
    def failed(client):
        if client is not None:
            raise RuntimeError(TOKEN)
    service._apply_home = failed
    with pytest.raises(HomeSetupError) as caught:
        service.select(["light.desk"])
    assert caught.value.code == "activation_failed" and TOKEN not in str(caught.value)
    assert path.read_bytes() == previous and not service.status()["active"]


def test_other_origin_never_reuses_existing_token(tmp_path, network):
    service, _, _ = create(tmp_path)
    service.connect(BASE, TOKEN)
    network.request.reset_mock()
    with pytest.raises(HomeSetupError, match="invalid_token"):
        service.connect("http://192.0.2.11:18766")
    network.request.assert_not_called()

def test_discovery_total_deadline_includes_trickled_headers_and_reaps_worker(monkeypatch):
    import subprocess
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from src.integrations import home_assistant_setup as setup

    entered = threading.Event()
    class SlowHeaders(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            entered.set()
            try:
                self.wfile.write(b"HTTP/1.1 200 OK\r\n")
                for _ in range(200):
                    self.wfile.write(b"X-Public-Fixture: value\r\n")
                    self.wfile.flush()
                    time.sleep(.05)
            except (BrokenPipeError, ConnectionResetError):
                pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), SlowHeaders)
    server.daemon_threads = True
    listener = threading.Thread(target=server.serve_forever, daemon=True)
    listener.start()
    launched = []
    original = subprocess.Popen
    def launch(args, **kwargs):
        assert TOKEN not in str(args) and "env" not in kwargs
        assert kwargs["stderr"] == subprocess.DEVNULL and kwargs["shell"] is False
        child = original(args, **kwargs)
        launched.append(child)
        return child
    monkeypatch.setattr(setup.subprocess, "Popen", launch)
    started = time.monotonic()
    try:
        with pytest.raises(HomeSetupError, match="connection_failed"):
            setup._discover_bounded(f"http://127.0.0.1:{server.server_port}", TOKEN, timeout_s=1)
        assert entered.is_set()
        assert time.monotonic() - started < 1.7
        assert launched and launched[-1].poll() is not None
    finally:
        server.shutdown()
        server.server_close()


def test_discovery_disconnect_cancels_and_reaps_pending_process(monkeypatch):
    import subprocess
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from src.integrations import home_assistant_setup as setup
    entered = threading.Event()
    class BlockedResponse(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            entered.set()
            time.sleep(3)
    server = ThreadingHTTPServer(("127.0.0.1", 0), BlockedResponse)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    children = []
    original = subprocess.Popen
    def launch(*args, **kwargs):
        child = original(*args, **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(setup.subprocess, "Popen", launch)
    started = time.monotonic()
    try:
        with pytest.raises(HomeSetupError, match="operation_superseded"):
            setup._discover_bounded(f"http://127.0.0.1:{server.server_port}", TOKEN,
                                    is_cancelled=entered.is_set, timeout_s=5)
        assert time.monotonic() - started < 1.5
        assert children and children[-1].poll() is not None
    finally:
        server.shutdown()
        server.server_close()