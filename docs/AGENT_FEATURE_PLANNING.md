# Agent 기능 확장 계획 (API 통합 중심)

이 문서는 ccoli Agent가 수행 가능한 기능을 API 중심으로 확장하기 위한 계획서입니다.

## 1) 목표
- 사용자 명령 한 번으로 Agent 통합 기능을 켜고 끌 수 있게 만들기
- 각 기능별 API Key를 `ccoli config` 커맨드로 입력/갱신할 수 있게 만들기
- 기능 실패 시에도 기본 대화 기능은 유지되는 안전한 구조 구성

## 2) 우선 지원 기능 리스트

### A. 날씨/환경
- 지역(도시명/위경도) + 날짜(오늘/내일/주간) 기준 날씨 조회
- 대기질(AQI), 강수확률, 체감온도, 일출/일몰
- 후보 API: OpenWeatherMap, WeatherAPI, Meteostat
- 설정 필요 키:
  - `WEATHER_API_KEY`

### B. 웹 검색/지식 조회
- 실시간 웹 검색 결과 요약
- 뉴스 카테고리별 브리핑(경제/IT/국제)
- 후보 API: SerpAPI, Tavily, Google Custom Search
- 설정 필요 키:
  - `SERPAPI_API_KEY` 또는 `TAVILY_API_KEY`
  - 선택 시 `GOOGLE_CSE_API_KEY`, `GOOGLE_CSE_CX`

### C. 캘린더/일정 (Google Calendar)
- 일정 조회/추가/수정/삭제
- “내일 오후 3시 회의 추가” 같은 자연어 입력 처리
- 설정 필요 키:
  - `GOOGLE_CLIENT_ID`
  - `GOOGLE_CLIENT_SECRET`
  - `GOOGLE_REFRESH_TOKEN`

### D. 메일/메시징 알림
- Gmail/Slack/Discord 요약 및 발송
- 설정 필요 키:
  - `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`
  - `SLACK_BOT_TOKEN`
  - `DISCORD_BOT_TOKEN`

### E. 위치/지도/경로
- 목적지까지 소요시간, 경로 요약
- 설정 필요 키:
  - `GOOGLE_MAPS_API_KEY` 또는 `NAVER_MAP_API_KEY`

### F. MCP 연동
- MCP 서버 등록/해제/상태 확인
- 도구 별 권한(읽기 전용/쓰기 허용) 부여
- 설정 필요 키:
  - MCP 서버별 키(예: `MCP_<NAME>_TOKEN`)

### G. 스마트홈/IoT
- Home Assistant 장치 상태 조회/제어
- 설정 필요 키:
  - `HOME_ASSISTANT_URL`
  - `HOME_ASSISTANT_TOKEN`

## 3) CLI 설계 초안
- `ccoli config integration list`
- `ccoli config integration set <provider> --api-key <key> [--extra-key value ...]`
- `ccoli config integration enable <provider>`
- `ccoli config integration disable <provider>`
- `ccoli config integration test <provider>`

예시:
```bash
ccoli config integration set weather --api-key xxx
ccoli config integration set calendar --google-client-id xxx --google-client-secret yyy --google-refresh-token zzz
ccoli config integration enable weather
ccoli config integration test weather
```

## 4) 아키텍처 제안
- `src/integrations/` 폴더 신설
  - `base.py`: 공통 인터페이스(`is_configured`, `health_check`, `execute`)
  - `weather.py`, `search.py`, `calendar.py`...
- Agent는 직접 API를 부르지 않고 Integration Registry를 통해 호출
- 실패/타임아웃은 표준 에러 객체로 반환

## 5) 보안/운영 정책
- 민감 키는 `server/.env`에만 저장 (로그 출력 금지)
- 설정 변경 시 키 전체 출력 금지(마스킹)
- 통합별 요청 제한(Rate limit) 및 캐시 정책 도입

## 6) 구현 우선순위 (제안)
1. Weather 고도화(지역/날짜 기반)
2. Web Search
3. Google Calendar
4. MCP 브리지
5. Slack/Discord 알림

## 7) 완료 기준 (DoD)
- `ccoli config` 명령으로 키 등록/검증 가능
- Agent 프롬프트에서 자연어로 기능 호출 가능
- 기능별 통합 테스트 + 실패 복구 시나리오 확보
