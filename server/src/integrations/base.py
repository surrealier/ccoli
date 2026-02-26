from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class IntegrationErrorCode(str, Enum):
    AUTH_INVALID_KEY = "AUTH_INVALID_KEY"
    AUTH_MISSING_KEY = "AUTH_MISSING_KEY"
    HTTP_4XX = "HTTP_4XX"
    HTTP_5XX = "HTTP_5XX"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


@dataclass
class IntegrationError:
    code: IntegrationErrorCode
    user_message: str
    debug: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IntegrationResult:
    ok: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[IntegrationError] = None

    @classmethod
    def success(cls, data: Dict[str, Any]) -> "IntegrationResult":
        return cls(ok=True, data=data, error=None)

    @classmethod
    def failure(
        cls,
        code: IntegrationErrorCode,
        user_message: str,
        debug: Optional[Dict[str, Any]] = None,
    ) -> "IntegrationResult":
        return cls(
            ok=False,
            data=None,
            error=IntegrationError(code=code, user_message=user_message, debug=debug or {}),
        )


class BaseIntegration:
    name: str = "base"

    def is_configured(self) -> bool:
        raise NotImplementedError

    def health_check(self) -> IntegrationResult:
        raise NotImplementedError

    def execute(self, intent: str, params: Optional[Dict[str, Any]] = None) -> IntegrationResult:
        raise NotImplementedError
