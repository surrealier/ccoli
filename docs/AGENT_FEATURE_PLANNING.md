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

---

## 3) 마스터 TODO 백로그 (PRD 항목 매핑)

> 상태 정의: `TODO` / `DOING` / `DONE` / `BLOCKED`

### EPIC-A: PRD 중심 운영 고정화 (PRD 1~4, 10)
- [ ] (SA-0, TODO) PRD/Planning 템플릿에 필수 섹션(배경/범위/테스트/롤백) 강제
- [ ] (SA-0, TODO) README/QUICKSTART에서 PRD↔Planning 링크 무결성 점검
- [ ] (SA-0, TODO) 기능 PR 템플릿에 “PRD 항목 매핑” 체크박스 추가
- 검증:
  - `rg "PRD|Planning" README.md QUICKSTART.md docs/*.md`

### EPIC-B: Docker 테스트 표준화 (PRD 6.3, 7)
- [ ] (SA-1, TODO) `docker/docker-compose.test.yml`를 테스트 단일 진입점으로 확정
- [ ] (SA-1, TODO) `server-test` 컨테이너에서 unit/integration/cli smoke 명령 통합
- [ ] (SA-1, TODO) CI에서 compose 기반 테스트만 실행하도록 파이프라인 정리
- [ ] (SA-1, TODO) 실패 로그 아카이브(테스트 리포트 + 핵심 로그) 수집
- 검증:
  - `docker compose -f docker/docker-compose.test.yml up --build --abort-on-container-exit`

### EPIC-C: 통신/회귀 테스트 확장 (PRD 6.2, 7)
- [ ] (SA-2, TODO) `client-sim` 컨테이너 추가 및 server와 프로토콜 핸드셰이크 검증
- [ ] (SA-2, TODO) 회귀 시나리오 3종(정상, 지연/재시도, 비정상 payload) 자동화
- [ ] (SA-2, TODO) 외부 API mock-services 템플릿 추가
- [ ] (SA-2, TODO) 통신 실패 사용자 안내 메시지 회귀 테스트화
- 검증:
  - `docker compose -f docker/docker-compose.test.yml run --rm client-sim`
  - `docker compose -f docker/docker-compose.test.yml run --rm server-test pytest -m protocol`

### EPIC-D: 연결/설정 UX 개선 (PRD 5.1)
- [ ] (SA-3, TODO) `server/config.yaml` 연결 모드 스키마(`wifi|wired`) 확장
- [ ] (SA-3, TODO) `ccoli config wifi ...`를 연결 모드 지원 CLI로 리팩터링
- [ ] (SA-3, TODO) firmware `device_secrets.h`와 키 이름/의미 1:1 동기화
- [ ] (SA-3, TODO) 설정 검증 에러를 행동 유도형 메시지로 통일
- 검증:
  - `pytest server/tests/test_cli_integration.py -k config`
  - `pytest server/tests/test_connection.py`

### EPIC-E: Integration 품질 고도화 (PRD 5.2)
- [ ] (SA-4, TODO) 연동 공통 인터페이스(타임아웃/재시도/오류코드) 표준화
- [ ] (SA-4, TODO) Weather/Search/Calendar/Notify/Maps 헬스체크 일관화
- [ ] (SA-4, TODO) 연동 실패 시 사용자용 TTS 메시지 + 내부 디버그 로그 분리
- [ ] (SA-4, TODO) 통합별 실패 케이스 테스트 추가
- 검증:
  - `pytest server/tests/test_integrations_extended.py`
  - `pytest server/tests/test_integration_error_tts.py`

### EPIC-F: Voice ID/개인화 안정화 (PRD 5.3)
- [ ] (SA-5, TODO) 등록/식별/삭제/threshold 조정 플로우 통합
- [ ] (SA-5, TODO) Voice ID ON/OFF 상태 기반 응답 게이트 고도화
- [ ] (SA-5, TODO) 사용자별 메모리 컨텍스트 분리 정책 반영
- [ ] (SA-5, TODO) CLI/음성 명령 동작 일치 테스트 추가
- 검증:
  - `pytest server/tests/test_voice_id_service.py`
  - `pytest server/tests/test_voice_store.py`

### EPIC-G: iOS 채널 확장 (PRD 5.4)
- [ ] (SA-6, TODO) Telegram bot 기반 채팅 MVP(메시지 수신/LLM 응답/전송) 구현
- [ ] (SA-6, TODO) 인증/레이트리밋/오류 응답 정책 수립
- [ ] (SA-6, TODO) 운영/배포 가이드(토큰 보안, 장애 대응) 문서화
- [ ] (SA-6, TODO) 향후 iOS 앱 연동을 위한 인터페이스 추상화
- 검증:
  - `pytest -m telegram`
  - `docker compose -f docker/docker-compose.test.yml run --rm server-test pytest -m channel`

### EPIC-H: 도구 PoC (PRD 5.5)
- [ ] (SA-7, TODO) Ralph 적용 후보 선정(문서 lint, 테스트 리포트 자동화)
- [ ] (SA-7, TODO) 보안/비용/충돌/유지보수 평가표 작성
- [ ] (SA-7, TODO) 단계적 도입안(실험→부분 적용→확장) 수립
- [ ] (SA-7, TODO) 적용/비적용 비교 리포트 제출
- 검증:
  - `python scripts/evaluate_poc.py --tool ralph`

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
