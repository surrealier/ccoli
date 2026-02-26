from __future__ import annotations

from typing import Dict, Optional

from .base import BaseIntegration, IntegrationErrorCode, IntegrationResult


class GoogleCalendarIntegration(BaseIntegration):
    name = "calendar-google"

    def __init__(self, client_id: str = "", client_secret: str = "", refresh_token: str = ""):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token

    def is_configured(self) -> bool:
        return all(bool(x.strip()) for x in (self.client_id, self.client_secret, self.refresh_token))

    def health_check(self) -> IntegrationResult:
        if not self.is_configured():
            return IntegrationResult.failure(
                IntegrationErrorCode.AUTH_MISSING_KEY,
                "Google Calendar OAuth 설정이 부족해요. `ccoli config integration set calendar-google ...`를 실행해 주세요.",
            )
        return IntegrationResult.success({"type": "calendar_health", "status": "ok"})

    def execute(self, intent: str, params: Optional[Dict] = None) -> IntegrationResult:
        if not self.is_configured():
            return IntegrationResult.failure(
                IntegrationErrorCode.AUTH_MISSING_KEY,
                "Google Calendar OAuth 설정이 부족해요. `ccoli config integration set calendar-google ...`를 실행해 주세요.",
            )
        params = params or {}
        # 최소 기능: 조회/추가/수정/삭제 요청 포맷만 표준화(실 API 연결은 추후 확장)
        if intent == "calendar.list":
            return IntegrationResult.success({"type": "calendar", "action": "list", "events": []})
        if intent == "calendar.create":
            return IntegrationResult.success({"type": "calendar", "action": "create", "event": params})
        if intent == "calendar.update":
            return IntegrationResult.success({"type": "calendar", "action": "update", "event": params})
        if intent == "calendar.delete":
            return IntegrationResult.success({"type": "calendar", "action": "delete", "event_id": params.get("event_id", "")})
        return IntegrationResult.failure(IntegrationErrorCode.UNKNOWN, "지원하지 않는 캘린더 요청이에요.")
