"""Verified Home Assistant onboarding with private explicit device selection."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

import requests

from .home_assistant import HomeAssistantIntegration

MAX_RESPONSE = 2 * 1024 * 1024
MAX_STORE = 128 * 1024
MAX_CANDIDATES = 256
ENTITY = re.compile(r"(?:light|switch)\.[a-z0-9_]{1,248}\Z")
MESSAGES = {
    "invalid_url": "Home Assistant에서 열리는 실제 http(s) 주소를 입력해 주세요.",
    "invalid_token": "프로필 보안 메뉴에서 만든 액세스 토큰을 확인해 주세요.",
    "authentication_failed": "액세스 토큰을 새로 확인하고 다시 연결해 주세요.",
    "redirect_rejected": "Home Assistant의 최종 주소를 입력해 주세요.",
    "connection_failed": "Home Assistant가 켜져 있는지와 주소·네트워크를 확인해 주세요.",
    "not_home_assistant": "Home Assistant 로그인 화면의 주소를 입력해 주세요.",
    "invalid_response": "Home Assistant의 API 응답을 확인하고 다시 연결해 주세요.",
    "response_too_large": "기기 수나 API 응답 크기를 확인하고 다시 연결해 주세요.",
    "verification_required": "먼저 연결 확인을 눌러 기기 목록을 불러와 주세요.",
    "selection_invalid": "목록에서 제어를 허용할 light/switch 기기를 선택해 주세요.",
    "operation_superseded": "설정이 변경되었습니다. 현재 연결 상태를 확인해 주세요.",
    "storage_failed": "비공개 설정 폴더의 쓰기 권한을 확인하고 다시 저장해 주세요.",
    "activation_failed": "홈 도구를 업데이트하지 못했습니다. 다시 저장해 주세요.",
    "storage_invalid": "저장된 홈 설정을 읽지 못했습니다. 주소와 토큰을 다시 연결해 주세요.",
}


class HomeSetupError(RuntimeError):
    """Stable code and safe guidance without external exception text."""
    def __init__(self, code: str) -> None:
        self.code = code
        self.message = MESSAGES[code]
        super().__init__(code)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise ValueError("nonfinite number")


def _token(value: Any) -> str:
    if not isinstance(value, str):
        raise HomeSetupError("invalid_token")
    value = value.strip()
    if not value or len(value) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise HomeSetupError("invalid_token")
    return value


def _entities(value: Any) -> list[str]:
    if (not isinstance(value, list) or len(value) > MAX_CANDIDATES
            or any(not isinstance(item, str) or not ENTITY.fullmatch(item) for item in value)
            or len(set(value)) != len(value)):
        raise HomeSetupError("selection_invalid")
    return sorted(value)


MAX_WORKER_REPLY = 256 * 1024


def _discover_http(base: str, token: str, timeout_s: float = 10) -> list[dict[str, str]]:
    deadline = time.monotonic() + timeout_s
    with requests.Session() as session:
        session.trust_env = False
        marker = HomeAssistantSetupService._fetch(session, base, "/api/", token, deadline)
        if not isinstance(marker, dict) or marker.get("message") != "API running.":
            raise HomeSetupError("not_home_assistant")
        return HomeAssistantSetupService._candidate_metadata(
            HomeAssistantSetupService._fetch(session, base, "/api/states", token, deadline), token)


def _discover_bounded(base: str, token: str, *, timeout_s: float = 10,
                      is_cancelled: Callable[[], bool] = lambda: False) -> list[dict[str, str]]:
    """Kill/reap the fixed helper to bound DNS and trickled headers as well as body IO."""
    deadline = time.monotonic() + timeout_s
    if is_cancelled():
        raise HomeSetupError("operation_superseded")
    process = None
    workers: list[threading.Thread] = []
    reply: list[bytes | None] = []
    received = threading.Event()
    failed = threading.Event()
    payload = (json.dumps({"base_url": base, "token": token, "timeout_s": timeout_s},
                          allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")
    try:
        # Fixed module avoids multiprocessing spawn reexecuting a user's voice
        # launcher. Secrets are sent through stdin, never argv or environment.
        process = subprocess.Popen(
            [sys.executable, "-u", "-m", "src.integrations.home_assistant_setup", "--discovery-worker"],
            cwd=str(Path(__file__).resolve().parents[2]), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
        def write() -> None:
            try:
                process.stdin.write(payload)
                process.stdin.flush()
            except Exception:
                failed.set()
        def read() -> None:
            try:
                reply.append(process.stdout.readline(MAX_WORKER_REPLY + 1))
            except Exception:
                reply.append(None)
            finally:
                received.set()
        workers = [threading.Thread(target=write, daemon=True, name="home-setup-input"),
                   threading.Thread(target=read, daemon=True, name="home-setup-output")]
        for worker in workers:
            worker.start()
        while True:
            if is_cancelled():
                raise HomeSetupError("operation_superseded")
            remaining = deadline - time.monotonic()
            if remaining <= 0 or failed.is_set():
                raise HomeSetupError("connection_failed")
            if received.wait(min(.05, remaining)):
                break
        content = reply[0] if reply else None
        if not content or len(content) > MAX_WORKER_REPLY or not content.endswith(b"\n"):
            raise HomeSetupError("invalid_response")
        value = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
        if not isinstance(value, dict):
            raise HomeSetupError("invalid_response")
        if set(value) == {"error"} and isinstance(value["error"], str) and value["error"] in MESSAGES:
            raise HomeSetupError(value["error"])
        if set(value) != {"candidates"}:
            raise HomeSetupError("invalid_response")
        data = value["candidates"]
        if (not isinstance(data, list) or len(data) > MAX_CANDIDATES
                or any(not isinstance(item, dict) or set(item) != {"entity_id", "name", "state"}
                       or not isinstance(item["entity_id"], str) or not ENTITY.fullmatch(item["entity_id"])
                       or not isinstance(item["name"], str) or len(item["name"]) > 128
                       or item["state"] not in {"on", "off", "unknown", "unavailable"} for item in data)):
            raise HomeSetupError("invalid_response")
        return data
    except HomeSetupError:
        raise
    except Exception:
        raise HomeSetupError("connection_failed") from None
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=.2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=.2)
            for worker in workers:
                worker.join(timeout=.2)
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    stream.close()


class HomeAssistantSetupService:
    def __init__(self, secret_path: str | Path,
                 apply_home: Callable[[HomeAssistantIntegration | None], None],
                 initial_home: HomeAssistantIntegration | None = None) -> None:
        self._path = Path(secret_path).absolute()
        self._apply_home = apply_home
        self._lock = threading.RLock()
        self._generation = 0
        self._pending = False
        self._verified = False
        self._candidates: list[dict[str, str]] = []
        self._error_code: str | None = None
        self._home = initial_home if initial_home and initial_home.is_configured() else None
        self._settings: dict[str, Any] = self._empty_settings()
        if initial_home and initial_home.base_url and initial_home._token:
            self._settings = {"v": 1, "base_url": initial_home.base_url,
                              "token": initial_home._token,
                              "allowed_entities": list(initial_home.allowed_entities)}
        self._load_settings()

    @staticmethod
    def _empty_settings() -> dict[str, Any]:
        return {"v": 1, "base_url": "", "token": "", "allowed_entities": []}

    def _check_path(self) -> None:
        if any(path.is_symlink() for path in (self._path, *self._path.parents)):
            raise HomeSetupError("storage_failed")
        if self._path.exists() and not self._path.is_file():
            raise HomeSetupError("storage_failed")

    def _load_settings(self) -> None:
        try:
            self._check_path()
            if not self._path.exists():
                return
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            with os.fdopen(os.open(self._path, flags), "rb") as stream:
                content = stream.read(MAX_STORE + 1)
            if len(content) > MAX_STORE:
                raise ValueError("store bound")
            data = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object,
                              parse_constant=_reject_constant)
            if (not isinstance(data, dict) or set(data) != {"v", "base_url", "token", "allowed_entities"}
                    or type(data["v"]) is not int or data["v"] != 1):
                raise ValueError("store schema")
            base = self._url(data["base_url"], allow_empty=True)
            selected = _entities(data["allowed_entities"])
            if not base:
                if data["token"] != "" or selected:
                    raise ValueError("empty store")
                token = ""
            else:
                token = _token(data["token"])
            client = HomeAssistantIntegration(base, token, selected) if selected else None
            self._apply_home(client)
            self._settings = {"v": 1, "base_url": base, "token": token, "allowed_entities": selected}
            self._home = client
        except (OSError, ValueError, TypeError, RecursionError, HomeSetupError, RuntimeError):
            self._error_code = "storage_invalid"

    @staticmethod
    def _url(value: Any, *, allow_empty: bool = False) -> str:
        if not isinstance(value, str) or len(value) > 2048:
            raise HomeSetupError("invalid_url")
        try:
            base = HomeAssistantIntegration._validate_url(value)
        except ValueError:
            raise HomeSetupError("invalid_url") from None
        if not base and not allow_empty:
            raise HomeSetupError("invalid_url")
        return base

    def _write_settings(self, settings: dict[str, Any]) -> None:
        encoded = json.dumps(settings, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_STORE:
            raise HomeSetupError("storage_failed")
        self._check_path()
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._check_path()
        fd, temporary = tempfile.mkstemp(prefix=".home-setup-", dir=self._path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                os.chmod(temporary, 0o600)
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            self._check_path()
            os.replace(temporary, self._path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def _commit(self, settings: dict[str, Any], client: HomeAssistantIntegration | None) -> None:
        previous = self._home
        try:
            self._apply_home(client)
        except Exception:
            try:
                self._apply_home(previous)
            except Exception:
                pass
            raise HomeSetupError("activation_failed") from None
        try:
            self._write_settings(settings)
        except (OSError, ValueError, HomeSetupError):
            try:
                self._apply_home(previous)
            except Exception:
                raise HomeSetupError("activation_failed") from None
            raise HomeSetupError("storage_failed") from None
        self._settings = settings
        self._home = client
        self._error_code = None

    @staticmethod
    def _fetch(session: requests.Session, base: str, path: str, token: str, deadline: float) -> Any:
        response = None
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HomeSetupError("connection_failed")
            response = session.request(
                "GET", base + path, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=min(5.0, remaining), allow_redirects=False, stream=True)
            if 300 <= response.status_code < 400:
                raise HomeSetupError("redirect_rejected")
            if response.status_code in {401, 403}:
                raise HomeSetupError("authentication_failed")
            if not 200 <= response.status_code < 300:
                raise HomeSetupError("connection_failed")
            length = response.headers.get("Content-Length", "")
            if len(length) > 20 or (length.isdecimal() and int(length) > MAX_RESPONSE):
                raise HomeSetupError("response_too_large")
            body = bytearray()
            # Per-byte decode also checks slow trickle peers: requests read timeout
            # resets on socket reads and alone is not a total elapsed-time limit.
            for chunk in response.iter_content(chunk_size=1):
                if time.monotonic() >= deadline:
                    raise HomeSetupError("connection_failed")
                body.extend(chunk)
                if len(body) > MAX_RESPONSE:
                    raise HomeSetupError("response_too_large")
            try:
                return json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object,
                                  parse_constant=_reject_constant)
            except (ValueError, UnicodeError, RecursionError):
                raise HomeSetupError("invalid_response") from None
        except requests.RequestException:
            raise HomeSetupError("connection_failed") from None
        finally:
            if response is not None:
                response.close()

    @staticmethod
    def _candidate_metadata(data: Any, token: str) -> list[dict[str, str]]:
        if not isinstance(data, list):
            raise HomeSetupError("invalid_response")
        if len(data) > 2000:
            raise HomeSetupError("response_too_large")
        candidates: dict[str, dict[str, str]] = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            entity = item.get("entity_id")
            if not isinstance(entity, str) or not ENTITY.fullmatch(entity):
                continue
            if entity in candidates:
                raise HomeSetupError("invalid_response")
            attributes = item.get("attributes", {})
            name = attributes.get("friendly_name", entity) if isinstance(attributes, dict) else entity
            if not isinstance(name, str) or token in name:
                name = entity
            name = "".join(c for c in name if ord(c) >= 32).strip()[:128] or entity
            state = item.get("state")
            if not isinstance(state, str) or state not in {"on", "off", "unknown", "unavailable"}:
                state = "unknown"
            candidates[entity] = {"entity_id": entity, "name": name, "state": state}
            if len(candidates) > MAX_CANDIDATES:
                raise HomeSetupError("response_too_large")
        return [candidates[key] for key in sorted(candidates)]

    def connect(self, base_url: str, token: str | None = None) -> dict[str, Any]:
        base = self._url(base_url)
        with self._lock:
            if token is None or token == "":
                token = self._settings["token"] if base == self._settings["base_url"] else ""
            private_token = _token(token)
            self._generation += 1
            generation = self._generation
            self._pending = True
        try:
            def is_cancelled() -> bool:
                with self._lock:
                    return generation != self._generation
            candidates = _discover_bounded(base, private_token, is_cancelled=is_cancelled)
            with self._lock:
                if generation != self._generation:
                    raise HomeSetupError("operation_superseded")
                available = {item["entity_id"] for item in candidates}
                same = base == self._settings["base_url"] and private_token == self._settings["token"]
                selected = [entity for entity in self._settings["allowed_entities"] if entity in available] if same else []
                client = HomeAssistantIntegration(base, private_token, selected) if selected else None
                self._commit({"v": 1, "base_url": base, "token": private_token, "allowed_entities": selected}, client)
                self._candidates = candidates
                self._verified = True
                self._pending = False
                return self.status()
        except HomeSetupError as error:
            with self._lock:
                if generation == self._generation:
                    self._pending = False
                    self._error_code = error.code
            raise
        except Exception:
            with self._lock:
                if generation == self._generation:
                    self._pending = False
                    self._error_code = "connection_failed"
            raise HomeSetupError("connection_failed") from None

    def select(self, allowed_entities: list[str]) -> dict[str, Any]:
        selected = _entities(allowed_entities)
        with self._lock:
            if not self._verified:
                raise HomeSetupError("verification_required")
            available = {item["entity_id"] for item in self._candidates}
            if not set(selected) <= available:
                raise HomeSetupError("selection_invalid")
            self._generation += 1
            self._pending = False
            client = HomeAssistantIntegration(self._settings["base_url"], self._settings["token"], selected) if selected else None
            self._commit({**self._settings, "allowed_entities": selected}, client)
            return self.status()

    def disconnect(self) -> dict[str, Any]:
        with self._lock:
            self._generation += 1
            self._pending = False
            self._commit(self._empty_settings(), None)
            self._verified = False
            self._candidates = []
            return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            base = self._settings["base_url"]
            active = bool(self._home and self._home.is_configured())
            state = "unconfigured" if not base else "ready" if self._verified and active else "verified" if self._verified else "unverified"
            return {
                "base_url": base, "verified": self._verified, "active": active,
                "token_present": bool(self._settings["token"]),
                "candidates": [dict(item) for item in self._candidates],
                "allowed_entities": list(self._settings["allowed_entities"]),
                "pending": self._pending, "state": state, "error_code": self._error_code,
                "links": {"login": base + "/" if base else None,
                          "token": base + "/profile/security" if base else None,
                          "devices": base + "/config/integrations" if base else None,
                          "installation": "https://www.home-assistant.io/installation/windows/",
                          "container_installation": "https://www.home-assistant.io/installation/linux/#install-home-assistant-container"},
                "steps": [{"id": "open", "label": "Home Assistant 열기", "complete": bool(base)},
                          {"id": "connect", "label": "주소·토큰 연결 확인", "complete": self._verified},
                          {"id": "select", "label": "제어할 기기 선택·저장", "complete": active}],
            }

def _discovery_worker() -> None:
    """One read-only setup request; stdout never includes private input/error text."""
    try:
        raw = sys.stdin.buffer.readline(16 * 1024 + 1)
        if len(raw) > 16 * 1024 or not raw.endswith(b"\n"):
            raise HomeSetupError("invalid_response")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
        if not isinstance(value, dict) or set(value) != {"base_url", "token", "timeout_s"}:
            raise HomeSetupError("invalid_response")
        timeout_s = value["timeout_s"]
        if type(timeout_s) not in {int, float} or not 0 < timeout_s <= 10:
            raise HomeSetupError("invalid_response")
        base = HomeAssistantSetupService._url(value["base_url"])
        token = _token(value["token"])
        result = {"candidates": _discover_http(base, token, timeout_s)}
    except HomeSetupError as error:
        result = {"error": error.code}
    except Exception:
        result = {"error": "connection_failed"}
    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


if __name__ == "__main__" and sys.argv[1:] == ["--discovery-worker"]:
    _discovery_worker()