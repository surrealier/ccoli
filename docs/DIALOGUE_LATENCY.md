# 다국어 응답 지연 / 품질 비교

`scripts/benchmark_dialogue.py`는 공개 합성 문장만 사용한다. 기억, 실제 발화, `.env`, 개인 음성을 읽지 않는다. 모델 설정도 변경하지 않는다. 기본 비교 대상은 현재 primary `gemini-3.8-flash`와 fast 후보 `gemini-3.5-flash-lite`다. 실제 공급자 응답이 없으면 mock 결과를 실제 성능이라고 표시하지 않는다.

## 호출 예산과 평가 구성

기본은 모델당 ko/en/zh/ja/es × 2회, 총 **20 provider attempts**다. 모델 목록은 최대 2개이며 자동 retry/fallback/warm-up 호출은 없다. Runtime의 `LLMClient` Gemini once 경로를 그대로 사용해 primary low, 해당 Lite minimal thinking payload를 비교한다. 짧은 일반 대화는 384 token cap, 상세/도구 복합 요청은 768 token cap이다. 실제 과금액은 공급자 가격/청구 기록으로 확인해야 하며 이 도구는 비용을 추정하지 않는다.

각 언어에 고양이의 가르랑거림에 대한 자연스러운 짧은 질문 1회, 화분 물주기 상세 3단계와 별도 `tasks.add` JSON 계획을 함께 요청하는 공개 평가 1회를 넣었다. 3유형을 각 언어/모델마다 독립 호출하면 30회가 필요하므로 상세/도구는 복합 요청이다. 복합 지연을 실제 단일 도구 계획 latency로 해석하지 않는다. 모델별/유형별 p50, nearest-rank p95, 전체와 성공 요청 지연을 따로 저장한다. 모델당 10표본은 작은 비교 실험이며 운영 p95의 확정값은 아니다.

자동 지표는 언어 heuristic, 짧은 답변 길이, empty/error, strict JSON, 정확한 도구 이름/제목/인자, 3단계 상세 답변 여부다. 언어 heuristic은 통계적 언어 판별기가 아니며 특히 Latin Spanish와 Kanji-only Japanese가 모호할 수 있다. 자연스러움, 정확한 설명, 필요한 정보 보존, false completion 여부는 JSON의 **공개 응답을 사람이 읽어서** 판정한다. 이 복합 요청은 실제 ToolAgent model turn을 그대로 재생하는 평가가 아니므로 실제 AgentMode/ToolAgent 시나리오 회귀와 함께 확인한다.

## 안전한 실제 실행

키는 주 작업자가 일시적인 Docker 환경변수 `GEMINI_API_KEY`로 전달한다. 명령줄에 키 값을 적거나 `.env` 전체를 마운트하지 않는다. 아래는 이미 키가 Docker 환경에 안전하게 전달되는 실행 환경에서의 명령이다.

```sh
python /app/scripts/benchmark_dialogue.py --models gemini-3.8-flash gemini-3.5-flash-lite --output /work/dialogue-benchmark-public.json
```

`server-test` 이미지에서 현재 script, `dialogue_policy.py`, `agent_mode.py`, `tool_agent.py`, `llm_client.py`와 공개 output 폴더만 선택 마운트한다. Runtime settings/user memory 디렉터리는 필요 없다. 단일 모델은 `--models <model>`로 선택할 수 있다. 출력에는 응답/검증 플래그/지연과 안전한 오류 코드만 있고 키나 HTTP 오류 본문은 없다. Failed call도 예산을 소비하며 provider 모델이 없다고 자동으로 다른 모델에 호출하지 않는다.

키 없이 로컬 경로만 실행할 수 있다.

```sh
python /app/scripts/benchmark_dialogue.py --local-only --output /work/dialogue-local-public.json
```

이 경로는 임시 SQLite의 실제 PersonalStore + ToolAgent direct read로 5언어 owner isolation/zero model calls를 확인한다. 실제 AgentMode의 TTS cache dispatch도 실행하지만 합성 PCM generator를 사용하므로 결과는 **cache overhead**만 나타낸다. 이 값은 실제 Edge/Gemini TTS synthesis latency, 음질, 재생 지연이 아니다. 동일 텍스트 cache hit와 언어/voice 변경 miss를 확인하며 음성을 디스크에 저장하지 않는다. 개인 답변/실행 결과 cache는 사용하지 않는다.

## 모델 적용 기준

실제 provider 결과에서 5언어 응답과 상세 요청, strict tool schema/정확한 title, false completion 여부를 검토한다. Fast 후보의 오류/잘림/도구 correctness가 primary에 비해 나빠지지 않고 일반 대화 지연이 유의하게 줄었을 때에만 `dialogue.fast_model` 적용을 검토한다. 자동 승격하지 않는다. Primary와 fast 모델 선택은 분리되고 fast 실패 시 runtime은 원래 primary chain으로 돌아간다. Fixed language와 owner 별 auto continuity를 유지한다.

STT는 5 fixed language와 auto→None, LLM은 턴별 언어/짧은 응답 정책, TTS는 language voice와 backend/model/voice/text hash/padding별 bounded memory TTL/singleflight를 사용한다. Cache는 최신 도구 상태/개인 답변을 대신하지 않는다. 이 실험은 키 없는 Docker contract RED 5 failures → GREEN 5 tests로 작성됐다. 실제 API 비교 수치와 인간 품질 판정은 주 작업자가 실행 후 기록한다.

## 실제 공급자 비교 (2026-10-09)
이 PC에 설정된 Gemini 키를 출력하지 않고 격리 Docker 환경으로 전달했다. 공개 합성 문장만 사용해 자동 재시도 없이 모델당 10회(일반 대화 5언어 + 상세/도구 계획 복합 요청 5언어), 총 20회 실행했다. 두 모델 모두 10/10 정상 종료, 잘림/오류 없음, 언어·짧은 답변·요청 title 보존·strict JSON schema 조건을 통과했다. 공개 응답 전체를 사람이 읽고 자연스러운 표현, 상세 설명 유지와 작업을 실행했다는 허위 주장 여부를 확인했다.

| 모델 | 일반 대화 표본 | 일반 대화 p50 | 일반 대화 p95 |
|---|---:|---:|---:|
| gemini-3.8-flash | 5 | 2251.61 ms | 5140.13 ms |
| gemini-3.5-flash-lite | 5 | 1028.62 ms | 1365.52 ms |

이 표본에서 Lite의 일반 대화 중앙값이 약 54% 짧았다. 이는 HTTP 요청부터 완성된 LLM 답변까지의 시간이며 STT/TTS/Atom 전송·실제 재생 시간은 포함하지 않는다. 작은 공개 표본은 광범위한 사실 정확도나 실생활 도구 실행 성공을 보증하지 않는다. 상세/도구 요청은 복합 테스트이며 독립 도구 지연으로 해석하지 않는다. 비유·건강 주장 등의 사실 정확성에는 별도 평가가 필요하다.

이 결과를 근거로 이 프로젝트의 Gemini 대화 기본 설정에는 gemini-3.5-flash-lite를 적용한다. 기본 primary chain은 유지하며 실패 시 원래 chain으로 복귀한다. 다른 provider 설치와 기존 명시 설정은 빠른 모델을 선택하지 않으면 그대로 동작한다. 공식 모델 목록은 3.5 Flash-Lite와 3.8 Flash를 현재 프로젝트용 모델로 안내한다: https://ai.google.dev/gemini-api/docs/models

원본 공개 결과: output/robotics-poc/dialogue-benchmark-public.json. API 키, 실제 개인 대화, 저장된 일정, 실기 실행 결과는 실험 입력이나 결과에 포함하지 않았다.
