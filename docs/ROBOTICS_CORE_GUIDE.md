# 일상용 로보틱스 핵심 사용·통합 가이드

2026-10-09. 범위: `server/src/robotics/`의 발견·안전 상태·명령·관측·생활 작업·기록·시뮬레이터. 선택 SDK/VLA worker는 별도 계층이며 스크립트 제스처를 learned VLA라고 부르지 않는다.

## 사용자가 할 일

Atom Echo만 있으면 **음성만 사용** 프로필로 대화를 시작한다. 모터와 Home Assistant는 대화에 필수가 아니다. 모터를 추가할 때는 **장치 발견 → 프로필 선택 → 배선/전원 확인 → 각 채널 범위 설정 → arm → 작은 시험** 순서다. 보드가 응답하지 않으면 로봇 연결 완료로 표시하지 않는다.

`direct_1`/`direct_2`는 Atom의 G26/G32 신호와 외부 서보 전원·공통 GND를 사용한다. OLED는 G25/G21을 사용한다. Atom 직결 LCD는 서보 핀과 충돌하므로 모터 4개와 LCD는 `companion_4_lcd` 보조보드 프로필을 선택한다. 각 프로필은 `need_parts`, `wiring`, `power`, `setup_steps`, `capability`를 제공한다. 구체 배선과 BOM은 [기존 로봇 문서](ROBOT_MODE_WAVESHARE_PRD.md)에 있다.

캘리브레이션의 영점은 논리 참조값이며 서보를 움직이지 않는다. SG90은 실제 위치를 읽지 못하므로 혼을 알려진 기준에 맞춰 설치하고 작은 범위부터 확인해야 한다. arm도 중앙 복귀를 수행하지 않는다. **정지**는 현재 위치를 hold하거나 PWM을 detach하며, 중앙으로 움직이는 명령이 아니다. 정지·케이블 상실·새 boot 후에는 발견과 캘리브레이션을 다시 명시적으로 진행한다.

## 상태와 결과 의미

상태는 `disconnected → discovered → configured → calibrated → armed → executing → completed`이며 오류는 `fault`, 정지는 `stopped`다. 프로필을 고른 것만으로 모터를 활성화하지 않는다. 발견은 보드/boot/펌웨어 revision/서보 수/display/feedback/sensors를 확인한다. pending calibration/arm/action 중에는 프로필을 바꿀 수 없다.

모든 명령 API의 반환 `status=pending`은 송신 요청의 기록이다. `ACK`/`RUNNING`/`DONE`/`ERROR`/`STOPPED`를 같은 command/session/boot/seq로 확인한다. `DONE`은 MCU scheduler 완료이며 SG90의 접촉·정확한 물리 위치·생활 작업 성공을 증명하지 않는다. `commanded_angles`와 `measured_angles`를 분리하고, 측정 없는 값은 `measured_angles=null`로 제공한다.

물리 성공은 `physical_success=true`가 되려면 작업 후조건의 실제 측정이 있어야 한다. 검증이 없으면 `null`, 시뮬레이션이면 항상 `false`다. 새 RGB 프레임을 얻은 camera scan은 프레임 수를 따로 보고한다. open-loop 모터나 연결이 확인되지 않은 카메라 마운트에서는 기계적 스캔 성공을 주장하지 않는다.

## 서버 통합 API

`RobotController(transport, clock=time.monotonic, calibration_path=None, observation_store=None)`에서 `transport.send(payload: dict)`가 기존 Python protocol CMD frame을 보낸다. `AtomDriver`는 선택적 `priority_sender`로 정지를 전송하고 `CompanionDriver`도 동일 wire contract를 사용한다. native MCU/SimDriver는 모두 이 controller를 사용한다.

| 메서드 | 의미 |
|---|---|
| `discover()` | 새 session·seq를 만들고 bootstrap 발견. 이전 arm/calibration 무효화 |
| `configure(profile_id)` | 실제 capability에 맞는 프로필 선택 |
| `calibrate(channels)` | 선택한 채널 전체의 영점·방향·범위·속도 검증과 적용, 동작 없음 |
| `arm()` | 캘리브레이션 후 명시 활성화, lease 2000ms |
| `move(servo, angle, duration_ms=1000, expected_session=None)` | 지정 채널만 이동, 범위·속도 검사 |
| `move_joints(joints, duration_ms=1000, expected_session=None)` | SO-101의 전체 6축을 선검증한 뒤 한 명령으로 전송 |
| `gesture(id, intensity=.3, expected_session=None)` | whitelist·보정 범위 내 4/5단계 preset, 최대 5초 |
| `stop(mode='detach')` | normal dispatch/model lock 우회, session/calibration 안전 무효화 |
| `heartbeat()` / `request_state()` | lease 갱신 / 실제 장치 상태 요청 |
| `accept(packet)` | PTYPE_ROBOT_STATUS 0x14 JSON 상태를 검사·반영 |
| `poll()` / `disconnected()` | timeout/lease 검사와 실패 정지 / 연결 상실 무효화 |
| `snapshot()` | 상태·capabilities·feedback·SDK calibration hash·결과·측정 metrics |

정상 명령은 seq 할당부터 송신까지 직렬화한다. 정지는 그 dispatch lock을 우회한다. pending은 32개, 최근 command ID는 64개, latency 표본은 256개 이하로 제한한다. 다른/늦은 응답과 중복 완료는 재실행하지 않는다. 현재 command의 장치 ERROR나 SDK calibration 변경은 state lock을 해제한 다음 priority STOP을 보내고 오류 사유를 유지한다. profile generation과 session을 최종 dispatch까지 묶어 오래 걸리는 policy가 정지 후 새 arm을 재사용할 수 없다.

wire metadata는 최대 **2048 bytes**, v1, command/session IDs 48자 이하, seq uint32 양수, valid_for/lease 1..2000ms다. 모든 op에 `lease_ms`가 있다. gesture에는 `duration_ms`를 보내지 않고 같은 MCU preset으로 예상 deadline을 계산한다. host는 약 500ms마다 heartbeat하고 MCU는 host 없이 lease 만료 정지를 수행한다. RGB는 이 UART packet에 넣지 않는다.

## 캘리브레이션과 SO-101 단위

채널마다 `servo`, `min_angle`, `max_angle`, `center_angle`, `max_speed_dps`, `inverted` 여섯 필드를 정확히 받는다. 채널 순서는 0..N-1이며 bool/NaN/Infinity·역전 범위·초과 속도를 거부한다. MCU는 0..180도, 속도 1..90도/초, 이동 1..5000ms다.

SO-101은 capability `units=mixed`, `joint_units=[degrees,degrees,degrees,degrees,degrees,percent]`로 실제 SDK 단위를 보존한다. 5축 signed degrees의 outer bound는 -180..180, 그리퍼 percent는 0..100이며 개별 안전 범위는 이보다 좁게 보정한다. 레거시 API key `max_speed_dps`는 SO-101에서 각 축의 **native unit/초** 값으로 해석되며 실제 단위는 `joint_units`가 명시한다. 그리퍼를 가짜 degree로 변환하지 않는다.

물리 SO-101 arm은 SDK encoder calibration의 SHA256 `sdk_calibration_id`가 있어야 한다. policy는 revision·관절 순서·joint units·SDK calibration hash를 정확히 일치시켜야 한다. 액션 chunk 전체의 숫자·차원·순서·속도·범위를 첫 이동 전에 검증한다. base checkpoint inference PoC와 실제 작업에 검증된 policy를 구분한다.

`calibration_path`를 명시한 경우에만 로컬 파일을 저장한다. `saved_calibration()`은 device/revision/profile/채널/SDK hash schema를 검증한 **재적용 자료**다. `boot_matches`와 `requires_reapply=true`를 반환한다. 다른 boot에서도 같은 보드·revision 자료를 다시 선택할 수 있지만 자동으로 calibration이나 arm이 되지 않는다. 개인 runtime 경로를 Git/Docker build에 넣지 않는다.

## 관측과 신뢰 경계

`ObservationStore`는 RGB/joint/sensor/objects 종류별 source ID·sequence·로컬 monotonic 캡처/수신 시각·provenance·calibration snapshot을 보존한다. 기본 유효 시간은 2초이며 오래된/순서 역전/미측정 관측을 거부한다. 기본 `snapshot()`에는 RGB pixel array가 없고 `include_frames=True`가 명시된 내부 기록에서만 포함한다.

실제 드라이버 초기화 후 `register_source(kind, source_id, driver_id=<확인한 로컬 장치>, provenance='measured')`로 출처를 묶는다. 등록 전 caller가 단순히 `measured`로 적은 값은 물리 후조건에 사용할 수 없다. 등록 시 기존 관측을 지우므로 새로운 드라이버 sample이 필요하다. `update(kind, id, data, sequence=..., provenance=..., captured_at=..., calibration=...)`는 출처와 순서도 검사한다. `unregister_source()`는 연결이 끝난 출처를 제거한다. **HTTP 사용자 JSON에는 measured 등록/업로드 경로를 열지 않는다.** manual/sim 입력은 `simulated`로 표시하고 실제 driver의 source를 덮어쓰지 못하게 한다.

RGB는 `{frame_id,width,height,rgb:[uint8...]}`, joint는 `{angles:[...]}`, objects는 `{objects:[{id,location,confidence}]}`다. RGB dimension/pixel·전체 크기·source 수를 제한한다. SO-101 joint 관측의 calibration binding은 `{firmware_revision,joint_order,profile_id}`이고 실제 robot state의 boot/캘리브레이션/SDK hash도 episode에 함께 보존한다.

## 생활 작업 실행기

`TaskRunner(controller, observations, policy=None, recorder=None).start(skill, params, authorized=True)`와 `tick()/stop()/snapshot()`을 사용한다. 현재 사용자의 명시 요청이 필요하며 모델/이미지의 지시나 인용·부정·질문에서 각도를 만들지 않는다. 5언어 whole-turn stop/gesture corpus를 검사한다.

| 작업 | 선조건 | 완료 증거 |
|---|---|---|
| `button_press` | 보정한 채널, 신뢰 센서의 현재 pressed=false | press 뒤 새 pressed=true, release 뒤 새 pressed=false |
| `camera_scan` | 최대 8개 보정 각도, 카메라 source | 각 이동 완료 뒤 새 RGB. 물리 기계 성공에는 측정 위치와 보드/boot/채널에 묶인 camera mount 정보 추가 |
| `notification` | arm·보정, 작은 whitelist gesture | scheduler DONE. 물리 자세가 측정되지 않으면 물리 성공은 unknown |
| `sensor_actuation` | 신뢰 센서의 현재 값이 설정 threshold 초과 | 이동 뒤 신선한 measured joint target 확인 |
| `object_tidy` | SO-101/측정 feedback/검증 policy·fresh RGB/joint/object | 대상 물체가 지정 destination에 있고 confidence≥0.8인 새 실제 관측 |

흐름은 observe→plan→전체 validate→execute→observe→evaluate다. 후조건은 완료 후 새 sequence/캡처 시각을 요구한다. task는 60초, policy 최대 16 chunk, postcondition 대기는 1초로 제한한다. 버튼 접촉 확인 실패는 한 번의 저속 retraction만 허용하고 완료 후 정지한다. 자동 재arm/반복 press는 하지 않는다. 사람의 정지는 policy inference lock을 기다리지 않는다.

시뮬레이터의 `simulated` sensor/RGB도 같은 선후조건을 통과해야 한다. 성공해도 실제 물리 성공이 아니며 `physical_success=false`다. 실제 하드웨어가 없거나 policy/센서가 준비되지 않은 작업은 missing/unsupported reason을 유지한다.

## 로컬 episode와 replay

`EpisodeRecorder(directory, enabled=False)`는 기본 꺼져 있다. 명시 opt-in 후 start/record/finish/load로 RGB·로봇 상태·캘리브레이션·command ID·액션·결과·실패·인간 개입을 같은 monotonic 시간축에 저장한다. event 순서·크기·경로를 검증하고 API key/token/password/audio/transcript field는 기록하지 않는다. 자동 업로드는 없다. 저장 실패 시 `abort(reason)`은 기록을 즉시 비활성화하고 부분 episode에 aborted 결과를 붙여 최대 129 MB의 로컬 파일로 atomic 저장을 시도한다. 디스크 오류가 나면 원래 관측·액션 이벤트를 한 개의 pending episode로 메모리에 보존하며 예외를 안전 루프로 내보내지 않는다. 반환값은 `enabled`, `episode_id`, `saved_locally`, `preserved_in_memory`, `recovery_required`다. `load(id)`는 이 pending 기록도 읽고 `recover_aborted()`는 재저장을 시도한다. 복구 전 새 opt-in/episode 시작을 거부하므로 후속 기록이 이를 덮어쓰지 않는다. 디스크 저장에 실패한 메모리 기록은 현재 프로세스가 유지되는 동안만 보존된다.

`replay_episode(episode, sink, allow_actions=False)`는 검증된 관측/개입 이벤트를 재생하며 액션은 기본 건너뛴다. `allow_actions=True`는 액션 이벤트를 sink로 제공할 뿐 모터를 직접 움직이지 않는다. 실제 재실행을 제공하는 caller는 새 calibration/arm/session으로 기존 액션을 현재 controller의 검사에 다시 통과시켜야 한다. 옛 wire packet을 그대로 보내지 않는다.

## 검증과 측정

전체 Docker single entrypoint는 `bash scripts/run_docker_tests.sh`다. core를 개발할 때 기존 production runtime/private 설정을 mount하지 않고 src/tests와 공개 C++ header/harness만 read-only mount했다. g++는 test image에만 설치된다.

```bash
docker compose -f docker/docker-compose.test.yml run --rm --build server-test \
  pytest server/tests/test_robotics_core.py server/tests/test_robotics_wire.py -q
```

2026-10-09 targeted gate: **97 passed**. RED→GREEN으로 capability/state/숫자/protocol/fault injection/정지·profile·policy races/5언어 intent/실후조건/기록과 replay를 검증했다. `test_robotics_wire.py`는 production `CcoliRobotControl.h`를 g++로 실제 컴파일한 뒤 C++ --wire subprocess와 Python controller를 연결한다. C++ native harness는 enabled output·inversion·duplicate·malformed·subset calibration·STOP·lease·rollover도 assertion으로 검사한다.

측정 예시: compiled MCU no-hardware, 250ms 지정 이동 5회, ACK/DONE 수신까지 p50 **0.254007s**, p95 **0.254297s**, priority STOP 상태 수신 **0.000202s**, timeout 0. 이 수치는 PC native C++ 모델의 통신·scheduler 시험이며 USB 실모터 지연이나 물리 작업 성공을 대신하지 않는다. `snapshot().metrics`는 nearest-rank p50/p95·timeout·stop latency·수신 telemetry Hz, observation snapshot은 source age/Hz, task snapshot은 성공/실패/개입 건수를 제공한다.

실기 완료는 모터/전원/카메라/센서/팔의 실제 발견과 저속·정지·작업 후조건을 별도로 기록해야 한다. 현재 targeted gate만으로 해당 실물 장착이나 task 성공을 주장하지 않는다. 롤백은 정지 후 voice-only로 복귀하고 보정·episode 자료는 삭제하지 않는다.