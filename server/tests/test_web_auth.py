"""Web dashboard authentication protects both HTTP and live events."""

import asyncio
import base64
import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from web import app as web_app
from web.auth import configure, token_matches


@pytest.fixture(autouse=True)
def reset_auth_and_clients():
    configure("")
    with web_app._ws_lock:
        web_app._ws_clients.clear()
    yield
    configure("")
    with web_app._ws_lock:
        web_app._ws_clients.clear()


def dashboard_client():
    return TestClient(web_app.create_app(lambda: object(), lambda: None, lambda: "agent"))


async def wait_for_registered_client(expected: int) -> None:
    for _ in range(100):
        with web_app._ws_lock:
            count = len(web_app._ws_clients)
        if count == expected:
            return
        await asyncio.sleep(0.01)
    assert count == expected


def test_http_and_websocket_share_unicode_token_verification():
    configure("한글🔐")
    assert token_matches("한글🔐")
    assert not token_matches("한글🔑")
    assert not token_matches(None)
    assert not token_matches(17)

    with dashboard_client() as client:
        with client.websocket_connect("/ws") as socket:
            socket.send_json({"event": "authenticate", "token": "한글🔐"})
            client.portal.call(wait_for_registered_client, 1)
            client.portal.call(web_app.broadcast, {"event": "chat_response", "text": "private"})
            assert socket.receive_json() == {"event": "chat_response", "text": "private"}


def test_http_requires_configured_token():
    configure("test-only-token")
    with dashboard_client() as client:
        assert client.get("/api/agent/").status_code == 401
        assert client.get("/api/agent/", headers={"X-Auth-Token": "wrong"}).status_code == 401
        assert client.get("/api/agent/", headers={"X-Auth-Token": "test-only-token"}).status_code == 200


def test_http_accepts_explicit_utf8_base64url_unicode_token():
    token = "한글🔐"
    configure(token)
    encoded = base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii").rstrip("=")
    with dashboard_client() as client:
        response = client.get("/api/agent/", headers={
            "X-Auth-Token": encoded,
            "X-Auth-Token-Encoding": "utf8-base64url",
        })
        assert response.status_code == 200
        assert client.get("/api/agent/", headers={"X-Auth-Token": encoded}).status_code == 401


@pytest.mark.parametrize("token,encoding", [
    ("expected-token", "unknown"),
    ("expected-token", ""),
    ("%%%", "utf8-base64url"),
    ("_w", "utf8-base64url"),  # valid base64url, invalid UTF-8
    ("Zg=", "utf8-base64url"),  # non-canonical padding
])
def test_http_rejects_unknown_or_invalid_token_encodings(token, encoding):
    configure("expected-token")
    with dashboard_client() as client:
        response = client.get("/api/agent/", headers={
            "X-Auth-Token": token,
            "X-Auth-Token-Encoding": encoding,
        })
        assert response.status_code == 401


def test_lone_surrogate_token_is_rejected_and_websocket_closes():
    configure("expected-token")
    assert not token_matches("\ud800")
    with dashboard_client() as client:
        with client.websocket_connect("/ws") as socket:
            socket.send_text(json.dumps({"event": "authenticate", "token": "\ud800"}))
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_text()
            assert error.value.code == 4401
            client.portal.call(wait_for_registered_client, 0)


def test_unauthenticated_socket_never_receives_private_broadcast():
    configure("expected-token")
    with dashboard_client() as client:
        with client.websocket_connect("/ws") as socket:
            client.portal.call(wait_for_registered_client, 0)
            client.portal.call(web_app.broadcast, {"event": "chat_response", "text": "private"})
            socket.send_json({"event": "authenticate", "token": "wrong-token"})
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_json()
            assert error.value.code == 4401
            client.portal.call(wait_for_registered_client, 0)


@pytest.mark.parametrize("first_frame", [
    "",
    "ping",
    "{}",
    '{"event":"authenticate"}',
    '{"event":"authenticate","token":12}',
    '{"event":"authenticate","token":"wrong"}',
])
def test_invalid_first_frame_closes_without_registration(first_frame):
    configure("expected-token")
    with dashboard_client() as client:
        with client.websocket_connect("/ws") as socket:
            socket.send_text(first_frame)
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_text()
            assert error.value.code == 4401
            client.portal.call(wait_for_registered_client, 0)


def test_oversized_valid_authentication_frame_is_rejected():
    configure("x" * 4096)
    with dashboard_client() as client:
        with client.websocket_connect("/ws") as socket:
            socket.send_json({"event": "authenticate", "token": "x" * 4096})
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_text()
            assert error.value.code == 4401
            client.portal.call(wait_for_registered_client, 0)


def test_authentication_timeout_closes_without_registration(monkeypatch):
    configure("expected-token")
    monkeypatch.setattr(web_app, "WS_AUTH_TIMEOUT_SECONDS", 0.02)
    with dashboard_client() as client:
        with client.websocket_connect("/ws") as socket:
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_text()
            assert error.value.code == 4401
            client.portal.call(wait_for_registered_client, 0)


def test_legacy_socket_without_configured_token_receives_broadcast():
    with dashboard_client() as client:
        with client.websocket_connect("/ws") as socket:
            client.portal.call(wait_for_registered_client, 1)
            client.portal.call(web_app.broadcast, {"event": "status_update", "mode": "agent"})
            assert socket.receive_json() == {"event": "status_update", "mode": "agent"}
