# ccoli — 자연스러운 다국어 대화와 일상용 Physical AI PRD

작성: 2026-10-09. 사용자 요청 5개를 모두 보존한다. 완료 판정은 실제 구현·전체 품질 게이트·각 기능의 검증 증거로 한다. 특정 테스트가 쉽다는 이유로 범위를 감정 제스처나 시뮬레이션만으로 줄이지 않는다.

## 원래 요청과 완료 증거

| 요청 | 산출물/완료 기준 | 현재 |
|---|---|---|
| 1. 기존 작업 main merge | 기존 source/docs/tests의 공개 적합성 감사, 최신 main 충돌 통합, 전체 Docker/통신/CLI/펌웨어 게이트, 원격 main SHA 일치 | 완료: daf991b6634be0988d1bb7370c51f707e49021f1 |
| 2. 자연스럽고 짧고 빠른 다국어 대화 | ko/en/zh/ja/es/auto의 STT→LLM→실도구 결과→해당 음성; 동시 화자 언어 격리; 상세 요청 존중; 공개 합성 문장의 정확성·지연 비교 | 부분 구현·검증. 아래 상태/검증 문서 참조 |
| 3. Atom Echo 회사 소개 메일 | 실제 기능에 맞는 짧은 영문 초안과 공식 수신처·출처. 메일 전송은 요청 범위 아님 | M5STACK_EMAIL_DRAFT.md |
| 4. 접근성/편의성 | 음성만/모터/카메라/홈 연결을 버튼 중심 wizard로 분리. 발견→준비물→연결→작은 시험→중단. 설치·토큰·핀·전원 세부는 안내 가능한 단계로 제공 | 부분 구현·검증. 아래 상태/검증 문서 참조 |
| 5. 일상 VLA/RX/Physical AI 계획과 전체 구현 | 아래 R01~R20, 실제 motor/display/양방향 결과, 관측→계획→행동→검증, SDK/VLA inference/학습·평가 경로와 실생활 작업 증거 | 부분 구현·검증. 아래 상태/검증 문서 참조 |

RX는 이 문서에서 장치 발견·설치·조작·시범 학습·결과 확인을 포함한 로봇 사용 경험으로 다룬다. 특정 모델/표준을 가리키는 추가 정보가 있으면 그 요구도 반영한다. 현재 실제로 확인된 하드웨어는 Atom Echo이며 모터/보조보드/카메라 보유 여부를 사용자에게 확인 중이다. 하드웨어 미확인은 소프트웨어와 공개 policy 구현을 중단할 이유가 아니지만 실기 완료 증거를 대신 만들 수는 없다.

## 조사와 선택

- [OpenAI 지연 최적화](https://developers.openai.com/api/docs/guides/latency-optimization): 작은 모델, 짧은 출력, 적은 왕복, 필요한 곳의 결정적 처리. 기존 도구 정확성/실결과 검증을 지연 최적화보다 먼저 보존한다.
- [Gemini 3.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite): 빠른 일반 대화 후보. 기존 Gemini 3.8 Flash와 공개 합성 5언어/도구 평가 후 적용하며, API 계정 성공을 Docker mock으로 대신하지 않는다.
- [LeRobot SmolVLA](https://huggingface.co/docs/lerobot/main/en/smolvla): RGB·로봇 상태·언어에서 행동 chunk를 생성하는 공개 450M policy. 자기 작업 데이터의 fine-tuning이 필요하며 약 50 episode는 시작점이지 성공 보장이 아니다.
- [LeRobot SO-101](https://huggingface.co/docs/lerobot/main/so101): 비휴머노이드 소형 arm의 공개 SDK·calibration·teleoperation 경로. 사용 가능한 실제 embodiment와 검증된 관절 순서를 요구한다.
- [LeRobot HIL](https://huggingface.co/docs/lerobot/main/hil_data_collection): 중단·인간 수정·재개와 recording/evaluation. 자동 Hub 업로드를 하지 않고 명시적 local recording을 사용한다.
- [Gemini Robotics 2](https://deepmind.google/blog/gemini-robotics-2-brings-whole-body-intelligence-to-robots/): VLA의 관측/수치 상태/행동 계층 분리 참고. 제한 접근 모델은 이 프로젝트의 필수 설치 의존성으로 두지 않는다.
- [Physical Intelligence 연구](https://www.pi.website/blog): 실제 실패·수정 경험과 장단기 상태의 가치 참고. 공개 문서 범위를 넘겨 성능을 주장하지 않는다.
- [Stretch 4](https://hello-robot.com/stretch-4/), [SwitchBot Bot](https://us.switch-bot.com/pages/switchbot-bot): 사람 형태보다 좁고 유용한 작업과 쉬운 조작을 우선하는 상용 사례.
- [Atom Echo](https://docs.m5stack.com/en/atom/atomecho), [SG90](https://towerpro.com.tw/product/sg90-analog/), [Waveshare LCD](https://www.waveshare.com/wiki/1.69inch_LCD_Module): 음성 GPIO 유지, 외부 서보 전원·공통 GND, 디스플레이 로직/전원·핀 충돌 검증.

대안 A(선택): 기존 음성 서버 + 작은 robotics core + MCU 로컬 scheduler/stop + 선택적 별도 LeRobot/VLA worker. 음성 기본 설치는 가볍게 유지하고 기존 Atom/Companion을 실제 구동기로 완성한다.
대안 B: LeRobot/torch 전체를 기본 음성 프로세스에 넣으면 손쉬운 import 대신 설치 용량·GPU/추론 지연·권한이 묶인다.
대안 C: 폐쇄 상용 robotics model에 전적으로 의존하면 현재 계정 접근과 재현성이 보장되지 않는다.

외부 SDK 도입은 pin한 버전·license·설치 비용·기존 환경 충돌·실제 공개 checkpoint inference PoC를 기록한 뒤 opt-in으로 적용한다. 대화 LLM이 각도 문자열을 만드는 것만으로 learned VLA 완료라고 부르지 않는다.

## 사용자 경험과 대화 요구

- 기본 첫 화면은 '대화 시작', '언어', '장치 연결', '정지'처럼 짧고 직접적인 조작을 제공한다. Atom Echo만 있어도 대화를 시작할 수 있다.
- UI 언어와 대화 언어를 분리한다. 대화는 auto/한국어/English/中文/日本語/Español을 지원하며 STT 감지 언어를 턴별로 전달한다.
- 기본 답변은 자연스러운 1~2문장, 불필요한 서론/반복/도구 내부 JSON 없이 말한다. 자세히 요청하면 제한을 완화한다. 기억/할 일/행동 결과는 실제 성공·실패에 맞는 같은 언어로 안내한다.
- 빠른 대화 모델은 실제 품질·지연 평가를 통과해야 사용한다. 위험하거나 모호한 액추에이터 요청을 모델의 추측으로 실행하지 않는다.
- 캐싱은 크기/TTL/voice/backend/text/pad로 분리한 메모리 내 TTS와 안전한 동일 요청 병합에 한정한다. 개인 대화·변하는 상태·도구/행동 결과를 이전 최종 답변으로 재사용하지 않는다.
- 홈 연결은 '설치/연결→로그인/인증→허용할 기기 선택→상태 확인/시험'으로 안내한다. 토큰은 마스킹하고 비밀 저장은 공개 YAML과 분리한다. 실제 HA 인스턴스 없는 경우 그 상태를 정확히 표시한다.

## 로보틱스 필수 요구와 검증

| ID | 요구 | 완료 증거 |
|---|---|---|
| R01 | 보드/boot/protocol/서보 수/display/sensors/feedback capability 발견 | 미응답/불일치 board는 연결됨 표시 금지; Docker integration+실제 handshake |
| R02 | disconnected/discovered/configured/calibrated/armed/executing/completed/fault/stopped 상태 머신 | boot/연결 변경 시 calibration/arm 무효화, 자동 재실행 없음 |
| R03 | voice-only·direct1/2서보·companion4서보/LCD·camera·sensor·supported arm 프로필 버튼 | 준비물/배선/전원·GPIO 충돌 검사, 빈 환경도 대화 가능 |
| R04 | 채널별 작은 jog, 방향/영점/범위/속도 calibration과 저장 | bool/NaN/범위 거부, profile/board/firmware revision 바인딩 |
| R05 | command/session/deadline/version/상한 frame와 ACK/RUNNING/DONE/ERROR | 중복 무동작, 다른/늦은 응답 무시, timeout 성공 금지 |
| R06 | 실제 지정 채널 motor scheduler·속도 제한·hold/disable stop | native harness+firmware compile+실제 저속 채널 검사; STOP은 중앙 복귀 아님 |
| R07 | MCU watchdog·deadman·동작 lease·우선 정지 | 서버/케이블 상실 시 local stop; UI stop은 LLM lock을 기다리지 않음 |
| R08 | 실제 LCD 표정·blink/gaze/talking/전환·gesture scheduler | 기존 companion display/servo PRD를 실제 구현; sleep/stop/명령 우선순위 |
| R09 | 서버↔Atom↔Companion 양방향 telemetry/결과 | 동일 command ID의 protocol end-to-end 및 실제 반환 |
| R10 | RGB frame/time·joint/sensor·provenance·calibration snapshot | stale/out-of-order/측정 누락 검사; SG90 목표 각도를 측정 각도로 표시 금지 |
| R11 | observe→plan→validate→execute→observe→evaluate→bounded recovery | 실제 전후조건·실패 주입·정지·retry 상한 |
| R12 | calibrated button press·camera scan·알림 gesture·sensor 조건 actuator·arm의 작은 물체 정리 | 작업별 capability/측정 postcondition, 실제 작업 확인; sim 성공과 분리 |
| R13 | 현재 사용자 명시 의도·armed 상태만 행동 허용 | 5언어 인용/부정/질문 corpus, 모델/영상 지시 주입·임의 숫자 차단 |
| R14 | 실제 지원 nonhumanoid SDK arm adapter(SO101 기본 후보) | 실제 SDK discover/calibrate/teleop/read/send/stop; placeholder 금지 |
| R15 | learned VLA checkpoint inference·RGB/state preprocess·action postprocess | 공개 checkpoint actual smoke; 차원/단위/joint order/revision 검증 |
| R16 | local opt-in episode recording/replay(영상/상태/행동/결과/개입/실패) | 동기화 round-trip·replay 재현·개인 영상 자동 전송 없음 |
| R17 | task training/eval·human correction·checkpoint rollback | 재현 Docker PoC+held-out 작업변형 평가, mock policy로 VLA 완료 금지 |
| R18 | 동일 protocol/state/task runner를 쓰는 no-hardware sim·fault injector | server-test/client-sim/firmware-controller 게이트 단일 스크립트 |
| R19 | action latency p50/p95·observation age·Hz·timeout/stop·success/intervention | 측정된 보고서; 음성/클라우드/모터 지연 구분 |
| R20 | 준비물/BOM/배선/지원 한계/롤백·license/security·운영 문서 | README/QUICKSTART와 실기 증거 표 일치 |

SG90 open-loop 동작 DONE은 명령 진행 완료의 증거이고 실제 접촉·정확한 물리 위치/작업 성공을 증명하지 않는다. encoder/카메라/버튼 상태 등의 관측과 task별 후조건을 별도로 요구한다. 가벼운 물체 정리 기능은 지원하는 arm·카메라·calibration·안전 workspace와 해당 작업 policy가 준비돼야 활성화한다.

## 구현 경계/실행 순서

1. `src/dialogue_policy.py`, AgentMode/ToolAgent/STT: 언어·짧은 답변·voice cache RED→GREEN. 부모는 server.py/RuntimeController/Chat API/설정/UI를 통합한다.
2. `arduino/robot_companion_controller/`, Atom robot_bridge/protocol/servo: motor/LCD/ACK/stop/watchdog RED native harness→실제 펌웨어 빌드. 부모는 Python transport와 status routing을 연결한다.
3. `src/robotics/{models,profiles,controller,safety,observations,task_runner,episodes,policies,drivers}`: capability/state/lease/calibration/관측/실결과→독립 sim/fault injection RED→GREEN.
4. `api_robotics.py`, `api_setup.py`, dashboard: 발견·프로필·작은 시험·정지·Home 안내·대화 설정, 인증/토큰 마스킹/장치 상실 UX를 테스트한다.
5. optional LeRobot/SmolVLA worker와 SO101 adapter: pin된 환경 PoC→actual checkpoint inference→episode recording/replay/train/eval→supported hardware 통합.
6. 실제 PC의 공개 합성 다국어·실기 voice·연결/정지·생활 작업 시나리오·측정 지연·human intervention을 검증한다. 실물 없는 기능을 실기 완료로 표시하지 않는다.

각 작업은 테스트 실패를 먼저 확인하고 작은 구현으로 통과시킨다. 독립 스펙 준수→코드 품질 리뷰 후 전체 `bash scripts/run_docker_tests.sh`와 핵심 CLI 시나리오를 실행한다. 자동 테스트는 Docker만 사용한다. source/docs/tests를 함께 갱신하고 개인 .env/영상/DB/일정/모델은 Git·Docker 기본 이미지에서 제외한다.

롤백: 다국어·fast model은 기존 ko/기존모델 설정으로, 로봇은 stop/disarm 후 voice-only로 복귀한다. firmware 업로드 전 기존 flash를 백업하고 MCU 측 no-arm 기본을 유지한다. 새 calibration/episode 데이터는 코드 롤백과 함께 삭제하지 않는다.

## main 통합 증거 (10/9)

기존 모든 공개 작업을 fdb0f61로 커밋하고 최신 origin/main의 Greenhouse 디자인을 daf991b로 통합했다. 새 심볼·인증·다국어 UI hook·reduced-motion·dark theme 계약을 보존했다. baseline과 통합 후 모두 614 passed/1 skipped, client-sim/dashboard auth smoke 및 firmware4종 성공. 통합 후 CLI exit0, 이미지에 .env/일정/개인 memory 부재를 검사했다. remote main은 daf991b6634be0988d1bb7370c51f707e49021f1과 정확히 일치한다. 새 개선은 codex/everyday-physical-ai에서 수행한다.

## 대화 서버 통합 단계 (10/9)
- server/server.py의 STT 결과 언어를 턴에 보존하고 일반 답변 및 병렬 TTS/전체 재시도까지 같은 언어로 전달한다. 고정 언어는 감지보다 우선한다.
- server/config_loader.py/config.yaml/env.example: 새 기본 auto, 짧은 답변; 기본 라이브러리 fast model은 opt-in으로 비우고, 프로젝트 config는 공개 5언어 실측 후 gemini-3.5-flash-lite를 사용한다. 기존 STT_LANGUAGE 환경 변수도 대화 언어에 적용하며 DIALOGUE_LANGUAGE가 우선한다.
- /api/dialogue/의 부분 변경은 런타임과 파일 저장에 모두 성공해야 성공한다. 설정 파일은 임시 파일 + atomic replace로 저장하고 실패를 호출자에게 전달하며 기존 파일을 보존한다.
- Docker RED→GREEN: 5언어 인식/합성/실패 재시도, model ID 규칙, 설정 저장 실패 롤백, 기존 전체 서버 orchestration·config tests.

## 로봇 화면/런타임 연결 단계 (10/9)
- server/src/robotics/runtime.py: 기본 Atom transport는 미연결. 현재 socket에만 물리는 generation token으로 재연결/늦은 응답을 분리한다. 명시 선택한 simulator는 source=sim으로 같은 core를 사용한다.
- server/web/routes/api_robotics.py: 인증을 요구하는 상태·프로필·발견·범위·동작 허용·작은 시험·정지·작업·local recording API. 보드/프로필 변경은 자동 구동하지 않으며 정지 후 재발견/범위 설정을 요구한다.
- heartbeat/poll은 모델·음성 송출·긴 policy planning과 독립적으로 진행한다. STOP은 task lock을 기다리지 않고 실제 controller에 전달한다. 상태 조회에는 cached task snapshot을 써서 긴 planning 때문에 막히지 않게 한다.
- HTTP로 측정된 센서/영상/관절인 척하는 입력을 허용하지 않는다. 시뮬레이터 이벤트는 simulated로만 저장한다. 신뢰한 native camera/SDK driver의 측정만 실제 후조건 증거다.
- Docker RED→GREEN: 미연결/재연결, 늦은 status, simulation 명령/완료, 비인증·잘못된 숫자/확인 거부, STOP과 길어진 planning, heartbeat 독립성.

### 런타임 독립 리뷰 보완
- 보정 파일은 source/device+firmware hash/profile별로 분리한다. simulator가 실기 설정을 덮지 않는다.
- 교체된 연결의 늦은 policy 오류는 새 연결의 상태를 덮지 않는다. 기록 장치 오류가 heartbeat thread를 종료하지 않으며 우선 STOP 후 비밀 경로 없이 오류 종류만 남긴다.
- SO101 worker source/port/캘리브레이션/teleop 화면은 별도 구현·실기 검증 항목으로 유지한다. 현재 Atom/sim 화면만으로 R14 완료라 하지 않는다.

## 현재 검증 범위와 남은 완료 조건

다국어 정책·턴별 언어·실제 도구 결과·bounded TTS cache, Atom/sim 설정 UI, 양방향 robot transport와 core, firmware watchdog/STOP, HA 연결·기기 선택, 선택 SDK/VLA worker는 구현했다. 공개 Gemini 실측 일반 대화 p50은 primary2251.61ms에서 Lite1028.62ms였다. 실제 공개 450M CUDA fixture inference p50은0.4427초, stdio 왕복 p95는0.6382초였다. 이 수치는 실제 사용자 음성 또는 집안 로봇 작업의 종단 지연/성공률이 아니다.

전체 원래 목표는 진행 중이다. 실제 PC 서버 재기동/새 펌웨어 실기 검증, 모터·보조보드·HA 기기의 확인, SO101/카메라/센서 선택·calibration/teleop의 host UI 연결, 실제 관측과 물체 판정, 생활 작업 데이터/실행/후조건/개입률 검증이 남아 있다. R01~R20 완료를 mock·sim·합성 학습만으로 선언하지 않는다. 단계별 근거와 다음 검증은 [EVERYDAY_PHYSICAL_AI_VERIFICATION.md](EVERYDAY_PHYSICAL_AI_VERIFICATION.md)에 기록한다.