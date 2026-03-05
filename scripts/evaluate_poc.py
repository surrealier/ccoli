#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def evaluate_ralph() -> dict:
    return {
        "tool": "ralph",
        "candidates": ["docs lint", "test report automation"],
        "security": "외부 업로드 경로 차단 시 도입 가능",
        "cost": "초기 PoC는 low",
        "conflict": "기존 docker test 파이프라인과 충돌 낮음",
        "maintenance": "중간",
        "rollout": ["experiment", "partial", "full"],
        "decision": "proceed_with_limited_poc",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", required=True)
    parser.add_argument("--out", default="docs/ralph_poc_report.json")
    args = parser.parse_args()

    if args.tool.lower() != "ralph":
        print(json.dumps({"error": "unsupported tool", "tool": args.tool}, ensure_ascii=False))
        return 2

    result = evaluate_ralph()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
