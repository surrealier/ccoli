from __future__ import annotations

from typing import Dict, Tuple

import numpy as np


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-8
    if denom <= 0:
        return 0.0
    return float(np.dot(a, b) / denom)


class SpeakerMatcher:
    def __init__(self, threshold: float = 0.72):
        self.threshold = threshold

    def match(self, embedding: np.ndarray, profiles: Dict[str, np.ndarray]) -> Tuple[str | None, float]:
        best_user = None
        best_score = -1.0
        for user, ref in profiles.items():
            score = cosine_similarity(embedding, ref)
            if score > best_score:
                best_user = user
                best_score = score
        if best_user is None or best_score < self.threshold:
            return None, max(best_score, 0.0)
        return best_user, best_score
