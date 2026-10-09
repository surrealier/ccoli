# Everyday Physical AI verification — 2026-10-09

This record preserves all five user requests in [the PRD](EVERYDAY_PHYSICAL_AI_PRD.md). The original previous-work merge is already on remote main at `daf991b6634be0988d1bb7370c51f707e49021f1`, including the new icon. The subsequent work is on `codex/everyday-physical-ai`. This increment does not complete every physical-hardware acceptance criterion.

## What changed

- Conversation: per-turn ko/en/zh/ja/es/auto, short natural replies with detail-request handling, multilingual tool messages, separate fast model, bounded memory TTS cache/singleflight. Voice and web chat share one dispatch path; ordinary robot-mode conversation no longer adds a classifier call.
- Setup: authenticated conversation, Atom/simulator discovery/profile/calibration/jog/arm/STOP, local recording, and existing Home Assistant connection/selected-light-and-switch controls. Private HA credentials and atomic temporary files are excluded from Git/Docker. HA discovery has a cancellable hard wall deadline in a fixed subprocess.
- Robotics: capability-bound core, session/deadline/result validation, observation provenance, tasks with actual postcondition requirements, local episode recovery, bidirectional status, MCU movement/display scheduler and watchdog. Runtime storage failure stops/disarms, preserves an active episode, and keeps its safety loop alive.
- Optional learned policy: pinned LeRobot0.6.1/SmolVLA, named joint/unit/calibration/camera checks, separate SDK/policy stdio workers, public checkpoint inference, training/evaluation/checkpoint rollback. Native Windows COM launch validation is implemented, while host UI/hardware setup remains unfinished.
- M5Stack: [email draft and official recipient](M5STACK_EMAIL_DRAFT.md); no message sent.

## Evidence and limits

| Check | Evidence | Limit |
|---|---|---|
| Root runtime + actual framed socket dialogue | Docker47 tests passed; independent spec then quality review passed | Public fake STT/model/TTS and simulated actuation |
| Home Assistant | Docker78 tests; independent review passed, including slow HTTP headers, cancellation, helper reap, token-safe errors | No actual HA instance or allowed device exercised |
| VLA/SO101 contracts | Docker31 tests; race/measurement/launcher checks | No connected SO101/leader/three-view cameras |
| Public Gemini comparison | Exactly20 provider calls; both models10/10 valid responses; ordinary5-language p50 primary2251.61ms, Lite1028.62ms | LLM HTTP completion only; small sample, separate factual-accuracy work remains |
| Actual learned inference/training | CUDA model p50 .4427s/p95 .5864s; stdio p95 .6382s; 2 optimizer steps, new-process eval, checkpoint rollback | Public synthetic RGB/joints/tasks; no household task success |
| Firmware | Six variants compiled; native sanitizer harness passed; independently reviewed13 source hashes match final build | New firmware not yet flashed/tested on this Atom Echo |
| Full Docker entrypoint | Frozen-source run:900 passed/1 skipped in32.69s; client-sim, dashboard auth/setup, native firmware harness, all6 firmware variants passed; exit0 | Does not substitute for actual device acceptance |

Detailed experiment inputs, model hashes and bounds: [dialogue](DIALOGUE_LATENCY.md), [VLA](LEROBOT_VLA_POC.md), [core](ROBOTICS_CORE_GUIDE.md), [wire](ROBOT_FIRMWARE_PROTOCOL.md), [HA](HOME_SETUP.md). Private `.env`, audio/video, memories, calendars, robotics data, model weights, and checkpoints are not committed.

## Remaining acceptance work

1. Intentionally restart the actual PC runtime with the new routes, back up flash and deploy reviewed firmware, then verify actual Atom handshake/status and five-language speech/audio. Static changes alone do not prove the running process imported them.
2. Obtain actual motor/controller/camera/HA hardware details and run explicit low-speed channel, STOP, cable-loss, watchdog and confirmed task-postcondition checks.
3. Connect native SDK installation/port selection, interactive calibration/teleoperation, measured camera/sensor capture, and policy selection to the host wizard. A profile entry is not a working SDK connection.
4. Gather consented synchronized local demonstrations, held-out household task variants and actual success/intervention/latency reports. Open-loop DONE, synthetic loss, or simulation success cannot complete R12/R17/R19.

## Rollback

Set conversation language and fast-model settings back through the authenticated dialogue controls, retaining the primary chain. Stop/disarm before selecting voice-only or reverting the code. Restore the previous firmware backup if needed. Preserve private calibration/episode data during code rollback. Disconnect HA through its setup panel to clear credentials and disable home tools. Select the pinned base checkpoint for policy rollback; checkpoint selection alone never arms a robot.
## Final reproducible gate for this increment

```bash
COMPOSE_PROJECT_NAME=robotics-push bash scripts/run_docker_tests.sh
docker run --rm robotics-push-server-test ccoli --help
```

Both returned exit0. The standard Compose entrypoint built fresh images, ran all900 server tests (one existing hardware-dependent integration test skipped), client-sim, Node dashboard authentication/setup controls, the native firmware harness, and4 Atom+2 companion variants. M5GFX emits an upstream deprecated board_M5Atom warning; compilation succeeds. Server image `sha256:4bf5978c19a49f4584cc78c0491d72425f4164a9703efde1ee8b12ee9b8dc82c`; firmware image `sha256:0a42896f55b00a67b6dc6a35c3690dc4398a4f616adcd31713c4af07f21094b1`. A separate container checked absence of private .env/device credentials, memory/logs/calendars, SQLite, robot data, HA store/tempfiles, models/output and Git metadata. Public staging path/fingerprint checks and `git diff --cached --check` passed.

Independent specification then quality reviews passed for firmware/core/SDK/multilingual runtime, HA deadline, active-episode recovery, dashboard disconnect and final documentation. The API network tests and model experiments retain the limitations in the table above. Logs remain local at ignored `artifacts/test-logs/`.