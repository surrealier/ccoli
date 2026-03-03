from __future__ import annotations

from typing import Dict, Optional

from .base import BaseIntegration, IntegrationErrorCode, IntegrationResult


class MapsIntegration(BaseIntegration):
    name = "maps"

    def __init__(self, api_key: Optional[str]):
        self.api_key = api_key

    def is_configured(self) -> bool:
        return bool((self.api_key or "").strip())

    def health_check(self) -> IntegrationResult:
        if not self.is_configured():
            return IntegrationResult.failure(
                IntegrationErrorCode.AUTH_MISSING_KEY,
                "지도 API 키가 없어요. `ccoli config integration set maps --api-key ...`로 등록해 주세요.",
            )
        return IntegrationResult.success({"type": "maps_health", "status": "ok"})

    def execute(self, intent: str, params: Optional[Dict] = None) -> IntegrationResult:
        if not self.is_configured():
            return IntegrationResult.failure(
                IntegrationErrorCode.AUTH_MISSING_KEY,
                "지도 API 키가 없어요. `ccoli config integration set maps --api-key ...`로 등록해 주세요.",
            )
        params = params or {}
        if intent not in {"maps.route", "maps"}:
            return IntegrationResult.failure(IntegrationErrorCode.UNKNOWN, "지원하지 않는 지도 요청이에요.")
        origin = params.get("origin", "")
        destination = params.get("destination", "")
        if not origin or not destination:
            return IntegrationResult.failure(IntegrationErrorCode.HTTP_4XX, "출발지와 목적지를 알려주세요.")

        return IntegrationResult.success(
            {
                "type": "maps",
                "origin": origin,
                "destination": destination,
                "eta_min": 0,
                "summary": f"{origin}에서 {destination}까지 경로를 확인했어요.",
            }
        )
