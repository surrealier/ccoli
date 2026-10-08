# Granite 4.2 voice template PoC — 2026-09-25

The installed `granite4.2:3b` had `{{ .Prompt }}` as its template and only the `completion` capability. A separate `ccoli-granite4.2:3b-voice` model was created from the same weights using `models/Modelfile.granite42-voice`. The source model and Ollama service settings were not changed.

Source: https://huggingface.co/ibm-granite/granite-4.2-3b/blob/main/chat_template.jinja . The voice profile uses ChatML message boundaries and the official disabled-thinking assistant prefix. This profile accepts text/JSON messages; it does not implement native XML tool calls.

Recreate with `ollama create ccoli-granite4.2:3b-voice -f models/Modelfile.granite42-voice`.

Two actual `/api/chat` requests used `think:false`, `keep_alive:0`, `num_ctx:2048`, temperature 0.2 and a 90-second timeout. STT CUDA was already running, and other GPU workloads were not stopped.

| Scenario | Total | Model load | Decode | Result |
|---|---:|---:|---:|---|
| Korean greeting (64 token cap) | 5.97 s | 5.51 s | 0.376 s / 47 tokens | Coherent Korean; exceeded requested one-sentence style |
| Required tasks.list JSON (96 token cap) | 2.26 s | 1.97 s | 0.230 s / 29 tokens | FAILED: plain text claimed an empty task list without a tool call |

Both responses stopped normally. Correct framing resolves the earlier long self-dialogue behavior, but these results do **not** validate Granite as the personal-state tool agent. Do not select this model as a verified fallback until it passes the application's actual tool and evidence tests. No stored task was read or changed in this PoC. No further inference requests were issued.

## JSON-mode follow-up (two synthetic requests)

With a stricter explicit tasks.list instruction, temperature 0, and the same 96-token/2048-context/keep_alive:0 limits:

| Format | Total | Model load | Decode | Result |
|---|---:|---:|---:|---|
| `format: "json"` | 2.04 s | 1.72 s | 0.094 s / 12 tokens | `{"tool":"tasks.list","arguments":{}}` |
| JSON Schema restricted to tasks.list | 1.49 s | 1.27 s | 0.088 s / 12 tokens | `{"tool":"tasks.list","arguments":{}}` |

Both passed the requested narrow output criterion. Because the prompt was strengthened too, this does not isolate JSON mode as the sole cause. The schema-constrained test forces the one possible tool and does not demonstrate autonomous selection. Neither probe executes a tool or validates the full application loop. The model remains inactive. A generic JSON mode may be worth integrating behind model-specific configuration and testing with real ToolAgent prompts, including incorrect tool choices and mutation refusals, before activating this fallback.

## Actual ToolAgent integration (Docker, synthetic SQLite)

Used the unmodified ToolAgent.run prompt and loop with a wrapper adding generic `format: json`. Temporary SQLite existed only inside the disposable Docker container and was seeded with one task, `합성 연결 점검`. No user state or live application configuration was accessed. Six model requests total; each used keep_alive:0, timeout90s, context4096, and ToolAgent's temperature/token settings. Per-scenario quotas were 3/3/2 requests to enforce the overall eight-request limit.

- List request: 5.293s / 2 requests. tasks.list succeeded and returned the seeded task, but the final answer falsely claimed there were no tasks. JSON formatting alone does not prevent contradictory state claims. Current ToolAgent verifies that a read occurred, not that the prose matches its results.
- Add request: 5.320s / 3 requests. tasks.add succeeded but changed the title to `합성 테스트 문서 작성 일`. It then called tasks.list twice and reached the probe quota. The runtime's deterministic mutation summary accurately retained the created ID, followed by its connection-failure message when the wrapper declined a fourth call. This is a probe limit, not a transport failure.
- Greeting: 1.910s / 1 request. Valid Korean answer, no tools; passed.

Recommendation: do not activate this Granite fallback or treat generic JSON mode as a reliability fix. ToolAgent's read-only final-answer path also needs evidence-grounded rendering to prevent this observed contradictory list answer with any provider. Source and derived models remain unchanged by these tests.

## Read-only result correction

The observed read contradiction now has a Docker regression using seeded synthetic tasks and a model that falsely says the list is empty. An equivalent memory regression is included. Both failed before the change. Explicit task/memory/home-state queries now render successful current-turn tool data with the existing bounded summary formatter instead of accepting contradictory model prose. Mutation-plus-read summaries retain their original timing behavior; owner selection still comes from the server. This does not activate Granite or repair its title alteration/repeated-read behavior.

Docker validation: `pytest server/tests/test_tool_agent.py server/tests/test_nextgen_runtime.py -q --tb=short` via the test Compose service: 90 passed, one existing Starlette deprecation warning.
