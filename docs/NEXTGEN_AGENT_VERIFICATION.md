# 차세대 ccoli 검증 기록

기준: 2026-09-18~22, Windows PC, COM3. 미검증 항목을 통과로 표시하지 않는다.

| 항목 | 결과 |
|---|---|
| 기존 Docker 전체 | 294 passed, 1 skipped, 4 warnings |
| 개인 상태 저장소 | Docker RED 후 60 passed, 독립 스펙/품질 PASS |
| 초기 ToolAgent | Docker RED 후 11 passed; 리뷰 수정 진행 |
| 초기 runtime 연결 | Docker RED 후 관련45 passed |
| Web 환경변수 | Docker RED 후 1 passed |
| Home Assistant | Docker RED 후 45 passed, 독립 스펙/품질 PASS; 실제 HA 계정 미연결 |
| client-sim | smoke passed, exit0 |
| firmware | 기본/OLED/LCD/bridge 4개 모두 성공 |
| firmware 산출물 | artifacts/firmware/default에 bin/elf/map/로그/SHA256 manifest 보존 |
| COM3 수동 수신 | 115200, DTR/RTS false, 5초324바이트, PING 4회, 송신0바이트 |
| Windows runtime | output/nextgen-runtime에 별도 설치 |
| Whisper small | CPU int8 로드 성공 |
| Gemini | gemini-2.5-flash-lite 실제 짧은 응답 성공, error_code None |
| 9/19 전체 회귀 | 438 passed, 1 skipped, 4 warnings. 이후 실모델 문제를 발견하여 추가 수정 중 |
| 서버→실기 TTS | 9/19 실제 음성 처리 후 MIC_LOCK → AUDIO_OUT → MIC_UNLOCK 로그 확인. 사용자가 들었는지 별도 확인 필요 |
| 마이크→STT→LLM→TTS | 9/19 COM3 오디오 수신 → STT 문장 → Gemini 응답 → TTS 전송 기록 있음. 의도한 사용자 발화인지/가청 출력 품질은 미확인 |
| 실기 재연결 | 아직 미검증 |

Docker 시작 오류는 stale userAnalyticsOtlpHttp.sock이 원인이었다. Docker 전용 프로세스를 정지하고 LOCALAPPDATA/Docker/run을 run-stale-20260918로 보존, 빈 run에서 다시 시작했다. 이미지/볼륨 삭제나 다른 WSL 종료는 하지 않았다.

기존 사용자 변경은 보존했고 codex/nextgen-home-agent 브랜치에서 작업한다. 커밋/푸시하지 않았다. 기존 펌웨어는 교체하지 않았다.
## 9/21 재개 조사

기존 서버의 실제 PID7560(런처PID3856)이 살아 있고 COM3 연결을 보고함. 이전 실제 할일 완료 응답에는 tasks.complete 기록이 없어 성공 주장이 잘못됐음을 확인. 실행증거 없는 답변 차단을 추가 중이다. Gemini 시스템 지침을 일반 user 메시지로 내리던 경로는 systemInstruction으로 수정하여 Docker RED 후 공급자 관련18개 테스트 통과.
## 9/21 실제 요청 재검증

- Docker Compose 전체: 464 passed, 1 skipped, 4 warnings (11.21초). 이후 독립 리뷰의 조회/명령 오인 및 오래된 mutation 캐시 문제를 추가 수정 중이므로 최종 수치는 별도 기록한다.
- 서버 재시작 후 19:57:25 COM3 연결, initial PONG, 19:57:26 START handshake 확인. 이는 서버 재시작 복구이며 물리 USB 뽑기/다시 꽂기 검증과는 구별한다.
- 실제 Gemini + 검증용 owner에서 이전 실행의 할 일 조회 → tasks.complete 성공 → tasks.list로 남은 항목 없음 확인. 이전의 실행 없는 완료 주장 재현 사례가 실제 도구 실행으로 해결됐다.
- 검증용 선호 색상 기억 저장(memory.remember) 후 별도 owner에서 memory.recall: 저장 내용 없음. 저장/조회는 metadata의 실제 도구 실행으로 교차 확인했다.
- 두 번째 실제 서버 재시작 후 같은 owner가 검증용 색상 기억을 조회함(memory.recall), 삭제(memory.forget) 후 재조회에서 없음 확인. SQLite 재시작 보존 및 삭제를 실모델 호출로 검증했다.
- 개발 중 전체 이미지 빌드가 Home Assistant 잘못된 성공 payload의 RED 테스트 추가와 수정 사이 스냅샷을 포함하여 478 passed / 1 failed / 1 skipped를 반환했다. 실패는 test_invalid_home_success_payload_is_not_confirmed의 KeyError(entity_id). 실제 수정 후 통합 검증을 다시 실행한다. 재현 명령은 위 표와 같은 Docker Compose 전체 명령이다.

## 9/22 재검증

재개 당시 ccoli 서버 프로세스가 없고 Docker Linux engine pipe도 없었다. Docker 시작 로그에서 userAnalyticsOtlpHttp.sock 접근 실패를 확인했다. Docker 전용 프로세스만 정지하고 run 폴더를 run-stale-20260922-230026으로 보존한 뒤 빈 run을 생성해 Docker 27.3.1 응답을 복구했다. COM3는 Windows PnP에서 USB Serial Port, Status OK로 확인했다.

복합 요청 조회 결과 누락 수정은 현재 파일에 존재하지만, 독립 리뷰에서 성공 결과 뒤에 오류가 붙어도 테스트가 통과하던 문제를 확인했다. 명시적 기억 저장과 다른 도메인 조회를 분리해 판정하고, 정상 완료에 오류가 없다는 테스트를 보강 중이다.

- 9/22 Docker Compose 전체 재빌드: 483 passed, 1 skipped, 4 warnings (13.36초), exit0. client-sim smoke도 exit0.
- 23:03:49 서버가 COM3 연결, initial PONG 후 23:03:50 START handshake. 초기 오디오는 STT에서 empty/filtered 처리됐다.
- 실제 Gemini 복합 요청(검증용 owner): memory.remember → tasks.list 모두 성공, 응답에 두 결과가 함께 표시됨. 후속 memory.recall → memory.forget으로 검증용 기억 삭제 확인.
- 남은 기능 조정: 복합 조회의 내부 도구명/JSON을 음성으로 읽기 쉬운 표현으로 변경. 이 후 테스트는 별도 기록한다.

## 최종 소스 자동 검증 및 현재 실행 상태 (9/22)

- 최종 음성 표현 수정 포함 전체: **490 passed, 1 skipped, 4 warnings**, 16.91초, exit0.
- 실행 명령: `docker compose -f docker/docker-compose.test.yml run --rm -v C:/bongkj/Projects/LLM_Arduino/server:/app/server server-test pytest server/tests -q --tb=short`. 직전 전체 이미지 재빌드 Compose 검증은 483 passed이며 마지막 소스는 이 마운트 실행으로 검증했다.
- 독립 리뷰에서 발견한 복합 요청 오류는 RED 2 → GREEN65, 음성 표현 변경은 RED9 → GREEN72로 검증했다. 루트가 최종 결과 생성 코드와 전체 회귀를 확인했다.
- 최종 서버 재시작 후 23:08:14 COM3 연결. 실제 Gemini에 기억 저장+할 일 조회를 요청해 “확인된 실행 결과: 기억 저장 … 확인된 조회 결과: 할 일: 남은 할 일이 없습니다.” 응답과 memory.remember/tasks.list 성공 기록을 확인했다. 검증용 기억은 memory.forget으로 삭제했다.
- 서버 로그: `output/nextgen-runtime/server-0922-final.stdout.log`, stderr 동일 접두사. 대시보드 `http://127.0.0.1:8005`.
- **남은 외부 확인:** 사용자의 의도한 마이크 발화가 인식되고 응답 음성이 실제로 들리는지, 물리 USB 분리/재연결 후 같은 동작이 되는지. 보드 모델은 FTDI/COM3 정보만으로 확정하지 않았다. 실제 Home Assistant 인스턴스는 미연결이며 어댑터 Docker 검증만 완료했다.
- 전체 목표를 완료로 표시하지 않았다. 실기 음성/물리 재연결의 직접 확인 전에는 자동 테스트를 근거로 완전 동작을 주장하지 않는다.
## 최신 실기 전송 증거 추가 확인

최종 서버 PID 24208(런처32032)이 살아 있고 진단 API는 COM3 connected=true를 반환했다. 9/22 23:08:45 및 23:09:59에 실제 수신 오디오의 STT 문장과 에이전트 응답이 생성됐다. 각각 TTS PCM16 56,320바이트를 생성한 뒤 23:08:48 및 23:10:02에 wired mu-law 8kHz 14,080바이트를 ESP32에 전송하고 MIC_UNLOCK까지 완료한 로그가 있다. 따라서 최종 코드의 마이크 수신→STT→에이전트→TTS→직렬 전송 경로 증거가 확보됐다. 사용자 의도 발화인지와 스피커에서 실제로 들린 음질은 이 로그로 확정하지 않는다.

전체 suite의 skipped 1개는 RUN_INTEGRATION_TESTS 환경변수로 제어되는 기존 assert True placeholder다. 프로토콜/CLI 및 새 통합 기능 검증은 별도 실제 테스트들에서 수행됐으며 이 placeholder를 실기 검증으로 계산하지 않는다.

미완료 게이트는 의도한 음성의 가청 응답, 물리 USB 재연결 확인, 보드 모델 확인이다. 실제 HA 인스턴스가 없어 실서비스 홈 제어는 미검증으로 유지한다. 현재 서버와 연결을 유지하며 사용자 확인을 기다린다.

## 장치 분리·재연결 후 음성 경로 확인 (9/22 23:20~21)

진단 API와 로그에 새로운 분리/재연결 증거가 나타났다. 23:20:54 연결 종료 후 COM3 open이 FileNotFoundError로 실패했고, 23:20:58 포트 재등장과 자동 연결, initial PONG을 확인했다. 23:20:59 START handshake가 복구됐다. 23:21:05 수신 오디오 76,160바이트가 STT/응답/TTS를 거쳐 23:21:13 mu-law 23,840바이트 전송과 MIC_UNLOCK으로 완료됐다. 이후 23:21:23과 23:21:47에도 응답 전송이 완료됐다.

따라서 OS에서 포트가 사라졌다가 다시 나타난 상황의 자동 재연결과 후속 음성 처리 복구는 실기 증거로 확인했다. 케이블 조작 자체는 직접 관찰하지 않았으며, 사용자가 들은 응답의 품질은 아직 확인되지 않았다. 남은 사용자 확인은 가청 응답과 정확한 보드 모델이다.
사용자 확인(9/22): “다 들려.”라고 응답하여 실제 가청 출력 확인 완료. 이어서 최신 모델 전환과 지연 개선을 요청했으므로 추가 작업은 MODEL_LATENCY_UPGRADE.md로 추적한다.

## 9/25 최신 모델·지연 개선 최종 소스 검증

- 모델 요청 형식: Gemini 3.8 Flash를 실제 계정 모델 목록과 호출로 확인했고, OpenAI GPT-6 Luna/Claude Haiku 4.5는 문서·Docker 계약 테스트로 확인했다. 두 공급자의 키가 없어 실제 응답 성공을 주장하지 않는다. 로컬 Qwen3.5:4b는 격리 합성 SQLite의 ToolAgent 목록/추가/인사 3시나리오를 수행했다. 첫 조회는 32.484초로 느려 운영 음성의 주 경로에 두지 않았다.
- 동일 8.616초 합성 한국어 음성 3회 STT: small CPU 평균 8.243초, turbo CUDA 평균 0.410초. 핵심 발화 인식 유지. 이전 로그에서 실제 사용자 턴은 END→STT 약 6.275초, STT→LLM 약 1.525초, TTS 약 0.75초였으나 초 단위 로그의 40건 집계이며 새 실기 왕복과 직접 비교하지 않는다. 새 sid별 정밀 `VOICE_LATENCY` 계측은 최종 서버에 배포됐다.
- 최종 소스 Docker Compose 전체 재빌드: **513 passed, 1 skipped, 3 warnings**, 12.03초, exit0. `client-sim smoke passed`, CLI `ccoli --help` exit0. skipped 1개는 기존 환경변수 조건부 placeholder. 새 테스트는 공급자 모델 요청 형식, 활성 API 장애 시 Qwen 전환, 읽기 결과 모순 방지, TTS 병렬 순서·예외 복구, 개인 입력·응답·키 로그 미기록을 포함한다.
- 최종 코드 재기동 후 진단 API: `mode=agent`, `stt.model_size=turbo`, `device_in_use=cuda`, STT/TTS 준비=true, wired COM3 connected=true. 실제 웹 인사 요청 약 1.54초, 활성 `gemini-3.8-flash`, 공급자 오류 없음. 요청 문장과 응답 본문은 최종 stdout 로그에서 발견되지 않았다. 최종 로그는 `output/nextgen-runtime/server-0925-privacy-final.stdout.log`.
- 기존 9/22 실제 ESP32 음성 전송과 사용자의 “다 들려” 확인은 유효하다. 9/25 새 코드의 보드 연결·STT 필터 입력은 직접 관측했으나, 의도한 새 사용자 발화의 마이크→응답 스피커 전체 왕복은 아직 새 버전에서 직접 관측하지 못했다. TTS 병렬 경로는 Docker 통합 테스트이며 현재 서버의 음성 체감 개선 수치는 사용자 발화 후 확인해야 한다.
- 실제 계정의 개인 할 일 조회를 새 Gemini에 보내는 검증은 자동 승인 검토가 개인 데이터의 원격 전송 위험을 이유로 거부해 실행하지 않았다. 개인 상태 도구는 합성·격리 데이터와 기존 9/21~22 실모델 성공 기록으로 구분해 평가한다. 승인 없이 재시도하지 않았다.
- Home Assistant 실제 인스턴스와 Claude/OpenAI 키는 여전히 미설정. 해당 외부 서비스의 실연동 성공은 검증하지 않았다. 보드 모델도 COM3 FTDI 정보만으로 확정되지 않았다. 서버·저장된 개인 SQLite·다른 프로젝트 프로세스는 보존했다.


## 9/25 최신 음성 모델 선택과 최종 재검증

- Gemini 3.8 Flash-Lite TTS는 공식 9/22 GA 속도형 모델이다. 합성 한국어 한 문장을 실제 키로 호출해 24 kHz raw PCM 응답을 확인했다. 어댑터는 응답 형식을 읽어 ESP32 경로의 16 kHz PCM으로 변환했으며, 실제 호출 결과 80,640바이트/2.52초 오디오, 생성 지연 2.235초였다. Edge 합성은 같은 문장에서 0.392·0.404초, Gemini는 1.941·1.630초여서 실시간 기본값은 Edge로 유지한다. Gemini 선택은 환경변수로 가능하며 실패 시 Edge로 복구한다.
- 새 기능을 포함한 Docker Compose 전체 재빌드: **519 passed, 1 skipped, 3 warnings**, 12.05초, exit0. client-sim smoke와 Docker CLI 도움말도 exit0. 새 테스트는 실제 반환 샘플레이트 기준 변환, 기본 WAV, 선택/복구, 개인 음성 문장의 오류 로그 비노출, 설정 우선순위와 클라우드 가속기 안내를 포함한다.
- 최종 소스 서버 재시작 후 COM3 유선 연결과 START handshake, turbo/CUDA STT·Edge TTS 준비를 다시 확인했다. 합성 웹 인사 요청은 1.330초, Gemini 3.8 Flash 정상 답변 18자, 공급자 오류 없음이었다. 요청과 답변 원문은 새 stdout 로그에 없었다. 로그: output/nextgen-runtime/server-0925-tts-final.stdout.log.
- 사용자의 이전 “다 들려”는 기존 실기 음성에 대한 확인이다. 이번 최신 코드에서는 의도한 새 사용자 발화의 왕복 지연과 가청 결과가 아직 직접 검증되지 않았다. Home Assistant 인스턴스 미설정과 Claude/OpenAI 키 부재도 동일하다. 전체 목표는 완료로 표시하지 않는다.


## 9/25 최종 리뷰·운영 반영

- 독립 리뷰가 이전 TTS 경로의 부분 재생 위험을 제기했고, 현재 소스에서 재현했다. 청크 일부와 전체 문장 재합성이 함께 실패하면 성공한 앞부분만 전송하던 경로를, 불완전 응답은 전송하지 않는 동작으로 수정했다. Docker RED 1 → GREEN 2로 확인했다.
- 자체 리뷰에서 Gemini TTS의 손상된 base64 예외 처리에 임포트 누락이 있음을 발견했다. Docker RED에서 NameError를 확인한 후 보정했고 해당 모듈 6개 테스트가 통과했다.
- 모든 최종 변경을 포함한 Docker Compose 전체 재빌드: **521 passed, 1 skipped, 3 warnings**, 12.30초, exit0. 앞서 client-sim과 CLI 스모크도 exit0. diff --check 통과.
- 최종 서버를 다시 시작해 agent 모드, Gemini 3.8 Flash, turbo/CUDA STT와 Edge TTS 준비, COM3 유선 연결을 확인했다. 합성 웹 인사 응답은 1.306초·18자·공급자 오류 없음이었다. 합성 요청과 응답 원문은 최종 stdout 로그에 없었다. 로그: output/nextgen-runtime/server-0925-reviewed-final.stdout.log.
- 독립 리뷰 에이전트의 최신 소스 읽기는 자동 승인 검토의 사용량 한도로 거부됐다. 이전 코드의 위험 제보는 루트가 직접 재현·수정·검증했지만, 이번 최종 변경 전체에 대한 독립 리뷰 완료로 기술하지 않는다.
- 사용자의 최신 버전 의도 발화에 대한 실제 ESP32 왕복 및 체감 지연 확인은 여전히 대기 중이다. Home Assistant 실기 인스턴스도 제공되지 않았다. 목표 상태는 진행 중이다.
## 9/25 표준 시작 설정과 회귀 검증

- 저장소의 일반 `ccoli start` 경로는 기존에 로컬 Ollama 우선이었고 개인 도구가 기본 비활성이며, 빈 인증 토큰으로 대시보드가 `0.0.0.0`에 바인딩될 수 있었다. 프로젝트 설정을 Gemini API 우선, `agent.enabled=true`, `web.host=127.0.0.1`로 맞췄다. CLI에서 공급자를 선택할 때 모델 표와 우선순위도 함께 저장한다.
- 표준 `Config(config_file="config.yaml")` 실제 로딩 결과: `install_target=api`, 개인 도구 활성, 웹 `127.0.0.1`, 유선 연결, 첫 후보 Gemini `gemini-3.8-flash`, 다음 후보 Ollama `qwen3.5:4b`. 기존 환경변수의 명시적 재정의는 유지된다.
- 관련 Docker 테스트 16 passed. 전체 `docker compose -f docker/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from server-test`: **525 passed, 1 skipped, 3 warnings**, exit0. Docker CLI `ccoli --help` exit0, `git -c core.safecrlf=false diff --check` 통과.
- 실행 중인 서버 진단 API는 `mode=agent`, `stt=turbo/cuda`, `llm=gemini/gemini-3.8-flash`, `COM3 connected=true`, STT/TTS 준비=true를 반환했다. 이 서버는 전용 런처의 동일한 개인 도구·웹 범위 설정으로 이미 시작돼 있어 이번 구성 파일만 변경한 뒤 재시작하지 않았다.
- 최신 코드에서 의도한 사용자 발화의 ESP32 마이크→응답 스피커 왕복 체감은 아직 확인되지 않았다. Home Assistant 실기 인스턴스도 미설정이다.
## 9/25 짧은 음성 입력의 현장 진단

- 16:21 운영 로그에서 0.68초 입력이 END까지 도달했으나 STT 계측이 없었다. 펌웨어·서버 소스를 조사해 END 자체는 마이크를 잠그지 않고 작업 종료 시 서버 입력 게이트도 해제됨을 확인했다. 오디오 원본이 없으므로 실제 발화인지 주변 소음인지 단정하지 않는다.
- 음성 내용이나 PCM 없이 `VOICE_INPUT`의 세션 번호, `too_short`/`too_quiet` 코드, 길이, RMS만 남겨 다음 입력의 필터 원인을 확인할 수 있게 했다. Docker RED에서 helper 부재를 확인한 뒤 GREEN을 확인했다. 전체 Docker Compose 재빌드 **526 passed, 1 skipped, 3 warnings**, exit0.
- 운영 서버를 프로젝트 런처로 재시작하고 COM3 핸드셰이크, `mode=agent`, turbo/CUDA STT 및 TTS 준비를 확인했다. 합성 웹 인사 요청은 1.346초, Gemini 3.8 Flash 정상 응답 18자였다. 새 stdout 로그는 `output/nextgen-runtime/server-0925-voice-filter.stdout.log`. 시작 직후 0.56초 입력은 STT에서 빈 결과로 필터됐으며, 의도한 새 사용자 발화 검증은 아직 필요하다.
## 9/25 명확한 홈 명령의 빠른 경로

- 격리 합성 Home Assistant HTTP 서버와 실제 Gemini 3.8 Flash로 `실험실 테스트 조명 켜줘`를 검증했다. 모델이 `home.states`를 조회하고 `home.control`을 호출한 뒤 HTTP GET으로 `on` 상태를 확인했다. 약 7.049초, 제어 POST 1회와 상태 GET 2회였다. 실제 Home Assistant나 물리 조명은 사용하지 않았다.
- 단일 기기의 정확한 표시 이름 또는 엔티티 ID와 명확한 켜기/끄기 명령은 도구 허용 목록과 상태 재확인을 유지한 채 모델 호출 없이 처리하도록 했다. 같은 합성 HTTP 서버의 GET→POST→GET 경로는 약 5ms였고 `on` 확인 후에만 성공 응답을 냈다. 합성 로컬 서버 지연이므로 실제 Home Assistant의 네트워크 지연을 나타내지는 않는다.
- 같은 이름의 기기가 여럿이면 ID를 요청하고 제어하지 않는다. 방법 질문·부정 요청·복합 요청은 직접 제어하지 않는다. 상태 불일치 응답은 실패로 처리한다. 관련 Docker 도구 테스트 83 passed, 전체 Docker Compose 재빌드 **535 passed, 1 skipped, 3 warnings**, exit0. 정확한 허용 ID 요청은 사전 전체 조회를 건너뛰고 POST→GET만 수행해 합성 서버에서 약 4ms였다. 명확한 한국어 명령은 목적격 조사 `을/를`도 허용한다.
- 운영 서버를 최신 소스로 재시작했다. 진단 API에서 agent 모드, Gemini 3.8 Flash, turbo/CUDA STT, TTS 준비 및 COM3 연결을 확인했다. 최종 소스 재시작 후 합성 웹 인사는 1.918초·18자였다. 현재 운영 서버에는 Home Assistant URL·토큰·허용 목록이 없어서 홈 도구는 비활성이다. 로그: `output/nextgen-runtime/server-0925-home-exact-final.stdout.log`.

## 9/25 홈 이름 조회 검토 및 병렬화

- 독립 리뷰에서 `서재 켜줘`처럼 이름에 `조명`/`스위치`가 없는 단일 명령이 느린 모델 경로로 빠지고, 이름 조회가 허용 기기를 직렬로 읽어 무관한 기기 타임아웃에 따라 지연되는 문제를 확인했다.
- Docker RED로 이름 명령, 부정 요청, 조회 실패 시 모델 재시도 금지, 허용 ID 병렬 조회 및 부분 실패 중단을 재현했다. 여러 허용 기기는 최대 8개씩 개별 `/api/states/{entity_id}`를 병렬 GET한다. 전체 `/api/states`는 조회하지 않는다. 정확한 허용 ID의 POST→GET 확인 경로는 유지한다.
- 합성 로컬 HTTP 서버에서 허용 기기 2개(하나는 `unavailable`)의 GET→GET→POST→GET 후 `서재` 상태 `on` 확인. 모델 호출 없이 6ms였다. 이는 실제 Home Assistant 지연이나 물리 기기 제어의 증거가 아니다.
- 전체 Docker Compose 재빌드 **540 passed, 1 skipped, 3 warnings**, exit0. `client-sim smoke passed`, `git -c core.safecrlf=false diff --check` 통과. 관련 Home Assistant/ToolAgent 테스트 133 passed.
- 최신 코드 운영 서버는 9/25 COM3·turbo/CUDA 연결과 Gemini 3.8 Flash를 확인했다. 합성 웹 인사 2.344초. 실제 홈 인스턴스는 미설정이다.

## 9/30 서버 재개와 실제 음성 지연

- 재개 시 서버 프로세스 및 로컬 HTTP가 없었다. PnP/pyserial은 FTDI COM3를 다시 표시했다. 런처를 시작해 COM3 연결, turbo/CUDA STT 및 Edge TTS 준비를 확인했다.
- 새 런타임 로그에서 실제 장치 입력 sid=6(2.60초)과 sid=7(1.08초)이 STT→Gemini 응답→Edge TTS→ESP32 mu-law 음성 전송 및 MIC_UNLOCK까지 완료됐다. 입력 종료→첫 전송은 각각 **2.519초**, **3.645초**; STT 0.232/0.208초, LLM 1.810/3.022초, TTS 0.472/0.412초였다. 입력·응답 원문은 기록하지 않아 사용자의 의도 발화 여부와 가청 출력은 아직 별도 확인이 필요하다.
- 기존 수동 프로세스를 종료하고 사용자 로그인 자동 시작 작업 `ccoli Nextgen Agent`를 설치했다. 첫 시험은 Task Scheduler 결과 1로 끝났고, 콘솔 없는 `pythonw.exe` 실행의 stdout/stderr를 로컬 파일에 연결한 후 다시 시작했다. 두 번째 시험에서 작업 상태 `Running`, 진단 API `mode=agent`, `COM3 connected=true`, `stt_ready=true`, `tts_ready=true` 확인. 합성 웹 인사는 2.285초, `gemini-3.8-flash`, 오류 없음. 재로그인 후 자동 시작은 아직 직접 검증하지 않았다.
- 본 PC의 작업은 `scripts/install_windows_autostart.ps1`로 다시 만들 수 있으며 사용자 계정에만 등록됐다. 실제 Home Assistant 사용 여부와 허용 기기, 의도한 최신 음성 발화의 가청 결과는 사용자 확인을 기다린다. 보드 모델은 FTDI 정보만으로 특정하지 않는다.

## 9/30 공식 모델 재대조와 Claude 후보 갱신

- 공식 OpenAI 모델 목록에서 GPT-6 Luna가 효율형 현행 모델이고, Google 모델 목록에서 Gemini 3.8 Flash가 최신 신규 프로젝트 후보임을 재확인했다. Claude는 9/28 공개된 Sonnet 5.5가 최신 속도·지능 균형 후보라 기본값을 Haiku 4.5에서 `claude-sonnet-5-5`로 갱신했다. Haiku가 가장 빠르지만 가까운 은퇴 시점과 최신 모델 요청을 함께 고려했다. Claude 키는 미설정이라 실제 호출은 하지 않았다.
- Sonnet 5.5는 non-default temperature를 거부하고 생각을 기본으로 시작한다. Docker RED 2개에서 구 요청·구 기본값을 재현한 뒤, `between_tools`/낮은 effort/텍스트 블록만 반환으로 수정했다. 기존 Haiku 요청 계약은 유지했다.
- Docker Desktop 시작은 기존 stale `userAnalyticsOtlpHttp.sock` 오류로 실패했다. Docker 전용 프로세스만 중지하고 `%LOCALAPPDATA%/Docker/run`을 `run-stale-20260930-212839`로 보존한 뒤 빈 run에서 재시작해 엔진 27.3.1을 복구했다. 이미지·볼륨·다른 WSL 인스턴스는 삭제하지 않았다.
- 전체 Docker Compose **541 passed, 1 skipped, 3 warnings**, exit0; `client-sim smoke passed`. 로그인 자동 시작 작업의 서버를 최신 런처로 재시작해 `Running`, COM3 연결, STT/TTS 준비, 합성 웹 인사 1.883초와 활성 Gemini 3.8 Flash를 확인했다. 개인 키·개인 기억 원문은 출력하지 않았다.

## 9/30 긴 저음량 입력의 음성 보존 검증

- 운영 로그의 약 8.18초, 전체 RMS -46.7~-51.8 dBFS 입력은 기존 -45 dBFS 전체 평균 검사에서 STT 전에 폐기됐다. 원본 오디오를 저장하지 않으므로 실제 사용자 발화인지 판단하지 않았다.
- 전체 RMS가 낮아도 240ms 안의 20ms 창 12개 중 9개가 기존 음량 바닥을 넘으면 Whisper VAD에 보내도록 서버 필터를 보정했다. 전역 임계값은 그대로이며 100ms 단발 충격음과 지속 저음량 입력은 폐기한다. 펌웨어는 변경하지 않았다.
- Docker RED: 처음 3개 합성 테스트에서 새 PCM 분류 인자가 없음을 확인했다. 창 정렬/짧은 저에너지 공백에 대한 추가 2개도 기존 구현에서 실패하는 것을 확인했다. GREEN: 필터 6개 통과. 독립 2단계 리뷰의 경계·공백 제보를 테스트로 재현해 해결했고 최종 읽기 전용 리뷰에서 blocker 없음.
- 최종 Docker Compose 전체 소스 테스트 `docker compose -f docker/docker-compose.test.yml run --rm -v C:/bongkj/Projects/LLM_Arduino/server:/app/server server-test pytest server/tests -q --tb=short`: **546 passed, 1 skipped, 3 warnings**, exit0. 앞선 전체 이미지 재빌드 544 passed/1 skipped는 경계 보강 전 스냅샷이다. `client-sim smoke passed`, Docker CLI 도움말 exit0, diff --check 통과.
- 로그인 작업 `ccoli Nextgen Agent`만 재시작한 후 Running, COM3 connected, turbo/CUDA STT 및 TTS 준비를 확인했다. 합성 웹 인사는 1.878초, 18자 응답, 활성 `gemini-3.8-flash`, 공급자 오류 없음. 원문·오디오를 로그에 남기지 않았다.
- 현재 코드의 의도한 실제 사용자 발화→스피커 가청 응답 및 체감 지연은 아직 직접 확인하지 않았다. Home Assistant 실기 인스턴스와 Claude/OpenAI 계정 키도 미설정이다. 기존 가청 확인은 이전 버전에 대한 사용자 답변이므로 이 변경의 실기 성공으로 간주하지 않는다.

## 9/30 개인 목록의 빠른 조회와 운영 재검증

- 실제 Gemini 3.8 Flash 운영 서버에서 격리된 합성 화자를 사용해 기억 저장→조회→삭제→재조회를 수행했다. 각 웹 요청은 3.290/2.996/4.354/3.244초였고 `/api/agent/`의 네 도구 실행(memory.remember, memory.recall, memory.forget, memory.recall)은 모두 `ok=true`였다. 삭제 후 조회에는 합성 값이 없었다. 기존 개인 데이터는 조회·출력하지 않았다.
- 단일 전체 목록 요청만 모델 없이 기존 owner-scoped `_execute`와 `_read_summary`로 처리한다. 복합·부분·완료 항목·쓰기 요청은 기존 모델 경로다. Docker RED에서 단일 조회/오류 경로 3개가 실패하고 복합 요청은 모델로 가는 것을 확인했다. GREEN에서 관련 ToolAgent 88 passed, 최종 전체 Docker Compose 이미지 재빌드 **548 passed, 1 skipped, 3 warnings**, exit0. `client-sim smoke passed`, Docker CLI 도움말 exit0, diff --check 통과. 독립 스펙/품질 리뷰에서 신규 회귀 blocker 없음.
- Docker Desktop은 다시 stale `userAnalyticsOtlpHttp.sock`로 시작 실패했다. Docker 전용 프로세스가 종료된 상태를 확인한 뒤 `%LOCALAPPDATA%/Docker/run`을 `run-stale-20260930-222840`으로 보존하고 새 run에서 엔진 27.3.1을 복구했다. 다른 WSL·이미지·볼륨은 변경하지 않았다.
- 로그인 작업 `ccoli Nextgen Agent`만 재시작해 Running, COM3 connected, turbo/CUDA STT와 TTS 준비를 확인했다. 격리된 빈 화자의 실제 웹 요청은 `내 할 일 보여줘` 52ms, `내 기억 목록 보여줘` 4ms, 다른 표현의 모델 경로 기억 질문 5.774초였다. 이 수치는 서로 다른 요청 표현의 한 번씩 측정이며 ESP32 음성 왕복 비교가 아니다. 활성 모델은 `gemini-3.8-flash`, 공급자 오류 없음, 도구 기록은 tasks.list/memory.recall/memory.recall이었다.
- README에서 Ollama를 현재 기본 경로로 소개하던 문장을 운영 설정에 맞게 고쳤다. 기본 Edge TTS에는 네트워크가 필요함을 명시했다. 당시 큰 개인 목록은 기존 2000자 말하기 상한에 걸리면 범위 축소 안내만 제공했다. 아래 10/6 이어보기 보완으로 해소했다.
- 최신 코드의 의도한 마이크 발화→스피커 가청 응답과 실제 Home Assistant 인스턴스 제어는 여전히 사용자/외부 환경 확인이 필요하다. 자동 시작의 재로그인 트리거는 수동 작업 시작으로 대체해 성공 주장하지 않는다.

## 10/6 긴 개인 목록·홈 제어 경계 최종 검증

- 긴 할 일·기억 목록은 모델 왕복 없이 사용자별 다섯 항목을 읽고 다음 항목의 실제 ID를 안내한다. 삭제/다른 사용자의 ID로 번호가 비어도 정확한 이어보기를 검증했다. 기억의 긴 본문에는 말줄임표를 사용하며 저장된 ASCII 의도 태그는 그대로 실행되지 않도록 표시한다. 목록/커서 Docker RED 3개와 이후 빈 커서 RED를 확인한 뒤 구현했다.
- 독립 리뷰가 저장된 문장/과거 대화에 의해 모델 홈 제어가 유도될 수 있는 기존 위험을 제보했다. 현재 문장 전체의 단일·순차 명령만 직접 실행하며, 모든 대상과 상태 조회 포함 최대 4회 예산을 실행 전에 확인한다. 중간 실패 후 즉시 멈추고 성공한 단계만 보고한다. 모델에는 home.control을 광고하지 않고 해당 제안을 항상 거부한다.
- Docker RED에서 과거 내용·부정·사용법 3개, 인용·모호한 선택 4개, 순차 제어/대상 선검증 3개 실패를 확인했다. 리뷰 제보의 인용문 증거 요구/기억 저장/미설정 응답 3개와 명령형 질문부호 1개도 RED→GREEN으로 수정했다. 최종 독립 스펙/코드 품질 리뷰에서 새 blocker 없음. 관련 ToolAgent **110 passed**.
- 최종 전체 이미지 재빌드 `docker compose -f docker/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from server-test`: **570 passed, 1 skipped, 3 warnings**, 14.90초, exit0. `docker compose -f docker/docker-compose.test.yml run --rm --build client-sim`: smoke passed. Docker `server-test ccoli --help` 및 diff --check exit0. 건너뜀은 기존 환경변수 조건부 integration placeholder다.
- Docker는 시작 시 같은 stale userAnalyticsOtlpHttp.sock 오류로 실패했다. Docker 전용 프로세스를 중지하고 실행 폴더를 run-stale-20261006-230822로 보존한 뒤 엔진 27.3.1을 복구했다. 다른 프로젝트/WSL/이미지/볼륨을 초기화하지 않았다.
- 현재 부팅 10/6 21:37:24.5 이후 로그인 트리거로 등록된 작업의 LastRunTime과 pythonw 생성 시간이 21:37:39였다. 작업과 서버가 실행 중이고 COM3/STT/TTS 준비를 관측했다. TaskScheduler 트리거 이벤트 로그는 사용 불가라 정확한 이벤트 종류를 직접 확인했다고 기술하지 않는다.
- 실제 Home Assistant 인스턴스는 미설정이므로 홈 제어의 실서비스 성공을 주장하지 않는다. 실제 최신 사용자 의도 발화의 청취 확인은 계속 별도 게이트로 유지한다. 변경 롤백과 사용법은 NEXTGEN_AGENT_PLAN.md 및 HOME_ASSISTANT_GUIDE.md에 반영했다.

### 10/6 운영 페이지 조회와 합성 데이터 정리

570개 테스트 버전 운영 재기동 후 격리된 빈 화자의 웹 요청은 할 일 커서 117ms, 기억 커서 7ms, Home 미설정 안내 3ms였다. 실제 Gemini 인사는 2.719초였고 COM3, turbo/CUDA STT, TTS 준비 및 공급자 오류 없음이 확인됐다.

별도 합성 화자의 실제 Gemini 기억 저장 6건은 각각 6.114/7.038/8.749/4.440/5.784/9.083초였다. 이때 장치 음성 요청도 운영 중이므로 이 수치는 순수 공급자 지연 비교가 아니다. 첫 다섯 항목·실제 다음 ID 안내·두 번째 페이지의 여섯 번째 값 표시가 성공했고, 6개를 모두 삭제한 뒤 빈 목록을 확인했다. 기존 개인 데이터를 조회하거나 출력하지 않았다.

## 10/6 다른 채널의 모델 대기에서 직접 경로 분리

- 공유 턴 잠금으로 다른 사용자의 로컬 조회가 느린 모델 턴을 기다리는 것을 Docker Event 기반 테스트에서 RED로 재현했다. 사용자별 턴 순서와 짧은 공용 상태 잠금을 분리해 직접 조회가 모델 종료 전 완료하도록 수정했다. 홈 제어 전체 순서는 별도 잠금으로 보존하고, 관련 없는 모델 요청이 홈 제어를 기다리던 추가 RED도 보정했다.
- 독립 스펙/코드 품질 리뷰 PASS 및 독립 Docker 관련 테스트 130 passed. 추가 공급자 상태 직렬화 검증을 포함한 runtime 테스트는 21 passed. 일반 사용자 모델 호출은 공유 공급자 상태 보호를 위해 직렬로 유지한다. 기존 proactive 레거시 경로는 이 잠금 범위 밖이며 본 PC 런처는 proactive=False다.
- 최종 전체 이미지 재빌드 `docker compose -f docker/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from server-test`: **575 passed, 1 skipped, 3 warnings**, 14.92초, exit0. 최종 client-sim 재빌드 smoke passed 및 Docker CLI 도움말 exit0. 원문·API 키·오디오를 검증 출력에 남기지 않았다.

### 10/6 최종 운영 재기동과 동시 HTTP 확인

지연 개선까지 반영한 최종 서버는 작업 Running, COM3 connected, turbo/CUDA STT와 TTS 준비를 확인했다. 격리된 두 합성 화자의 실제 웹 요청에서 Gemini 인사는 2.005초가 걸렸고, 그 요청이 완료되기 전에 다른 화자의 빈 할 일 목록은 **42ms**로 완료됐다. 모델 HTTP 요청은 조회 전·후 모두 진행 중이었으며 빈 결과가 정확했다. 활성 gemini-3.8-flash, 공급자 오류 없음. 이는 웹 직접 조회 대기 감소를 보여주며 ESP32 전체 발화 지연 수치로 대신하지 않는다.

최종 재기동 이후 장치 입력 sid=3은 입력 종료→첫 전송 3.206초와 MIC_UNLOCK을 기록했다. 실제 입력 원문과 오디오는 보존하지 않아 의도 발화 여부와 최신 응답의 청취 결과는 아직 사용자 확인과 구분한다. 보드 모델·실제 HA 인스턴스 조건도 미확정이므로 전체 목표를 완료로 표시하지 않는다. 실행 서버와 기존 개인 상태는 유지한다.

## 10/7~8 선제 응답 격리와 최종 운영 반영

- 개인 에이전트의 선제 생성이 일반 개인 대화/공용 개인 문서/자동 기억 추출을 사용하던 경로를 Docker RED 9건으로 재현했다. 공개 Soul과 현재 트리거만 쓰는 일회성 응답으로 분리했으며 개인 대화 이력 읽기·쓰기, SQLite 조회, 자동 추출, 도구 실행 및 장치 의도 전달을 하지 않는다. 이 PC의 proactive=False 설정은 유지했다.
- 같은 스레드 모델 콜백 재진입 RED 1건, 태그/중첩 도구 JSON RED 3건, 접두 평문 뒤 JSON/코드펜스 RED 3건을 추가했다. 사용자 모델 턴이 진행 중이면 선제 생성은 즉시 건너뛴다. 응답의 모든 INTENT 태그를 제거하고, answer 래퍼를 푼 뒤 본문에 JSON 중괄호 또는 코드펜스가 남으면 발화하지 않는다. 오류 로그는 예외 종류만 남긴다. 이 형식 제한은 선제 응답에만 적용한다.
- 독립 스펙 준수 → 코드 품질 리뷰 최종 PASS. 리뷰의 접두 문장 뒤 JSON/펜스 발화 P2를 RED로 확인한 후 수정했다. 관련 Docker 테스트 **159 passed**, 전체 이미지 재빌드 `docker compose -f docker/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from server-test`: **591 passed, 1 skipped, 3 warnings**, 16.04초, exit0. `docker compose -f docker/docker-compose.test.yml run --rm --build client-sim`: smoke passed. Docker CLI `server-test ccoli --help`와 diff --check exit0.
- Docker Desktop 시작 실패의 stale userAnalyticsOtlpHttp.sock을 공식 프로세스 로그에서 확인했다. Docker 전용 프로세스를 중지한 뒤 실행 폴더를 run-stale-20261007-235144로 보존하고 새 run으로 엔진 27.3.1을 복구했다. 다른 WSL·이미지·볼륨·개인 데이터는 보존했다.
- 최종 소스를 로그인 작업 `ccoli Nextgen Agent` 재시작으로 반영했다. 10/8 00:11 로그에서 STT/TTS warmup 완료와 COM3 연결·START handshake를 확인했다. HTTP 진단은 task Running, connected=True, Whisper turbo/CUDA, stt_ready=True, tts_ready=True, 활성 Gemini gemini-3.8-flash, 공급자 오류 없음, proactive.enabled=False였다.
- 서로 다른 격리 합성 화자의 동시 HTTP 점검에서 Gemini 인사는 **2.117초**, 다른 화자의 직접 할 일 조회는 **7ms**였다. 모델 요청은 조회 전·후 모두 진행 중이었다. 최초 빈 목록 비교는 조회 접두 문구를 빠뜨려 false였고, 실제 서버 형식인 '확인된 조회 결과: 할 일: 남은 할 일이 없습니다.'로 별도 합성 owner에서 재확인해 정확히 일치했다(73ms). 실제 사용자 목록·키·발화·오디오 원문은 출력하지 않았다. 이 HTTP 수치는 ESP32 음성 전체 왕복 시간이 아니다.
- 사용자는 앞서 '다 들려'로 가청 응답을 확인했다. 최신 음성 최적화의 의도 발화 청취, 정확한 보드 모델과 실제 Home Assistant 인스턴스는 추가 증거가 없으므로 전체 원래 목표의 완료로 대신하지 않는다. 모델/속도 구현과 현재 운영 반영은 완료했으며, 같은 전체 테스트를 근거 없이 반복하지 않는다. 전체 목표의 남은 외부 조건은 위 세 항목뿐이다. API 키가 없는 Claude/OpenAI는 최신 기본 후보 및 Docker 요청 계약 검증까지 완료했고 실제 계정 호출은 검증하지 않았다.

롤백은 NEXTGEN_AGENT_PLAN.md의 선제 생성 분기/관련 테스트 복구 절차를 따르고 같은 Compose 게이트 후 작업을 재시작한다. 현재 선제 기능 비활성 설정과 개인 데이터는 유지한다.

## 10/8 운영 인증과 완료 감사

완료 감사에서 발견한 운영 인증 공백을 해소했다. 본 PC의 server/.env에 강한 무작위 WEB_AUTH_TOKEN을 설정했고 값은 소스·문서·명령 출력에 남기지 않았다. HTTP와 실시간 이벤트는 동일한 토큰으로 보호되며, WS는 첫 인증 프레임을 5초/4096바이트 이내로 확인한 뒤에만 구독자에 등록한다. 거부는 4401이다. 기존 ASCII 헤더를 유지하면서 브라우저의 Unicode 토큰은 명시적 UTF-8/base64url 헤더로 처리한다.

- Docker 행동 RED: 이전 WS 구현 overlay에서 무인증 등록 기대 0/실제 1 실패를 확인했다. malformed Unicode와 HTTP 인코딩 경계 RED 4건, 실제 dashboard.js 실행의 개인 캐시 미삭제 RED, 환경 비밀값 저장 관련 RED 4건을 수정했다.
- 토큰 교체 시 개인 캐시와 화면을 지우며 이전 HTTP 응답/JSON 파싱 결과 및 이전 WS 이벤트를 무시한다. 4401 이후 자동 재연결을 중단하고 토큰 입력을 안내한다. Config.save는 환경 비밀 경로를 YAML 원본값으로 복원한 사본만 저장하고, 설정 API는 bot_token/client_secret/refresh_token까지 마스킹한다.
- 작성자와 별개의 독립 스펙 준수 → 코드 품질 최종 리뷰 PASS. 전체 단일 진입점 `bash scripts/run_docker_tests.sh`를 Windows Git Bash에서 실행해 **614 passed, 1 skipped, 3 warnings**, 15.92초를 확인했다. client-sim과 dashboard auth smoke passed, default/OLED/LCD/companion bridge 펌웨어 **4종 빌드 성공**, 전체 스크립트 exit0. CI도 같은 스크립트로 실행하도록 연결했다. Docker CLI 도움말 exit0이며 실제 GitHub 원격 CI 실행을 주장하지 않는다.
- 최종 운영 작업만 재시작했다. 실제 무인증/오인증 `/api/agent/`는 **401**, 올바른 raw/encoded 토큰은 성공(**200**), 도구 6개 활성, 설정 토큰은 ***로 마스킹됐다. 같은 web.host 값을 인증된 PATCH로 저장해도 추적 YAML의 실제 토큰 포함 False 및 비어 있지 않은 알려진 비밀 필드 0을 확인했다. 실제 원문 값은 출력하지 않았다.
- 실제 잘못된 WS 인증은 **4401**, 정상 인증은 별도 합성 화자의 chat_response 이벤트와 응답의 일치를 확인했다. 동시에 Gemini 인사 **2.071초**, 다른 화자의 빈 할 일 조회 **8ms**였으며 모델 요청은 조회 전·후 모두 진행 중이었다. 빈 목록은 정확했다. 사용자 기존 기억·발화 원문은 검증에 사용하지 않았다.
- 10/8 07:59 재확인에서 작업 Running, COM3 connected, Whisper turbo/CUDA, STT/TTS ready, 활성 gemini-3.8-flash 및 공급자 오류 없음이다. 최신 실제 장치 sid41/42는 입력 종료→첫 전송 **2.557초/4.091초**, 각각 MIC_UNLOCK까지 기록됐다. 입력 내용과 스피커 청취 여부는 보존하지 않아 의도한 사용자 발화의 확인으로 대신하지 않는다.
- 브라우저 자동 검증은 Playwright MCP의 PC localhost 접근 불가와 in-app 브라우저 도구의 sandbox helper 시작 오류로 수행하지 못했다. 실제 브라우저 E2E를 성공으로 계산하지 않는다. 대신 실제 JS 행동은 Docker Node, 실제 보호된 HTTP/WS는 본 PC에서 각각 검증했다. 대시보드 첫 사용에는 페이지를 새로고침하고 고급 진단의 비밀번호 입력란에 개인 .env의 WEB_AUTH_TOKEN을 한 번 저장해야 한다.
- 마지막 로그 확인/정리 호출은 사용량 한도로 자동 승인 검토가 실패했으나, 07:58 계정의 실행 허용을 확인한 뒤 같은 승인 경로로 재개했다. 승인 검토를 우회하지 않았다.

### 원래 범위의 요구사항 대조

| 요구사항 | 현재 증거 | 판정 |
|---|---|---|
| 최신 홈/개인 에이전트 조사와 실행 가능한 설계 | NEXTGEN_AGENT_PRD/PLAN의 공식 출처·3개 대안·파일/검증/롤백, 구현 파일 | 완료 |
| 제한된 실행 엔진·4회·엄격 인자·실패 격리·실행 사실에 맞는 응답 | tool_agent.py 및 test_tool_agent.py, 전체 Docker 회귀 | 완료 |
| 사용자별 기억/할 일·재시작 보존·SQL·길이·동시 격리 | personal_store.py 및 60개 저장소 테스트, 이전 실제 합성 API 보존/정리 기록 | 완료 |
| 홈 allowlist·light/switch·시간 제한·리디렉션 차단·POST 후 확인 | home_assistant.py 및 47개 Docker 어댑터 테스트, 직접 제어/순차/실패 회귀 | 구현/모의 검증 완료, 실 HA 미설정 |
| 음성·웹·Telegram의 공통 실행 엔진과 일정/조회 경계 | server.py, api_chat.py, 채널/nextgen runtime/CLI 회귀 | 구현 완료, 외부 Telegram 계정 별도 |
| 실제 인증된 운영 도구/기록 API와 키 없는 도구 숨김 | 현재 HTTP 401/200 및 WS 4401/합성 이벤트, 도구 6개/Home 미노출, 저장/마스킹 회귀 | 완료 |
| 모델 교체·요청 호환·빠른 음성/조회·운영 설정 일치 | MODEL_LATENCY_UPGRADE, 실제 Gemini/로컬 PoC, Docker 계약, turbo/CUDA 및 최신 웹/장치 지연 | 완료, Claude/OpenAI 계정 키 미설정 |
| Docker 전체·통신·CLI·브라우저 인증 행동·펌웨어 4종·단일 CI 진입점 | 위 전체 스크립트 exit0 및 artifacts/test-logs | 완료 |
| 실제 COM3 핸드셰이크·TTS·포트 소실/재등장 복구 | 최신 준비/START 및 이전 9/22 포트 복구/후속 음성 기록, 사용자 '다 들려' | 확인됨 |
| 정확한 보드 제품명과 최신 가청 응답 | 10/8 사용자: esp32 atom echo, 잘들려. 실제 장치 STT/LLM/TTS·MIC_UNLOCK 기록과 함께 확인 | 확인됨 (체감 속도 만족은 별도) |

현재 코드 감사에서 추가 구현 누락은 발견하지 못했다. 10/8 사용자 답변으로 보드 식별과 가청 응답 확인이 해소됐다. PRD는 홈 허브나 외부 계정이 없는 연동의 모의 검증과 실서비스 검증을 구분한다. 현재 미설정인 Home Assistant·Telegram과 키가 없는 Claude/OpenAI의 실서비스 성공을 주장하지 않는다. 선택적 Home Assistant 설치나 임의 계정 생성은 핵심 음성·개인 에이전트 완료의 필수 조건이 아니다. 실제 서버와 개인 상태를 유지한다.

## 10/8 사용자 실기 확인과 현재 운영 상태

사용자는 연결한 장치를 `esp32 atom echo`로 확인하고 `잘들려`라고 응답했다. 이 확인은 최신 실기 가청 응답의 증거이며, 특정 테스트 문장의 원문이나 체감 속도 만족을 추정하는 근거로 사용하지 않는다. 앞서 관측한 실제 장치 STT→LLM→TTS→MIC_UNLOCK 및 포트 소실/재등장 복구 기록과 함께 PRD의 실기 게이트를 충족한다.

10/8 21:20 KST에 개인 토큰으로 진단·도구 API를 다시 조회했다. 작업은 Running, COM3 connected=True, Whisper turbo/CUDA, STT/TTS ready=True, 활성 gemini-3.8-flash, 공급자 오류 없음, 개인 도구 6개 활성이다. Home 도구는 미설정으로 노출되지 않았다. 토큰·개인 기억·발화·오디오 원문은 출력하지 않았다.

최종 Docker 614 passed/1 skipped, client-sim·dashboard auth smoke, 펌웨어 4종 빌드 기록을 재확인했다. 이번 변경은 사용자 확인과 안내 문서에 한정되어 생산 코드 변경이나 동일 전체 테스트의 반복은 하지 않았다. Home Assistant는 선택적 스마트홈 서버이고 이 PC에서 실제 장비를 제어했다고 주장하지 않는다.

독립 완료 감사에서도 PRD 구현 범위 1~6에 남은 필수 기능이 없고 최신 사용자 확인으로 실기 게이트를 충족한다는 판정을 받았다. 원래 구현 목표는 완료했으며, 실제 HA·미설정 외부 계정의 실서비스 검증은 위에 명시한 조건부 범위로 남긴다.
