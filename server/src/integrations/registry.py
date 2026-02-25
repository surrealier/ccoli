from __future__ import annotations

from typing import Dict, Optional

from .base import BaseIntegration, IntegrationResult


class IntegrationRegistry:
    def __init__(self):
        self._integrations: Dict[str, BaseIntegration] = {}
        self._enabled: Dict[str, bool] = {}

    def register(self, integration: BaseIntegration, enabled: bool = True) -> None:
        self._integrations[integration.name] = integration
        self._enabled[integration.name] = enabled

    def list(self) -> Dict[str, Dict[str, bool]]:
        out: Dict[str, Dict[str, bool]] = {}
        for name, integ in self._integrations.items():
            out[name] = {
                "enabled": self._enabled.get(name, False),
                "configured": integ.is_configured(),
            }
        return out

    def set_enabled(self, name: str, enabled: bool) -> bool:
        if name not in self._integrations:
            return False
        self._enabled[name] = enabled
        return True

    def execute(self, name: str, intent: str, params: Optional[dict] = None) -> Optional[IntegrationResult]:
        integ = self._integrations.get(name)
        if not integ:
            return None
        if not self._enabled.get(name, False):
            return None
        return integ.execute(intent, params or {})

    def health_check(self, name: str) -> Optional[IntegrationResult]:
        integ = self._integrations.get(name)
        if not integ:
            return None
        return integ.health_check()
