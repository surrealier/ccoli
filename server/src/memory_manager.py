"""
MemoryManager — 구조화된 md 파일 기반 메모리 시스템
- Soul/User/Shortterm/Longterm/Relation md 파일 로드·저장
- LLM 기반 메모리 추출 (대화 → 구조화된 기억)
- 주기적 자동 refresh
"""
import logging
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

# md 파일 이름 목록
_FILES = ("Soul.md", "User.md", "Shortterm_Memory.md", "Longterm_Memory.md", "Relation.md")

# ── LLM 메모리 추출 프롬프트 ──────────────────────────────────
_EXTRACT_PROMPT = """\
아래는 사용자와 AI 홈 에이전트 '콜리'의 최근 대화이다.
대화에서 아래 카테고리에 해당하는 새로운 정보가 있으면 추출하라.
정보가 없는 카테고리는 빈 칸으로 두어라. 기존 정보와 중복되면 생략하라.

카테고리:
[USER] 사용자 개인정보 (이름, 나이, 직업, 취미, 거주지, 선호, 습관 등)
[RELATION] 사용자의 인간관계 (가족, 친구, 연인, 동료, 반려동물 이름/특징)
[LONGTERM] 장기 기억할 사항 (중요 약속, 반복 언급 주제, 사용자가 강조한 것)
[SHORTTERM] 현재 대화 요약 (한두 문장), 사용자의 현재 기분/상태

기존 메모리:
{existing}

최근 대화:
{conversation}

형식 — 해당 카테고리 태그 뒤에 한 줄씩 작성. 새 정보가 없으면 태그 자체를 생략.
"""

# ── 단기 기억 요약 프롬프트 ────────────────────────────────────
_SUMMARIZE_SHORT_PROMPT = """\
아래 대화 내용을 3문장 이내로 요약하라. 현재 대화 주제와 사용자의 기분/상태도 한 줄씩 적어라.

대화:
{conversation}

형식:
## 최근 대화 요약
(요약)

## 현재 대화 주제
(주제)

## 사용자의 현재 상태/기분
(상태)
"""


class MemoryManager:
    def __init__(self, llm_client, memory_dir: str = None, refresh_interval: int = 5):
        """
        Args:
            llm_client: LLMClient 인스턴스
            memory_dir: md 파일 디렉토리 경로
            refresh_interval: N번 대화마다 자동 refresh
        """
        self.llm = llm_client
        self.memory_dir = Path(memory_dir or Path(__file__).resolve().parent.parent / "memory")
        self.memory_dir.mkdir(exist_ok=True)
        self.refresh_interval = refresh_interval
        self._turn_count = 0
        self._last_refresh = time.time()

        # 메모리 캐시 (파일 → 내용)
        self._cache: dict[str, str] = {}
        self._load_all()

    # ── 파일 I/O ──────────────────────────────────────────────

    def _load_all(self):
        for name in _FILES:
            path = self.memory_dir / name
            if path.exists():
                self._cache[name] = path.read_text(encoding="utf-8")
            else:
                self._cache[name] = ""
        log.info("Memory loaded from %s (%d files)", self.memory_dir, len(self._cache))

    def _save(self, name: str, content: str):
        (self.memory_dir / name).write_text(content, encoding="utf-8")
        self._cache[name] = content

    # ── 시스템 프롬프트 조립 ──────────────────────────────────

    def build_system_prompt(self) -> str:
        """Soul + User + Memory 를 하나의 시스템 프롬프트로 조립"""
        soul = self._cache.get("Soul.md", "")
        user = self._cache.get("User.md", "")
        short = self._cache.get("Shortterm_Memory.md", "")
        long = self._cache.get("Longterm_Memory.md", "")
        rel = self._cache.get("Relation.md", "")

        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")

        parts = [
            soul,
            f"\n---\n현재 시각: {now}",
            f"\n---\n{user}" if "(아직 모름)" not in user or user.count("(아직 모름)") < user.count("\n") else "",
            f"\n---\n{rel}" if "(아직 모름)" not in rel or rel.count("(아직 모름)") < rel.count("\n") else "",
            f"\n---\n{long}" if "축적된 기억 없음" not in long else "",
            f"\n---\n{short}" if "대화 기록 없음" not in short else "",
        ]
        return "\n".join(p for p in parts if p)

    # ── 대화 후 메모리 갱신 ───────────────────────────────────

    def after_turn(self, conversation_history: list):
        """매 대화 턴 후 호출. refresh_interval마다 자동 갱신."""
        self._turn_count += 1
        if self._turn_count % self.refresh_interval == 0:
            self.refresh(conversation_history)

    def refresh(self, conversation_history: list):
        """LLM을 사용해 대화에서 메모리를 추출하고 md 파일에 반영"""
        if not conversation_history:
            return
        try:
            recent = conversation_history[-20:]
            conv_text = "\n".join(
                f"{'사용자' if m['role']=='user' else '콜리'}: {m['content']}"
                for m in recent if m.get("content")
            )
            self._update_shortterm(conv_text)
            self._extract_and_merge(conv_text)
            self._last_refresh = time.time()
            log.info("Memory refreshed (turn %d)", self._turn_count)
        except Exception as exc:
            log.error("Memory refresh failed: %s", exc)

    def _update_shortterm(self, conv_text: str):
        """단기 기억 요약 갱신"""
        prompt = _SUMMARIZE_SHORT_PROMPT.format(conversation=conv_text[-2000:])
        result = self.llm.chat(
            [{"role": "system", "content": "너는 대화 요약 도우미다. 지시대로만 출력하라."},
             {"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=300,
            think=False,
        )
        if result.strip():
            header = "# Shortterm Memory — 단기 기억\n\n"
            self._save("Shortterm_Memory.md", header + result.strip())

    def _extract_and_merge(self, conv_text: str):
        """LLM으로 User/Relation/Longterm 정보 추출 후 기존 md에 병합"""
        existing = (
            f"[USER 기존]\n{self._cache.get('User.md','')}\n"
            f"[RELATION 기존]\n{self._cache.get('Relation.md','')}\n"
            f"[LONGTERM 기존]\n{self._cache.get('Longterm_Memory.md','')}"
        )
        prompt = _EXTRACT_PROMPT.format(existing=existing, conversation=conv_text[-2000:])
        result = self.llm.chat(
            [{"role": "system", "content": "너는 정보 추출 도우미다. 지시된 형식으로만 출력하라."},
             {"role": "user", "content": prompt}],
            temperature=0.2, max_tokens=500,
            think=False,
        )
        if not result.strip():
            return

        # 태그별 파싱 및 병합
        sections = {"[USER]": "User.md", "[RELATION]": "Relation.md", "[LONGTERM]": "Longterm_Memory.md"}
        current_tag = None
        lines_by_tag: dict[str, list[str]] = {t: [] for t in sections}

        for line in result.strip().splitlines():
            stripped = line.strip()
            if stripped in sections:
                current_tag = stripped
            elif current_tag and stripped and stripped != "-":
                lines_by_tag[current_tag].append(stripped)

        for tag, filename in sections.items():
            new_lines = lines_by_tag[tag]
            if not new_lines:
                continue
            old = self._cache.get(filename, "")
            merged = self._merge_into_md(old, new_lines)
            if merged != old:
                self._save(filename, merged)
                log.info("Updated %s (+%d lines)", filename, len(new_lines))

    @staticmethod
    def _merge_into_md(old_content: str, new_lines: list[str]) -> str:
        """기존 md 내용에 새 정보를 중복 없이 추가"""
        old_lower = old_content.lower()
        additions = []
        seen = set()
        for line in new_lines:
            # (아직 모름) 자리를 대체하거나, 중복이 아니면 추가
            core = line.lstrip("- ").strip()
            core_lower = core.lower()
            if core and core_lower not in old_lower and core_lower not in seen:
                additions.append(f"- {core}")
                seen.add(core_lower)

        if not additions:
            return old_content

        # "(아직 모름)" 이 있는 첫 번째 섹션 끝에 삽입
        marker = "(아직 모름)"
        if marker in old_content:
            # 첫 번째 (아직 모름)을 새 정보로 교체
            idx = old_content.index(marker)
            return old_content[:idx] + "\n".join(additions) + old_content[idx + len(marker):]

        # 마지막 줄 뒤에 추가
        return old_content.rstrip() + "\n" + "\n".join(additions) + "\n"
