from src.memory_manager import MemoryManager


class _FakeLLM:
    def __init__(self):
        self.responses = [
            "## 최근 대화 요약\n사용자가 커피를 좋아한다고 말했다.",
            "[USER]\n- 이름은 민수\n[RELATION]\n- 고양이 이름은 나비\n[LONGTERM]\n- 매주 화요일 회의",
        ]

    def chat(self, *args, **kwargs):
        return self.responses.pop(0)


def test_memory_manager_refresh_updates_md_files(tmp_path):
    (tmp_path / "Soul.md").write_text("# Soul", encoding="utf-8")
    (tmp_path / "User.md").write_text("- (아직 모름)", encoding="utf-8")
    (tmp_path / "Relation.md").write_text("- (아직 모름)", encoding="utf-8")
    (tmp_path / "Longterm_Memory.md").write_text("축적된 기억 없음", encoding="utf-8")
    (tmp_path / "Shortterm_Memory.md").write_text("대화 기록 없음", encoding="utf-8")

    mm = MemoryManager(_FakeLLM(), memory_dir=str(tmp_path), refresh_interval=1)
    history = [{"role": "user", "content": "나는 민수야. 고양이 나비를 키워."}]

    mm.after_turn(history)

    assert "민수" in (tmp_path / "User.md").read_text(encoding="utf-8")
    assert "나비" in (tmp_path / "Relation.md").read_text(encoding="utf-8")
    assert "화요일" in (tmp_path / "Longterm_Memory.md").read_text(encoding="utf-8")
    assert "최근 대화 요약" in (tmp_path / "Shortterm_Memory.md").read_text(encoding="utf-8")


def test_memory_merge_replaces_unknown_and_avoids_duplicates():
    original = "- 이름: (아직 모름)\n"
    merged = MemoryManager._merge_into_md(original, ["- 이름은 민수", "- 이름은 민수"])
    assert "(아직 모름)" not in merged
    assert merged.count("민수") == 1
