import numpy as np

from src.voice_id import VoiceIDService


def _pcm(seed: int):
    rng = np.random.default_rng(seed)
    return rng.normal(0, 0.1, 16000).astype(np.float32)


def test_voice_id_register_and_gate(tmp_path):
    svc = VoiceIDService(tmp_path, enabled=True, threshold=0.1)
    msg = svc.begin_register("alice")
    assert "등록" in msg

    for i in range(4):
        m = svc.consume_sample(_pcm(i))
        assert "더 필요" in m
    done = svc.consume_sample(_pcm(5))
    assert "완료" in done

    result = svc.gate(_pcm(1))
    assert result.allowed is True


def test_voice_id_blocks_when_no_profiles(tmp_path):
    svc = VoiceIDService(tmp_path, enabled=True)
    result = svc.gate(_pcm(0))
    assert result.allowed is False
