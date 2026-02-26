from __future__ import annotations

from typing import Dict, Optional

from .base import BaseIntegration, IntegrationErrorCode, IntegrationResult


class SearchIntegration(BaseIntegration):
    name = "search"

    def __init__(self, api_key: Optional[str]):
        self.api_key = api_key

    def is_configured(self) -> bool:
        return bool((self.api_key or "").strip())

    def health_check(self) -> IntegrationResult:
        if not self.is_configured():
            return IntegrationResult.failure(
                IntegrationErrorCode.AUTH_MISSING_KEY,
                "검색 API 키가 없어요. `ccoli config integration set search --api-key ...`로 등록해 주세요.",
            )
        return IntegrationResult.success({"type": "search_health", "status": "ok"})

    def execute(self, intent: str, params: Optional[Dict] = None) -> IntegrationResult:
        if intent not in {"search.query", "search"}:
            return IntegrationResult.failure(IntegrationErrorCode.UNKNOWN, "지원하지 않는 검색 요청이에요.")
        if not self.is_configured():
            return IntegrationResult.failure(
                IntegrationErrorCode.AUTH_MISSING_KEY,
                "검색 API 키가 없어요. `ccoli config integration set search --api-key ...`로 등록해 주세요.",
            )

        query = (params or {}).get("query", "").strip()
        if not query:
            return IntegrationResult.failure(IntegrationErrorCode.HTTP_4XX, "검색어를 알려주세요.")

        try:
            import requests

            response = requests.get(
                "https://api.tavily.com/search",
                params={"api_key": self.api_key, "query": query, "max_results": 3},
                timeout=6,
            )
            if response.status_code == 401:
                return IntegrationResult.failure(IntegrationErrorCode.AUTH_INVALID_KEY, "검색 API 키가 유효하지 않아요.")
            if response.status_code == 429:
                return IntegrationResult.failure(IntegrationErrorCode.RATE_LIMITED, "검색 요청 한도를 초과했어요.")
            if 400 <= response.status_code < 500:
                return IntegrationResult.failure(IntegrationErrorCode.HTTP_4XX, "검색 요청이 거절되었어요.")
            if response.status_code >= 500:
                return IntegrationResult.failure(IntegrationErrorCode.HTTP_5XX, "검색 서비스가 불안정해요.")

            data = response.json()
            results = data.get("results", []) if isinstance(data, dict) else []
            top = [
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", ""),
                }
                for item in results[:3]
                if isinstance(item, dict)
            ]
            return IntegrationResult.success({"type": "search", "query": query, "results": top})
        except Exception as exc:
            return IntegrationResult.failure(
                IntegrationErrorCode.PROVIDER_UNAVAILABLE,
                "검색 서비스에 연결하지 못했어요.",
                {"error": str(exc)},
            )
