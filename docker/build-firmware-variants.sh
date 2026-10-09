#!/usr/bin/env bash
# Compile the Atom Echo sketch once per supported peripheral wiring.
#
# Atom Echo exposes only G21/G25/G26/G32, so the display and the servos compete
# for the same pins (see arduino/atom_echo_m5stack_esp32_ino/config.h). Building
# every combination keeps a pin reassignment from breaking a variant that the
# default build never touches.
set -euo pipefail

FQBN="${FQBN:-m5stack:esp32:m5stack_atom}"
SKETCH="${SKETCH:-/workspace/atom_echo_m5stack_esp32_ino}"

# label:extra_flags
VARIANTS=(
  "default (no display, servos on G26/G32):"
  "SSD1306 OLED on G25/G21:-DDISPLAY_TYPE=1"
  "ST7789V2 LCD on G25/G21/G26/G32:-DDISPLAY_TYPE=2"
  "companion UART bridge on G26/G32:-DROBOT_BRIDGE_ENABLED=1"
)

failed=0
for variant in "${VARIANTS[@]}"; do
  label="${variant%%:*}"
  flags="${variant#*:}"

  echo "=============================================================="
  echo "Building variant: ${label}"
  echo "  extra flags: ${flags:-<none>}"
  echo "=============================================================="

  args=(compile --fqbn "$FQBN" --warnings default --libraries /workspace/libraries)
  if [ -n "$flags" ]; then
    args+=(--build-property "build.extra_flags=-DESP32 $flags")
  fi
  args+=("$SKETCH")

  if arduino-cli "${args[@]}"; then
    echo "OK: ${label}"
  else
    echo "FAILED: ${label}" >&2
    failed=1
  fi
  echo
done

# Exercise the exact shared controller and strict parser natively with memory /
# undefined-behavior sanitizers before compiling the ESP32 adapters.
g++ -std=c++11 -Wall -Wextra -Werror -fsanitize=address,undefined \
  -I/workspace/libraries/CcoliRobotControl/src \
  /workspace/firmware-controller-smoke.cpp -o /tmp/firmware-controller-smoke
/tmp/firmware-controller-smoke

COMPANION_FQBN="${COMPANION_FQBN:-m5stack:esp32:m5stack_core}"
for display in 0 1; do
  echo "Building companion controller (display=${display}, ${COMPANION_FQBN})"
  if ! arduino-cli compile --fqbn "$COMPANION_FQBN" --warnings default \
      --libraries /workspace/libraries \
      --build-property "build.extra_flags=-DESP32 -DCOMPANION_DISPLAY_ENABLED=${display}" \
      /workspace/robot_companion_controller; then
    failed=1
  fi
done

if [ "$failed" -ne 0 ]; then
  echo "One or more firmware variants failed to build." >&2
  exit 1
fi

echo "All firmware variants built successfully."
