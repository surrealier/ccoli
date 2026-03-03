# Docker 설치 및 구동 가이드

이 문서는 본 프로젝트의 Docker 환경(테스트/실사용) 구성, 설치, 실행, 검증, 트러블슈팅을 한 번에 제공합니다.

## 1. 제공되는 Docker 자산
- 테스트용 서버 이미지: `docker/server/Dockerfile`
- 실사용 서버 이미지: `docker/server-runtime/Dockerfile`
- 클라이언트 시뮬레이터 이미지: `docker/sim-client/Dockerfile`
- 테스트 오케스트레이션: `docker-compose.test.yml`
- 런타임 오케스트레이션: `docker-compose.runtime.yml`
- 공통 실행 명령: `Makefile`
- 자율형 루프 스크립트: `scripts/autonomous_coding_loop.sh`

## 2. 사전 설치

### Linux
1. Docker Engine 설치
2. Docker Compose v2 설치 (`docker compose` 명령)
3. 현재 사용자 docker 그룹 권한 부여

### macOS / Windows
- Docker Desktop 설치 후 `docker` / `docker compose` 명령 확인

## 3. 설치 확인
```bash
docker --version
docker compose version
```

## 4. 테스트 환경 실행

### 4.1 기본 단위 테스트 (권장)
```bash
make test-docker
```
- 내부적으로 `docker-compose.test.yml`을 사용해 `tests/server_tests`를 실행합니다.

### 4.2 통합 프로파일 실행(시뮬레이터 포함)
```bash
make test-docker-integration
```
- `integration` profile을 활성화하여 sim-client 컨테이너까지 포함 실행합니다.

## 5. 실사용 서버 실행

### 5.1 환경 파일 준비
```bash
cp server/env.example server/.env
```
필요한 API key를 `.env`에 설정하세요.

### 5.2 서버 실행
```bash
make run-server-docker
```
- 5001 포트를 호스트로 노출합니다.
- 로그/오디오 로그 디렉터리는 볼륨으로 유지됩니다.

### 5.3 서버 중지
```bash
docker compose -f docker-compose.runtime.yml down
```

## 6. 공식 스펙 기반 검증 체크리스트
Docker/클라이언트 변경 시 아래 항목을 점검하세요.
- 프레임 크기: 20ms @16kHz 모노 PCM16LE(640 bytes/frame)
- 2-byte 정렬 보장(PCM16)
- 버퍼/청크 크기 상한이 장치 스펙과 충돌하지 않는지 확인

참고 공식 문서
- M5Stack ATOM Echo: https://docs.m5stack.com/en/atom/atomecho
- ESP32 Programming Guide: https://docs.espressif.com/projects/esp-idf/en/latest/esp32/
- ESP-IDF I2S: https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/i2s.html

## 7. 자율형 코딩 루프(ralph 스타일 적용)
```bash
make autoloop
```
- `scripts/autonomous_coding_loop.sh`가 반복적으로 Docker 테스트를 수행합니다.
- 최대 반복 횟수는 `MAX_ITERS`(기본 5)로 제어됩니다.

예시:
```bash
MAX_ITERS=3 make autoloop
```

## 8. 트러블슈팅
- `docker compose` 명령 없음: Docker Compose v2 미설치
- 권한 오류: Linux에서 docker 그룹 권한 확인
- 이미지 빌드 실패: 네트워크/프록시, pip 인덱스 접근 확인
- 런타임 실패: `server/.env`, `server/config.yaml` 경로 및 값 확인
