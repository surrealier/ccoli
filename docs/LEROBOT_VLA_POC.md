# LeRobot / SmolVLA 실제 PoC

관련 요구사항: [일상 Physical AI PRD](EVERYDAY_PHYSICAL_AI_PRD.md)의 R14, R15, R17. 기본 음성 서버에는 LeRobot/Torch 의존성을 추가하지 않는다. 공개 모델과 SDK는 별도 Python 3.12 Docker 작업자로 실행한다. 개인 영상, `.env`, 기억 저장소는 이 컨테이너에 마운트하지 않으며 Hub 업로드, 원격 코드 실행, WandB 기록을 사용하지 않는다.

## 고정한 공식 구현

- [LeRobot v0.6.1 release](https://github.com/huggingface/lerobot/releases/tag/v0.6.1), [SmolVLA stable documentation](https://huggingface.co/docs/lerobot/v0.6.1/en/smolvla), [SDK dependency source](https://github.com/huggingface/lerobot/blob/v0.6.1/pyproject.toml).
- 공개 checkpoint `lerobot/smolvla_base` revision `5e8d12a6e2975b0e5e5fce7c8caf47c371d257b6`. [공개 모델](https://huggingface.co/lerobot/smolvla_base/tree/5e8d12a6e2975b0e5e5fce7c8caf47c371d257b6)의 실제 가중치를 읽는다.
- tokenizer/config backbone `HuggingFaceTB/SmolVLM2-500M-Video-Instruct` revision `7b375e1b73b11138ff12fe22c8f2822d8fe03467`. 이미 base checkpoint에 포함된 VLM 가중치를 중복 다운로드하지 않는다. AutoConfig/AutoProcessor는 `trust_remote_code=False`, 모델 로드는 로컬 검증 파일만 사용한다.
- 재현 환경: Python 3.12, `lerobot[smolvla,training,feetech]==0.6.1`, Torch `2.10.0+cpu`, torchvision `0.25.0`, transformers `5.5.0`, torchcodec `0.10.0`. 마지막 두 버전은 v0.6.1 허용 범위와 Torch ABI에 맞춘다. LeRobot Apache-2.0 및 모델 카드의 Apache-2.0 조건을 적용한다.

## 실제로 실행한 증거

아래 결과는 fake SDK 시험과 별도로 공개 450M checkpoint를 읽은 실제 PyTorch 연산이다. 입력은 직접 만든 공개 합성 RGB/관절/언어 fixture이며 실제 집안 카메라나 로봇은 사용하지 않았다. 산출물은 ignored `output/robotics-poc/`와 named volume `vla-dev_vla-model-cache`에만 있다.

| 실행 | 확인 결과 |
| --- | --- |
| CPU 이미지 build | `ccoli-vla:0.6.1`, image SHA `e77be2584b812149384180a4d9db50bee909c6f4fd43fc524d5ee6bedde40142` (초기 PoC 이미지) |
| SDK offline inspection | 실제 v0.6.1 SO101Follower/config import, 6축 및 DEGREES/RANGE_0_100 확인, 연결 false |
| actual inference 3회 | 파라미터 450,046,176; 4.4606 / 4.4000 / 4.4298초; SDK postprocessor 후 이름이 있는 6개 행동 |
| persistent stdio inference | 새 worker를 1회 로드하고 `SubprocessPolicyWorker`로 실제 요청/응답, 4.5581초, `learned_checkpoint` |
| actual optimizer 2 steps | train loss 129.327911 / 125.215767; 분리한 eval episode loss 241.613144 → 240.762085 |
| 저장 checkpoint | SHA256 `54340fadb36afd80b12184abeffaaba2fe41551b17ddc50de23d3cb428a1fd4a` |
| 새 프로세스 eval | 위 저장 가중치/전처리/후처리를 다시 읽고 240.762085, 저장 직전 값과 일치 |
| checkpoint 선택 및 rollback | 학습한 local checkpoint 선택 후 pinned 공개 base로 실제 CLI 되돌림; physical motion은 둘 다 false |

RTX3070 실제 Docker GPU passthrough (`--gpus all`)와 Torch `2.10.0+cu128`의 `cuda.is_available=True`를 확인했다. Driver591.86, VRAM8192MiB다. 별도 이미지 `ccoli-vla-cuda:0.6.1`만 CUDA wheel을 사용하고 CPU 이미지 및 실행 중인 음성/STT 환경은 유지한다. [PyTorch 공식 고정 버전 설치 명령](https://pytorch.org/get-started/previous-versions/), [Docker Windows WSL2 GPU 공식 문서](https://docs.docker.com/desktop/features/gpu/)에 맞춘 opt-in profile이다.

| 추가 실제 CUDA 실행 | 결과 |
| --- | --- |
| 최초 GPU inference | cold 2.697초, 이어서 0.4795 / 0.4891초 |
| public warm-up 후 10회 inference | 0.4128–0.5864초, p50 0.4427초, nearest-rank p95 0.5864초 |
| persistent stdio 3×256×256 RGB 5회 | 왕복 p50 0.6186초 / p95 0.6382초; 공개 fixture, 실제 SDK postprocessed 6축 |
| GPU actual train 2 steps | train loss 116.069328 / 113.509041, held-out124.573364 →116.711952 |
| GPU 저장 checkpoint | SHA256 `4e36adc44b3da95edf54a3f9de68d8a3c465488ac4d9b81ca8f46e0e03a8bdf6` |
| 별도 GPU reload eval | 116.711952로 저장 직전 평가와 일치 |

CPU/CUDA 난수 생성은 같지 않아 두 환경의 loss 절댓값을 성능 우열로 비교하지 않는다. 첫 CUDA 저장은 safetensors의 GPU tensor staging 중 host memory 오류가 났다. 학습 buffer/gradient를 해제하고 CPU tensor에서 SDK save_pretrained를 호출하도록 고친 뒤 새 output에서 학습·저장·별도 재평가가 성공했다. 실패 output도 보존한다. 작은 loss fixture는 실제 작업 성공을 증명하지 않는다.

손실의 작은 변화는 학습/저장/복구 파이프라인 검증이다. 물체 정리 성공률, 정책의 실제 안전성, 새 배치 일반화 성능을 뜻하지 않는다. 현재 `hardware_validated=False` manifest는 실제 실행을 차단한다. CPU 추론 약 4.4초는 기본 2초 관측 freshness 제한을 넘으므로 실제 arm planning을 차단한다. 체크포인트 선택은 모터 활성화와 별개다.

준비된 GPU의 공개 fixture 왕복은 2초 제한 안에 들어왔다. 이는 실제 camera→robot 왕복 시험은 아니다. `serve --device cuda`는 공개 합성 입력으로 warm-up을 끝내고 action queue를 비운 뒤 READY를 내보내며 실제 요청마다 새 관측으로 policy를 reset한다. 시작의 느린 cold action을 실행하거나 warm-up 행동을 모터로 보내지 않는다. 현재 관측 자체의 age와 추론/전달 시간을 합쳐 여전히 2초 이하인지 각 턴에서 검증한다.

## 재현 명령

저장소 루트 PowerShell에서 실행한다. 다른 server/test 작업을 종료하지 않는 독립 project다. Torch/CUDA는 실행 중인 음성/STT 환경에 설치하지 않는다.

```powershell
docker compose -p vla-dev -f docker/docker-compose.robotics.yml build
docker compose -p vla-dev -f docker/docker-compose.robotics.yml run --rm --no-deps policy-worker smoke --output /work/smoke.json
docker compose -p vla-dev -f docker/docker-compose.robotics.yml run --rm --no-deps policy-worker sdk-info --output /work/sdk-info.json
docker compose -p vla-dev -f docker/docker-compose.robotics.yml run --rm --no-deps policy-worker train --steps 2 --output /work/checkpoints/new-synthetic-run
docker compose -p vla-dev -f docker/docker-compose.robotics.yml --profile cuda build policy-worker-cuda
docker compose -p vla-dev -f docker/docker-compose.robotics.yml --profile cuda run --rm --no-deps policy-worker-cuda smoke --device cuda --warmup --samples 10 --output /work/smoke-cuda-warm.json
```

학습 명령은 새 폴더를 요구해 기존 checkpoint를 덮어쓰지 않는다. 생성한 `training_report.json`의 `checkpoint_digest`를 사용한다.

```powershell
docker compose -p vla-dev -f docker/docker-compose.robotics.yml run --rm --no-deps policy-worker eval --checkpoint local:checkpoints/new-synthetic-run --revision <checkpoint_digest> --output /work/evaluation.json
docker compose -p vla-dev -f docker/docker-compose.robotics.yml run --rm --no-deps policy-worker activate --checkpoint local:checkpoints/new-synthetic-run --revision <checkpoint_digest>
docker compose -p vla-dev -f docker/docker-compose.robotics.yml run --rm --no-deps policy-worker activate --checkpoint lerobot/smolvla_base --revision 5e8d12a6e2975b0e5e5fce7c8caf47c371d257b6
```

평가는 학습과 같은 합성 fixture 중 episode 단위로 분리한 eval 샘플을 사용한다. 실제 recording을 평가할 때에는 `--dataset /work/demonstrations.json`을 명시한다. `active-checkpoint.json`은 현재와 직전 checkpoint metadata만 보관한다.

## 관절, 카메라, calibration 계약

[SO follower 공식 소스](https://github.com/huggingface/lerobot/blob/v0.6.1/src/lerobot/robots/so_follower/so_follower.py)의 `use_degrees=True`를 유지한다. 순서는 `shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`, `wrist_roll`, `gripper`다. 앞의 5축은 signed degrees, 마지막은 0–100 percent다. 앱 capability는 `units=mixed`, `joint_units=[degrees,degrees,degrees,degrees,degrees,percent]`다. MCU의 0–180도 servo 계약과 혼합하지 않는다. 실제 사용자 calibration 범위와 native unit/s 속도 제한이 더 엄격하게 적용된다.

[공식 SmolVLA 구현](https://github.com/huggingface/lerobot/blob/v0.6.1/src/lerobot/policies/smolvla/modeling_smolvla.py), [processor](https://github.com/huggingface/lerobot/blob/v0.6.1/src/lerobot/policies/smolvla/processor_smolvla.py)를 사용한다. Base의 state/action feature는 이름이 있는 6축, 내부 padding은 32, action horizon은 50이다. `select_action` → checkpoint postprocessor → `make_robot_action`을 통과한 정확한 6개 이름을 매핑한다. raw 32차원 벡터의 앞부분을 각도로 잘라 사용하지 않는다.

Base는 `observation.images.camera1/2/3` 세 입력을 기대한다. Manifest는 이 feature를 서로 다른 실제 camera source에 연결해야 한다. 빠진 view를 같은 사진으로 복사하거나 합성 화면을 measured로 표시하지 않는다. RGB와 joint는 실제 local driver가 ObservationStore에 등록한 `driver_id`, measured provenance, 2초 이하 age가 필요하다. SDK calibration 파일의 SHA256, profile, SDK motion implementation revision, 6축 이름/단위가 모두 일치해야 한다. `firmware_revision=lerobot-0.6.1`은 이 SDK 구현의 revision이며, 읽지 않은 모터 펌웨어 버전을 뜻하지 않는다.

`SmolVLAAdapter.plan(instruction, observation, robot_state)`는 전체 6축 계획을 범위/속도 검증한 뒤 반환한다. 반환값은 `actions=[{joints:[{servo,angle}],duration_ms}]`, checkpoint revision, joint order/units, `sdk_calibration_id`다. Arm 상태 변경, stale observation, revision/calibration mismatch는 거부한다. 반환된 계획도 core에서 전 궤적을 다시 검증한다.

## 실제 SDK lifecycle와 인간 개입

`SO101Driver`는 공식 `bus.connect`, `disable_torque`, `get_observation`, `calibrate`, `configure`, `send_action`, `disconnect`를 호출한다. 발견 시 `SOFollower.connect()`가 configure 안에서 torque를 다시 켜는 것을 피하려고 공식 bus lifecycle만 사용한다. 연결만으로 arm하지 않는다. 보정된 실제 현재 각도를 목표로 먼저 써 두고 명시적인 arm에서 torque를 켠다. SDK calibration이 없는 새 arm은 normalized measurement도 읽을 수 없으므로 UI framed discover가 measurement_unavailable로 끝날 수 있다. 이를 0도로 꾸미지 않는다.

실제 정상 read가 성공한 뒤에만 measured joint source를 등록하며 disconnect 때 지운다. 모든 local STOP/lease expiry/takeover/SDK 재보정은 이전 session/results/active command를 무효화한다. 따라서 예전 arm command ID로 cached armed:true를 되돌려주지 않는다. Lease 만료는 마지막 command와 연결한 STOPPED telemetry를 보내며, torque IO에 실패하면 성공 대신 ERROR를 보낸다.

새 SO101의 native SDK calibration은 explicit port를 선택한 사람의 interactive session에서만 진행한다. 사람이 torque-off arm을 직접 움직이는 작업이다. 현재 PC에서 이 명령을 실행하지 않았다.

```powershell
# 실제 장치가 준비된 전용 SDK 환경에서만. Linux Docker는 명시적인 --device 연결이 추가로 필요하다.
python scripts/robotics_policy.py sdk-calibrate --port <selected-port> --robot-id ccoli-so101
```

Leader의 실제 [SO101Leader SDK](https://github.com/huggingface/lerobot/blob/v0.6.1/src/lerobot/teleoperators/so_leader/so_leader.py)도 `SO101Teleoperator`가 연결/calibrate/read/close를 수행한다. Leader target은 follower로 바로 보내지 않고 같은 calibrated controller 이동 경로에 넣는다. 인간 takeover는 detach STOP 후 실제 joint를 읽는다. STOP은 epoch를 올리고 arm/lease/limit를 즉시 무효화해 늦은 arm/이동 준비가 다시 활성화하지 못한다. Host watchdog은 lease 만료에 torque-off를 요청하고 IO 오류 후에도 살아 있지만, 죽은 PC/프로세스나 끊긴 USB를 하드웨어 자체가 멈춘다고 검증하지 않았다. 실제 운용 전 독립 전원 차단/E-stop 또는 검증된 bus deadman이 필요하다.

기본 voice runtime은 dependency-free `SubprocessRobotTransport(command, observation_store=...)`를 사용하고 별도 SDK 환경의 `serve-sdk --port <explicit-port>`에 framed protocol을 보낸다. SDK worker는 공개 network listener 없이 stdio만 사용하며 STOP을 일반 명령 queue보다 우선 처리한다. `SubprocessPolicyWorker(command, revision=...)`는 policy의 `serve`에 연결한다. Shell 문자열 대신 argv list를 사용하고, 시작/revision/크기/시간 제한을 검증하며 입력 프레임/발화를 로그로 남기지 않는다.

### Windows COM launcher 계약

Linux Docker의 `--device`에 Windows `COM12`를 넣으면 지원된 serial 연결이 되지 않는다. Windows는 **기본 voice Python과 분리한 Python3.12 SDK venv** 또는 사용자가 실제 USB를 연결한 Linux SDK host가 필요하다. 이 PC에 SO101용 venv/실포트를 설치하거나 연결했다고 주장하지 않는다. 준비되지 않은 환경은 sdk_environment_unavailable, Linux port를 Windows에 넣으면 unsupported_sdk_port로 명확히 거부한다.

Windows의 native SDK 준비 예시(사용자가 해당 장치를 준비했을 때):

```powershell
py -3.12 -m venv output/robotics-sdk
output/robotics-sdk/Scripts/python.exe -m pip install torch==2.10.0 torchvision==0.25.0 --index-url https://download.pytorch.org/whl/cpu
output/robotics-sdk/Scripts/python.exe -m pip install 'lerobot[feetech]==0.6.1'
output/robotics-sdk/Scripts/python.exe -u scripts/robotics_policy.py sdk-info --work-root output/robotics-poc
```

호스트의 port 후보 목록은 후보이며 SO101의 실제 존재를 뜻하지 않는다. 사용자가 port와 so101 profile을 선택하면 host는 `sdk_worker_launch(python_executable, script_path, port='COM12', robot_id=..., work_dir=...)`로 argv를 만들고 `SubprocessRobotTransport(..., observation_store=...)`에 연결한다. READY는 SDK0.6.1이 설치된 별도 process에서만 나온다. Discover는 torque-off SDK bus handshake/read로 실제 상태를 확인한다. Torch를 voice runtime에 import하지 않는다.

Native calibration 버튼은 먼저 STOP/disconnect하고 동일한 SDK interpreter에 `sdk-calibrate --port COM12 --robot-id ... --work-root <same-private-output>`를 **사람이 조작할 수 있는 terminal**로 연다. 보정 완료 후 새 worker/discover, channel 범위 설정, explicit arm 순서다. Noninteractive background process에서 SDK calibration을 완료한 척하지 않는다. Leader teleoperation은 같은 SDK 환경의 `SO101Teleoperator` lifecycle/read_target을 사용하고, 얻은 native named targets를 core의 calibrated move 경로로만 보낸다. 웹 API가 원격 callback/임의 shell/Python 경로를 받도록 하지 않는다. Linux local SDK환경은 `/dev/ttyUSB*`, `/dev/ttyACM*`, `/dev/serial/by-id/*`만 explicit port 후보로 받으며 실제 USB 연결된 Linux worker에만 device 권한을 제공한다.

Windows native lifecycle은 아직 실제 SO101/leader가 없어 실장치 검증 전이다. 플랫폼 launcher/port 거부/측정 source lifecycle/STOP race는 Docker contract regression으로 검증했다.

## 자체 데이터로 학습하고 평가하기

1. 실제 등록 camera/joint driver, SDK calibration, 좁은 작업 공간, 사용자 recording consent를 준비한다. Core EpisodeRecorder의 관측/행동/실패/중단/인간 수정/결과를 로컬에 저장한다. 자동 recording/upload는 없다.
2. 실제 task 성공이 검증된 완료 episode만 고른다. 실패 구간은 label에서 제외하고 실패 자체와 개입은 원본에 남긴다. Train/eval episode ID를 겹치지 않게 나눈다. 최소 약 50 episode는 공식 시작 참고점이며 성능 보장이 아니다.
3. `prepare-episodes --dataset /work/episodes --manifest /work/manifest.json --eval-episodes heldout-one,heldout-two --output /work/demonstrations.json`으로 변환한다. 실제 source는 registered measured/fresh와 calibration binding을 검증한다. Sim episode는 simulated provenance를 보존한다. 현재 core sparse `move_joints` target을 50-step label로 반복하므로 dense 실제 servo trajectory와 같다고 주장하지 않는다. 정밀 조작에는 촘촘한 동기화 teleoperation state/action recording이 추가로 필요하다.
4. `train --dataset /work/demonstrations.json --steps <budget> --output /work/checkpoints/task-run-one`, 별도 process `eval`, 명시적 checkpoint 선택/rollback을 수행한다. 생성된 deployment manifest template은 SHA64 placeholder calibration과 hardware false를 갖는다. 실제 SDK hash/camera source를 연결하고 검증 전 false를 유지한다.
5. 실제 학습/held-out loss와 실제 task 성공은 분리한다. 처음 보는 물체/위치/조명에서 success 판정 센서, 충돌/범위 위반, 개입 횟수, 관측→계획 지연 p50/p95, STOP 시간, 연결 끊김/프로세스 종료를 시험한다. 모든 action의 범위/속도·freshness·calibration binding을 통과한 정책만 해당 hardware/profile에서 검증 상태로 등록한다.

현재 SO101, leader, 실제 3-view camera, measured object detector, 해당 집안 task 학습 데이터는 확인되지 않았다. 따라서 실제 물체 정리 학습 성공이나 실모터 safety를 완료했다고 표시하지 않는다. 현재 결과는 actual model inference/train/save/eval/rollback과 실제 SDK 호출 구현, Docker 계약 회귀까지다.
