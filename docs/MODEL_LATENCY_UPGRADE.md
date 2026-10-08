# 최신 모델·음성 지연 개선 (2026-09-23)

사용자가 응답 음성이 들린다고 확인했다. 새 요구는 모든 활성 모델/기본 모델의 최신화와 느린 응답의 최적화다. 기존 기억·도구 실행 안전성 및 USB 재연결 동작을 유지한다.

## 실행 계획 및 검증

1. 공식 모델 문서와 실제 계정 모델 목록으로 제공 모델을 확인한다. CLI/runtime/env/config 기본값을 함께 갱신하되 과거 테스트 fixture는 임의 대체하지 않는다. 현재 Gemini 키만 있고 Claude/OpenAI는 미설정이다.
2. LLM 요청 schema를 모델별로 맞춘다. Gemini 3.x의 thinkingLevel, OpenAI 최신 계열의 token/추론 파라미터 등은 공식 지원 확인 후 Docker RED→GREEN으로 변경한다. 단순히 이름만 바꾸지 않는다.
3. 실제 로그 기준 병목은 END→STT 7~8초, LLM 1~2초, TTS 1~2초다. Whisper small CPU 단일 스레드/beam5를 최신 한국어 지원 STT 및 GPU 실행으로 교체하고 동일 합성 한국어 샘플로 전후 지연과 텍스트 정확도를 비교한다. 합성 입력을 사용자 실기 확인으로 주장하지 않는다.
4. TTS 다중 문장 생성의 불필요한 직렬 대기를 줄이고 도구 실행 결과 확인을 유지한다. 직렬 전송의 실시간 pacing은 유지한다.
5. Docker 전체/통신/CLI, 새 모델 실제 Gemini/로컬 호출, 운영서버 최종 모델·STT device 진단을 확인한다. 변경 전후 수치와 접근 불가 모델을 명시한다.

## 롤백

모델 및 inference 옵션은 설정으로 이전값 복구 가능하게 유지한다. 기존 서버 설정·작업트리·개인 SQLite 보존. 설치/다운로드는 이 프로젝트 독립 런타임 안에 한정하며 다른 프로젝트 Ollama/컨테이너를 정지하지 않는다.

## 공식 근거

- https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash
- https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite
- https://developers.openai.com/api/docs/models
- https://platform.claude.com/docs/en/models/overview
- https://ollama.com/library/qwen3.5:4b
- https://ollama.com/library/qwen3.8
- https://ollama.com/library/granite4.2:3b
- https://github.com/SYSTRAN/faster-whisper

## 측정 및 실행 결과 (2026-09-25)

- 공식 문서와 실제 Gemini 계정 모델 목록으로 `gemini-3.8-flash` 제공을 확인했다. 서버/CLI/env 기본 모델명은 Gemini 3.8 Flash, Claude Haiku 4.5, GPT-6 Luna로 갱신했다. Claude/OpenAI 키가 없으므로 두 공급자의 실제 응답은 검증하지 않았다. Gemini 3.x의 낮은 thinkingLevel과 OpenAI 6 계열의 토큰·추론 필드 호환성은 Docker 계약 테스트로 확인했다.
- 실행 중인 PC는 `gemini-3.8-flash`를 활성 모델로 보고했다. 실제 웹 인사 요청은 1.537초, 한국어 한 문장 응답, 공급자 오류 없음이었다. 개인 할 일 원문 조회를 포함한 실계정 점검은 자동 승인 검토가 개인 데이터의 원격 전송을 이유로 거부하여 실행하지 않았다. 합성 격리 데이터와 Docker 테스트로 도구 경로를 검증했다.
- 같은 8.616초 합성 한국어 음성을 3회 인식한 결과, 기존 Whisper small/CPU/1 thread/beam5는 8.243·8.461·8.026초(평균 8.243초), 새 Whisper turbo/CUDA/4 threads/beam1은 0.633·0.299·0.299초(평균 0.410초)였다. 두 설정 모두 핵심 문장을 올바르게 인식했다. 첫 모델 로드 약 40초는 대화별 지연에서 제외한다. 이는 합성 샘플 측정으로 실제 ESP32 왕복 시간은 아니다.
- 같은 짧은 텍스트 세 개의 LLM 단독 측정은 기존 Gemini 2.5 Flash-Lite 1.018·1.125·1.146초, Gemini 3.8 Flash 7.599초(첫 호출)·2.420·2.542초였다. 최신 모델 자체는 이전 경량 모델보다 느릴 수 있다. 음성 총 지연의 개선은 주로 STT에서 기대하며, 실제 실기 턴의 비교값은 별도 계측이 필요하다. 일부 응답은 마크다운 코드 블록으로 JSON을 감싸서 원시 JSON 판정이 false였고, ToolAgent는 해당 블록을 제거한다.
- 긴 답변의 TTS 청크 최대 3개를 병렬 생성한 뒤 원래 순서로 합친다. 한 청크가 예외를 내면 전체 문장을 한 번 재생성한다. `VOICE_LATENCY` 로그는 sid별 STT, LLM, TTS, END→첫 전송 시점을 원문 없이 기록한다. END→첫 전송은 실제 스피커 재생 완료 시간이 아니다. 발화·응답·TTS 문장 원문이 운영 로그에 남지 않도록 변경했다.
- 작은 최신 로컬 후보 Granite 4.2 3B는 공식 채팅 템플릿을 적용하면 생성은 빨라졌지만, 실제 ToolAgent 도구 선택과 조회 결과 일치에 실패해 기본값에서 제외했다. 이 PC의 로컬 장애 대체 모델은 `qwen3.5:4b`로 설정했다. 격리 SQLite 실제 ToolAgent PoC에서 조회 교정, 정확한 제목 추가, 한국어 인사를 확인했지만 첫 조회는 32.484초였다. 실시간 음성의 주 경로는 검증된 Gemini API 우선으로 둔다. 세부 근거: [Granite PoC](GRANITE42_POC.md), [Qwen PoC](QWEN35_POC.md).
- 활성 Gemini가 나중에 빈 응답을 반환하면 같은 요청에서 다음 공급자로 넘어가도록 회귀 테스트를 추가했다. 도구의 명시적 조회는 성공한 실제 도구 데이터를 결정적으로 요약하여 모델의 모순된 설명을 제거한다.

검증 진입점: `docker compose -f docker/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from server-test`; 통신은 `docker compose -f docker/docker-compose.test.yml run --rm client-sim`. 최신 전체 수치는 검증 기록을 참조한다.

## 음성 합성 모델 선택 (2026-09-25 추가)

Google의 공식 출시 기록에 따르면 Gemini 3.8 Flash-Lite TTS는 2026-09-22 공개된 최신 속도형 TTS 모델이다. 같은 합성 한국어 문장으로 PC에서 직접 측정한 생성 지연은 Edge TTS 0.392·0.404초, Gemini 3.8 Flash-Lite TTS 1.941·1.630초였다. 이 계정은 신모델 호출에 성공했고, 요청한 16 kHz와 달리 실제 응답 MIME은 24 kHz PCM으로 왔다. 반환 MIME 기준으로 리샘플링해야 ESP32의 16 kHz PCM 경로가 안전하다.

따라서 다음과 같이 구현한다: Gemini TTS를 명시적으로 선택할 수 있게 하되 기존 빠른 Edge 기본값을 유지한다. 외부 호출 코드는 integrations 경계에 두고, Gemini 오류 시 Edge로 복구한다. 합성 텍스트만 사용해 통합 PoC를 하고, 실제 개인 대화 내용은 시험 목적으로 보내지 않는다. Docker 테스트로 24 kHz/16 kHz 변환, WAV 변형, 선택/복구, 기본 속도 경로를 검증한다. 공식 근거: https://ai.google.dev/gemini-api/docs/changelog 및 https://ai.google.dev/gemini-api/docs/generate-content/speech-generation .



- 최신 TTS 어댑터를 명시적 선택 기능으로 추가했다. 합성 문장으로 실제 Gemini 3.8 Flash-Lite TTS → 16 kHz PCM16LE 80,640바이트(2.52초 음성) 변환을 확인했고, 호출 시간은 2.235초였다. 직접 비교 실험에서는 Edge 0.392·0.404초, Gemini 1.941·1.630초였으므로 현재 PC 운영 기본값은 Edge로 유지한다. 출력 샘플레이트는 요청값보다 실제 MIME/WAV 헤더를 우선해 읽는다. 실패하면 Edge로 복구한다.

- 같은 합성 인사 JSON 프롬프트에서 Gemini 3.5 Flash-Lite는 1.110·1.217·1.120초, Gemini 3.8 Flash는 1.339·2.411·2.176초였다. 격리 할 일 ToolAgent에서 3.5 Flash-Lite는 추가 작업을 완료했고 조회 결과는 첫 시도 불일치, 재시도 일치였다. 이 좁은 PoC만으로 전체 개인 도구 품질을 보장할 수 없어 현재 3.8 Flash 기본값을 유지한다. 빠른 모델의 폭넓은 도구 평가 뒤 별도 라우팅을 결정한다.

- 최종 리뷰에서 TTS 청크 일부와 전체 재합성이 모두 실패하면 앞부분만 재생되는 결함을 확인해 차단했다. 손상된 Gemini 오디오 base64의 예외 변환도 보강했다. 각각 Docker RED→GREEN 후 전체 521 passed, 1 skipped를 확인했다. 최신 운영 서버는 Gemini 3.8 Flash·turbo/CUDA·빠른 Edge TTS·COM3로 재기동했고, 합성 웹 인사는 1.306초였다.


## 표준 시작 경로의 모델 우선순위

운영용 개인 런처는 API 우선이지만 저장소의 config.yaml은 Ollama 우선으로 남아 있었다. 따라서 일반 ccoli start를 쓰면 설치된 로컬 Qwen을 먼저 선택해 대화가 다시 느려질 수 있다. 프로젝트 config.yaml을 API → Ollama 순으로 맞추고, CLI에서 공급자를 명시적으로 바꾸면 선택한 공급자에 맞춰 우선순위를 함께 저장한다. API 키가 없는 환경은 기존 로컬 후보로 내려간다. 환경변수의 명시적 LLM_PRIORITY는 계속 최우선이다. Docker 테스트로 구성 파일과 CLI 공급자 변경·되돌리기를 먼저 RED로 확인하고 GREEN 후 전체 회귀를 실행한다.


## 표준 시작의 개인 기능·웹 범위

전용 런처에는 AGENT_ENABLED=true와 WEB_HOST=127.0.0.1이 있으나 저장소 config.yaml에는 agent 항목이 없고 웹은 0.0.0.0이었다. 일반 ccoli start에서는 개인 도구가 꺼지고 인증 토큰이 비어 있는 대시보드가 LAN에 열릴 수 있다. 이 프로젝트의 표준 구성에 agent.enabled=true와 web.host=127.0.0.1을 명시한다. 유선 ESP32 설정은 유지한다. 다른 PC에서 Wi-Fi 대시보드를 열려면 별도 인증·네트워크 설정을 명시하도록 문서화한다. 환경변수 AGENT_ENABLED=false는 롤백으로 계속 허용한다. Docker RED→GREEN 후 실제 표준 Config 로드와 전체 회귀로 검증한다.
## 짧은 실기 입력 진단

9/25 운영 로그에서 0.68초 입력이 END까지 도달했으나 STT 시간·결과 로그가 없었다. 서버는 0.45초 미만 또는 -45 dBFS 미만 입력을 STT 전에 걸러낸다. 펌웨어는 음성 END만으로 마이크를 잠그지 않고, 서버 입력 게이트는 작업 종료 시 해제된다. 실제 발화인지 주변 소음인지는 오디오 원본을 보존하지 않아 판단할 수 없다.
앞으로 이 경로는 발화 내용이나 PCM 없이 `VOICE_INPUT`의 세션 번호·고정 사유 코드·길이·RMS만 남긴다. `too_short` 또는 `too_quiet`가 반복되면 마이크 입력 수준/VAD를 먼저 점검하고, STT 단계가 기록됐으나 텍스트가 비어 있으면 인식 모델·언어 설정을 살핀다. Docker RED→GREEN과 전체 회귀 통과 후 운영 서버에 적용했다.
## 명확한 홈 명령의 빠른 경로

격리 합성 Home Assistant와 실 Gemini 3.8 Flash의 이름 기반 조명 요청은 `home.states`→`home.control`과 서비스 POST 후 GET 상태 확인까지 성공했지만 7.049초가 걸렸다. 도구 실행 자체보다 모델과의 여러 왕복이 길다.
단일 조명·스위치의 명확한 켜기/끄기 명령만 이름 또는 정확한 엔티티 ID로 매칭해 모델 호출 전에 실행한다. 허용 목록 안의 현재 상태를 읽고 유일한 일치 항목일 때만 기존 `home.control` 검증·상태 재조회 경로를 사용한다. 동일한 이름의 기기가 여럿이면 정확한 ID를 요청하고, 복합적인 요청은 기존 에이전트로 넘긴다. 방법 질문과 부정 요청은 직접 실행하지 않는다. 읽기/쓰기 실행 메타데이터는 남기되 이름·토큰·원문은 로그에 남기지 않는다.
Docker RED→GREEN으로 명확한 명령, 모호한 명령, 질문·부정을 검증했다. 격리 합성 Home Assistant의 이름 기반 실 Gemini 경로는 7.049초, 같은 GET→POST→GET을 수행한 직접 경로는 5ms였다. 정확한 허용 엔티티 ID는 전체 이름 조회를 건너뛰고 해당 기기 POST→GET만 수행해 합성 서버에서 4ms였다. 전체 Docker 회귀는 535 passed, 1 skipped로 통과했다. 실제 홈 기기 제어는 Home Assistant 인스턴스와 허용 목록 설정 전까지 수행하지 않는다.

## 홈 명령 이름 조회와 최신 실기 지연 (9/30)

독립 리뷰에서 일반 표시 이름(예: `서재`)의 명확한 제어 명령이 빠른 경로에서 누락되고, 허용 기기들의 직렬 상태 조회가 각 5초 타임아웃을 누적할 수 있음을 확인했다. 명확한 이름/ID 명령은 조회 실패 시 모델로 재시도하지 않으며, 이름 조회는 허용된 엔티티의 개별 REST GET을 최대 8개 병렬로 실행한다. 정확한 ID 명령은 기존처럼 직접 POST→GET 확인만 수행한다. 합성 HTTP에서 허용 기기 두 개 중 하나가 `unavailable`이어도 이름 기반 제어는 6ms에 확인됐다. 실제 HA 네트워크 측정치는 아니다.

9/30 새 운영 서버의 장치 입력 두 건에서 입력 종료→첫 TTS 전송이 2.519초와 3.645초였다. STT는 0.232/0.208초, LLM은 1.810/3.022초, TTS는 0.472/0.412초로 모델 응답이 현재 주 병목이다. 입력 원문과 실제 스피커 청취 결과는 로그에 남지 않으므로 이 수치만으로 사용자의 체감 성공을 주장하지 않는다. 전체 Docker 회귀는 540 passed, 1 skipped 및 client-sim 통과다.

## 9/30 최신 Claude 후보 갱신

공식 [Claude Sonnet 5.5 모델 페이지](https://platform.claude.com/docs/en/models/sonnet-5-5/overview)는 2026-09-28 출시한 `claude-sonnet-5-5`를 최신 속도·지능 균형 모델로 설명한다. 기존 Haiku 4.5는 가장 빠르지만 [모델 목록](https://platform.claude.com/docs/en/models/overview)의 은퇴 예정 시점이 가까워 Claude 기본 후보를 Sonnet 5.5로 바꿨다. 이 PC에는 Claude API 키가 없어 현재 실제 음성 경로의 Gemini 3.8 Flash 속도에는 영향이 없다. Claude를 활성화하면 Sonnet 5.5는 Haiku보다 비용이 높고 실제 지연은 키·계정 환경에서 다시 측정해야 한다.

[공식 마이그레이션 안내](https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide)에 따라 `temperature`를 빼고, 음성 폴백에 `thinking.type=between_tools`와 `output_config.effort=low`를 쓴다. 응답의 `text` 블록만 사용자 출력에 연결한다. 기존 사용자 지정 Claude 모델과 Haiku 요청 형식은 유지한다. OpenAI의 [모델 목록](https://developers.openai.com/api/docs/models)은 GPT-6 Luna를 효율형으로, Google의 [모델 목록](https://ai.google.dev/gemini-api/docs/models)은 Gemini 3.8 Flash를 최신 신규 프로젝트 후보로 계속 표시해 주 경로는 변경하지 않았다.

9/30 계약 테스트에서 Sonnet 5.5 요청이 `temperature`를 생략하고 `thinking.type=between_tools`, `output_config.effort=low`를 사용하며 thinking 블록을 음성 답변에 합치지 않음을 RED→GREEN으로 확인했다. 모델 기본값과 CLI 기본값도 함께 검증했다. Docker Compose 전체 재빌드 **541 passed, 1 skipped, 3 warnings**, exit0; `client-sim smoke passed`. Claude 키가 없어 실제 Sonnet 5.5 응답·지연은 측정하지 않았다. 로그인 작업의 운영 서버는 재시작 후 Gemini 3.8 Flash 합성 웹 응답 1.883초, COM3 연결과 STT/TTS 준비를 반환했다.

## 10/6 공식 모델 재확인과 직접 제어 확대

[OpenAI 모델 목록](https://developers.openai.com/api/docs/models)과 [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna)는 현재 효율형 GPT-6 Luna를, [Google 모델 목록](https://ai.google.dev/gemini-api/docs/models)은 최신 안정 Flash인 Gemini 3.8 Flash를, [Claude Sonnet 5.5](https://platform.claude.com/docs/en/models/sonnet-5-5/overview)는 최신 Sonnet을 계속 제공한다. 음성 지연과 비용을 고려한 기존 기본 후보 gpt-6-luna/gemini-3.8-flash/claude-sonnet-5-5를 유지한다. 키가 없는 OpenAI/Claude 실제 계정 응답은 검증하지 않았다.

10/6 홈 직접 경로는 현재 발화 전체에 맞는 순차 명령으로 확대했다. 전 대상과 4회 예산을 먼저 확인하고 요청 순서대로 제어하므로 해당 경로에는 모델 왕복이 없다. 이전 기록의 복합 요청 모델 경로는 이 변경으로 대체됐다. 인용·질문·모호한 선택과 모델 자체 홈 제어 제안은 실제 기기 변경으로 연결하지 않는다. 긴 개인 목록도 다섯 항목과 실제 다음 ID로 이어볼 수 있다. 최종 Docker 검증 570 passed, 1 skipped, client-sim/CLI 통과.

### 10/6 채널 간 직접 조회 대기 감소

운영 합성 쓰기가 장치 음성과 겹칠 때 공유 턴 잠금의 대기를 확인했다. ToolAgent.try_direct를 분리하고 사용자별 턴 잠금과 짧은 공용 상태 잠금을 사용해, 다른 사용자의 직접 개인 조회가 느린 모델 종료 전 완료되게 했다. 같은 사용자의 대화와 홈 전체 제어 순서는 유지한다. 일반 사용자 모델 자체는 공급자 상태 보호를 위해 직렬로 유지한다. Docker RED2→GREEN 및 독립 리뷰 PASS, 전체575 passed/1 skipped와 client-sim/CLI 통과다. 이 기능을 모델 자체 추론 시간의 단축이나 모든 모델 호출의 병렬화로 소개하지 않는다.

### 10/8 최종 운영 재확인

선제 응답은 개인 상태와 도구를 쓰지 않는 일회성 경로로 격리했고, 사용자 모델 턴이 진행 중이면 즉시 건너뛴다. 전체 Docker 591 passed/1 skipped와 통신/CLI 및 독립 리뷰를 마친 소스를 운영 작업에 반영했다. COM3, turbo/CUDA 및 STT/TTS 준비가 정상이며 Gemini 실제 웹 응답 2.117초 동안 다른 화자 직접 목록 조회는 7ms였다. 음성 전체 왕복 수치와 구분한다. 실제 응답 내용의 원문은 로그에 남기지 않았다. 상세 결과와 남은 외부 조건은 NEXTGEN_AGENT_VERIFICATION.md의 10/7~8 기록에 있다.
