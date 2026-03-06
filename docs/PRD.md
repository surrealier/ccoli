# ccoli Product Requirements Document (PRD)

## 1. 문서 목적
이 문서는 `ccoli` 프로젝트의 제품 요구사항을 단일 기준으로 관리하기 위한 PRD다.
- 프로젝트의 목적/문제정의
- 현재 제공 기능(Current State)
- 향후 기능(Roadmap)
- 품질 기준(테스트/운영)
- 릴리즈 판단 기준(DoD)

> 원칙: 기능 계획(Planning)은 PRD를 기준으로 파생되며, 구현보다 PRD 업데이트를 선행한다.

---

## 2. 제품 개요

### 2.1 제품명
- `ccoli`: Atom Echo ESP32 + Python 서버 기반 음성 에이전트

### 2.2 문제 정의
- 메이커/개발자가 임베디드 음성 디바이스와 LLM 백엔드를 빠르게 연결하고 실험하기 어렵다.
- 로컬 환경 편차로 인해 재현 가능한 테스트/검증 경로가 부족하다.
- 기능 확장(날씨/검색/캘린더/알림/지도 등) 시 연동 규약과 오류 처리 방식이 분산되기 쉽다.

### 2.3 제품 목표
- ESP32 음성 입력을 안정적으로 서버로 전달하고, STT→LLM→TTS 파이프라인으로 응답한다.
- Agent/Robot 모드를 분리해 실험/확장을 용이하게 한다.
- Docker 기반 테스트 표준을 확립해 개발/CI 재현성을 높인다.

### 2.4 비목표(현 단계)
- 운영 환경 전체를 즉시 컨테이너로 전환하지 않는다.
- ESP32 실물 플래시 자동화를 강제하지 않는다(초기에는 시뮬레이션 중심).

---

## 3. 사용자 및 핵심 시나리오

### 3.1 대상 사용자
- 메이커/학생/개발자
- 로컬 AI 에이전트 실험자
- 음성 인터랙션 + 임베디드 연동 PoC 팀

### 3.2 핵심 시나리오
1. 사용자가 Atom Echo에 음성 명령
2. ESP32가 오디오를 서버로 전송
3. 서버가 STT 처리 후 LLM 추론
4. 서버가 TTS 응답(또는 Robot 제어 페이로드) 반환
5. 디바이스가 응답 재생/동작 수행

---

## 4. 현재 기능(Current State)

### 4.1 현재 제공 기능
- Agent mode: 사용 가능
- Robot mode: 개발 중(기능 플래그 기반)
- CLI 제공:
  - `ccoli start`
  - `ccoli config wifi ...`
  - `ccoli config llm ...`
  - `ccoli config integration ...`
  - `ccoli config voice-id ...`

### 4.2 현재 아키텍처(요약)
- 서버 진입점: `server/server.py`
- CLI 진입점: `ccoli/cli.py`
- 핵심 모듈: `server/src/*` (protocol, stt, llm_client, agent_mode 등)
- 설정: `server/config.yaml`, `server/.env`
- 펌웨어: `arduino/atom_echo_m5stack_esp32_ino/`

### 4.3 현재 제약
- 외부 API 연동 확장 시 통합 품질 게이트가 더 강화되어야 함
- ESP32 통신 회귀 테스트의 자동화 수준을 지속 확장 필요
- 문서상 계획(Planning)과 제품 요구사항(PRD)의 경계가 혼재될 수 있음

---

## 5. 기능 요구사항 (Future Requirements)

## 5.1 기능 트랙 A — 연결/설정 UX
- Wi-Fi/유선 연결 모드 명시적 지원
- CLI에서 연결 모드 선택/검증 UX 제공
- 서버 설정과 펌웨어 설정 키 동기화 보장

## 5.2 기능 트랙 B — 통합(Integration) 확장
- Weather / Search / Calendar / Notify / Maps 기능 고도화
- 연동별 공통 인터페이스/헬스체크/표준 오류코드 유지
- API 실패 시 사용자 안내형 TTS 디버깅 강화

## 5.3 기능 트랙 C — Voice ID
- 화자 등록/식별, ON/OFF 토글, 삭제, threshold 제어
- 등록 화자 기반 응답 게이트
- 사용자별 개인화 컨텍스트 분리

## 5.4 기능 트랙 D — iOS 연동 채널
- Telegram bot 기반 최소 채팅 연동(우선)
- 향후 개인 배포형 iOS 채팅 앱 연동 검토

## 5.5 기능 트랙 E — 개발 생산성/도구 적용
- Codex/Claude 템플릿 규칙의 점진적 흡수
- `snarktank/ralph`는 런타임 치환보다 문서/테스트 자동화 영역부터 PoC 적용

## 5.6 기능 트랙 F — Robot 모드 (서보 + 디스플레이 기반 로봇 펫)

> 목표: Atom Echo에 SG90 서보모터와 SSD1306 OLED 디스플레이를 연결하여, LLM 응답에 따른 감정 표현(얼굴 애니메이션)과 물리적 액션(서보 동작)을 수행하는 로봇 펫 모드를 구현한다.

### F-1. 하드웨어 제약 및 핀 배분

#### Atom Echo 사용 가능 GPIO (공식 문서 기준)
- **재사용 금지 핀**: G19, G22 (NS4168 I2S 스피커), G23, G33 (SPM1423 PDM 마이크)
- **내부 전용**: G27 (SK6812 RGB LED), G39 (버튼), G12 (IR TX)
- **사용 가능 핀**: G21, G25 (우측 헤더), G26, G32 (Grove HY2.0-4P 포트)
- **전원**: Grove 포트에서 5V/GND 공급 가능, GPIO는 모두 3.3V 레벨

> 출처: [M5Stack Atom Echo 공식 문서](https://docs.m5stack.com/en/atom/atomecho), [M5Stack 커뮤니티 핀 확인](https://community.m5stack.com/topic/4828/)

#### 핀 배분 계획

| 기능 | 핀 | 비고 |
|---|---|---|
| OLED SCL | G21 | I2C 클럭 (우측 헤더) |
| OLED SDA | G25 | I2C 데이터 (우측 헤더) |
| 서보 #1 PWM | G26 | Grove 포트, 고개 끄덕임(pitch) |
| 서보 #2 PWM | G32 | Grove 포트, 고개 갸웃(roll/tilt) |
| 서보 VCC | Grove 5V | SG90 동작 전압 4.8-6V |
| OLED VCC | 3V3 헤더 | SSD1306 동작 전압 3.3-5V |
| 공통 GND | Grove GND | 모든 외부 장치 공유 |

#### 부품 스펙 요약

| 부품 | 모델 | 주요 스펙 |
|---|---|---|
| 서보모터 | SG90 | 4.8-6V, PWM 50Hz, 180° 회전, 3.3V 신호 호환 |
| OLED 디스플레이 | SSD1306 0.96" | 128×64px, I2C, 3.3-5V, 주소 0x3C |

> 출처: [SG90 스펙](https://www.espboards.dev/sensors/sg90/), [SSD1306 + ESP32 연결](https://randomnerdtutorials.com/esp32-ssd1306-oled-display-arduino-ide/)

### F-2. 감정 표현 시스템 (Emotion Expression)

LLM 응답에서 감정 태그를 추출하고, 디스플레이 + 서보를 조합하여 로봇 펫의 감정을 표현한다.

#### 감정 정의 테이블

| 감정 ID | 이름 | OLED 표정 | 서보 #1 (pitch) | 서보 #2 (tilt) | RGB LED |
|---|---|---|---|---|---|
| `neutral` | 기본 | ●‿● 기본 눈 | 정면 90° | 정면 90° | 흰색 |
| `happy` | 기쁨 | ◠‿◠ 웃는 눈 | 위아래 끄덕 ×2 | 좌우 흔들 ×2 | 노란색 |
| `sad` | 슬픔 | ●︵● 처진 눈 | 아래로 천천히 | 정면 유지 | 파란색 |
| `angry` | 화남 | ▼_▼ 찡그린 눈 | 빠른 떨림 ×3 | 정면 유지 | 빨간색 |
| `surprised` | 놀람 | ◎◎ 큰 눈 | 위로 빠르게 | 정면 유지 | 흰색 깜빡 |
| `sleepy` | 졸림 | ─‿─ 감긴 눈 | 천천히 아래로 | 한쪽으로 기울임 | 어두운 보라 |
| `love` | 애정 | ♥‿♥ 하트 눈 | 위아래 끄덕 ×1 | 좌우 흔들 ×1 | 분홍색 |
| `curious` | 호기심 | ●_◉ 한쪽 큰 눈 | 정면 유지 | 한쪽으로 갸웃 | 초록색 |
| `excited` | 신남 | ★‿★ 별 눈 | 빠른 끄덕 ×4 | 빠른 흔들 ×4 | 무지개 순환 |
| `confused` | 혼란 | ●_●? 물음표 | 좌우 느린 회전 | 좌우 번갈아 기울임 | 주황색 깜빡 |

#### OLED 애니메이션 기본 요소
- **눈 깜빡임**: 3-5초 간격 랜덤 블링크 (모든 감정 공통)
- **시선 이동**: 눈동자 좌/우/위/아래 이동 (idle 상태에서 랜덤)
- **전환 애니메이션**: 감정 변경 시 200ms 페이드 전환
- **상태 텍스트**: 하단 영역에 짧은 상태 메시지 표시 가능 (예: "듣는 중...", "생각 중...")

### F-3. 물리 액션 프리셋 (Servo Action Presets)

서보 2개를 조합한 물리적 동작 프리셋을 정의한다.

| 액션 ID | 이름 | 서보 #1 동작 | 서보 #2 동작 | 소요 시간 |
|---|---|---|---|---|
| `nod_yes` | 끄덕끄덕 | 90°→70°→90° ×2 | 유지 | 800ms |
| `nod_no` | 도리도리 | 유지 | 90°→60°→120°→90° | 800ms |
| `tilt_curious` | 갸웃 | 유지 | 90°→65° (유지 1s) →90° | 1500ms |
| `bounce_happy` | 통통 | 90°→75°→90° ×3 (빠르게) | 90°→80°→100°→90° ×2 | 1200ms |
| `droop_sad` | 축 처짐 | 90°→110° (유지 2s) →90° | 유지 | 2500ms |
| `shake_angry` | 부르르 | 85°→95° ×5 (빠른 떨림) | 유지 | 600ms |
| `startle` | 깜짝 | 90°→60° (빠르게) →90° | 유지 | 400ms |
| `dance` | 춤 | 70°→110° 반복 ×4 | 60°→120° 반복 ×4 (역위상) | 2000ms |
| `sleep_drift` | 꾸벅꾸벅 | 90°→105°→90° (느리게) | 90°→80° (느리게) | 3000ms |
| `wiggle` | 꼬리흔들기 | 유지 | 75°→105° ×3 (빠르게) | 900ms |

### F-4. 서버-디바이스 통신 프로토콜 확장

기존 TTS 응답 파이프라인에 Robot 제어 페이로드를 추가한다.

#### Robot Control Payload 구조 (서버 → ESP32)
```json
{
  "type": "robot_action",
  "emotion": "happy",
  "action": "bounce_happy",
  "display": {
    "face": "happy",
    "text": "안녕!"
  },
  "led_color": [255, 200, 0]
}
```

#### 동작 우선순위
1. 음성 재생 (TTS) — 최우선, 서보/디스플레이와 동시 실행 가능
2. 감정 표현 (디스플레이 + 서보 + LED) — TTS와 병렬 실행
3. Idle 애니메이션 — 명시적 명령이 없을 때 기본 눈 깜빡임 + 랜덤 시선

### F-5. LLM 감정 추출 연동

#### 서버 측 처리 흐름
1. LLM 응답에서 감정 태그 추출 (프롬프트 엔지니어링 또는 후처리)
2. 감정 → (표정 + 액션 + LED 색상) 매핑
3. Robot Control Payload 생성
4. TTS 오디오와 함께 ESP32로 전송

#### 감정 추출 방식
- **방식 A (프롬프트)**: LLM 시스템 프롬프트에 `[emotion:happy]` 형식 태그 삽입 요청
- **방식 B (후처리)**: 응답 텍스트의 감성 분석으로 감정 자동 분류
- 초기 구현은 방식 A를 우선 적용, 방식 B는 고도화 단계에서 검토

### F-6. 기능 플래그 및 설정

```yaml
# server/config.yaml
features:
  robot_mode_enabled: true

robot:
  servo:
    pin_pitch: 26        # 서보 #1 (G26)
    pin_tilt: 32         # 서보 #2 (G32)
    angle_min: 0
    angle_max: 180
    default_angle: 90
  display:
    type: "ssd1306"
    width: 128
    height: 64
    i2c_scl: 21          # G21
    i2c_sda: 25          # G25
    i2c_addr: "0x3C"
  idle:
    blink_interval_min: 3000   # ms
    blink_interval_max: 5000
    gaze_interval: 8000
  emotion:
    default: "neutral"
    decay_to_neutral: true
    decay_interval: 30         # seconds
```

### F-7. 구현 단계 (Phased Rollout)

| Phase | 범위 | 산출물 |
|---|---|---|
| F-Phase 1 | OLED 기본 표정 표시 + 눈 깜빡임 idle | 펌웨어 디스플레이 드라이버, 표정 비트맵 |
| F-Phase 2 | 서보 단일 동작 (끄덕/도리) | 서보 PWM 드라이버, 액션 프리셋 |
| F-Phase 3 | 감정 ↔ 표정+액션 매핑 통합 | 서버 감정 추출, 제어 페이로드 전송 |
| F-Phase 4 | LLM 프롬프트 감정 태그 + 복합 애니메이션 | 프롬프트 템플릿, 동시 실행 스케줄러 |
| F-Phase 5 | Idle 행동 패턴 + 감정 감쇠 | 자율 idle 루프, neutral 복귀 로직 |

### F-8. 하드웨어 주의사항

- **접지 공유 필수**: 서보, OLED, Atom Echo는 반드시 공통 GND로 연결. 접지 분리 시 신호 불안정/오동작 발생
- **서보 전원 분리 권장**: SG90 stall 시 최대 ~750mA 소모. USB-C 500mA 한계 초과 가능. 서보 2개 동시 구동 시 외부 5V 전원 어댑터 권장
- **I2C 풀업**: ESP32 내부 풀업 사용 가능하나, 배선 길이 10cm 초과 시 외부 4.7kΩ 풀업 저항 추가 권장
- **PWM 채널 충돌**: ESP32 LEDC PWM 채널은 I2S와 공유됨. 서보 PWM은 채널 0-1, 스피커 I2S는 별도 하드웨어이므로 충돌 없음을 확인할 것
- **핀 재사용 금지**: G19/G22/G23/G33은 절대 외부 장치에 연결하지 않을 것 (Atom Echo 손상 위험)

---

## 6. 비기능 요구사항 (NFR)

### 6.1 보안
- API 키/토큰/비밀번호 평문 노출 금지
- 로그/문서/예시에서 민감정보 마스킹

### 6.2 신뢰성
- 통신 실패/외부 API 실패 시 재시도 및 사용자 안내 제공
- 모듈별 장애 격리(연동 실패가 전체 파이프라인 장애로 확산되지 않게 설계)

### 6.3 테스트/재현성
- 모든 테스트는 Docker 환경에서 재현 가능해야 함
- 테스트 단일 진입점(예: compose 파일) 유지

### 6.4 운영성
- 실패 원인 추적 가능한 구조화 로그
- 주요 CLI 시나리오 스모크 테스트 제공

---

## 7. 테스트 전략

### 7.1 테스트 레벨
- L1: 단위 테스트 (`server/src` 순수 로직)
- L2: 통합 테스트 (server + mock services)
- L3: 프로토콜 테스트 (client-sim ↔ server)
- L4: CLI 스모크 테스트

### 7.2 실행 원칙
- 새 기능은 테스트 선행 또는 동시 작성
- 병합 전 최소 L1/L2 통과
- L3/L4는 릴리즈/주기 실행으로 점진 강화

---

## 8. 릴리즈 로드맵 (High-level)

### Phase 1 (문서/규칙 정합)
- PRD 단일 기준 문서 운영
- Planning 문서는 PRD 기반 실행계획으로만 유지

### Phase 2 (테스트 표준화)
- Docker Compose 테스트 파이프라인 확정
- client-sim + mock-services 점진 도입

### Phase 3 (기능 고도화)
- Integration 기능군 고도화
- Voice ID/개인화 안정화
- iOS/Telegram 연동 확장

### Phase 4 (도구 PoC)
- Ralph PoC: 문서/테스트 자동화 중심 적용 평가

### Phase 5 (Robot 모드)
- F-Phase 1~2: OLED 디스플레이 표정 + 서보 기본 동작
- F-Phase 3~4: LLM 감정 추출 → 표정+액션 통합, 프로토콜 확장
- F-Phase 5: Idle 행동 패턴 + 감정 감쇠 자율 루프

---

## 9. 성공 지표
- 신규 기여자가 문서 기준으로 1일 내 로컬 셋업/테스트 재현 가능
- 주요 회귀 버그가 Docker 통합 테스트로 포착됨
- 사용자 체감 실패율(연결/인증/타임아웃) 감소
- Robot 모드: 감정 표현 10종이 LLM 응답과 연동되어 디스플레이+서보로 출력됨

---

## 10. Definition of Done (DoD)
- PRD가 최신 상태이며 목적/현재기능/향후기능/NFR/테스트전략이 포함됨
- 구현 PR은 PRD의 기능 트랙 또는 NFR 항목과 매핑됨
- 테스트 결과가 Docker 기준 명령으로 제출됨
