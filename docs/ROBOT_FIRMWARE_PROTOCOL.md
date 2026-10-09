# Robot firmware protocol v1

2026-10-09. Shared controller: `arduino/libraries/CcoliRobotControl`.
The Atom Echo remains the microphone/speaker. Optional direct servos or an
ESP32 companion add physical output. Firmware compilation and a simulator do
not prove that a motor, camera, sensor, or companion is connected.

## Install and wiring

Copy `arduino/libraries/CcoliRobotControl` to the Arduino sketchbook's
`libraries/CcoliRobotControl` directory, or use Arduino CLI
`--libraries arduino/libraries`. Install ESP32Servo; the LCD build also needs
Adafruit GFX and Adafruit ST7735/ST7789. Docker includes these dependencies.

Atom direct: GPIO26 is channel0, GPIO32 channel1, external servo power and
common GND. DISPLAY_TYPE2 uses both pins and advertises zero local servos.
ROBOT_BRIDGE_ENABLED1 also disables local output. No motor is attached or
written at boot, calibration, or arm.

Companion reference is an ESP32 DevKit with accessible GPIO pins, not another
Atom Echo pin map:

| Connection | GPIO |
|---|---|
| Atom G26 TX → companion RX | 16 |
| Atom G32 RX ← companion TX | 17 |
| Servo0/1/2/3 signal | 13 / 14 / 25 / 26 |
| LCD CLK/DIN/CS/DC/RST/BL | 18 / 23 / 5 / 21 / 22 / 19 |
| Normally-open local stop button to GND | 27 (INPUT_PULLUP) |

Connect both board grounds. Give SG90 motors a separate appropriate 5V power
rail; do not draw four motors from the Atom's USB rail. LCD supply and logic
use 3.3V. Do not connect external 5V to an ESP32 GPIO or backfeed board power.
Physically mount the unloaded mechanism and set a conservative neutral position
before calibration. An SG90 has no external encoder: the software's initial
center is an operator reference, not an observed physical angle.

The Docker companion target defaults to `m5stack:esp32:m5stack_core`, proving
the ESP32 architecture/adapters compile. For an actual DevKit upload choose
its Espressif board target using `COMPANION_FQBN` and install that board core.
Target-specific boot/flash and physical wiring remain hardware gates. Do not
upload the companion sketch to the user's Atom Echo: its GPIO map conflicts
with Atom audio.

## Framing and commands

PC ↔ Atom uses the existing three-byte header: type uint8, payload length
uint16 little-endian, then the payload. CMD=0x11 carries UTF8 JSON.
ROBOT_STATUS=0x14 returns JSON up to 2048 bytes. Audio formats/rates and
MIC_LOCK/MIC_UNLOCK are unchanged. Camera images never travel over robot UART.

Atom ↔ companion uses one bounded JSON object followed by newline at 115200
baud. Oversized/null-containing lines are discarded through newline. Partial
companion commands expire after 250ms. The Atom bounds its incoming packet
poll to 5ms and companion receive work to 256 bytes per iteration, keeping
audio, button checks, and the local control loop serviced.

Common command fields, all required:

```json
{
  "cmd": "ROBOT_CONTROL", "v": 1, "op": "discover",
  "command_id": "unique-command", "session_id": "new-session",
  "boot_id": "", "seq": 1, "valid_for_ms": 2000, "lease_ms": 2000
}
```

command_id/session_id/boot_id use ASCII letters/digits/dot/colon/hyphen/underscore,
max48 characters. Only bootstrap discover and stop may use empty boot_id.
seq is integer1..4294967295 and increases per session. New discover creates a
disarmed session, clears calibration, and supplies the current boot_id.
Unknown/duplicate JSON members, wrong types, malformed UTF8/JSON, unknown fields,
non-finite numbers, and unsupported operations cannot actuate.

| op | Additional fields | Completion |
|---|---|---|
| discover | none | DONE + capabilities |
| calibrate | channels array | DONE; no PWM output |
| arm | none | DONE; no PWM output |
| move | servo, angle, duration_ms | ACK, RUNNING, DONE |
| gesture | id, intensity | ACK, RUNNING, DONE |
| heartbeat | none | DONE, renews active lease |
| state | none | DONE + capabilities |
| stop | mode: detach or hold (default detach) | STOPPED |

Calibration example (repeat only for the channels in the selected profile):

```json
{"servo":0,"min_angle":20,"center_angle":90,"max_angle":160,"max_speed_dps":45,"inverted":false}
```

Channels are unique zero-based indexes, with min < center < max inside0..180;
max_speed_dps is finite1..90 and inverted is a bool. One-channel profiles are
supported on two/four-channel boards; unconfigured channels cannot move.
Firmware stores calibration in RAM. The server persists the user-approved
profile bound to device/boot/firmware revision and explicitly reapplies it;
a reconnect never auto-arms or repeats a movement.

move duration is integer1..5000ms. Requested travel must fit the calibrated
angle and speed envelope. The controller interpolates without blocking,
applies direction inversion only at physical output, and returns logical
commanded angles. It rejects concurrent move/gesture with busy. A scheduler
gap over250ms stops instead of catching up with a sudden jump.

Gesture IDs: farewell_wave, goodnight_settle, curious_tilt, happy_bounce,
hurt_turnaway, idle_stretch, notification_nod, camera_scan. intensity is
finite0..1. Their small calibration-relative trajectories use only configured
channels and respect calibrated speed/angle limits. Sequence length is explicit;
zero delay no longer doubles as an accidental end marker.

## Lease, stop and returned state

valid_for_ms and lease_ms are integer1..2000ms. PC/MCU wall clocks are not
comparable, so firmware does not trust a PC epoch timestamp. Commands execute
immediately with boot/session/monotonic-sequence checks; there is no deferred
command queue. The server must enforce its own request deadline and send
heartbeat at most500ms apart while armed. Received arm/move/gesture/heartbeat
renews the MCU lease. A lease expiry locally detaches all PWM and invalidates
session and calibration. A frame arriving after expiry cannot re-arm.

The integrated Atom button stops direct motors or sends a companion stop;
holding it prevents new controls from being forwarded/accepted. The companion
GPIO27 button stops locally and refuses controls while held. Use a directly
wired companion stop button for a physical mechanism; an Atom UART stop still
takes link transmission time. Prototype software is not certified functional
safety and cannot replace appropriate physical power isolation or feedback.

STOP bypasses session/boot/seq checks solely to stop. detach removes PWM;
hold leaves the last output unchanged. Neither mode recenters the mechanism.
Both invalidate arm/session/calibration and caches. Explicit rediscover →
calibrate → arm is needed afterward. On a foreign/local bridge stop, firmware
also reports STOPPED/external_stop for the interrupted or last-known command
so the server can recognize the physical stop immediately.

Same last command ID/seq resends its cached status without re-execution.
A bounded16-ID history rejects changed-ID reuse, and monotonic seq rejects
older frames outside that cache. A new boot_id and session make old-session
frames unusable.

Response example:

```json
{
  "v":1,"status":"DONE","op":"discover",
  "command_id":"unique-command","session_id":"new-session",
  "boot_id":"random-boot","seq":1,
  "armed":false,"calibrated":false,"busy":false,
  "commanded_angles":[90,90],"feedback_kind":"commanded",
  "capabilities":{
    "device_id":"atom-hardware-id","boot_id":"random-boot",
    "controller":"legacy_direct","firmware_revision":"robot-control-1",
    "protocol_version":1,"servo_count":2,"display":"none",
    "feedback_kind":"commanded","sensors":[]
  }
}
```

Statuses: ACK/RUNNING/DONE/ERROR/STOPPED. DONE means the commanded scheduler
finished; it does not prove that a servo moved accurately, a button was pressed,
or a household task succeeded. No measured_angles are invented. sensors is
empty until a real sensing adapter is implemented/verified.

Stable error strings include invalid_json, invalid_fields, unknown_op,
unknown_field, invalid_move, invalid_stop, invalid_gesture, invalid_calibration,
boot_mismatch, session_mismatch, stale_seq, command_id_reused, duplicate_command,
duplicate_expired, must_disarm, channel_mismatch, no_servos, not_calibrated,
not_armed, busy, angle_limit, speed_limit, unknown_gesture, gesture_duration_limit, lease_expired,
scheduler_stalled, physical_stop, peer_lost, legacy_stop, external_stop.

Legacy ROBOT_STATE/ROBOT_EMOTION still update display/LED. Unscoped legacy
SERVO_SET/ROTATE/EMOTION motor packets are retired; they cannot bypass explicit
ROBOT_CONTROL authority. Their wrapper APIs intentionally generate no motor
output. Legacy STOP remains a fail-safe stop. The servo index is parsed correctly
instead of silently selecting channel0.

## Display and validation

The companion LCD drives a real ST7789 240x280 over hardware SPI: neutral boot
face, blink3..7s, gaze5..12s, eased eyelids/gaze, emotion brows/mouth, talking
pulse, sleepy yawn and sleep suppression. Legacy state is display-only and
cannot cause a motor gesture. Motion is supplied through explicit v1 gesture
commands; idle animations do not autonomously arm or drive an actuator.

Docker gates:

```bash
docker compose -p firmware-dev -f docker/docker-compose.test.yml run --rm --build firmware-build
docker compose -p firmware-dev -f docker/docker-compose.test.yml run --rm --build server-test pytest -q server/tests/test_robot_firmware_contract.py server/tests/test_firmware_config.py
```

The firmware service compiles all four existing Atom variants plus companion
LCD-on/off variants and runs the same shared controller natively with ASAN/UBSAN.
The native harness exercises no-arm boot, real interpolation/inversion,
duplicates, invalid schemas/numbers, subset channels, speed limit, gestures,
STOP hold/detach, late-session protection, lease expiry including uint32 wrap,
and parser fuzz fixtures. Its optional --wire mode accepts v1 JSON on stdin and
emits statuses on stdout with a realtime5ms tick; it is explicitly a simulation
without motors, suitable for Python/MCU contract round trips.

10/9 evidence: native RED missing-header failure before implementation,
then native ASAN/UBSAN GREEN; Docker contract/config20 tests pass; first complete
Atom4 + companion2 compilation passed. Final source rebuild and independent
review are required after any subsequent edits. No firmware was flashed and no
physical companion/motor/LCD result is claimed. Hardware gate: channel-specific
unloaded jog, measured stop/lease-loss response, real LCD behavior, cable/boot
recovery, then sensor-confirmed household task postconditions.

## Atom connection-loss safety boundary

The Atom loop must run its local button/watchdog/bridge pump before connection
management and every disconnected early return. Connection retries remain on the
same loop owner; no competing task may call the controller. A detected Wi-Fi/TCP
loss immediately detaches direct PWM and forwards a companion STOP. Wi-Fi retry
settling is split into 5ms pump intervals. TCP reconnect uses only a numeric
SERVER_IP and a 100ms socket-connect timeout, avoiding a blocking DNS lookup.
Disconnected idle waits likewise pump every 5ms. Successful reconnect does not
restore calibration or arm; rediscovery and explicit calibration/arm are needed.

Regression gate compiles the actual connection.cpp against native Arduino/Wi-Fi
fakes, arms the shared controller, then injects TCP/Wi-Fi loss and retry waits.
It must observe detach before the network retry and safety pumping during the
settling wait. A source integration assertion binds the pump to the real Atom
loop before its transport/server early returns. Physical button/stop latency
still requires the unloaded hardware gate above.
ROBOT_STATUS callbacks only enqueue into a fixed four-frame queue; transmission
runs outside controller calls. Queue saturation retains the newest states.
Wi-Fi send uses the socket's nonblocking MSG_DONTWAIT API with a 20ms budget;
send-buffer backpressure pumps safety each millisecond and aborts the socket,
invalidation/detach included, instead of waiting in WiFiClient.write retries.
USB Serial writes use available buffer space and at most64-byte chunks, pumping
between chunks; successful partial chunks continue the same packet without
truncating ordinary audio frames. This preserves a single controller owner and
avoids network-triggered recursive controller callbacks.
## Final compiled snapshot evidence (2026-10-09)

Docker firmware image
`sha256:02c0e4c348c7d31a629bc960a51806bd052605a8abf71dae72d4cea9e11050dd`
completed the full build with exit0 after the connection-safety, bounded TX,
status queue and30s companion speech TTL changes. Thirteen public adapter/shared
controller/native-harness source SHA256 values in that image match the checkout.
No credential file is included in the source-hash record. Local evidence files
are `output/firmware-dev-final-v2-build.log`,
`output/firmware-dev-final-manifest.json` and
`output/firmware-dev-image-source-hashes.txt`.

| Compiled target | Program bytes | Static RAM bytes |
|---|---:|---:|
| Atom default | 962577 | 92852 |
| Atom SSD1306 | 977341 | 92916 |
| Atom ST7789V2 | 969993 | 92908 |
| Atom companion UART bridge | 971165 | 95052 |
| Companion LCD off | 302185 | 28040 |
| Companion LCD on | 323829 | 28716 |

Toolchain: m5stack ESP32 core2.1.2, M5Unified0.2.25, M5GFX0.2.32,
ESP32Servo3.2.1, AdafruitGFX1.12.6, BusIO1.17.4, ST7789library1.11.0.
The ASAN/UBSAN native controller gate also passed. Docker contract/config22tests
include the actual connection.cpp native loss/backpressure gate. These are
compile/simulation results; physical feedback accuracy, stop latency, companion
wiring/display and household task outcomes remain separate hardware checks.
Any further firmware edit requires another matching compiled snapshot.