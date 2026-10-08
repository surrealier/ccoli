# Home Assistant 연결 안내

Home Assistant는 여러 브랜드의 스마트 조명·플러그·센서 등을 연결해 제어하고 자동화하는 오픈 소스 서버입니다. 지원하는 기기를 연결하면 상태 확인, 시간·센서 조건에 따른 자동화, 대시보드와 음성 제어를 사용할 수 있습니다. [공식 소개](https://www.home-assistant.io/)와 [Assist 음성 안내](https://www.home-assistant.io/voice_control/)를 참고하세요.

이 프로젝트에서는 Atom Echo가 음성 입출력을, ccoli PC 서버가 AI 대화와 도구 실행을, 선택적으로 연결한 Home Assistant가 실제 스마트홈 기기 통신을 맡습니다. 현재 ccoli가 지원하는 홈 기능은 허용한 조명·스위치의 상태 조회와 켜기·끄기입니다. Home Assistant가 없어도 AI 대화·개인 기억·할 일은 동작합니다. 2026-10-08 현재 이 PC의 Home Assistant는 미설정이며 연결 어댑터의 모의 검증을 실제 장비 제어 성공과 구분합니다.

ccoli의 홈 도구는 운영자가 허용한 `light`와 `switch` 엔티티의 상태 조회 및 `turn_on`/`turn_off`만 제공합니다. [Home Assistant REST API](https://developers.home-assistant.io/docs/api/rest/)의 서비스 호출 뒤 상태 조회를 수행합니다.

## 설정

Home Assistant 프로필에서 Long-Lived Access Token을 발급하고 서버 프로세스 환경변수로 전달합니다. 실제 토큰을 소스, 예제 파일, 채팅 또는 로그에 붙여넣지 않습니다.

| 환경변수 | 값 |
|---|---|
| `HOME_ASSISTANT_URL` | Home Assistant 서버 원점. 예: `http://homeassistant.local:8123` |
| `HOME_ASSISTANT_TOKEN` | 발급한 토큰. 인증 헤더로만 전송 |
| `HOME_ASSISTANT_ALLOWED_ENTITIES` | 쉼표로 구분한 정확한 ID. 예: `light.study,switch.fan` |

URL은 HTTP/HTTPS와 호스트가 필요합니다. 사용자명·비밀번호, 쿼리, fragment, `/api` 등의 경로를 포함하지 않습니다. HTTPS를 사용하는 경우 시스템이 신뢰하는 인증서를 사용합니다. 서버를 지정하지 않거나 토큰·허용 목록이 비어 있으면 연동은 미설정 상태이고 상태 목록은 비어 있습니다.

허용 목록은 운영자가 설정합니다. 와일드카드, 그룹 전체 호출, lock/alarm 서비스 및 임의 서비스는 지원하지 않습니다. `switch`에 연결된 실제 장비가 무엇인지 확인한 뒤 등록하세요. 사용자 음성이나 모델이 허용 목록을 확장할 수 없습니다.

## 사용과 결과 확인

1. Home Assistant에서 대상 ID와 현재 상태를 확인합니다.
2. ccoli에 등록된 홈 도구로 상태를 조회합니다. 결과는 ID, 상태, 표시 이름만 포함합니다.
3. 허용한 조명 켜기·끄기를 요청합니다. 서비스 호출이 성공해도 후속 조회가 목표 `on`/`off`를 확인한 경우에만 `confirmed: true`를 반환합니다.
4. 오류나 상태 불일치가 발생하면 실제 장비와 Home Assistant 상태를 확인합니다. 자동 재시도는 하지 않습니다. 장비 반영이 지연되는 경우 이후 상태 조회로 확인하세요.

기기 이름이나 정확한 ID를 넣은 단일 명령(예: `서재 켜줘`, `light.study 꺼줘`)은 빠른 경로로 처리합니다. 이 경로도 허용된 상태 조회, 서비스 호출, 목표 상태 재조회가 모두 성공해야 완료로 답합니다. 정확한 허용 ID를 말하면 다른 기기 이름 조회를 생략하고 해당 기기만 제어·재확인합니다. 같은 표시 이름의 기기가 여러 개면 제어하지 않고 정확한 ID를 요청합니다. 현재 발화 전체에 맞는 순차 명령도 처리합니다. 예: `서재 켜고 껐다가 다시 켜줘`, `서재 켜줘 그리고 거실 꺼줘`. 모든 대상이 먼저 확인돼야 실행을 시작하며 상태 조회와 제어를 합쳐 최대 4회로 제한합니다. 중간 단계가 실패하면 즉시 멈추고 확인된 성공만 보고합니다. 인용문·방법 질문·모호한 선택은 조작으로 해석하지 않으며, 모델이 제안한 홈 제어 도구 호출은 실행하지 않습니다. 지원되지 않는 표현은 기기 이름과 동작을 포함한 명령으로 다시 말씀하세요.

조회는 전체 `/api/states` 목록을 가져오지 않고 허용된 ID마다 `/api/states/{entity_id}`만 요청합니다. 여러 기기의 이름은 최대 8개씩 병렬 조회하며, 하나라도 조회가 실패하면 제어하지 않고 연결·허용 목록 확인을 안내합니다. 제어는 `/api/services/{light|switch}/{turn_on|turn_off}`에 단일 `entity_id`를 보냅니다. 각 HTTP 요청의 타임아웃은 5초이며 리디렉션을 따라가지 않습니다. 환경 프록시 및 `.netrc`의 암묵적 인증은 사용하지 않습니다.

## 진단과 검증

연결·인증 실패나 리디렉션은 사용자에게 설정 확인을 안내합니다. 응답 본문, 토큰과 원래 예외 문자열은 오류 메시지에 포함하지 않습니다. 상태 응답이 잘못되거나 `unknown`/`unavailable`이면 제어 성공으로 보고하지 않습니다.

```powershell
docker compose -f docker/docker-compose.test.yml run --rm -v C:/bongkj/Projects/LLM_Arduino/server:/app/server server-test pytest server/tests/test_home_assistant.py -q
```

47개 fake-session 테스트로 URL·허용 목록·인증·HTTP 실패·타임아웃·리디렉션·잘못된 JSON·상태 확인·오류 비밀값 비노출을 검증했습니다. 실제 Home Assistant 및 물리 장비 검증을 대신하지 않습니다. 사용 중단은 토큰 또는 허용 목록을 제거하고 서버를 재시작하면 됩니다.
