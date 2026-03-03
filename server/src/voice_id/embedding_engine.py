from __future__ import annotations

import numpy as np


class EmbeddingEngine:
    """경량 화자 임베딩 엔진.

    - speechbrain이 설치되어 있으면 해당 엔진으로 대체 가능하도록 구조만 유지.
    - 기본 구현은 외부 의존성 없이 동작 가능한 통계/스펙트럼 기반 임베딩.
    """

    def __init__(self, sr: int = 16000):
        self.sr = sr

    def extract(self, pcm: np.ndarray) -> np.ndarray:
        if pcm.size == 0:
            return np.zeros(16, dtype=np.float32)

        x = pcm.astype(np.float32)
        if np.max(np.abs(x)) > 1.5:
            x = x / 32768.0

        energy = float(np.mean(np.abs(x)))
        zcr = float(np.mean(np.abs(np.diff(np.signbit(x)).astype(np.float32))))
        mean = float(np.mean(x))
        std = float(np.std(x) + 1e-8)

        spec = np.abs(np.fft.rfft(x[: min(len(x), self.sr)]))
        if spec.size < 8:
            bands = np.zeros(8, dtype=np.float32)
        else:
            splits = np.array_split(spec, 8)
            bands = np.array([float(np.mean(s)) for s in splits], dtype=np.float32)
            bands = bands / (np.linalg.norm(bands) + 1e-8)

        feats = np.concatenate(
            [
                np.array([energy, zcr, mean, std], dtype=np.float32),
                bands,
                np.array([float(np.max(x)), float(np.min(x)), float(np.median(x)), float(np.percentile(x, 75))], dtype=np.float32),
            ]
        )
        return feats.astype(np.float32)
