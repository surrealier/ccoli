"""Guards for firmware/server agreement that no single-side test can catch.

The Atom Echo exposes only G21/G25/G26/G32, so display and servo builds compete
for the same pins, and the wire protocol constants are duplicated in C and in
Python. Both classes of mismatch fail silently on real hardware — a pin clash
just makes the panel render garbage while the servos jitter — so they are
checked here against the actual header instead of a restated copy.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from src import protocol, robot_mode


REPO_ROOT = Path(__file__).resolve().parents[2]
FIRMWARE_DIR = REPO_ROOT / "arduino" / "atom_echo_m5stack_esp32_ino"
CONFIG_H = FIRMWARE_DIR / "config.h"
SERVER_CONFIG_YAML = REPO_ROOT / "server" / "config.yaml"

# Atom Echo pins wired to the I2S microphone and speaker. Official M5Stack docs
# mark these as "do not reuse"; grabbing one kills audio.
RESERVED_AUDIO_PINS = {19, 22, 23, 33}


class FirmwareError(Exception):
    """Raised when a build variant hits an #error directive."""


def _evaluate(expr: str, defines: dict[str, int]) -> bool:
    """Evaluate the small subset of #if expressions config.h uses."""
    # Resolve identifiers before introducing Python keywords, otherwise the
    # `and`/`or` this function just inserted get substituted away as macros.
    python_expr = re.sub(
        r"[A-Za-z_]\w*",
        lambda m: str(defines.get(m.group(0), 0)),
        expr.split("//")[0],
    )
    python_expr = python_expr.replace("&&", " and ").replace("||", " or ")
    python_expr = re.sub(r"!(?!=)", " not ", python_expr)
    return bool(eval(python_expr, {"__builtins__": {}}, {}))  # noqa: S307 - fixed local input


def _as_int(raw: str):
    raw = raw.split("//")[0].strip()
    try:
        return int(raw, 0)
    except ValueError:
        return raw


def resolve_config_h(**overrides: int) -> dict[str, int]:
    """Expand config.h for one build variant, mirroring the C preprocessor."""
    defines: dict[str, int] = dict(overrides)
    # branch_taken tracks whether any arm of the current #if chain already ran,
    # so #else only activates when every preceding arm was false.
    stack: list[tuple[bool, bool]] = []

    for line in CONFIG_H.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        active = all(state for state, _ in stack)

        if stripped.startswith("#ifndef "):
            taken = stripped.split(None, 1)[1].strip() not in defines
            stack.append((active and taken, taken))
        elif stripped.startswith("#ifdef "):
            taken = stripped.split(None, 1)[1].strip() in defines
            stack.append((active and taken, taken))
        elif stripped.startswith("#if "):
            taken = _evaluate(stripped[4:], defines)
            stack.append((active and taken, taken))
        elif stripped.startswith("#else"):
            outer = all(state for state, _ in stack[:-1])
            _, taken_before = stack[-1]
            stack[-1] = (outer and not taken_before, True)
        elif stripped.startswith("#endif"):
            stack.pop()
        elif stripped.startswith("#error"):
            if active:
                raise FirmwareError(stripped)
        elif stripped.startswith("#define ") and active:
            parts = stripped[len("#define "):].split(None, 1)
            name = parts[0]
            defines[name] = _as_int(parts[1]) if len(parts) > 1 else 1

    return defines


def _claimed_pins(defines: dict[str, int]) -> dict[str, set[int]]:
    """Pins each enabled peripheral drives in this build variant."""
    claimed: dict[str, set[int]] = {}

    if defines["DISPLAY_TYPE"] == 1:
        claimed["ssd1306"] = {defines["DISPLAY_SDA_PIN"], defines["DISPLAY_SCL_PIN"]}
    elif defines["DISPLAY_TYPE"] == 2:
        claimed["st7789v2"] = {
            defines["LCD_PIN_DIN"],
            defines["LCD_PIN_CLK"],
            defines["LCD_PIN_CS"],
            defines["LCD_PIN_DC"],
        }

    if defines["ROBOT_BRIDGE_ENABLED"]:
        claimed["companion_uart"] = {
            defines["ROBOT_BRIDGE_TX_PIN"],
            defines["ROBOT_BRIDGE_RX_PIN"],
        }

    if defines["LOCAL_SERVO_ENABLED"]:
        claimed["servos"] = {defines["SERVO_PIN_PITCH"], defines["SERVO_PIN_TILT"]}

    return claimed


SUPPORTED_VARIANTS = [
    pytest.param({}, id="default-no-display"),
    pytest.param({"DISPLAY_TYPE": 1}, id="ssd1306-oled"),
    pytest.param({"DISPLAY_TYPE": 2}, id="st7789v2-lcd"),
    pytest.param({"ROBOT_BRIDGE_ENABLED": 1}, id="companion-uart-bridge"),
]


@pytest.mark.parametrize("overrides", SUPPORTED_VARIANTS)
def test_no_two_peripherals_claim_the_same_pin(overrides):
    claimed = _claimed_pins(resolve_config_h(**overrides))

    owners = list(claimed.items())
    for i, (name_a, pins_a) in enumerate(owners):
        for name_b, pins_b in owners[i + 1:]:
            overlap = pins_a & pins_b
            assert not overlap, f"{name_a} and {name_b} both drive GPIO {sorted(overlap)}"


@pytest.mark.parametrize("overrides", SUPPORTED_VARIANTS)
def test_peripherals_never_touch_the_i2s_audio_pins(overrides):
    for name, pins in _claimed_pins(resolve_config_h(**overrides)).items():
        clash = pins & RESERVED_AUDIO_PINS
        assert not clash, f"{name} claims reserved audio GPIO {sorted(clash)}"


def test_spi_panel_and_companion_bridge_cannot_be_built_together():
    # Both want G26/G32; the header must reject the combination outright rather
    # than let two drivers fight over the Grove port at runtime.
    with pytest.raises(FirmwareError):
        resolve_config_h(DISPLAY_TYPE=2, ROBOT_BRIDGE_ENABLED=1)


def test_device_and_server_agree_on_max_packet_payload():
    defines = resolve_config_h()
    assert defines["RX_MAX_PACKET_PAYLOAD"] == protocol.DEVICE_MAX_PACKET_PAYLOAD


def test_device_and_server_agree_on_audio_rates():
    defines = resolve_config_h()
    assert defines["WIRED_TTS_SAMPLE_RATE"] == protocol.WIRED_TTS_SAMPLE_RATE
    assert defines["AUDIO_SAMPLE_RATE"] == 16000


def test_device_and_server_agree_on_wired_baudrate():
    defines = resolve_config_h()
    server_config = yaml.safe_load(SERVER_CONFIG_YAML.read_text(encoding="utf-8"))
    assert defines["SERIAL_BAUD_RATE"] == server_config["connection"]["serial_baudrate"]


def test_shipped_server_config_describes_the_firmware_display():
    defines = resolve_config_h()
    server_config = yaml.safe_load(SERVER_CONFIG_YAML.read_text(encoding="utf-8"))
    declared = server_config["robot"]["display"]["type"]

    assert declared in robot_mode.DISPLAY_TYPE_TO_FIRMWARE, f"unknown display type {declared!r}"
    assert robot_mode.DISPLAY_TYPE_TO_FIRMWARE[declared] == defines["DISPLAY_TYPE"]


def test_shipped_server_config_matches_the_firmware_servo_pins():
    defines = resolve_config_h()
    server_config = yaml.safe_load(SERVER_CONFIG_YAML.read_text(encoding="utf-8"))
    servo = server_config["robot"]["servo"]

    if defines["LOCAL_SERVO_ENABLED"]:
        assert servo["pin_pitch"] == defines["SERVO_PIN_PITCH"]
        assert servo["pin_tilt"] == defines["SERVO_PIN_TILT"]

    assert servo["angle_min"] == defines["SERVO_MIN_ANGLE"]
    assert servo["angle_max"] == defines["SERVO_MAX_ANGLE"]
    assert servo["default_angle"] == defines["SERVO_CENTER_ANGLE"]


def test_companion_bridge_pins_match_the_documented_wiring():
    defines = resolve_config_h(ROBOT_BRIDGE_ENABLED=1)
    companion = robot_mode.DEFAULT_ROBOT_CONFIG["companion"]

    assert companion["tx_pin"] == defines["ROBOT_BRIDGE_TX_PIN"]
    assert companion["rx_pin"] == defines["ROBOT_BRIDGE_RX_PIN"]
    assert companion["baudrate"] == defines["ROBOT_BRIDGE_BAUD"]


def test_preroll_burst_fits_in_one_packet():
    # preroll_send() ships the whole ring buffer in a single AUDIO frame.
    defines = resolve_config_h()
    preroll_samples = defines["AUDIO_SAMPLE_RATE"] * defines["PREROLL_MS"] // 1000
    wifi_payload = preroll_samples * 2
    wired_payload = wifi_payload // 4  # mu-law at half the sample rate

    assert wifi_payload <= protocol._MAX_INCOMING_AUDIO_PAYLOAD
    assert wired_payload <= protocol._MAX_INCOMING_AUDIO_PAYLOAD
