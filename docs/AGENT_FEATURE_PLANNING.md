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

---

## 2) 현재 우선순위 실행계획

### P0 — PRD 중심 운영 전환
- [x] PRD 문서 신설 (`docs/PRD.md`)
- [x] Planning 문서 역할 재정의(PRD 참조형)
- [x] README/QUICKSTART에 PRD 링크 추가

### P1 — Docker 테스트 표준화
- [ ] `docker/docker-compose.test.yml` 단일 진입점 확정
- [ ] `server-test` 컨테이너에서 pytest 표준화
- [ ] CI에서 compose 테스트 실행

### P2 — 통신/회귀 테스트 확장
- [ ] `client-sim` 컨테이너 추가
- [ ] 프로토콜 회귀 시나리오 3종 구축
- [ ] 외부 API mock-services 기본 템플릿 도입

### P3 — 기능 고도화 (PRD 기능 트랙 기준)
- [ ] 연결 모드(Wi-Fi/유선) UX 개선
- [ ] Integration(Weather/Search/Calendar/Notify/Maps) 품질 고도화
- [ ] Voice ID 및 개인화 안정화
- [ ] iOS/Telegram 연동 확장

### P4 — 도구 적용 PoC
- [ ] `snarktank/ralph`를 문서/테스트 자동화 영역에서 PoC
- [ ] 적용/비적용 비교 리포트 작성

---

## 3) 검증/완료 기준
- 각 작업은 PRD 항목(기능 트랙 또는 NFR)과 매핑되어야 한다.
- 구현 완료 PR에는 Docker 기준 테스트 명령이 포함되어야 한다.
- 계획 변경 시, Planning만 수정하지 않고 PRD도 함께 갱신한다.
