from __future__ import annotations

import time
from typing import Any, Dict, Optional

from .base import BaseIntegration, IntegrationErrorCode, IntegrationResult


class WeatherIntegration(BaseIntegration):
    name = "weather"

    def __init__(self, api_key: Optional[str], lat: float = 37.5665, lon: float = 126.9780, ttl_sec: int = 300):
        self.api_key = api_key
        self.lat = lat
        self.lon = lon
        self.ttl_sec = ttl_sec
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_at = 0.0

    def is_configured(self) -> bool:
        return bool((self.api_key or "").strip())

    def health_check(self) -> IntegrationResult:
        if not self.is_configured():
            return IntegrationResult.failure(
                IntegrationErrorCode.AUTH_MISSING_KEY,
                "날씨 API 키가 없어요. `ccoli config integration set weather --api-key ...`로 등록해 주세요.",
            )
        return self.execute("weather.current", {})

    def execute(self, intent: str, params: Optional[Dict[str, Any]] = None) -> IntegrationResult:
        if intent not in {"weather.current", "weather"}:
            return IntegrationResult.failure(
                IntegrationErrorCode.UNKNOWN,
                "지원하지 않는 날씨 요청이에요.",
                {"intent": intent},
            )
        if not self.is_configured():
            return IntegrationResult.failure(
                IntegrationErrorCode.AUTH_MISSING_KEY,
                "날씨 API 키가 없어요. `ccoli config integration set weather --api-key ...`로 등록해 주세요.",
            )

        now = time.time()
        if self._cache and (now - self._cache_at) < self.ttl_sec:
            return IntegrationResult.success(self._cache)

        try:
            import requests

            url = "http://api.openweathermap.org/data/2.5/weather"
            response = requests.get(
                url,
                params={
                    "lat": self.lat,
                    "lon": self.lon,
                    "appid": self.api_key,
                    "units": "metric",
                    "lang": "kr",
                },
                timeout=5,
            )
            if response.status_code == 401:
                return IntegrationResult.failure(
                    IntegrationErrorCode.AUTH_INVALID_KEY,
                    "날씨 API 키가 유효하지 않아요. `ccoli config integration set weather --api-key ...`로 다시 등록해 주세요.",
                    {"status_code": response.status_code},
                )
            if response.status_code == 429:
                return IntegrationResult.failure(
                    IntegrationErrorCode.RATE_LIMITED,
                    "날씨 API 요청 한도를 초과했어요. 잠시 후 다시 시도해 주세요.",
                    {"status_code": response.status_code},
                )
            if 400 <= response.status_code < 500:
                return IntegrationResult.failure(
                    IntegrationErrorCode.HTTP_4XX,
                    "날씨 요청을 처리하지 못했어요. 설정을 확인해 주세요.",
                    {"status_code": response.status_code},
                )
            if response.status_code >= 500:
                return IntegrationResult.failure(
                    IntegrationErrorCode.HTTP_5XX,
                    "날씨 서비스가 일시적으로 불안정해요. 잠시 후 다시 시도해 주세요.",
                    {"status_code": response.status_code},
                )

            data = response.json()
            result = {
                "type": "weather",
                "city": data.get("name", ""),
                "description": data.get("weather", [{}])[0].get("description", ""),
                "temp": data.get("main", {}).get("temp"),
                "feels_like": data.get("main", {}).get("feels_like"),
                "humidity": data.get("main", {}).get("humidity"),
                "wind_speed": data.get("wind", {}).get("speed", 0),
            }
            self._cache = result
            self._cache_at = now
            return IntegrationResult.success(result)
        except Exception as exc:
            return IntegrationResult.failure(
                IntegrationErrorCode.PROVIDER_UNAVAILABLE,
                "날씨 서비스에 연결하지 못했어요. 네트워크 상태를 확인해 주세요.",
                {"error": str(exc)},
            )
