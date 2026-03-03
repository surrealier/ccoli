#!/usr/bin/env bash
set -euo pipefail

MAX_ITERS="${MAX_ITERS:-5}"
REPORT_DIR="${REPORT_DIR:-.codex/reports}"
mkdir -p "$REPORT_DIR"

for i in $(seq 1 "$MAX_ITERS"); do
  echo "[autoloop] iteration $i/$MAX_ITERS"
  if docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from server-tests; then
    echo "[autoloop] tests passed on iteration $i" | tee "$REPORT_DIR/success.txt"
    exit 0
  fi
  echo "[autoloop] tests failed on iteration $i" | tee "$REPORT_DIR/iter-${i}.log"
  docker compose -f docker-compose.test.yml down -v || true
  sleep 1
done

echo "[autoloop] max iterations reached" | tee "$REPORT_DIR/failure.txt"
exit 1
