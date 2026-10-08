# 차세대 ccoli 사용 가이드

기존 ESP32 음성·웹 채팅에 개인 기억, 할 일, 허용한 홈 기기 도구를 추가한다. 기존 Soul.md 말투는 유지하며 새 개인 기억은 SQLite에 사용자별로 분리한다.

## 이 PC에서 시작

이 PC의 저장소 루트 PowerShell에서 실행한다:

```powershell
& ./output/nextgen-runtime/Scripts/python.exe ./output/nextgen-runtime/run_server.py
```

이 PC 전용 런처는 개인 키를 파일에 복사하지 않고 `server/.env`를 읽는다. COM3 유선 연결, 로컬 웹 대시보드, 개인 도구, Gemini API 우선, Whisper `turbo`/CUDA를 설정한다. 현재 운영 모델은 `gemini-3.8-flash`; Claude/OpenAI 기본 모델명은 각각 `claude-sonnet-5-5`, `gpt-6-luna`지만 해당 API 키는 이 PC에서 설정되지 않았다. 이 PC의 독립 실행 환경에는 CUDA 12/cuDNN 9와 Whisper `turbo` 캐시가 준비되어 있다. 처음 로드할 때는 모델 준비가 필요하며 이후 요청의 인식 시간과 구분한다. 키를 명령줄·Git·로그에 남기지 않는다. 로컬 장애 대체 모델은 이 PC에 설치한 `qwen3.5:4b`이며 첫 호출이 느릴 수 있다. 다른 PC에서는 Ollama가 준비된 뒤 `ollama pull qwen3.5:4b`로 추가한다. 최신 모델·속도 비교와 한계는 [업그레이드 기록](MODEL_LATENCY_UPGRADE.md)에 적었다.

이 PC에서는 사용자 로그인 시 서버를 다시 시작하는 `ccoli Nextgen Agent` 작업을 설치했다. 현재 상태는 `Get-ScheduledTask -TaskName 'ccoli Nextgen Agent'`로 확인하고, 이미 종료됐다면 `Start-ScheduledTask -TaskName 'ccoli Nextgen Agent'`로 시작한다. 같은 PC에 다시 설치할 때는 `./scripts/install_windows_autostart.ps1`을 실행한다. 작업은 이 PC의 `output/nextgen-runtime`과 `server/.env`를 사용하므로 이 경로를 옮기면 작업을 다시 설정해야 한다. 콘솔 없는 시작 로그는 `output/nextgen-runtime/task-YYYYMMDD.*.log`, 앱 로그는 `server/logs/`에 기록된다. 자동 시작이 필요 없으면 `Unregister-ScheduledTask -TaskName 'ccoli Nextgen Agent' -Confirm:$false`로 등록을 해제한다.
저장소의 표준 `ccoli start` 경로도 `server/config.yaml`에서 개인 도구 활성화, `127.0.0.1` 대시보드, Gemini API 우선과 유선 연결을 읽는다. 이 PC의 CUDA/cuDNN 및 COM3 지정은 위 전용 런처가 담당한다. 다른 기기에서 대시보드에 접속하려면 인증 토큰과 `WEB_HOST` 네트워크 주소를 명시적으로 설정한다.

## 대화 예시

- 나는 디카페인 커피를 좋아한다고 기억해 줘.
- 내가 좋아하는 커피가 뭐지?
- 우유 사기를 할 일에 추가해 줘.
- 내 할 일을 보여 줘.
- 우유 사기 할 일을 완료해 줘.
- 커피에 대한 내 기억을 삭제해 줘.
- 서재 조명 켜줘. (Home Assistant에서 허용한 기기 이름일 때)

명확한 단일 전체 목록 요청(예: `내 할 일 보여줘`, `내 기억 목록 보여줘`)은 모델 호출 없이 해당 사용자 저장소를 즉시 읽는다. 완료 항목 조회, 부분 검색, 복합 요청과 변경 명령은 기존 모델 도구 경로를 사용한다. 긴 목록은 다섯 항목씩 읽고 다음 항목의 실제 ID를 안내한다. 예를 들어 `내 할 일 6번부터 보여줘` 또는 `내 기억 6번부터 보여줘`라고 말해 이어본다. 긴 기억 본문은 목록에서 일부만 표시하며 말줄임표로 알린다.

다른 사용자의 웹/음성 모델 응답이 진행 중이어도 명확한 개인 목록 조회는 먼저 처리한다. 같은 사용자의 요청은 앞선 턴이 끝난 뒤 처리해 대화 순서를 유지한다. 홈 기기의 순차 명령은 다른 사용자의 제어와 섞이지 않게 실행한다.

기억/할 일은 사용자별로 저장된다. 웹은 기본 web_user, 식별되지 않은 음성은 device를 사용한다. 식별자는 분리용 키이며 인증 수단이 아니다. 여러 사용자가 서로를 신뢰하지 않는 공개 서비스로 노출하지 않는다. 기존 로컬 일정은 가정 공용이며 개인 할 일과 별개다.

## 연결과 복구

[Home Assistant 안내](HOME_ASSISTANT_GUIDE.md)에 따라 HOME_ASSISTANT_URL, HOME_ASSISTANT_TOKEN, HOME_ASSISTANT_ALLOWED_ENTITIES를 설정한다. 허용한 light/switch의 켜기/끄기만 지원하며 요청 후 실제 상태를 다시 조회한다. 날씨/검색/Google Calendar 조회는 기존 integration 설정을 사용한다.

- 대시보드: http://localhost:8005
- API 설명: http://localhost:8005/api/docs
- GET /api/agent/: 사용 가능한 도구와 실행 성공/실패·소요 시간. 인자나 개인 기억 원문은 포함하지 않는다.
- 이 PC에는 WEB_AUTH_TOKEN을 설정했다. 대시보드 진단 탭의 고급 설정에서 server/.env의 WEB_AUTH_TOKEN 값만 인증 입력란에 넣고 저장한다. 첫 입력 후 REST 조회와 실시간 연결이 갱신되며, 인증을 지우면 다시 입력하기 전까지 보호된 정보를 읽을 수 없다. 값을 채팅·주소창·보고서에 붙여넣지 않는다.
- REST 요청에는 X-Auth-Token 헤더를 사용한다. 기존 ASCII 토큰은 그대로 보낸다. Unicode 토큰을 HTTP에서 사용할 때는 UTF-8/base64url 값과 X-Auth-Token-Encoding: utf8-base64url을 함께 보낸다(대시보드가 자동 처리). 브라우저 실시간 연결은 첫 프레임에서 같은 토큰을 검증하며 토큰을 URL에 넣지 않는다. 운영자용 공유 토큰이며 사용자별 인증은 아니다. 토큰을 미설정한 다른 로컬 설치는 기존 동작을 유지한다.
- 개인 상태 기본 경로: MEMORY_DIR/personal.sqlite3. AGENT_STATE_PATH로 별도 지정 가능.
- 이전 대화 경로로 롤백: AGENT_ENABLED=false 후 서버 재시작. SQLite 파일은 보존한다.
- COM 포트를 다른 앱이 사용 중이면 해당 Serial Monitor를 닫는다.

## 검증

```powershell
docker compose -f docker/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from server-test
docker compose -f docker/docker-compose.test.yml run --rm client-sim

docker compose -f docker/docker-compose.test.yml run --rm dashboard-test
docker compose -f docker/docker-compose.test.yml run --build --rm firmware-build
```

CI와 전체 로컬 품질 게이트의 단일 진입점은 Bash에서 실행하는 `scripts/run_docker_tests.sh`다. 서버·통신·브라우저 인증 행동·펌웨어 검증을 순서대로 수행한다. 실제 음성 왕복을 시뮬레이터로 대신하지 않는다. [검증 기록](NEXTGEN_AGENT_VERIFICATION.md)에서 실제 확인 범위를 확인한다.
## 실행 확인 범위

홈 제어는 현재 발화 전체에서 확인된 기기 이름/ID와 켜기·끄기 순서만 서버가 직접 실행한다. `서재 켜고 껐다가 다시 켜줘` 같은 순차 명령은 모든 대상을 먼저 확인하고 상태 조회 포함 최대 4회로 제한한다. 모델 도구 경로의 `home.control`은 차단해 이전 대화나 저장 내용이 기기를 조작하게 하지 않는다. 인용·질문·모호한 선택과 지원되지 않는 복합 표현은 기기 이름을 넣은 명령으로 나눠 요청한다.

명시적인 기억·할 일·홈 요청은 이번 대화 턴의 도구 성공 기록을 확인한다. 결과 없이 완료라고 답하면 제한된 횟수로 도구 실행을 다시 요청하고, 확인되지 않으면 실패를 안내한다. 요청 분류는 한국어·영어의 일반적인 표현에 대한 규칙이므로 모든 자연어의 의미를 보장하지 않는다. 복잡한 요청은 한 번에 한 동작으로 나누면 확인하기 쉽다. 방법을 묻는 질문이나 완료 항목 조회는 변경 명령으로 취급하지 않는다.

변경 도구를 실행한 턴의 응답은 실제 성공한 대상 ID와 결과를 정해진 형식으로 요약한다. 모델의 자유로운 완료 문장을 그대로 사용하지 않는다. 일부 변경 후 다른 요청이 실패하거나 실행 한도에 도달하면 성공한 부분과 실패 안내를 함께 표시한다. 복합 요청 전체의 의미를 자동으로 검증하는 기능은 아니므로 출력에 나타난 실제 대상들을 확인한다.
변경과 조회를 함께 요청하면 조회한 할 일·기억·홈 상태도 한국어로 함께 표시한다. 변경 전에 조회한 데이터에는 해당 시점을 표시한다.


### 음성 합성 선택

실시간 기본값은 이 PC에서 더 빠르게 측정된 Edge TTS다. 최신 Gemini 3.8 Flash-Lite TTS를 선택하려면 `server/.env`에 `TTS_BACKEND=gemini_tts`, `TTS_MODEL=gemini-3.8-flash-lite-tts`, `TTS_GEMINI_VOICE=Kore`를 설정하고 기존 `GEMINI_API_KEY`를 사용한다. 서버를 다시 시작하면 24 kHz 출력도 ESP32용 16 kHz PCM으로 변환된다. API 오류나 키 누락 시 Edge로 복구한다. 개인 대화도 원격 TTS 공급자로 전달될 수 있으므로 설정을 바꿀 때 이 점을 고려한다. [속도 비교](MODEL_LATENCY_UPGRADE.md)를 참고한다.

## 선제 생성의 개인 상태 격리

개인 에이전트가 활성일 때 선제 응답은 공용 Soul의 말투와 현재 트리거 문장만 사용한다. 개인 SQLite, 사용자별 대화 기록 및 User/Relation/Shortterm/Longterm 문서는 선제 문맥에 자동으로 넣지 않고, 선제 결과를 개인 기록이나 공용 자동 기억 추출에 저장하지 않는다. Soul에는 함께 공유할 말투·성격을 둔다.

일반 사용자 모델 응답이 진행 중이면 선제 생성을 건너뛰어 추가 대기를 만들지 않는다. 선제 응답은 대화 문장만 출력하며 장치 제어 의도를 전달하지 않는다. 도구 JSON·코드펜스 등의 내부 표현이 포함된 결과는 발화하지 않는다. 본 PC의 선제 설정은 현재 비활성 상태이며 이 수정은 설정을 켜지 않는다. 기존 개인 에이전트 비활성 모드는 종전 동작을 유지한다.
