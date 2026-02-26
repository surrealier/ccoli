from __future__ import annotations

from .base import IntegrationErrorCode


ERROR_TTS_TEMPLATES = {
    IntegrationErrorCode.AUTH_INVALID_KEY: "{name} API 키가 유효하지 않아요. `ccoli config integration set {provider} --api-key ...`로 다시 등록해 주세요.",
    IntegrationErrorCode.AUTH_MISSING_KEY: "{name} API 키가 없어요. `ccoli config integration set {provider} --api-key ...`로 먼저 등록해 주세요.",
    IntegrationErrorCode.RATE_LIMITED: "{name} API 요청 한도를 초과했어요. 잠시 후 다시 시도해 주세요.",
    IntegrationErrorCode.HTTP_4XX: "{name} 요청이 거절되었어요. 권한과 설정을 확인해 주세요.",
    IntegrationErrorCode.HTTP_5XX: "{name} 서비스가 불안정해요. 잠시 후 다시 시도해 주세요.",
    IntegrationErrorCode.TIMEOUT: "{name} 요청이 시간 초과됐어요. 네트워크 상태를 확인해 주세요.",
    IntegrationErrorCode.PROVIDER_UNAVAILABLE: "{name} 서비스에 연결하지 못했어요. 네트워크나 방화벽 설정을 확인해 주세요.",
    IntegrationErrorCode.UNKNOWN: "{name} 처리 중 오류가 발생했어요. 설정을 확인해 주세요.",
}


def build_tts_debug_message(provider: str, display_name: str, code: IntegrationErrorCode) -> str:
    template = ERROR_TTS_TEMPLATES.get(code, ERROR_TTS_TEMPLATES[IntegrationErrorCode.UNKNOWN])
    return template.format(name=display_name, provider=provider)
