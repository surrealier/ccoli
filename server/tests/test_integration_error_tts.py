from src.integrations import IntegrationErrorCode, build_tts_debug_message


def test_build_tts_debug_message_auth_invalid_key():
    message = build_tts_debug_message("weather", "날씨", IntegrationErrorCode.AUTH_INVALID_KEY)
    assert "set weather --api-key" in message


def test_build_tts_debug_message_provider_unavailable():
    message = build_tts_debug_message("weather", "날씨", IntegrationErrorCode.PROVIDER_UNAVAILABLE)
    assert "네트워크" in message
