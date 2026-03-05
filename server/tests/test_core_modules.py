import logging
from queue import Queue

import numpy as np

from src.intent_parser import parse_intent
from src.job_queue import JobQueue
from src.logging_setup import PerformanceLogger
from src.robot_mode import RobotMode
from src.utils import clean_text, clamp
from src.voice_id.embedding_engine import EmbeddingEngine
from src.voice_id.speaker_matcher import SpeakerMatcher, cosine_similarity


class _FakeLLM:
    def __init__(self, outputs):
        self.outputs = outputs

    def chat(self, *args, **kwargs):
        return self.outputs.pop(0)


def test_parse_intent_handles_valid_invalid_and_empty():
    assert parse_intent("[INTENT:sleep] 잘 자요") == ("sleep", "잘 자요")
    assert parse_intent("[INTENT:unknown] 테스트") == ("none", "테스트")
    assert parse_intent("") == ("none", "")


def test_job_queue_drop_oldest_and_reject_modes():
    jq = JobQueue(stt_maxsize=1)
    q = Queue(maxsize=1)
    assert jq.put(q, "old") is True
    assert jq.put(q, "new", drop_oldest=True) is True
    assert q.get_nowait() == "new"

    assert jq.put(q, "first") is True
    assert jq.put(q, "second", drop_oldest=False) is False
    assert q.get_nowait() == "first"


def test_utils_clean_text_and_clamp_behaviour():
    assert clamp(250, 0, 180) == 180
    assert clean_text("안녕,,,,   하세요!!!") == "안녕, 하세요!"
    assert clean_text("..............") == "."


def test_performance_logger_tracks_stats_and_errors(caplog):
    perf = PerformanceLogger()
    perf.log_stt(1.0)
    perf.log_llm(2.0)
    perf.log_tts(3.0)
    perf.log_error()

    stats = perf.get_stats()
    assert stats["stt_avg"] == 1.0
    assert stats["llm_avg"] == 2.0
    assert stats["tts_avg"] == 3.0
    assert stats["errors"] == 1

    with caplog.at_level(logging.INFO):
        perf.print_stats()
    assert "Performance Statistics" in caplog.text


def test_embedding_and_matcher_basic_flow():
    pcm = np.ones(16000, dtype=np.float32) * 0.2
    emb = EmbeddingEngine().extract(pcm)
    assert emb.shape == (16,)

    score = cosine_similarity(emb, emb)
    assert score > 0.99

    matcher = SpeakerMatcher(threshold=0.5)
    user, match_score = matcher.match(emb, {"alice": emb})
    assert user == "alice"
    assert match_score > 0.99


def test_robot_mode_llm_action_and_clamp():
    llm = _FakeLLM([
        "고개 오른쪽으로 돌려",
        '{"action":"SERVO_SET","servo":0,"angle":999}',
    ])
    robot = RobotMode(actions_config=[{"name": "turn", "action": "SERVO_SET", "keywords": ["오른쪽"]}], llm_client=llm)

    refined, action = robot.process_with_llm("오른쪽으로", current_angle=90)

    assert refined == "고개 오른쪽으로 돌려"
    assert action["action"] == "SERVO_SET"
    assert action["angle"] == 180
