# 차세대 ccoli 구현 계획

**Goal:** 개인 기억·할 일·홈 도구를 수행하는 에이전트를 실제 ESP32 음성 단말에서 검증한다.
**Architecture:** 기존 AgentMode/LLMClient/오디오 전송은 유지한다. PersonalStore, ToolAgent, HomeAssistantIntegration을 작은 경계로 추가한다.
**Tech Stack:** Python, SQLite, requests, FastAPI, Arduino ESP32, Docker Compose.
**Spec:** [NEXTGEN_AGENT_PRD.md](NEXTGEN_AGENT_PRD.md).

## 공통 제약과 결정

- 모든 자동 테스트는 Docker에서 실행한다. 기존 변경과 개인 상태는 보존한다.
- 사용자 요청은 설계와 전체 실행을 포함한다. 작업 중 추가 범위 승인으로 중단하지 않는다.
- 구현마다 실패 재현→최소 구현→통과→스펙 리뷰→품질 리뷰를 진행한다.
- 기존 staged/unstaged 변경이 혼재하므로 일괄 커밋하지 않는다.
- 파일 단위 소유권으로 충돌을 피한다. 새 기능 활성화는 회귀 통과 후 진행한다.
- 실행 엔진은 JSON을 엄격히 파싱하고 등록 도구만 실행한다. shell/eval/임의 URL 도구는 없다.

## 1. 환경과 기준 검증

- [x] 문서/작업 트리/COM 포트/설치 도구 조사.
- [x] Docker 실패 원인 조사 및 가역 복구. 손상된 run 소켓 디렉터리를 백업 이름으로 보존했으며 데이터·볼륨을 삭제하지 않음.
- [x] 기준 전체 테스트: 294 passed, 1 skipped. 최종 회귀는 별도 실행.
- [x] client-sim passed (exit0).
- [x] firmware-build 4개 variant passed (exit0).

## 2. 개인 상태 저장소

파일: `server/src/personal_store.py`, `server/tests/test_personal_store.py`.
인터페이스: `PersonalStore(path)`, `remember(owner,text)`, `recall(owner,query='')`, `forget(owner,item_id)`, `add_task(owner,title)`, `list_tasks(owner,include_done=False)`, `complete_task(owner,item_id)`.

- [x] 다른 owner로 조회/삭제/완료 불가, 재시작 보존, 빈 입력과 길이 초과, SQL 문자열, 동시 요청 테스트 작성.
- [x] Docker에서 RED 확인.
- [x] 연결별 트랜잭션/매개변수 SQL/명시적 입력 검증 구현.
- [x] Docker GREEN과 독립 리뷰. (실행 엔진 후속 리뷰 수정은 아래 진행 기록 참조)

검증: `docker compose -f docker/docker-compose.test.yml run --rm server-test pytest server/tests/test_personal_store.py -q`.
롤백: 엔진 비활성화. SQLite 파일은 보존.

## 3. 도구 실행 엔진

파일: `server/src/tool_agent.py`, `server/tests/test_tool_agent.py`, `server/src/agent_mode.py`.
인터페이스: `ToolAgent(llm,store,home=None)`, `run(text,owner,history)->str`, `catalog()->list`, `recent_runs()->list`.
LLM 응답은 `{"answer":"..."}` 또는 `{"tool":"memory.remember","arguments":{"text":"..."}}`. 사용자 식별자는 모델 인자가 아닌 서버에서 주입한다.

- [x] 개인 도구/알 수 없는 도구/초과 인자/최대 4회/도구 오류/LLM 오류 테스트 작성 후 RED 확인.
- [x] allowlist·인자 스키마·도구 결과 데이터 경계·크기 제한과 인자 없는 실행 메타데이터 구현.
- [x] 일반 텍스트 답변과 기존 공급자 호환. 성공 결과 없이 동작 완료 문장을 합성하지 않음.
- [x] AgentMode에 opt-in 설정과 기존 fallback을 통합하고 사용자별 memory prompt/refresh 격리를 테스트.
- [x] Docker GREEN과 독립 리뷰. (실행 엔진 후속 리뷰 수정은 아래 진행 기록 참조)

## 4. Home Assistant 연결

파일: `server/src/integrations/home_assistant.py`, `server/tests/test_home_assistant.py`.
인터페이스: `HomeAssistantIntegration(base_url,token,allowed_entities)`, `states()`, `control(entity_id,action)`.

- [x] fake HTTP session으로 허용목록 밖, 지원하지 않는 domain/action, 타임아웃, 401, redirect, 잘못된 JSON 테스트→RED.
- [x] 환경변수 토큰과 고정 REST 경로, 타임아웃, redirect 차단 구현.
- [x] POST 응답 후 상태 조회로 목표 상태 확인. 응답 불명확 시 성공이라고 주장하지 않음.
- [x] ToolAgent에 home.states/home.control 등록, Docker GREEN과 독립 리뷰.

## 5. 운영과 사용 흐름

파일: `server/web/routes/api_agent.py`, `server/web/app.py`, `server/config_loader.py`, `server/server.py`, `server/env.example`, `docs/NEXTGEN_AGENT_GUIDE.md`, README/QUICKSTART.

- [x] 인증된 도구 카탈로그·실행 기록 API 회귀→RED.
- [x] 환경변수 기반 opt-in과 운영 API 연결. 실행 기록에 원문·인자·토큰이 없음을 테스트.
- [x] 기존 웹 채팅을 통해 기억·할 일·도구 결과를 사용. 별도 UI 재작성 없이 기능 접근 가능.
- [x] 설정·시나리오·복구 문서와 Docker 전체 회귀.

## 6. 실제 장치와 릴리즈 검증

- [x] 보드 모델 확인. COM3의 장치를 사용자가 ESP32 Atom Echo로 확인했다 (10/8).
- [x] 포트 DTR/RTS false 상태로 수동 수신 진단 및 기존 프로토콜 확인.
- [x] Arduino 빌드 환경 및 4개 이미지 준비. 기존 기기가 호환 프로토콜로 통신하므로 펌웨어 교체는 불필요. 향후 교체가 필요하면 보드 모델 확인과 flash 백업/해시 후 업로드.
- [x] LLM/STT/TTS 실행 환경 구성. 키는 존재 여부만 확인하며 값을 출력하지 않음.
- [x] 서버 기동, PING/PONG 및 TTS 수신, 실제 사용자 마이크 발화의 STT/LLM/TTS 왕복. 최신 장치 로그와 10/8 사용자 가청 응답 확인을 함께 기록했다.
- [x] 서버 재시작 후 COM3 핸드셰이크 복구, 명시적 기억/할 일의 재시작 보존, 개인별 격리 실제 API 확인.
- [x] COM3 포트 소실→재등장 후 자동 재연결·핸드셰이크·후속 음성 전송 확인 (9/22 23:20~21 로그).
- [x] 가청 응답 사용자 확인 (이전: 다 들려, 10/8: 잘들려). 체감 속도 만족 여부는 이 답변만으로 추정하지 않는다. 케이블 조작 자체는 직접 관찰하지 않음.
- [x] 검증 결과·재현 명령·미해결 외부 조건을 `docs/NEXTGEN_AGENT_VERIFICATION.md`에 기록. 실제 증거가 없으면 완료 처리하지 않음.

## 검증 진행 기록

개인 상태 60 passed 및 독립 리뷰 PASS, Home Assistant 45 passed 및 독립 리뷰 PASS. ToolAgent 초기11 passed, runtime 초기45 passed. 이후 리뷰에서 실패 후 성공 주장/Soul/의도 처리 회귀를 발견해 추가 RED 테스트 및 수정 진행. 실제 실행 환경과 Whisper small 준비, Gemini 실응답 성공. 자세한 상태는 NEXTGEN_AGENT_VERIFICATION.md 참조.

## 9/25 홈 이름 조회와 실패 격리 보완

독립 리뷰에서 이름에 `조명`/`스위치`가 없는 허용 기기는 명확한 `켜줘`/`꺼줘` 명령에서도 모델 경로로 돌아가고, 이름 조회는 허용 엔티티마다 직렬 GET(각 5초)하여 하나가 실패하면 모델 경로까지 지연된다는 점을 확인했다.

1. Docker RED: 일반 친숙한 이름의 단일 명령은 모델 없이 제어되고, 부정/방법 요청은 제어되지 않는 회귀를 추가한다.
2. Docker RED: 허용된 엔티티의 개별 `/api/states/{entity_id}` 요청을 상한이 있는 병렬 실행으로 줄이고, 어느 하나라도 실패하면 제어 없이 안내하도록 검사한다. 전체 `/api/states` 조회로 허용 목록 밖의 상태를 받아오지 않는다. 조회 실패 후 모델 재시도로 제어하지 않는다.
3. GREEN: 현재 `home.control`의 allowlist·POST 후 GET 확인은 그대로 사용한다. 전체 Docker 테스트와 합성 HTTP 홈 시나리오를 재검증한다.
4. 운영 서버를 최신 코드로 재시작하고 COM3·진단·비밀정보 없는 지연 로그를 확인한다. 실제 홈 인스턴스가 없으면 합성 검증과 분리해 기록한다.

## 9/30 사용자 로그인 후 운영 지속성

재개 시 COM3는 다시 존재했지만 서버 프로세스가 없었다. 이 PC의 개인 런처를 로그인 시 시작하는 사용자 계정 작업을 설치하고 수동 시작으로 작업 상태·HTTP·COM3·모델 준비를 검증한다. 작업 파일은 `scripts/install_windows_autostart.ps1`; 개인 키는 작업 정의에 넣지 않는다. 로그인을 다시 수행한 후 자동 발화 여부는 향후 실기 확인으로 남긴다. 작업을 제거할 때는 `Unregister-ScheduledTask -TaskName 'ccoli Nextgen Agent' -Confirm:$false`를 사용하고 개인 데이터·서버 설정은 보존한다.

## 9/30 Claude 기본 모델 갱신

공식 Claude 문서에서 `claude-sonnet-5-5`가 9/28 공개된 최신 속도·지능 균형 모델이며 기존 Haiku 4.5의 은퇴 예정일이 가까움을 확인했다. 기본 Claude 후보를 Sonnet 5.5로 바꾼다. 이 모델은 기본 adaptive thinking과 non-default temperature 금지가 있으므로, 음성 폴백 지연을 줄이기 위해 `thinking.type=between_tools`, `output_config.effort=low`를 명시하고 temperature를 보내지 않는다. 기존 Haiku/사용자 지정 모델의 요청 형식은 유지한다. Docker RED→GREEN으로 요청 payload와 설정/CLI 기본값을 검증한 뒤 전체 회귀를 실행한다. Claude API 키가 없어 실제 계정 성공은 별도로 남긴다.

공식 근거: https://platform.claude.com/docs/en/models/sonnet-5-5/overview 및 https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide .

## 9/30 긴 저음량 녹음의 발화 보존

현장 로그에서 일부 입력은 약 8.18초로 펌웨어 최대 VAD 길이에 닿고 전체 RMS -46.7~-51.8 dBFS라 서버가 STT 전에 폐기했다. 원본을 저장하지 않아 사람 발화 여부는 확정할 수 없다. 전역 임계값을 낮추면 0.68초 잡음도 통과할 수 있으므로, 전체 RMS가 -45 dBFS 아래일 때만 240ms 범위의 20ms 창 12개 중 최소 9개가 -45 dBFS 이상인지 확인한다. 짧은 자음·폐쇄 구간과 검사 창 경계 어긋남을 허용하되, 100ms 단발 충격음은 통과시키지 않는다. 이 조건을 만족하면 기존 faster-whisper VAD/no-speech 검사로 넘긴다. 전부 조용한 입력은 유지해서 폐기한다.

1. 합성 PCM만 사용하는 Docker 테스트를 먼저 추가해 긴 입력의 국소 발화 허용, 지속 잡음 거부, 단발 충격음 거부를 RED로 확인한다.
2. 서버 pre-STT 필터에 작은 창별 에너지 함수를 추가하고 전체 RMS 경로와 로그의 개인정보 비기록을 유지한다.
3. Docker 전체/프로토콜/CLI 게이트를 실행하고 운영 작업만 재시작해 COM3 및 준비 상태를 검증한다. 사용자의 의도 발화가 확인되기 전에는 체감 개선을 주장하지 않는다.

롤백: 서버의 창별 예외 검사 호출만 제거하면 이전 전체 RMS 필터로 돌아간다. 펌웨어 및 개인 데이터는 변경하지 않는다.

## 9/30 개인 조회의 모델 왕복 단축

최신 운영 서버의 합성 기억 저장→조회→삭제→재조회는 각각 약 3.29/3.00/4.35/3.24초였다. 네 도구 모두 성공했지만 단순 조회가 모델 호출 1~2회에 묶인다. 선택지는 (A) 모든 자연어를 규칙으로 해석, (B) 명확한 전체 목록 요청만 서버에서 직접 읽기, (C) 현 모델 경로 유지다. 오인 위험과 지연을 고려해 B를 선택한다.

1. 사용자별 단일 요청인 한국어 `내 할 일 보여줘`/`내 기억 목록 보여줘` 등의 정확한 전체 목록 표현만 직접 처리한다. 완료 항목·부분 검색·복합·방법·부정·쓰기 요청은 기존 모델 경로다.
2. 모든 직접 조회는 기존 `_execute`로 처리해 owner 격리, 성공 기록, 오류 격리, 출력 크기 제한을 유지한다. 모델 호출 없이 현재 턴 저장소 결과만 말한다.
3. Docker RED에서 모델이 필요 없는 단일 조회, 다른 사용자 데이터 격리, 복합 요청 우회 금지, 저장소 오류 안내를 확인한다. GREEN 뒤 전체 Docker/CLI/프로토콜 게이트와 실운영 합성 조회 지연을 측정한다.

롤백: 직접 개인 조회 분기만 제거하면 기존 모델 도구 경로로 복귀한다. 저장 데이터 형식과 펌웨어는 변경하지 않는다.

## 9/30 긴 개인 목록의 이어보기

현행 `_read_summary`는 목록 결과가 2000자를 넘으면 모든 항목 대신 범위 축소 안내만 반환한다. 할 일/기억 도구에는 범위 지정 인자가 없어 사용자는 반복 요청해도 나머지를 볼 수 없다. 저장소·도구 스키마를 즉시 바꾸는 대신, 이미 소유자별로 조회한 결과를 음성에 적당한 다섯 항목 단위로 보여주고 다음 미표시 항목의 실제 ID를 이어보기 커서로 사용한다.

1. Docker RED: 긴 할 일/기억 목록의 첫 다섯 항목, 생략 개수와 다음 ID 안내, 이어보기, 다른 소유자 격리, 잘못된 이후 ID의 빈 결과를 검증한다. 복합·쓰기 요청은 이 경로에 들어오지 않는다.
2. 직접 개인 조회에서만 목록 표현을 제한하고 `N번부터` 단일 조회를 추가한다. 원문·인자는 실행 기록에 남기지 않으며 읽기는 기존 `_execute`를 거친다. 긴 기억 본문은 목록에서 짧게 표시하고 말줄임표로 알린다.
3. 전체 Docker/프로토콜/CLI 및 운영 합성 owner의 다수 항목을 검증하고 합성 데이터를 제거한다. 실제 음성 발화 완료로 주장하지 않는다.

롤백: 이어보기 파서와 형식화 함수를 제거하면 기존 전체 목록 응답으로 돌아간다. SQLite와 펌웨어는 변경하지 않는다.

## 9/30 저장 내용의 홈 제어 유도 차단

1. RED: 이전 대화/저장 텍스트에 기기 조작 명령이 있어도 현재 요청이 인사·조회·부정·사용법 문의이면 모델이 제안한 `home.control`을 실행하지 않는 회귀 테스트를 작성한다. 현재 발화의 명시적 조작과 기존 다단계 조작은 유지한다.
2. GREEN: 현재 턴의 문장 전체에 일치하는 홈 제어를 직접 실행하고 모델 home.control은 차단한다. 전체 대상과 상태 조회 포함 4회 예산을 먼저 검증하며 기존 allowlist·POST 후 상태 검증을 유지한다. 인용 속 명령은 홈 제어 증거를 요구하지 않고 실제 홈 연결이 없는 명령은 설정 안내를 직접 반환한다.
3. Docker에서 해당 테스트와 전체 테스트, client-sim 및 CLI 스모크를 확인한다. 독립 스펙·품질 리뷰와 운영 서버 재기동 후 격리된 합성 요청으로 확인한다.
4. 롤백은 복합 직접 홈 파서/실행과 모델 제어 차단, 관련 테스트를 함께 되돌린 뒤 같은 Docker 게이트를 재실행하는 것이다. 개인 SQLite 형식은 변경하지 않는다.

## 10/6 홈 제어 경계의 최종 설계

독립 리뷰의 인용문·대안 선택 및 복합 명령 대상/순서 위험을 반영해 단어 기반 모델 허용 검사를 사용하지 않는다. 현재 문장 전체에 일치하는 단일/순차 조작만 서버 파서가 대상과 순서를 확정하고, 모든 대상과 상태 조회 포함 최대 4회 예산을 먼저 확인한 뒤 순서대로 직접 실행한다. 실패 후 모델로 제어를 재시도하지 않으며 중간 실패는 확인된 단계만 보고한다. 모델 카탈로그에서는 홈 제어를 광고하지 않고 모델의 home.control 제안은 무조건 거부한다. 기억·할 일·홈 상태 읽기 도구는 기존 모델 경로를 유지한다.

- Docker RED: 인용·모호한 선택 4개, 직접 순차 제어/대상 선검증 3개 실패 확인.
- GREEN: 최초 관련 ToolAgent 106개 통과 후 리뷰 제보의 인용 증거·미설정·문장부호 경계를 추가 보정해 최종 110개 통과. 기존 fake Home은 실제 어댑터 규약의 states를 갖추도록 보강했다.
- 이후 전체 Compose/CLI/client-sim, 독립 리뷰, 운영 재기동·격리 HTTP 검증을 수행한다.

## 10/6 빠른 요청의 다른 채널 대기 제거

운영 합성 쓰기와 장치 음성이 겹칠 때 AgentMode._tool_turn_lock이 모델 왕복 전체를 잠가 다른 사용자/채널의 로컬 조회도 기다린다. 대안 A는 모든 공급자 호출을 즉시 병렬화(공유 오류/활성 후보 상태 경쟁 위험), B는 사용자별 턴 순서와 짧은 공용 상태 잠금을 분리하고 명확한 직접 조회·홈 제어가 다른 사용자의 모델을 기다리지 않게 하기, C는 기존 직렬 대기 유지다. 공급자 상태를 보존하면서 실질적인 대기를 줄이는 B를 적용한다.

1. server/tests/test_nextgen_runtime.py에서 느린 합성 웹 모델을 Event로 정지시킨 동안 다른 소유자의 실제 개인 조회가 먼저 완료되는 RED 테스트를 작성한다. 같은 소유자는 기존 턴 순서를 유지하고 다른 소유자의 입력/응답이 섞이지 않는 테스트도 포함한다.
2. ToolAgent.try_direct(text,owner,history)로 검증된 직접 경로를 분리한다. 모델 run도 이 경로를 재사용하며 홈 순차 제어는 전용 잠금으로 다른 사용자 간에도 순서를 보존한다.
3. AgentMode는 사용자별 턴 잠금, 짧은 공용 상태 잠금, 기존 모델 호출 잠금을 구분한다. 스케줄러/감정/카운터/공용 상태 갱신은 짧은 잠금 안에서 수행하고 모델 왕복 중에는 직접 경로를 막지 않는다. 일반 사용자 요청의 모델 자체 호출은 직렬로 유지하며 병렬화하지 않는다. 기존 proactive 레거시 경로는 별도이며 현재 운영에서는 비활성이다.
4. Docker RED→GREEN, 소유자 순서/격리 및 홈 제어 회귀, 독립 리뷰와 전체 Compose/client-sim/CLI를 완료한 뒤 운영 재기동한다.

롤백은 AgentMode의 전체 턴 잠금과 ToolAgent.run의 직접 경로로 복귀하는 것이다. 저장소 형식과 펌웨어는 변경하지 않는다.

## 10/7 선제 대화의 개인 상태 격리

완료 감사에서 AgentMode.generate_response(is_proactive=True)가 개인 에이전트의 격리 경로를 우회하여 공용 User/Relation/Memory와 개인 대화 기록을 프롬프트에 넣고 MemoryManager.after_turn으로 재추출할 수 있음을 확인했다. 대안 A는 선제 대화를 영구 제거, B는 공용 Soul과 현재 트리거 문장만 쓰는 일회성 대화, C는 이름 없이 특정 사용자 기억을 자동 선택하는 것이다. 선제 대화 기능과 화자 격리를 함께 유지하는 B를 적용한다.

1. server/tests/test_nextgen_runtime.py에서 기본 화자/이름 있는 화자의 개인 기록, 공용 개인 문서, 자동 추출, 제어 의도, 모델 대기와 오류 문자열 비노출을 Docker RED로 재현한다. 합성 표식만 사용한다.
2. 개인 에이전트 모드의 선제 생성은 _generate_proactive_response(text)로 분리한다. 공개 Soul과 트리거 문장만 보내고 개인 대화 기록을 읽거나 저장하지 않는다. 도구 실행과 장치 제어 의도를 전달하지 않는다. 일반 사용자 모델 턴이 이미 진행 중이면 조용히 건너뛰며 공급자 공유 상태를 동시에 사용하지 않는다.
3. 대화 카운터/감정 같은 공용 상태는 기존 짧은 잠금으로 갱신한다. 내부 오류 원문을 로그·응답에 노출하지 않는다. 기존 개인 에이전트 비활성 모드는 유지한다.
4. 독립 스펙/품질 리뷰, 전체 Compose/client-sim/CLI를 통과한 뒤 본 PC 작업을 재시작하고 연결·준비·합성 웹 요청을 검증한다. 선제 설정 자체는 본 PC에서 비활성 상태를 유지한다.

롤백: 개인 에이전트의 선제 생성 분기와 관련 테스트만 되돌린다. 개인 SQLite와 기존 메모리 문서는 변경하거나 삭제하지 않는다.

10/7~8 검증 보강: 기본 Docker RED9, 모델 콜백 재진입 RED1, 태그/중첩 도구 JSON RED3, 접두 평문+JSON/코드펜스 RED3을 확인했다. 모델 잠금은 재진입하지 않는 Lock으로 공유해 같은 스레드 콜백의 선제 호출도 skip한다. 선제 출력은 제어 태그를 모두 제거하고 answer JSON을 풀어낸 뒤, 본문 어디에든 JSON 중괄호나 코드펜스가 남으면 발화하지 않는다. 일반 사용자의 코드/도구 응답에는 이 선제 전용 형식 제한을 적용하지 않는다.

## 10/8 운영 HTTP·실시간 이벤트 인증

완료 감사에서 PRD 구현 범위 5의 인증된 운영 API와 실제 토큰 미설정 간의 공백을 확인했다. 현재 /api/agent/의 무인증 응답은 200이다. /ws는 인증 없이 chat_response와 로그 이벤트를 받을 수 있어 토큰 설정만으로 실시간 경로가 보호되지 않는다. A(HTTP 토큰만 설정), B(기존 토큰 UI와 HTTP 인증을 유지하며 WebSocket 첫 프레임까지 인증), C(새 사용자 계정 시스템)를 비교해 B를 적용한다.

1. server/tests/test_web_auth.py에 무인증/오인증 WS 거부, 정상 토큰 broadcast 수신, 등록 전 개인 이벤트 차단, Unicode 토큰 및 시간/크기 제한의 Docker RED 회귀를 추가한다.
2. server/web/auth.py의 공용 constant-time 비교, server/web/app.py의 제한 시간 내 첫 인증 프레임 검증 후 등록, server/web/static/dashboard.js의 토큰 저장/삭제에 따른 재연결과 4401 재시도 중단을 구현한다. 토큰을 URL·로그·화면 텍스트에 넣지 않는다. 토큰을 미설정한 기존 설치의 동작은 유지한다.
3. 본 PC server/.env에 기존 비밀값을 보존하고 강한 무작위 WEB_AUTH_TOKEN을 설정한다. 값은 소스·문서·보고서·명령 출력에 넣지 않는다. 기존 토큰이 있으면 유지한다. Docker 스펙/품질 리뷰와 전체/통신/CLI 게이트 이후 운영 작업만 재시작한다.
4. 실제 운영 무인증/잘못된 인증은 401, 정상 인증은 도구/진단/합성 채팅 정상, COM3/STT/TTS 준비를 검증한다. 브라우저는 기존 고급 진단의 토큰 입력 흐름을 사용하며 첫 연결에서 인증 토큰을 저장해야 한다. 실제 사용자 데이터 조회는 검증에 사용하지 않는다.

롤백: server/.env의 WEB_AUTH_TOKEN을 비우고 서버를 재시작하면 이전 로컬 무인증 동작으로 돌아간다. 개인 저장소와 다른 공급자의 키는 유지한다. 코드 롤백은 HTTP·WS·브라우저 인증 변경과 대응 테스트를 함께 되돌린다.

독립 리뷰의 배포 전 보강:
- 잘못된 Unicode 토큰은 인증 실패로 처리해 WebSocket 4401 종료를 유지한다. 브라우저 HTTP는 Unicode 토큰을 UTF-8/base64url로 인코딩하고 X-Auth-Token-Encoding: utf8-base64url을 명시한다. 기존 ASCII X-Auth-Token 요청은 호환한다.
- 인증 토큰 저장/삭제 시 개인 캐시·화면을 지우고 인증 세대를 바꿔 이전 요청의 늦은 결과를 무시한다. 실제 dashboard.js를 Docker Node VM에서 실행하는 행동 스모크를 추가한다.
- Config.save는 환경에서 유입된 비밀 경로를 YAML 원본값으로 복원한 사본만 저장한다. 기존 YAML의 명시값과 비밀 아닌 설정 편집은 보존한다. 인증된 설정 조회도 기존 bot_token/client_secret/refresh_token까지 마스킹한다. 본 PC의 추적 YAML에는 비어 있지 않은 알려진 비밀 필드가 없음을 값 출력 없이 확인했다.
- CI/CD와 로컬 전체 게이트의 단일 진입점 scripts/run_docker_tests.sh에 dashboard-test Compose 서비스를 추가한다. 서비스는 브라우저 JS와 행동 스모크 두 파일만 읽기 전용으로 마운트하며 개인 .env/메모리를 마운트하지 않는다.
