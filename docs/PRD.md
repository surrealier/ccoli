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

---

## 9. 성공 지표
- 신규 기여자가 문서 기준으로 1일 내 로컬 셋업/테스트 재현 가능
- 주요 회귀 버그가 Docker 통합 테스트로 포착됨
- 사용자 체감 실패율(연결/인증/타임아웃) 감소

---

## 10. Definition of Done (DoD)
- PRD가 최신 상태이며 목적/현재기능/향후기능/NFR/테스트전략이 포함됨
- 구현 PR은 PRD의 기능 트랙 또는 NFR 항목과 매핑됨
- 테스트 결과가 Docker 기준 명령으로 제출됨
