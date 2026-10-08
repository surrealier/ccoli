# Qwen3.5 4B actual ToolAgent PoC — 2026-09-25

The official downloaded `qwen3.5:4b` model was exercised through the actual ToolAgent prompt and loop, using a disposable Docker container and temporary synthetic SQLite only. The native text protocol was used without JSON-mode enforcement; `think:false`, `keep_alive:0`, context4096, ToolAgent's temperature0.2/token768, timeout90s. Total: six model requests, within the eight-request cap. No source model, service configuration or personal data was changed.

| Scenario | Total latency | Calls | Verified result |
|---|---:|---:|---|
| List one seeded task | 32.484s | 3 | PASS after correction: tasks.list returned ID1 `합성 연결 점검`, final deterministic summary matched |
| Add exact title | 8.533s | 2 | PASS: tasks.add created ID2 with exact title `합성 테스트 문서 작성`; final summary matched |
| Greeting | 3.862s | 1 | PASS: Korean greeting, no tools |

The first list response falsely asserted there were no tasks without calling a tool. ToolAgent's existing evidence correction recovered by requiring tasks.list. The first cold request took23.897s, then4.029s and4.556s. Add requests took4.216s and4.305s. Because keep_alive:0 was required, these numbers include loading and are not warm-session latency estimates. Other GPU workloads were left running; observed model GPU residency was4.41GB at context4096.

Compared with the Granite JSON PoC, Qwen preserved the requested title and completed the bounded agent loop. It is a stronger local fallback candidate on these narrow scenarios, but has substantially slower startup and requires runtime evidence guards. Prefer the verified cloud model for this PC's low-latency voice path; do not describe local Qwen as a speed improvement from these results. Broader tool accuracy is unproven.

## Local fallback selection

The project default and CLI/env examples now use `qwen3.5:4b`. Explicit custom model names still take precedence. This is the compatible small local fallback selected for this PC, not a claim that Qwen3.5 is the newest model family overall. The newer Qwen3.8 27B candidate does not fit fully in this PC's 8GB GPU memory; CPU offload would not satisfy the low-latency voice goal. Granite4.2 was evaluated and rejected for tool-agent quality failures despite its faster decoding. Gemini remains the preferred operational voice provider; changing live API priority belongs to runtime configuration.

Defaults verification: Docker runtime-preference, CLI setup, and next-generation settings tests:18 passed. Both local-default regressions failed before replacement. Custom-model preservation test remains passing.
