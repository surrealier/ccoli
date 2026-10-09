import concurrent.futures
import threading

import pytest


def test_dialogue_languages_and_voice_profiles():
    from src.dialogue_policy import SUPPORTED_LANGUAGES, normalize_language, voice_for_language
    assert SUPPORTED_LANGUAGES == ('ko', 'en', 'zh', 'ja', 'es')
    assert normalize_language('zh-CN') == 'zh'
    assert normalize_language('auto', allow_auto=True) == 'auto'
    with pytest.raises(ValueError):
        normalize_language('fr')
    assert voice_for_language('es') == 'es-ES-ElviraNeural'
    assert voice_for_language('ja') == 'ja-JP-NanamiNeural'


@pytest.mark.parametrize('text,expected', [('안녕하세요','ko'), ('こんにちは','ja'), ('你好','zh'),
    ('Hola, ¿cómo estás?', 'es'), ('How are you?', 'en')])
def test_text_language_selection(text, expected):
    from src.dialogue_policy import detect_language
    assert detect_language(text) == expected


def test_short_policy_respects_explicit_detail_and_language():
    from src.dialogue_policy import conversation_instructions
    assert '1–2 sentences' in conversation_instructions('en', True, 'Hello')
    assert 'Spanish' in conversation_instructions('es', True, 'Hola')
    assert 'requested detail' in conversation_instructions('ja', True, '詳しく説明して')


def test_tts_cache_separates_settings_expires_and_never_caches_failure():
    from src.dialogue_policy import AudioCache
    now = [0.0]
    cache = AudioCache(max_bytes=8, ttl_seconds=1, clock=lambda: now[0])
    calls = []
    def synthesize():
        calls.append(1)
        return b'abcd'
    assert cache.get_or_create(('en', 180), synthesize) == b'abcd'
    assert cache.get_or_create(('en', 180), synthesize) == b'abcd'
    assert len(calls) == 1
    cache.get_or_create(('es', 180), synthesize)
    now[0] = 2
    cache.get_or_create(('en', 180), synthesize)
    assert len(calls) == 3
    assert cache.get_or_create(('failed',), lambda: b'') == b''
    assert cache.get_or_create(('failed',), synthesize) == b'abcd'
    assert cache.bytes_used <= 8


def test_audio_cache_singleflight_preserves_order_and_result():
    from src.dialogue_policy import AudioCache
    cache = AudioCache()
    entered = threading.Event()
    release = threading.Event()
    calls = []
    def synthesize():
        calls.append(1)
        entered.set()
        assert release.wait(2)
        return b'pcm'
    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        first = pool.submit(cache.get_or_create, ('same',), synthesize)
        assert entered.wait(1)
        second = pool.submit(cache.get_or_create, ('same',), synthesize)
        release.set()
        assert first.result() == second.result() == b'pcm'
    assert calls == [1]


def test_stt_auto_maps_to_none_and_fixed_languages_reach_whisper():
    import numpy as np
    from src.stt_engine import STTEngine
    calls = []
    class Model:
        def transcribe(self, pcm, **kwargs):
            calls.append(kwargs['language'])
            return [], {'language': 'es'}
    engine = STTEngine('turbo', 'cpu', language='auto')
    engine.model = Model()
    engine.safe_transcribe(np.zeros(16000, dtype=np.float32))
    assert calls == [None]
    for language in ('ko', 'en', 'zh', 'ja', 'es'):
        engine.set_language(language)
        engine.safe_transcribe(np.zeros(16000, dtype=np.float32))
    assert calls[1:] == ['ko','en','zh','ja','es']
    with pytest.raises(ValueError):
        engine.set_language('fr')


def test_audio_cache_eviction_and_exceptions_do_not_poison_followup():
    from src.dialogue_policy import AudioCache
    cache=AudioCache(max_bytes=5,max_entries=1)
    assert cache.get_or_create(('large',),lambda:b'123456')==b'123456'
    assert cache.bytes_used==0
    def fail():
        raise RuntimeError('synthetic failure')
    with pytest.raises(RuntimeError):
        cache.get_or_create(('fault',),fail)
    assert cache.get_or_create(('fault',),lambda:b'1234')==b'1234'
    assert cache.get_or_create(('other',),lambda:b'abc')==b'abc'
    assert cache.bytes_used==3


def test_auto_plain_english_and_existing_spanish_and_japanese_continuity():
    from src.dialogue_policy import detect_language
    assert detect_language('Cats purr.')=='en'
    assert detect_language('Bananas are yellow.')=='en'
    assert detect_language('Gatos ronronean.',fallback='es')=='es'
    assert detect_language('明日は晴天',fallback='ja')=='ja'
    assert detect_language('123',fallback='es')=='es'
