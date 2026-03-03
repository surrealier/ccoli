from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from .embedding_engine import EmbeddingEngine
from .speaker_matcher import SpeakerMatcher
from .speaker_store import SpeakerStore


@dataclass
class VoiceGateResult:
    allowed: bool
    user: Optional[str] = None
    score: float = 0.0
    message: str = ""


class VoiceIDService:
    def __init__(self, base_dir: Path, enabled: bool = False, threshold: float = 0.72):
        self.store = SpeakerStore(base_dir)
        self.engine = EmbeddingEngine()
        self.matcher = SpeakerMatcher(threshold=threshold)
        self.enabled = enabled
        self.threshold = threshold

        self._profiles: Dict[str, np.ndarray] = {}
        self._registering_user: Optional[str] = None
        self._samples: List[np.ndarray] = []
        self._failed_count = 0
        self._load_profiles()

    def _load_profiles(self) -> None:
        self._profiles.clear()
        for user in self.store.list_users():
            npy = self.store.base_dir / f"{user}.npy"
            if npy.exists():
                try:
                    self._profiles[user] = np.load(npy)
                except Exception:
                    continue

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def set_threshold(self, threshold: float) -> None:
        self.threshold = threshold
        self.matcher.threshold = threshold

    def begin_register(self, user: str) -> str:
        self._registering_user = user.strip()
        self._samples = []
        return f"{self._registering_user}님 목소리 등록을 시작할게요. 샘플 5개를 순서대로 말해 주세요."

    def cancel_register(self) -> None:
        self._registering_user = None
        self._samples = []

    def consume_sample(self, pcm: np.ndarray) -> Optional[str]:
        if not self._registering_user:
            return None
        emb = self.engine.extract(pcm)
        self._samples.append(emb)
        remain = 5 - len(self._samples)
        if remain > 0:
            return f"샘플이 저장됐어요. {remain}개 더 필요해요."

        stacked = np.stack(self._samples, axis=0)
        mean_emb = np.mean(stacked, axis=0)
        user = self._registering_user
        self.store.upsert_profile(user, sample_count=5, threshold=self.threshold)
        np.save(self.store.base_dir / f"{user}.npy", mean_emb)
        self._profiles[user] = mean_emb
        self.cancel_register()
        return f"{user}님 목소리 등록이 완료됐어요."

    def delete_user(self, user: str) -> bool:
        deleted = self.store.delete_profile(user)
        self._profiles.pop(user, None)
        return deleted

    def gate(self, pcm: np.ndarray) -> VoiceGateResult:
        if not self.enabled:
            return VoiceGateResult(allowed=True)
        if not self._profiles:
            return VoiceGateResult(allowed=False, message="등록된 사용자 음성만 응답해요. 먼저 목소리를 등록해 주세요.")

        emb = self.engine.extract(pcm)
        user, score = self.matcher.match(emb, self._profiles)
        if user:
            self._failed_count = 0
            return VoiceGateResult(allowed=True, user=user, score=score)

        self._failed_count += 1
        if self._failed_count >= 3:
            return VoiceGateResult(
                allowed=False,
                score=score,
                message="등록된 사용자 음성만 응답해요. 주변 소음이 큰지 확인해 주세요.",
            )
        return VoiceGateResult(allowed=False, score=score, message="등록된 사용자 음성만 응답해요.")
