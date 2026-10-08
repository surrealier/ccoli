#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="docker/docker-compose.test.yml"
LOG_DIR="artifacts/test-logs"
mkdir -p "${LOG_DIR}"

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] docker command not found."
  echo "[HINT] Run the same test stack in GitHub Actions runner via .github/workflows/docker-tests.yml"
  exit 127
fi

cleanup() {
  docker compose -f "${COMPOSE_FILE}" down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

set +e
docker compose -f "${COMPOSE_FILE}" up --build --abort-on-container-exit --exit-code-from server-test 2>&1 | tee "${LOG_DIR}/compose-server-test.log"
SERVER_RC=${PIPESTATUS[0]}

if [ ${SERVER_RC} -eq 0 ]; then
  docker compose -f "${COMPOSE_FILE}" run --rm --build client-sim 2>&1 | tee "${LOG_DIR}/compose-client-sim.log"
  CLIENT_RC=${PIPESTATUS[0]}
else
  CLIENT_RC=0
fi

if [ ${SERVER_RC} -eq 0 ] && [ ${CLIENT_RC} -eq 0 ]; then
  docker compose -f "${COMPOSE_FILE}" run --rm dashboard-test 2>&1 | tee "${LOG_DIR}/compose-dashboard-test.log"
  DASHBOARD_RC=${PIPESTATUS[0]}
else
  DASHBOARD_RC=0
fi

if [ ${SERVER_RC} -eq 0 ] && [ ${CLIENT_RC} -eq 0 ] && [ ${DASHBOARD_RC} -eq 0 ]; then
  docker compose -f "${COMPOSE_FILE}" run --rm --build firmware-build 2>&1 | tee "${LOG_DIR}/compose-firmware-build.log"
  FIRMWARE_RC=${PIPESTATUS[0]}
else
  FIRMWARE_RC=0
fi
set -e

if [ ${SERVER_RC} -ne 0 ] || [ ${CLIENT_RC} -ne 0 ] || [ ${DASHBOARD_RC} -ne 0 ] || [ ${FIRMWARE_RC} -ne 0 ]; then
  echo "[ERROR] Docker tests failed. server-test=${SERVER_RC}, client-sim=${CLIENT_RC}, dashboard-test=${DASHBOARD_RC}, firmware-build=${FIRMWARE_RC}"
  exit 1
fi

echo "[OK] Docker tests passed. Logs saved to ${LOG_DIR}"
