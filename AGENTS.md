# AGENTS.md — ccoli Codex Project Rules

이 파일은 Codex 에이전트가 이 저장소에서 작업할 때 항상 따라야 하는 기본 규칙을 정의합니다.

## 1) 작업 기본 원칙
- 변경 전 `README.md`, `QUICKSTART.md`, `docs/`의 관련 문서를 먼저 확인한다.
- 기능 변경 시 **문서/코드/테스트**를 함께 업데이트한다.
- 사용자 요청이 계획(Planning) 중심이면, 실행 가능한 단계/산출물/검증 기준이 포함된 PRD 형태로 제시한다.
- 민감정보(API Key, 토큰, 비밀번호)는 코드/문서/로그에 평문으로 남기지 않는다.

## 2) Python 서버 개발 규칙
- 서버 코드(`server/`)는 타입 힌트와 작은 단위 함수 분리를 우선한다.
- 외부 연동(OpenWeather, Google, Slack 등)은 `server/src/integrations/` 경계 안에서 처리한다.
- 오류 처리는 사용자 안내 메시지와 내부 디버깅 정보를 분리한다(사용자 출력은 행동 유도형).

## 3) ESP32/클라이언트 연동 규칙
- 펌웨어 설정(`arduino/.../device_secrets.h`)과 서버 설정(`server/config.yaml`) 간 키 이름/의미를 일치시킨다.
- 연결 모드(Wi-Fi/유선) 관련 변경은 서버/CLI/문서를 함께 수정한다.

## 4) Docker 기반 테스트 규칙 (필수)
- 모든 테스트는 로컬 Python 직접 실행이 아닌 Docker 환경에서 재현 가능해야 한다.
- 최소 2개 컨테이너를 기준으로 한다.
  - `server-test`: Python 서버 단위/통합 테스트 실행
  - `client-sim`(선택): ESP32 프로토콜/패킷 시뮬레이션
- CI/CD는 Docker Compose 기반 테스트 명령을 단일 진입점으로 유지한다.
  - 예: `docker compose -f docker/docker-compose.test.yml up --build --abort-on-container-exit`

## 5) TDD/품질 게이트
- 새 기능은 가능한 한 **테스트 먼저(또는 동시)** 작성한다.
- 최소 품질 게이트:
  1. 단위 테스트 통과
  2. 프로토콜/통신 통합 테스트 통과
  3. 핵심 CLI 시나리오 스모크 테스트 통과
- 테스트 실패 시 원인/재현 명령/수정 계획을 PR에 명시한다.

## 6) 문서/PR 규칙
- 큰 변경은 `docs/`의 PRD/Planning 문서에 먼저 반영 후 구현한다.
- PR 본문에는 다음을 포함한다.
  - 배경/문제
  - 변경 범위
  - 테스트 결과(실행 명령)
  - 롤백 전략

## 7) 외부 레포/도구 도입 원칙
- Claude/Codex 전용 템플릿 또는 프레임워크를 도입할 때는
  1) 현재 구조와의 충돌 여부,
  2) 보안/비용,
  3) 유지보수 난이도,
  4) 단계적 적용 가능성
  을 먼저 평가하고 PoC 후 점진 도입한다.
