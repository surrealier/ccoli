# ccoli Feature Planning (Execution Plan)

이 문서는 **실행 계획(Planning)** 전용이다.
제품 요구사항의 기준 문서는 `docs/PRD.md`이며, 본 문서는 PRD를 구현하기 위한 단계/작업/검증 항목만 관리한다.

- PRD: `docs/PRD.md`
- Planning: `docs/AGENT_FEATURE_PLANNING.md`

---

## 1) Planning 운영 원칙
- 목적/요구사항/현재 기능 정의는 PRD에서 관리한다.
- Planning은 “무엇을 언제 어떻게 구현할지”에 집중한다.
- 신규 요구사항이 들어오면 `PRD 업데이트 → Planning 반영 → 구현` 순서로 진행한다.
- 모든 구현 작업은 **TODO 단위 산출물 + 검증 명령 + 롤백 전략**을 포함한다.

---

## 2) 개발 추진 구조 (TODO + Sub Agent)

아래 Sub Agent는 병렬 작업 단위이며, 각 Sub Agent는 PR 단위로 결과를 제출한다.

| Sub Agent | 담당 범위 | 주요 산출물 |
|---|---|---|
| SA-0 Product Docs | PRD/Planning 정합성 유지 | PRD 업데이트, Planning 체크리스트 |
| SA-1 Platform TestOps | Docker/CI 테스트 단일 진입점 | `docker-compose.test.yml`, CI job |
| SA-2 Protocol QA | ESP32 통신/회귀 자동화 | `client-sim`, 프로토콜 회귀 시나리오 |
| SA-3 Connection UX | Wi-Fi/유선 연결 모드 UX | CLI/설정 스키마/문서 업데이트 |
| SA-4 Integrations | Weather/Search/Calendar/Notify/Maps | 연동 인터페이스 개선, 에러 표준화 |
| SA-5 Voice ID | 화자 등록/식별/게이트 | Voice ID 기능 안정화 + 테스트 |
| SA-6 Channel Expansion | Telegram 기반 iOS 채널 | Bot 연동 MVP + 운영 가이드 |
| SA-7 Dev Productivity | 도구 PoC/자동화 | Ralph PoC 리포트 |
| SA-8 Robot Mode | Companion 기반 로봇 모드 | 로봇 PRD, bridge protocol, companion firmware, 하드웨어 가이드 |

---

## 3) 마스터 TODO 백로그 (PRD 항목 매핑)

> 상태 정의: `TODO` / `DOING` / `DONE` / `BLOCKED`

### EPIC-A: PRD 중심 운영 고정화 (PRD 1~4, 10)
- [x] (SA-0, DONE) PRD/Planning 템플릿에 필수 섹션(배경/범위/테스트/롤백) 강제
- [x] (SA-0, DONE) README/QUICKSTART에서 PRD↔Planning 링크 무결성 점검
- [x] (SA-0, DONE) 기능 PR 템플릿에 “PRD 항목 매핑” 체크박스 추가
- 검증:
  - `rg "PRD|Planning" README.md QUICKSTART.md docs/*.md`

### EPIC-B: Docker 테스트 표준화 (PRD 6.3, 7)
- [x] (SA-1, DONE) `docker/docker-compose.test.yml`를 테스트 단일 진입점으로 확정
- [x] (SA-1, DONE) `server-test` 컨테이너에서 unit/integration/cli smoke 명령 통합
- [x] (SA-1, DONE) CI에서 compose 기반 테스트만 실행하도록 파이프라인 정리
- [x] (SA-1, DONE) 실패 로그 아카이브(테스트 리포트 + 핵심 로그) 수집
- 검증:
  - `docker compose -f docker/docker-compose.test.yml up --build --abort-on-container-exit`

### EPIC-C: 통신/회귀 테스트 확장 (PRD 6.2, 7)
- [x] (SA-2, DONE) `client-sim` 컨테이너 추가 및 server와 프로토콜 핸드셰이크 검증
- [x] (SA-2, DONE) 회귀 시나리오 3종(정상, 지연/재시도, 비정상 payload) 자동화
- [x] (SA-2, DONE) 외부 API mock-services 템플릿 추가
- [x] (SA-2, DONE) 통신 실패 사용자 안내 메시지 회귀 테스트화
- 검증:
  - `docker compose -f docker/docker-compose.test.yml run --rm client-sim`
  - `docker compose -f docker/docker-compose.test.yml run --rm server-test pytest -m protocol`

### EPIC-D: 연결/설정 UX 개선 (PRD 5.1)
- [x] (SA-3, DONE) `ccoli setup` 대화형 설치 위저드 추가(Ollama local / Cloud API / later)
- [x] (SA-3, DONE) Python 의존성을 base/runtime/test profile로 분리하고 기본 경로에서 무거운 미사용 패키지 제거
- [x] (SA-3, DONE) `server/config.yaml` 연결 모드 스키마(`auto|wifi|wired`) 확장
- [x] (SA-3, DONE) `ccoli config wifi ...`를 연결 모드 지원 CLI로 리팩터링
- [x] (SA-3, DONE) firmware `device_secrets.h`와 키 이름/의미 1:1 동기화
- [x] (SA-3, DONE) 설정 검증 에러를 행동 유도형 메시지로 통일
- [x] (SA-3, DONE) USB serial wired 런타임 추가 및 `ccoli start` auto-detect 경로 구현
- [x] (SA-3, DONE) ??? ????(`??/API/??/????`) ?? ?? ? ??/? ???? ??? ?? ??
- 검증:
  - `docker compose -f docker/docker-compose.test.yml run --rm server-test pytest server/tests/test_cli_setup.py server/tests/test_cli_smoke.py`
  - `pytest server/tests/test_cli_integration.py -k config`
  - `pytest server/tests/test_connection.py`

### EPIC-E: Integration 품질 고도화 (PRD 5.2)
- [x] (SA-4, DONE) 연동 공통 인터페이스(타임아웃/재시도/오류코드) 표준화
- [x] (SA-4, DONE) Weather/Search/Calendar/Notify/Maps 헬스체크 일관화
- [x] (SA-4, DONE) 연동 실패 시 사용자용 TTS 메시지 + 내부 디버그 로그 분리
- [x] (SA-4, DONE) 통합별 실패 케이스 테스트 추가
- 검증:
  - `pytest server/tests/test_integrations_extended.py`
  - `pytest server/tests/test_integration_error_tts.py`

### EPIC-F: Voice ID/개인화 안정화 (PRD 5.3)
- [x] (SA-5, DONE) 등록/식별/삭제/threshold 조정 플로우 통합
- [x] (SA-5, DONE) Voice ID ON/OFF 상태 기반 응답 게이트 고도화
- [x] (SA-5, DONE) 사용자별 메모리 컨텍스트 분리 정책 반영
- [x] (SA-5, DONE) CLI/음성 명령 동작 일치 테스트 추가
- 검증:
  - `pytest server/tests/test_voice_id_service.py`
  - `pytest server/tests/test_voice_store.py`

### EPIC-G: iOS 채널 확장 (PRD 5.4)
- [x] (SA-6, DONE) Telegram bot 기반 채팅 MVP(메시지 수신/LLM 응답/전송) 구현
- [x] (SA-6, DONE) 인증/레이트리밋/오류 응답 정책 수립
- [x] (SA-6, DONE) 운영/배포 가이드(토큰 보안, 장애 대응) 문서화
- [x] (SA-6, DONE) 향후 iOS 앱 연동을 위한 인터페이스 추상화
- 검증:
  - `pytest -m telegram`
  - `docker compose -f docker/docker-compose.test.yml run --rm server-test pytest -m channel`

### EPIC-H: 도구 PoC (PRD 5.5)
- [x] (SA-7, DONE) Ralph 적용 후보 선정(문서 lint, 테스트 리포트 자동화)
- [x] (SA-7, DONE) 보안/비용/충돌/유지보수 평가표 작성
- [x] (SA-7, DONE) 단계적 도입안(실험→부분 적용→확장) 수립
- [x] (SA-7, DONE) 적용/비적용 비교 리포트 제출
- 검증:
  - `python scripts/evaluate_poc.py --tool ralph`

### EPIC-I: Web Dashboard Redesign (PRD 5.1)
- [ ] (SA-0/SA-3, TODO) 대시보드 범위를 PRD/Planning에 반영하고 `English` 기본 UI + `한국어/日本語/中文` 전환 정책 확정
- [ ] (SA-3, TODO) `server/web/static/`를 HTML shell + 분리된 CSS/JS asset 구조로 재편
- [ ] (SA-3, TODO) 개요 화면을 짧은 제목/보조 본문 구조로 재설계하고 브로콜리 마스코트 이미지는 메인 hero 1곳에만 유지
- [ ] (SA-3, TODO) Diagnostics 탭을 추가해 Runtime Summary / STT / Connection / Integrations / Advanced 섹션으로 재구성
- [ ] (SA-3, TODO) STT `device`, `model_size`와 Connection `mode`만 안전한 편집 대상으로 제한한 curated config UI 추가
- [ ] (SA-3, TODO) `GET /api/diagnostics/`, `POST /api/diagnostics/check`와 대시보드 공유 runtime state를 추가
- [ ] (SA-1/SA-3, TODO) 정적 UI 테스트와 diagnostics API 테스트를 보강하고 Docker 진입점으로 회귀 검증
- 검증:
  - `docker compose -f docker/docker-compose.test.yml run --rm server-test pytest server/tests/test_web_dashboard_static.py server/tests/test_web_runtime_routes.py`
  - `docker compose -f docker/docker-compose.test.yml run --rm server-test pytest server/tests/test_runtime_controller.py server/tests/test_runtime_preferences.py`
  - `docker compose -f docker/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from server-test`

### EPIC-J: Robot Mode Re-Architecture (PRD 5.6)
- [ ] (SA-0, TODO) Atom Echo/SG90/Waveshare 공식 문서 기반 제약과 권장 아키텍처를 `docs/PRD.md` 및 `docs/ROBOT_MODE_WAVESHARE_PRD.md`에 고정
- [ ] (SA-2/SA-8, TODO) `server -> Atom Echo -> Companion` 로봇 상태 페이로드와 회귀 시나리오를 정의하고 protocol test에 편입
- [ ] (SA-8, TODO) `arduino/robot_companion_controller/` 신규 펌웨어 스켈레톤과 ST7789V2 + SG90(1~4채널) 드라이버 구조를 확정
- [ ] (SA-5/SA-8, TODO) `SOUL + RELATION + MOOD + AFFECT + BODY` 기반 감정 지속 모델과 idle action policy를 설계/테스트
- [ ] (SA-8, TODO) farewell/sleep/idle gesture preset과 display state machine(blink/gaze/yawn/talk overlay)을 구현
- [ ] (SA-1/SA-2/SA-8, TODO) Docker 검증 명령과 실기 하드웨어 smoke checklist를 단일 실행 계획으로 문서화
- 검증:
  - `docker compose -f docker/docker-compose.test.yml run --rm server-test pytest server/tests/test_emotion_system.py server/tests/test_robot_mode_extended.py`
  - `docker compose -f docker/docker-compose.test.yml run --rm server-test pytest server/tests/test_protocol.py`
  - `docker compose -f docker/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from server-test`

---

## 4) 실행 순서 (권장 스프린트)

### Sprint 1 (기반 고정)
- SA-0, SA-1 수행: 문서 정합 + Docker 테스트 진입점 확정
- Exit Criteria:
  - compose 단일 명령으로 테스트 실행 가능
  - PR 템플릿에 PRD 매핑 항목 반영

### Sprint 2 (품질 게이트)
- SA-2, SA-3 수행: 통신 회귀 + 연결 UX 정리
- Exit Criteria:
  - 프로토콜 회귀 3종 자동화 완료
  - 연결 모드 설정/검증 시나리오 테스트 통과

### Sprint 3 (핵심 기능 고도화)
- SA-4, SA-5 수행: Integrations/Voice ID 안정화
- Exit Criteria:
  - 연동별 에러 표준화 + 테스트 확보
  - Voice ID 주요 사용자 시나리오 회귀 테스트 확보

### Sprint 4 (채널 확장 + 도구 PoC)
- SA-6, SA-7 수행: Telegram MVP + Ralph PoC
- Exit Criteria:
  - Telegram 채널 E2E smoke 통과
  - 도구 도입 의사결정 리포트 완료

### Sprint 5 (Robot Mode)
- SA-0, SA-2, SA-5, SA-8 수행: Companion 구조 확정 + 감정 지속 엔진 + 디스플레이/서보 제어
- Exit Criteria:
  - Atom Echo 단독 직결 대신 Companion 기반 배선/프로토콜이 문서와 설정에 반영됨
  - insult -> apology lingering mood 시나리오가 단위 테스트로 재현됨
  - ST7789V2 display state machine과 1~4채널 servo profile이 하드웨어 smoke checklist를 통과함

---

## 5) 공통 Definition of Ready / Done

### DoR (착수 조건)
- PRD 항목 매핑이 명확함
- TODO별 산출물/검증 명령/롤백 전략이 정의됨
- 민감정보 처리 원칙(평문 금지)이 반영됨

### DoD (완료 조건)
- 코드/문서/테스트 동시 업데이트
- Docker 기준 검증 명령 및 결과 첨부
- 실패 케이스와 복구(롤백) 절차 문서화

---

## 6) 리스크 및 대응
- 테스트 인프라 지연: SA-1 우선순위 최상위 유지, 앱 기능 개발 전 게이트 선행
- 외부 API 변동: mock-services와 표준 오류코드로 회귀 안정성 확보
- 채널 확장 복잡도: Telegram MVP로 범위 제한 후 iOS 앱은 인터페이스 추상화 우선
- 도구 도입 리스크: PoC 결과 기반 점진 적용, 런타임 경로 직접 치환 금지
- 로봇 하드웨어 제약: Atom Echo 단독 핀/전원 한계를 전제로 Companion 구조를 조기에 확정하고, direct path는 레거시 fallback으로만 유지

## 2026-10-08 대시보드 브랜드 아이콘 갱신

사용자 요청에 따라 브로콜리 모티프는 유지하면서 얼굴·볼·겹친 음영을 제거하고, 짙은 녹색 바탕과 민트색 실루엣·음성 파형으로 단순화한다. 기존 SVG 경로를 유지해 외부 이미지 서비스나 추가 런타임 없이 사용한다.

- 대상: `assets/ccoli.svg`, `server/web/static/index.html`, `server/web/static/dashboard.css`, `server/tests/test_web_dashboard_static.py`와 관련 PRD/계획 문서. favicon·상단 로고·hero에 같은 버전 쿼리를 적용하고 alt 설명을 새 심볼에 맞춘다.
- 검증: 16/22/32/64/128px의 밝은·어두운 배경 렌더 확인, 기존 Docker 정적 UI/런타임 테스트·client-sim·CLI 스모크, 실제 HTTP의 SVG 응답과 HTML 참조 확인.
- 롤백: 기존 SVG와 해당 HTML/CSS 변경만 복원하고 아이콘 버전 쿼리를 갱신한다. 이전 SVG는 개인 작업 산출물 `output/design/icon-refresh/icon-before.svg`에 보존했다.

완료 검증: 독립 스펙 준수→디자인/코드 품질 리뷰 PASS. 위 다섯 크기의 밝은/어두운 렌더를 확인했다. 현재 HTML/CSS/SVG 세 파일만 읽기 전용 마운트한 Docker `server-test`에서 `pytest server/tests/test_web_dashboard_static.py server/tests/test_web_runtime_routes.py -q`: **10 passed**, client-sim smoke 및 `ccoli --help` exit0. 실제 운영 HTTP는 페이지·버전 SVG 모두200, SVG image/svg+xml·작업 파일과 일치·HTML 버전 참조3개·작업 Running을 확인했다. 브라우저 실제 화면을 자동 조작한 검증으로 대신하지 않는다. 생산 로직·인증·음성 설정은 변경하지 않았다. 정적 파일은 재시작 없이 제공되며 열린 페이지는 새로고침하면 새 아이콘을 읽는다.

푸시 전 검증: HEAD 소스를 별도 산출물에 펼치고 이번 변경 6개 파일만 반영한 서버·브랜드 폴더를 Docker에 읽기 전용으로 마운트했다. 정적 UI/런타임 테스트 **10 passed**. 기존 PNG 경로·minified CSS에 묶인 정적 테스트를 현재 SVG 및 레이아웃 규칙으로 갱신했으며 독립 리뷰도 PASS였다.
