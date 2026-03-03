# Ralph Compatibility (Claude Repo -> Codex Adaptation)

대상 참고 저장소: https://github.com/snarktank/ralph

## 목적
Claude 중심 워크플로/레포 구성을 이 프로젝트(Codex 사용)에서 어떻게 재사용할 수 있는지 분류하고 단계적으로 적용합니다.

## 분류

### A. 즉시 이식 가능
- 운영 규칙 문서화(체크리스트/PR 규칙/테스트 증적)
- PRD 단일 소스 운영
- 테스트 명령 표준화(예: `make test-docker`)

### B. 부분 이식 권장
- 자동 태스크 분해/작업 단위 템플릿
- 역할 기반 프롬프트 분리(설계/구현/검증)
- 문서-코드 정합성 검증 스크립트

### C. 현재는 비권장/후순위
- 실기기 전제 자동화(하드웨어 의존 CI)
- 네트워크/외부 API 강의존 E2E의 무분별한 상시 실행

## 적용 단계 (제안)
1. 문서 레이어 우선
   - `docs/PRD.md`, `docs/PROJECT_RULES_CODEX.md` 정착
2. 테스트 레이어 확장
   - Docker 통합 테스트 및 프로토콜 계약 테스트 구축
3. 자동화 레이어 확장
   - PR 템플릿 강제, 체크 스크립트, CI 품질 게이트

## 성공 지표 (KPI)
- PR당 문서 누락 비율 감소
- 프로토콜 회귀 이슈 감소
- 신규 기여자 온보딩 시간 단축

## 주의사항
- Codex/Claude 실행 환경 차이로 도구 명령/프롬프트 인터페이스는 직접 매핑 필요
- 하드웨어 스펙은 벤더 공식 문서를 우선 근거로 삼고, 시뮬레이터 제약도 동일하게 관리


## 구현 상태
- 자율 루프 설정 파일 추가: `.codex/autonomous-loop.yaml`
- 루프 실행 스크립트 추가: `scripts/autonomous_coding_loop.sh`
- 실행 문서: `docs/integration/ralph-autonomous-loop.md`
