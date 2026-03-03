# Docker Test Plan

## 목표
- 서버/프로토콜 테스트를 Docker에서 일관되게 실행
- 하드웨어 의존 로직은 시뮬레이터로 대체하되, 공식 스펙 제약을 반영
- 설치부터 구동까지 한 문서로 재현 가능한 운영 기준 확보 (`docs/DOCKER_SETUP_AND_RUN.md`)

## 구성
- `docker/server/Dockerfile`: Python 테스트 실행 이미지
- `docker/server-runtime/Dockerfile`: 실사용 서버 이미지
- `docker/sim-client/Dockerfile`: ESP32 패킷 송수신 시뮬레이터
- `docker-compose.test.yml`: 테스트 오케스트레이션
- `docker-compose.runtime.yml`: 실사용 오케스트레이션
- `Makefile`: 표준 실행 명령 래퍼

## 테스트 범위
1. 단위 테스트
   - 패킷 프레이밍(타입/길이)
   - JSON CMD 인코딩
   - 프레임 크기 계산(스펙 검증)
2. 통합 테스트(확장)
   - START -> AUDIO -> END -> CMD 왕복 시나리오
   - PING/PONG keepalive

## 공식 스펙 참조 원칙 (필수)
Docker 및 클라이언트 관련 수정 시 아래 스펙을 가능한 한 먼저 확인합니다.
- M5Stack Atom Echo 공식 핀맵/회로 문서
- Espressif ESP32 공식 기술 문서(특히 I2S, DMA, 버퍼 제약)
- 사용 라이브러리 공식 문서(M5Unified, Arduino-ESP32)

### 반영 항목 예시
- 오디오 프레임 크기(20ms @16kHz => 320 samples, 640 bytes)
- PCM16LE 바이트 정렬(2-byte align)
- 전송 chunk 크기 및 버퍼 upper bound

## 실행 명령
- `make test-docker`
- `make test-docker-integration`
- `make run-server-docker`

## 산출물
- 테스트 성공/실패 코드
- compose 로그
- 자율 루프 실행 로그(`.codex/reports/`)
