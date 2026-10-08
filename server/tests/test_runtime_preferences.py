from src.runtime_preferences import HardwareProfile, RuntimePreferences


def _preferences(*, platform="darwin", accelerators=None, tts_backend="edge_tts"):
    return RuntimePreferences(
        llm_priority=["ollama", "api", "ollama_cpu", "other"],
        api_priority=["gemini", "claude", "chatgpt"],
        connection_priority=["wired", "wifi"],
        processor_priority=["gpu", "cpu"],
        llm_models={
            "ollama": "qwen2.5:0.5b",
            "gemini": "gemini-2.5-flash",
            "claude": "claude-3-5-haiku-latest",
            "chatgpt": "gpt-4o-mini",
        },
        hardware=HardwareProfile(accelerators=accelerators or ["mps"], platform=platform),
        tts_backend=tts_backend,
    )


def test_runtime_preferences_keep_stt_on_cpu_when_only_mps_is_detected():
    prefs = _preferences(accelerators=["mps"])

    assert prefs.resolved_stt_devices() == ["cpu"]


def test_runtime_preferences_report_mac_mps_limits_for_current_audio_stack():
    prefs = _preferences(accelerators=["mps"])

    notes = prefs.audio_runtime_notes()

    assert any("MPS" in note and "STT" in note for note in notes)
    assert any("Edge TTS" in note and "MPS" in note for note in notes)


def test_runtime_preferences_status_snapshot_exposes_audio_capability_flags():
    prefs = _preferences(accelerators=["mps"])

    runtime = prefs.to_dict()

    assert runtime["hardware"]["mps_available"] is True
    assert runtime["stt_supported_devices"] == ["cuda", "cpu"]
    assert runtime["stt_mps_supported"] is False
    assert runtime["tts_mps_supported"] is False


def test_current_api_defaults_match_selected_workloads():
    from src.runtime_preferences import DEFAULT_API_MODELS, resolve_llm_models

    expected = {
        "gemini": "gemini-3.8-flash",
        "claude": "claude-sonnet-5-5",
        "chatgpt": "gpt-6-luna",
    }
    from ccoli.cli import DEFAULT_LLM_MODELS
    assert DEFAULT_LLM_MODELS["claude"] == expected["claude"]
    assert DEFAULT_API_MODELS == expected
    resolved = resolve_llm_models({})
    assert {provider: resolved[provider] for provider in expected} == expected


def test_explicit_models_remain_configurable_after_default_upgrade():
    from src.runtime_preferences import resolve_llm_models

    resolved = resolve_llm_models({
        "provider": "gemini",
        "api_models": {"gemini": "custom-gemini", "claude": "custom-claude", "chatgpt": "custom-openai"},
        "ollama_model": "custom-local",
    })
    assert resolved == {
        "ollama": "custom-local", "gemini": "custom-gemini",
        "claude": "custom-claude", "chatgpt": "custom-openai",
    }


def test_local_default_uses_current_small_multilingual_model():
    from src.runtime_preferences import DEFAULT_OLLAMA_MODEL
    assert DEFAULT_OLLAMA_MODEL == 'qwen3.5:4b'


def test_cloud_tts_does_not_claim_local_acceleration():
    prefs = _preferences(tts_backend="gemini_tts")
    runtime = prefs.to_dict()
    assert runtime["tts_processor_selectable"] is False
    assert any("remote model" in note for note in runtime["audio_runtime_notes"])
