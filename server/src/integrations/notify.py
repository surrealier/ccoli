from __future__ import annotations

from typing import Dict, Optional

from .base import BaseIntegration, IntegrationErrorCode, IntegrationResult


class NotifyIntegration(BaseIntegration):
    name = "notify-slack"

    def __init__(self, bot_token: Optional[str]):
        self.bot_token = bot_token

    def is_configured(self) -> bool:
        return bool((self.bot_token or "").strip())

    def health_check(self) -> IntegrationResult:
        if not self.is_configured():
            return IntegrationResult.failure(
                IntegrationErrorCode.AUTH_MISSING_KEY,
                "Slack 토큰이 없어요. `ccoli config integration set notify-slack --api-key ...`로 등록해 주세요.",
            )
        return IntegrationResult.success({"type": "notify_health", "status": "ok"})

    def execute(self, intent: str, params: Optional[Dict] = None) -> IntegrationResult:
        if not self.is_configured():
            return IntegrationResult.failure(
                IntegrationErrorCode.AUTH_MISSING_KEY,
                "Slack 토큰이 없어요. `ccoli config integration set notify-slack --api-key ...`로 등록해 주세요.",
            )
        params = params or {}
        if intent == "notify.send":
            channel = params.get("channel", "")
            text = params.get("text", "")
            if not channel or not text:
                return IntegrationResult.failure(IntegrationErrorCode.HTTP_4XX, "채널과 메시지를 함께 알려주세요.")
            return IntegrationResult.success({"type": "notify", "channel": channel, "text": text, "sent": True})
        if intent == "notify.recent":
            return IntegrationResult.success({"type": "notify", "messages": []})
        return IntegrationResult.failure(IntegrationErrorCode.UNKNOWN, "지원하지 않는 알림 요청이에요.")
