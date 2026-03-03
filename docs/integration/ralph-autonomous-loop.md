# Ralph-style Autonomous Coding Loop for Codex

이 문서는 ralph 스타일의 자율형 코딩 루프를 이 저장소에서 동작시키기 위한 최소 구성입니다.

## 구성 요소
- 루프 설정: `.codex/autonomous-loop.yaml`
- 실행 스크립트: `scripts/autonomous_coding_loop.sh`
- 품질 게이트: Docker 테스트 (`docker-compose.test.yml`)

## 동작 흐름
1. 계획(Plan)
2. 구현(Implement)
3. Docker 테스트(Verify)
4. 실패 분석(Analyze)
5. 패치(Patch)
6. 최대 반복 횟수 도달 전까지 반복

## 실행
```bash
make autoloop
```

환경변수:
- `MAX_ITERS`: 최대 반복 횟수
- `REPORT_DIR`: 로그 저장 경로

## 원칙
- 테스트 통과 전까지 루프 반복
- 각 반복마다 로그 남김
- 반복 종료 후 성공/실패 아티팩트 보존
