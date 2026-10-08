# ccoli 차세대 개인·홈 에이전트 PRD

작성: 2026-09-18. 기존 PRD의 확장 요구사항이며, 실제 검증 전에는 완료로 표시하지 않는다.

## 목표와 완료 기준

현재 ESP32 음성 단말과 PC의 STT/LLM/TTS를 유지하면서, 요청을 여러 도구로 수행하고 결과를 확인하는 개인 에이전트로 발전시킨다. 완료는 코드 작성이 아니라 Docker 회귀 테스트, 펌웨어 빌드, 연결된 장치의 핸드셰이크, 마이크 입력과 스피커 출력, 실 LLM 응답까지 확인한 상태다. 계정이나 별도 홈 허브가 없는 외부 연동은 모의 검증과 실서비스 검증을 구분한다.

## 조사와 아키텍처 선택

- [Home Assistant LLM API](https://developers.home-assistant.io/docs/core/llm/): 노출한 엔티티·의도에 제한된 도구 제어. ccoli에도 서버 측 허용 목록을 둔다.
- [Home Assistant Conversation API](https://developers.home-assistant.io/docs/intent_conversation_api/): 대화 ID와 실행 결과를 명시. 성공을 모델의 문장만으로 판단하지 않는다.
- [ESPHome Voice Assistant](https://esphome.io/components/voice_assistant/): 단말 오디오와 서버 추론을 분리. 원형 ESP32의 메모리 한계를 고려하여 USB mu-law 경로를 유지한다.
- [OpenClaw](https://github.com/openclaw/openclaw): 개인 PC의 gateway, 교체 가능한 모델, 채널과 로컬 상태 관리에서 영감. 전체 프레임워크 도입은 기존 Python 런타임과 중복되고 유지보수·권한 범위가 커져 채택하지 않는다.
- [Xiaozhi ESP32](https://github.com/78/xiaozhi-esp32): 음성 단말과 도구 연결 분리 참고. 보드와 서버를 동시에 교체하는 비용을 피하기 위해 펌웨어 전면 이식은 하지 않는다.
- [Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling): 도구→결과→후속 추론의 제한된 반복 실행을 참고한다.

대안 A(선택): 기존 ccoli에 작은 실행 엔진, 개인 상태 저장소, Home Assistant 어댑터를 추가한다. 기존 공급자·프로토콜 호환성과 롤백이 쉽다.
대안 B: ESPHome/HA 전체 전환은 성숙한 홈 생태계가 장점이나 기존 개인화·USB 흐름의 재구축이 필요하다.
대안 C: 외부 개인 에이전트 전체 도입은 도구 생태계가 장점이나 추가 런타임과 광범위한 실행 권한이 필요하다.

## 구현 범위

1. **실행 엔진**: 모든 기존 LLM 공급자가 사용할 수 있는 검증된 JSON 도구 요청, 최대 4회 도구 실행, 알 수 없는 도구·잘못된 인자 차단, 실패 시 행동 유도형 안내. 실행 기록은 인자/비밀값을 저장하지 않고 도구명·결과 상태·소요 시간만 남긴다.
2. **개인 상태**: SQLite에 사용자별 명시적 기억과 할 일을 보존. 기억 추가/검색/삭제와 할 일 추가/목록/완료. 재시작 보존, 사용자간 격리, 매개변수 SQL, 크기 제한. 기존 공용 Soul은 유지하되 다른 화자의 자동 추출 기억이 섞이지 않게 한다.
3. **홈 연결**: `server/src/integrations/home_assistant.py`에서 HTTP 요청을 수행. 환경변수 토큰, 제한된 엔티티 목록, light/switch의 turn_on/turn_off만 지원. 상태 조회와 변경 결과 구분, HTTP 타임아웃, 리디렉션 차단. 잠금장치·보안·임의 서비스 실행은 범위에 넣지 않는다.
4. **채널 통합**: ESP32 음성·웹·기존 Telegram이 같은 AgentMode 실행 엔진을 사용한다. 기존 일정/날씨 등 명시적 처리와 충돌하지 않도록 실행 분기를 테스트한다.
5. **운영**: 현재 상태·도구 목록·실행 기록을 인증된 API에서 조회. 키가 없는 연동을 사용 가능하다고 표시하지 않는다. 설치/실행/USB 진단 및 복구 문서를 제공한다.
6. **검증과 기기**: 기존 변경 보존, Docker 단위/통합/CLI 및 client-sim, 펌웨어 4종 빌드. 실기 확인 후 필요할 때만 백업·업로드. 합성 음성만으로 실제 마이크 성공을 주장하지 않는다.

## 보안·신뢰성 제약

웹 API는 로컬 개인 설치가 기본이다. 화자 이름은 인증 자격이 아니며 음성 ID는 보안 인증을 대신하지 않는다. 외부 서비스 쓰기는 허용된 홈 기기의 요청된 동작에 한정한다. 도구 결과와 기억은 지시가 아닌 데이터로 제공한다. 네트워크/모델 오류는 임의 성공 응답으로 숨기지 않는다. 비밀값, 오디오 원본, 개인 메모리를 소스·Docker 이미지·작업 보고서에 포함하지 않는다.

## 품질 게이트와 롤백

- Docker 테스트: 기존 전체 suite + 새 도구 인자 오류/반복 한도/격리/재시작/홈 실패 회귀.
- client-sim: 실제 프레임 정상·분할·잡음·지연 동작.
- firmware-build: 지원 보드 설정 컴파일.
- 실기: 식별→핸드셰이크→TTS→사용자 음성→STT/LLM/TTS→재연결.
- 새 엔진을 비활성화하면 기존 대화 경로로 복귀. 새 SQLite 상태는 삭제하지 않는다. 펌웨어 변경 시 기존 이미지 백업을 별도 보존한다.

## 현재 확인된 환경

- Windows COM3, FTDI USB Serial Port. 2026-10-08 사용자가 ESP32 Atom Echo임을 확인했다.
- Docker Desktop 복구 완료. Docker Compose 전체 회귀와 펌웨어 4종 빌드 성공.
- 작업 폴더에 사용자 변경 다수 존재. 자동 reset/clean/일괄 commit 금지.
- Arduino CLI/Ollama는 PATH에 없음. API 키의 존재만 확인하고 값은 표시하지 않는다.

## 실행 상태

- [x] 기존 README/QUICKSTART/PRD/Planning/프로토콜 조사
- [x] 공식 최신 사례와 아키텍처 비교
- [x] 기반 Docker 테스트 및 환경 복구
- [x] 개인 상태 저장소와 검증
- [x] 제한된 도구 실행 엔진과 채널 통합
- [x] Home Assistant 어댑터와 Docker 검증 (실제 HA 인스턴스 미연결)
- [x] 운영 API·사용 가이드
- [x] 전체 회귀·펌웨어 빌드 (최신 실행 결과는 검증 기록 참조)
- [x] 실제 Atom Echo 음성 왕복과 재연결. 장치 STT/LLM/TTS 로그와 10/8 사용자 가청 응답 확인, 이전 포트 소실/재등장 복구 기록으로 검증했다.
