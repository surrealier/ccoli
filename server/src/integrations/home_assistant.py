"""Explicitly allowlisted Home Assistant light/switch access."""

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Sequence
from urllib.parse import urlsplit

import requests


class HomeAssistantIntegration:
    def __init__(self, base_url: str, token: str, allowed_entities: Sequence[str]) -> None:
        self.base_url = self._validate_url(base_url or "")
        if not isinstance(token, str) or any(c in token for c in "\r\n"):
            raise ValueError("Home Assistant 토큰 설정을 확인해 주세요.")
        self._token = token.strip()
        if isinstance(allowed_entities, (str, bytes)) or not isinstance(allowed_entities, (list, tuple, set, frozenset)):
            raise ValueError("허용할 엔티티 ID 목록을 지정해 주세요.")
        if any(not isinstance(entity, str) or not re.fullmatch(r"(?:light|switch)\.[a-z0-9_]+", entity)
               for entity in allowed_entities):
            raise ValueError("light 또는 switch의 정확한 엔티티 ID만 허용됩니다.")
        self.allowed_entities = tuple(sorted(set(allowed_entities)))

    @staticmethod
    def _validate_url(value: str) -> str:
        message = "Home Assistant 주소를 http(s)://호스트:포트 형식으로 설정해 주세요."
        if not isinstance(value, str):
            raise ValueError(message)
        if not value:
            return ""
        if any(char.isspace() or ord(char) < 32 for char in value) or "\\" in value:
            raise ValueError(message)
        try:
            parts = urlsplit(value)
            valid = (
                parts.scheme in {"http", "https"} and parts.hostname
                and parts.username is None and parts.password is None
                and not parts.query and not parts.fragment
                and "?" not in value and "#" not in value
                and parts.path in {"", "/"}
            )
            parts.port  # Validate the port before making any request.
        except ValueError:
            raise ValueError(message) from None
        if not valid:
            raise ValueError(message)
        return value.rstrip("/")

    def is_configured(self) -> bool:
        return bool(self.base_url and self._token and self.allowed_entities)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}
        try:
            with requests.Session() as session:
                # Avoid implicit .netrc credentials overriding the explicit bearer token.
                session.trust_env = False
                response = session.request(
                    method, self.base_url + path, headers=headers,
                    timeout=5, allow_redirects=False, **kwargs,
                )
                if not 200 <= response.status_code < 300:
                    raise RuntimeError("Home Assistant 요청 실패")
                return response.json()
        except (requests.RequestException, ValueError, RuntimeError):
            raise RuntimeError("Home Assistant 요청을 처리하지 못했어요. 연결과 인증 설정을 확인해 주세요.") from None

    @staticmethod
    def _validated_state(data: Any, entity_id: str) -> dict[str, str]:
        if (not isinstance(data, dict) or data.get("entity_id") != entity_id
                or not isinstance(data.get("state"), str)):
            raise RuntimeError("Home Assistant 상태 응답을 확인할 수 없어요. 기기 상태를 확인해 주세요.")
        attributes = data.get("attributes", {})
        name = attributes.get("friendly_name", entity_id) if isinstance(attributes, dict) else entity_id
        return {"entity_id": entity_id, "state": data["state"],
                "name": name if isinstance(name, str) else entity_id}

    def _state(self, entity_id: str) -> dict[str, str]:
        return self._validated_state(self._request("GET", f"/api/states/{entity_id}"), entity_id)

    def states(self) -> list[dict[str, str]]:
        if not self.is_configured():
            return []
        if len(self.allowed_entities) == 1:
            return [self._state(self.allowed_entities[0])]
        # Each request reads only one allowlisted ID. Parallel reads prevent an
        # unrelated device timeout from delaying every subsequent device.
        with ThreadPoolExecutor(max_workers=min(8, len(self.allowed_entities))) as pool:
            return list(pool.map(self._state, self.allowed_entities))
    def control(self, entity_id: str, action: str) -> dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("Home Assistant 주소, 토큰과 허용 기기를 설정해 주세요.")
        if entity_id not in self.allowed_entities or action not in ("turn_on", "turn_off"):
            raise ValueError("허용된 light/switch 기기의 켜기와 끄기만 요청할 수 있어요.")
        domain = entity_id.split(".", 1)[0]
        self._request("POST", f"/api/services/{domain}/{action}", json={"entity_id": entity_id})
        result = self._state(entity_id)
        if result["state"] != ("on" if action == "turn_on" else "off"):
            raise RuntimeError("요청 후 원하는 기기 상태를 확인하지 못했어요. 기기를 확인해 주세요.")
        return {**result, "action": action, "confirmed": True}
