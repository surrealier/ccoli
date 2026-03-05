# Agent 기능 확장 계획 (현행 코드 기준)

이 문서는 **현재 코드 구조를 기준으로** 다음 요구사항을 구현하기 위한 실행 계획이다.

- (1) API 키 등록 CLI 단순화
- (2) README의 bash 예시 보강
- (3) API 실패 원인 TTS 디버깅 안내
- (4) 기능군 A~H(날씨/검색/캘린더/알림/지도/통합 아키텍처/보안/완료 기준) 구현
- (5) 화자 등록/식별(Voice ID) 기반 응답 게이트 및 개인화
- (6) 연결 방식 확장(Wi-Fi + 유선) 및 CLI 선택 지원
- (7) 공공데이터포털 기반 Home Agent 추천 API 큐레이션
- (8) 아이폰 연동 채팅 앱(개인 배포) 기획
- (9) Telegram(BotFather) 기반 아이폰 연동 기획

---

## 구현 TODO 진행현황
- [x] Integration 공통 인터페이스(`IntegrationResult`, `IntegrationError`, `BaseIntegration`) 추가
- [x] Integration Registry(등록/활성화/헬스체크/실행) 추가
- [x] Weather integration 구현 및 표준 에러 코드 적용
- [x] `AgentMode`에서 날씨 요청을 IntegrationRegistry 경유로 처리
- [x] `ccoli config integration` (`list/set/enable/disable/test`) CLI 추가
- [x] `ccoli config voice-id` (`status/enable/disable/delete/threshold`) CLI 추가
- [x] 신규 기능 테스트 케이스 추가 및 전체 테스트 통과
- [x] README bash 예시 보강(integration/voice-id 설정·검증·실패 예시)

- [x] 검색/캘린더/알림/지도 integration 모듈 1차 구현 및 Agent 라우팅 연결
- [x] Integration 실패 원인별 TTS 디버깅 템플릿 1차 적용(날씨 경로)
- [x] Voice ID 임베딩/식별 엔진(경량 기본 엔진) 및 런타임 게이트 구현
- [x] 사용자별 대화 히스토리 분리(개인화 기반) 및 프로필 저장/삭제 구현

## 0) 현재 코드 구조 요약 (Planning 근거)

### 런타임 진입점
- `server/server.py`: ESP32 오디오 수신, STT→LLM→TTS 파이프라인, agent/robot 모드 분기.
- `ccoli/cli.py`: `start`, `config wifi`, `config llm` 지원.

### 핵심 모듈
- `server/src/agent_mode.py`: 대화 메모리, 정보 서비스 호출, LLM 응답 생성, TTS 변환.
- `server/info_services.py`: 시간/날짜/날씨(OpenWeather)/뉴스(RSS)/타이머.
- `server/src/llm_client.py`: Ollama/Gemini/Claude/ChatGPT 멀티 프로바이더.
- `server/config_loader.py`: `config.yaml + .env` 병합 로딩.

### 현재 구조의 강점
- 이미 CLI 기반 설정과 `.env` 저장 경로가 존재함.
- AgentMode 내부에 `InfoServices` 주입 구조가 있어 통합 확장 포인트가 명확함.
- LLM provider abstraction이 있어 외부 API 오류 처리 레이어를 추가하기 쉬움.

### 현재 구조의 한계
- Integration별 공통 인터페이스(상태/헬스체크/에러 표준화)가 없음.
- API 실패 시 로그는 남지만 사용자 TTS 디버깅 안내가 약함.
- CLI가 Wi-Fi/LLM 중심이라 기능별 API 키 등록 경험이 분산됨.

---

## 1) 요구사항 대응 로드맵 (Phase 기반)

## Phase 0 — 연결 모드 확장(유선 + Wi-Fi)
목표: 설치 환경 제약(공유기/SSID)과 무관하게 ESP32 연결 성공률을 높인다.

1. 연결 모드 모델 추가
   - `connection.mode`를 `wifi | wired`로 명시.
   - 기본값은 기존 호환을 위해 `wifi` 유지.

2. CLI 확장
   - 신규/확장 명령:
     - `ccoli config connection mode <wifi|wired>`
     - `ccoli config wifi --ssid <ssid> --password <pw>` (wifi일 때만 필수)
   - 유선 모드일 때 SSID/PASSWORD를 요구하지 않고, 연결 확인 안내를 단순화.

3. 펌웨어/서버 설정 경로 통일
   - 아두이노 `config.h`(또는 생성 파일)와 서버 `config.yaml`에서 동일한 모드 키를 참조.
   - 모드 불일치 시 부팅 로그/CLI에서 즉시 경고.

4. 운영 UX
   - Wi-Fi: 기존 방식 유지(SSID/PW 등록 + 재부팅 안내).
   - 유선: "케이블 연결 후 자동 DHCP/링크 확인" 중심의 최소 단계 안내.
   - README/QUICKSTART에 모드별 빠른 시작 섹션 추가.

## Phase 1 — 설정 UX/문서 우선 안정화
목표: 사용자가 "설정 때문에 막히지 않게" 만들기.

1. CLI를 통합형으로 확장
   - 신규 명령:
     - `ccoli config integration list`
     - `ccoli config integration set <provider> ...`
     - `ccoli config integration enable <provider>`
     - `ccoli config integration disable <provider>`
     - `ccoli config integration test <provider>`
   - `--api-key` 단일 옵션 + provider별 필수 필드 자동 안내.
   - 키 저장은 `server/.env`만 사용, 출력은 마스킹.

2. README bash 예시 전수 보강
   - 설치/실행/설정/검증/트러블슈팅까지 **실행 가능한 명령만** 제시.
   - API 키 등록 예시를 provider별로 일관된 포맷으로 제공.
   - `config integration test` 성공/실패 예시 추가.

3. 설정 유효성 검사
   - 누락 키, 잘못된 포트, provider 오타를 CLI 단계에서 차단.
   - 실패 시 "다음 액션"까지 출력 (`어떤 키가 부족한지`, `어떤 파일을 수정할지`).

---

## Phase 2 — 통합 아키텍처 도입 (F 선행)
목표: 기능 A~E를 붙일 수 있는 공통 기반 마련.

### 2-1. 디렉토리 구조
- `server/src/integrations/`
  - `base.py`: `IntegrationResult`, `IntegrationError`, `BaseIntegration`
  - `registry.py`: 등록/활성화/권한/헬스체크
  - `weather.py`, `search.py`, `calendar_google.py`, `notify.py`, `maps.py`

### 2-2. 표준 인터페이스
- `is_configured() -> bool`
- `health_check() -> IntegrationResult`
- `execute(intent, params) -> IntegrationResult`

### 2-3. 에러 표준화
- 에러 코드 예:
  - `AUTH_INVALID_KEY`
  - `AUTH_MISSING_KEY`
  - `HTTP_4XX`, `HTTP_5XX`
  - `RATE_LIMITED`
  - `TIMEOUT`
  - `PROVIDER_UNAVAILABLE`
- 모든 에러는 사용자 친화 메시지 + 내부 디버깅 메타 포함.

### 2-4. Agent 연결점
- `AgentMode.generate_response()` 내 직접 API 호출을 줄이고,
  `IntegrationRegistry`를 통해 데이터 수집/실행.
- 결과는 LLM 컨텍스트에 주입하되, 에러는 별도 TTS 디버깅 경로로 전달.

---

## Phase 3 — 기능 A~E 구현
목표: 사용자가 체감 가능한 기능 단위 릴리스.

### A. 날씨/환경
- 현재 `InfoServices.get_weather()`를 integration으로 이관.
- 확장 범위: 현재/시간대/주간, 체감온도, 강수확률, AQI.
- 키: `WEATHER_API_KEY`.

### B. 웹 검색/지식 조회
- 실시간 검색 API(SerpAPI/Tavily 중 1개 우선) + 결과 요약.
- 키: `SERPAPI_API_KEY` 또는 `TAVILY_API_KEY`.

### C. 캘린더/일정 (Google Calendar)
- 조회/추가/수정/삭제 최소 기능.
- OAuth 토큰 저장/갱신 경로 정의.
- 키: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`.

### D. 메일/메시징 알림
- 1차: Slack/Discord 발송 + 최근 메시지 요약.
- 2차: Gmail 읽기/발송.
- 키: `SLACK_BOT_TOKEN`, `DISCORD_BOT_TOKEN`, Gmail OAuth 세트.

### E. 위치/지도/경로
- 출발지/목적지 기반 ETA + 요약 경로 안내.
- 키: `GOOGLE_MAPS_API_KEY` 또는 `NAVER_MAP_API_KEY`.

---

## Phase 4 — API 오류 TTS 디버깅 (요구사항 3)
목표: "왜 실패했는지"를 음성으로 즉시 안내.

1. 실패 감지 지점
   - Integration `execute()`/`health_check()` 실패.
   - LLM 외부 프로바이더 호출 실패 (`llm_client.py`).

2. TTS 디버깅 정책
   - 사용자 음성 출력: 간결/행동 유도 중심.
     - 예: "날씨 API 키가 유효하지 않아요. `ccoli config integration set weather --api-key ...`로 다시 등록해 주세요."
   - 내부 로그: HTTP 코드, provider 응답 본문(민감정보 마스킹).

3. 오류 분류별 멘트 템플릿
   - 인증 오류: 키 재등록 유도
   - 권한 오류: API 콘솔 권한/스코프 확인 유도
   - 서버 장애: 잠시 후 재시도 안내
   - Rate limit: 대기 시간 안내
   - 네트워크 타임아웃: 로컬 네트워크/방화벽 점검 안내

4. 재시도/폴백
   - 동일 요청 자동 재시도(1회) + 실패 시 TTS 디버깅.
   - 가능한 경우 대체 프로바이더 폴백.

---

## Phase 5 — 화자 등록/식별(Voice ID) 기능 추가
목표: 노이즈/외부 음성으로 인한 오동작을 줄이고, 사용자별 개인화 기반을 만든다.

### 5-1. 핵심 요구사항
- 사용자가 음성으로 "@@사용자 목소리 등록" 같은 의도를 말하면 등록 플로우 시작.
- 등록 플로우에서 약 5회 음성 샘플을 수집하고 임베딩(캐싱) 저장.
- 음성 명령으로 Voice ID 기능 ON/OFF 가능.
- 특정 사용자 음성 데이터 삭제 가능.
- 기능 ON 시 **등록된 화자에게만** 응답(미등록/불일치 화자는 무응답 또는 짧은 안내음).
- 목적:
  1) YouTube/TV/주변 소음으로 인한 강제 응답 제거(1순위)
  2) 장기적으로 사용자별 응답 최적화(2순위)

### 5-2. 아키텍처 제안
- 신규 모듈: `server/src/voice_id/`
  - `embedding_engine.py`: speechbrain 기반 화자 임베딩 추출
  - `speaker_store.py`: 사용자별 임베딩 저장/로드/삭제
  - `speaker_matcher.py`: 코사인 유사도 기반 식별 + 임계값 판정
  - `voice_id_service.py`: 등록/식별/모드 토글 상태 관리
- `server/server.py`의 STT 직전(또는 직후) 게이트에 Voice ID 판정 훅 추가.
- `server/src/agent_mode.py`와 연결해 등록/삭제/토글 intent 처리.

### 5-3. 데이터 모델
- 저장 위치: `server/data/voice_profiles/`
- 파일 예시:
  - `profiles.json` (메타: 사용자명, 등록일, 샘플 수, threshold)
  - `<user_id>.npy` (평균 임베딩 벡터)
- 등록 시:
  - 샘플 5개 각각 임베딩 생성
  - 이상치 제거 후 평균 벡터 저장
  - 품질 점수(SNR/길이) 낮은 샘플은 재녹음 요구

### 5-4. CLI/음성 UX 설계
1. 음성 기반(주 경로)
- 등록 시작: "@@내 목소리 등록", "@@사용자 등록"
- 토글 ON/OFF: "@@화자 인식 켜", "@@화자 인식 꺼"
- 삭제: "@@홍길동 목소리 삭제"

2. CLI 기반(보조 경로)
```bash
ccoli config voice-id status
ccoli config voice-id enable
ccoli config voice-id disable
ccoli config voice-id delete --user <name>
ccoli config voice-id threshold --value 0.72
```

### 5-5. 식별 정책 (노이즈 방지 중심)
- 모드 OFF: 기존과 동일 동작.
- 모드 ON:
  - 유사도 ≥ 임계값: 정상 처리(응답 생성)
  - 유사도 < 임계값: 요청 드롭 또는 짧은 TTS("등록된 사용자 음성만 응답해요")
- 추천 기본 임계값: 0.70~0.78 범위 실측 튜닝.
- 연속 실패 N회 시 환경 노이즈 경고 멘트 제공.

### 5-6. 개인화 확장(2순위 목적)
- 사용자 ID를 대화 메모리 키로 사용해 개인 컨텍스트 분리.
- 선호 톤/호칭/자주 묻는 주제 등 사용자 프로필 저장.
- 동일 질문이라도 사용자별 요약 길이/스타일을 다르게 적용.

---

## Phase 6 — 공공데이터포털 API 큐레이션(PRD 반영)
목표: Home Agent 활용도가 높은 무료 API를 우선 선정해 빠르게 기능화한다.

> 참고 소스: data.go.kr API 목록(무료 오픈 API 중심). 전체 전수조사 대신 **활용도/즉시성/구현 난이도** 기준으로 우선순위화.

### 6-1. 우선순위 API 리스트 (추천)

1. 기상청 단기예보/초단기실황/초단기예측
   - 사용자 질문 예: "지금 비 와?", "퇴근 시간에 우산 필요해?"
   - 핵심 값: 강수형태, 1시간 강수량, 기온, 하늘상태
   - Home Agent 가치: 매우 높음(일상 질문 빈도 최상위)

2. 기상특보/재난문자(행안부·기상청 계열)
   - 사용자 질문 예: "우리 지역 폭염 경보 떴어?"
   - 핵심 값: 특보 발효/해제 시각, 대상 지역
   - Home Agent 가치: 안전·알림 자동화에 직접 연계

3. 한국환경공단 에어코리아 대기질 API
   - 사용자 질문 예: "오늘 미세먼지 어때?"
   - 핵심 값: PM10/PM2.5, 통합대기지수, 오존
   - Home Agent 가치: 외출/환기/공기청정기 자동화 트리거로 활용

4. 공휴일 정보 API(국가공휴일)
   - 사용자 질문 예: "다음 연휴 언제야?"
   - 핵심 값: 공휴일 날짜/명칭/대체공휴일 여부
   - Home Agent 가치: 일정/알림 기능과 결합 용이

5. 실시간 전력수급/전기요금 관련 공공 API(가용한 범위)
   - 사용자 질문 예: "지금 전력 피크 시간이야?"
   - 핵심 값: 수급 상태, 시간대 구분
   - Home Agent 가치: 에너지 절약 시나리오(에어컨/세탁기 권장 시간) 제공

6. 지진/재난 발생 정보 API
   - 사용자 질문 예: "방금 지진 있었어?"
   - 핵심 값: 발생 시각, 규모, 진앙지
   - Home Agent 가치: 즉시성 높은 안전 알림

### 6-2. PRD 반영 방식
- 통합 계층 `server/src/integrations/`에 `korea_public_data_*` 형태 provider 추가.
- 지역 기반 질의 표준 파라미터 정의:
  - `region_code`, `nx/ny`(기상청 격자), `sido/sigungu`.
- 응답 정규화 스키마:
  - `summary`, `confidence`, `source`, `observed_at`, `next_update_at`.
- API 장애 시 폴백:
  - 공공 API 실패 시 기존 글로벌 weather provider(OpenWeather)로 대체.

### 6-3. 단계적 구현
1) 날씨(초단기강수) + 대기질
2) 특보/재난 알림
3) 공휴일/생활형 정보

---

## Phase 7 — 아이폰 연동 채팅 앱(개인 배포)
목표: 앱스토어 배포 없이 개인 아이폰에서 Home Agent와 텍스트/음성 채팅을 사용한다.

### 7-1. 제품 방향
- 앱 형태: 1:1 챗봇 UI (대화 기록 + 명령/상태 카드)
- 입력 경로:
  1) 아이폰 텍스트 입력
  2) ESP32 음성 → STT 텍스트화된 입력(서버 경유)
- 출력 경로:
  - 텍스트 응답 + 선택적 TTS 재생

### 7-2. 기술 제안
- iOS: SwiftUI 기반 경량 앱
- 백엔드 연동: 기존 server에 모바일용 API/WebSocket 추가
  - `POST /chat/message`
  - `GET /chat/history`
  - `WS /chat/stream` (토큰 스트리밍/상태 이벤트)
- 인증: 개인 사용 전제의 단일 사용자 토큰 + 로컬 네트워크 허용 목록

### 7-3. 개인 배포 전략
- Xcode + 개인 Apple ID 사이드로딩
- 필요 시 TestFlight 내부 테스터(개인 계정) 활용
- 앱 내 설정에서 Home server 주소/토큰 변경 가능

### 7-4. 마일스톤
1) 텍스트 채팅 MVP
2) ESP32 음성 입력 이벤트를 채팅 타임라인에 병합
3) iOS 로컬 알림/위젯(선택)

---

## Phase 8 — Telegram(BotFather) 연동
목표: Openclaw와 유사하게 Telegram Bot을 통해 아이폰에서 동일 Agent를 사용한다.

### 8-1. 구성
- BotFather로 Bot 생성 및 토큰 발급
- 서버에 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_IDS` 설정
- 연동 방식:
  - 초기: Long Polling(설치 간단)
  - 확장: Webhook(운영 안정성)

### 8-2. 동작 시나리오
1) 사용자가 Telegram에서 텍스트 전송
2) 서버가 AgentMode로 처리 후 텍스트 응답
3) ESP32에서 수집된 음성 STT 결과도 동일 대화 스레드에 반영
4) 필요 시 TTS 음성 파일(voice message)로 회신

### 8-3. 보안/운영
- 허용 사용자 ID 화이트리스트 강제
- 명령어 제한(`/start`, `/status`, `/mute`, `/unmute`)
- 장애 시 재시도 및 관리자 알림(slack/discord) 연계

### 8-4. 구현 순서
1) Bot 수신/발신 최소 루프
2) Agent 파이프라인 연결
3) 음성 메시지/알림 고도화

### 5-7. 보안/프라이버시
- 음성 원본은 기본 비저장(옵션으로만 저장), 임베딩 중심 저장.
- 저장 데이터 암호화(최소 파일 권한 제한 + 추후 키 관리).
- 삭제 명령 실행 시 임베딩/메타를 즉시 제거.
- 로그에는 사용자 원음/민감정보 출력 금지.

### 5-8. 완료 기준(Voice ID DoD)
- 등록 플로우 5회 샘플 수집 및 임베딩 저장 성공.
- ON 상태에서 미등록 화자 입력 시 응답 차단 동작 검증.
- 특정 사용자 삭제 후 동일 화자 식별 실패 확인.
- 배경 영상/노이즈 환경에서 오동작 응답률 감소 수치 확보.
- 사용자별 컨텍스트 분리 기반 개인화 응답 데모 1개 이상.

---

## 2) README bash 예시 작성 원칙 (요구사항 2)

README에는 아래 카테고리별로 예시를 고정 순서로 배치한다.

1. 설치
```bash
pip install -r server/requirements.txt
pip install -e .
```

2. 기본 설정
```bash
ccoli config wifi <WiFi Name> password <password> port <port>
ccoli config llm --provider ollama --model qwen3:8b
```

3. 통합 설정 (신규)
```bash
ccoli config integration list
ccoli config integration set weather --api-key <WEATHER_API_KEY>
ccoli config integration enable weather
ccoli config integration test weather
```

4. 서버 실행
```bash
ccoli start
ccoli start --port 5002
```

5. 진단/오류 대응
```bash
ccoli config integration test search
ccoli config integration test calendar
```

---

## 3) 보안/운영 정책 (G)

- 민감값 저장 위치: `server/.env` 고정.
- CLI 출력/로그에서 키 원문 노출 금지(앞 2~4글자만 표시).
- 에러 로그에 요청 본문 기록 시 민감 필드 자동 마스킹.
- Integration별 타임아웃/재시도/레이트리밋 정책 명시.
- 운영 플래그(`enable/disable`)로 장애 기능 즉시 차단 가능.

---

## 4) 완료 기준 (H / DoD)

1. CLI
- `integration list/set/enable/disable/test` 동작.
- provider별 필수 키 누락 시 명확한 오류 출력.

2. 기능
- A~E 각 기능 최소 1개 핵심 시나리오 성공.
- 실패 시 TTS 디버깅 멘트가 사용자에게 전달.

3. 문서
- README에 모든 bash 실행 예시 포함.
- `docs/API.md`에 신규 integrations 아키텍처 반영.

4. 테스트
- 단위 테스트: Integration별 성공/실패/타임아웃.
- 통합 테스트: Agent 요청→Integration→TTS 안내까지 검증.
- Voice ID 테스트: 등록/식별/삭제/ON-OFF/노이즈 환경 회귀 테스트.

---

## 5) 구현 순서 제안 (현실적 릴리스 순서)

1. F(Integration 아키텍처) + CLI 골격
2. A(날씨) + 오류 TTS 템플릿
3. B(검색)
4. C(Google Calendar)
5. D(알림)
6. E(지도/경로)
7. Voice ID(등록/식별/응답게이트/개인화 기초)
8. README/API 문서 최종 동기화 + 테스트 강화

이 순서를 따르면 "구조 먼저, 기능 확장 나중" 원칙으로 리스크를 줄이면서 빠르게 사용자 체감 기능을 제공할 수 있다.
