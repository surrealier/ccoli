"""CLI for the opt-in LeRobot worker; no physical action in smoke/train/eval."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'server'))

if __name__ == '__main__':
    from src.robotics.lerobot_worker import main
    raise SystemExit(main())
