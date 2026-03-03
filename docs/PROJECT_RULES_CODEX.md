# PROJECT_RULES_CODEX

이 문서는 Codex 기반 개발 시 저장소 전역에서 항상 따르는 운영 규칙입니다.

## 1) 작업 원칙
- 모든 변경은 **작은 단위**로 나누고, 목적/영향 범위를 PR 본문에 명시합니다.
- 서버(`server/`)와 클라이언트(`arduino/`) 프로토콜은 **계약(Contract)** 으로 취급합니다.
- 프로토콜 필드/패킷 타입 변경 시, 서버/클라이언트/문서를 같은 PR에서 함께 갱신합니다.

## 2) 브랜치/커밋 규칙
- 커밋 메시지는 Conventional Commits 권장:
  - `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- 커밋 본문에는 다음 중 해당되는 항목을 포함합니다.
  - 왜 바꿨는지(Problem)
  - 무엇을 바꿨는지(Change)
  - 어떤 검증을 했는지(Validation)

## 3) 코드 변경 전/후 체크리스트

### 변경 전
- 요구사항 출처 확인: `docs/PRD.md`
- 영향 영역 식별: server/client/protocol/docs/test
- 설정/비밀정보 포함 여부 검토

### 변경 후
- 최소 1개 이상의 검증 실행(단위 테스트/정적 점검/실행 확인)
- 문서 동기화:
  - 동작/설정이 바뀌면 `README.md` 또는 `QUICKSTART.md` 갱신
  - 제품 요구사항 변경 시 `docs/PRD.md` 갱신
- 회귀 위험이 큰 변경은 테스트 케이스 추가

## 4) 프로토콜/인터페이스 규칙
- 패킷 타입 및 구조 변경 시 아래를 동시 수정:
  1. `server/`의 송수신 구현
  2. `arduino/`의 송수신 구현
  3. `docs/PRD.md` 프로토콜 섹션
- JSON 명령 스키마의 필수/선택 필드는 명시적으로 문서화합니다.

## 5) Docker 테스트 규칙
- 테스트는 기본적으로 Docker에서 실행 가능해야 합니다.
- 로컬/CI 모두 동일 명령으로 실행 가능하도록 스크립트 또는 compose를 유지합니다.
- STT/LLM 등 외부 의존성이 큰 컴포넌트는 mock/fake 경로를 제공합니다.
- Docker 설치/구동/문제해결 가이드는 `docs/DOCKER_SETUP_AND_RUN.md`에 항상 최신으로 유지합니다.

## 6) 하드웨어 스펙 준수 규칙 (중요)
- 클라이언트(ESP32/M5Stack) 코드 또는 Docker 기반 시뮬레이터 작업 시, 가능하면 **공식 문서의 스펙**을 우선 참조합니다.
  - 예: 핀맵, I2S/ADC 제약, DMA/버퍼 크기, 샘플링 레이트, 전압/전류 한계
- 스펙 기반 변경이라면 PR 본문에 근거 링크/문구를 남깁니다.
- 스펙 불일치 가능성이 있는 경우, 코드 주석 또는 문서에 가정(assumption)을 기록합니다.

### 공식 문서 링크 (우선 참조)
- M5Stack ATOM Echo 제품/문서: https://docs.m5stack.com/en/atom/atomecho
- Espressif ESP32 기술 문서(Programming Guide): https://docs.espressif.com/projects/esp-idf/en/latest/esp32/
- ESP-IDF I2S API 레퍼런스: https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/i2s.html
- Arduino-ESP32 공식 문서: https://docs.espressif.com/projects/arduino-esp32/en/latest/
- M5Unified 라이브러리: https://github.com/m5stack/M5Unified

## 7) 설정/보안 규칙
- 민감정보는 커밋하지 않습니다.
- 서버는 `server/env.example`, 클라이언트는 `config.h.example` 패턴을 유지합니다.
- 기본값은 안전한 동작을 우선으로 합니다.

## 8) PR 작성 규칙
- PR 본문에는 반드시 아래를 포함합니다.
  - 변경 요약
  - 영향 범위(server/client/protocol/docs)
  - 테스트 결과(명령 + 결과)
  - 롤백 방법
- 사용자 영향이 있으면 마이그레이션/운영 가이드를 추가합니다.
