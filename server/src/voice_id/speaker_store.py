from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List


@dataclass
class VoiceProfile:
    user: str
    created_at: str
    sample_count: int
    threshold: float


class SpeakerStore:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.base_dir / "profiles.json"

    def _load_meta(self) -> Dict[str, Dict]:
        if not self.meta_path.exists():
            return {}
        data = json.loads(self.meta_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    def _save_meta(self, data: Dict[str, Dict]) -> None:
        self.meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_users(self) -> List[str]:
        return sorted(self._load_meta().keys())

    def upsert_profile(self, user: str, sample_count: int = 0, threshold: float = 0.72) -> None:
        data = self._load_meta()
        data[user] = {
            "user": user,
            "created_at": datetime.utcnow().isoformat(),
            "sample_count": sample_count,
            "threshold": threshold,
        }
        self._save_meta(data)

    def delete_profile(self, user: str) -> bool:
        data = self._load_meta()
        if user not in data:
            return False
        data.pop(user, None)
        self._save_meta(data)

        embed_path = self.base_dir / f"{user}.npy"
        if embed_path.exists():
            embed_path.unlink()
        return True
