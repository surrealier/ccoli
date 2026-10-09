"""Tests for server.py orchestration functions (pure + mock-based)."""
import builtins
import signal
import sys
import unittest.mock as mock

import numpy as np
import yaml


# server.py has heavy top-level imports (STTEngine → faster_whisper).
# We pre-mock the unavailable modules so we can import the pure helpers.
_HEAVY = [
    "faster_whisper",
    "faster_whisper.transcribe",
]
for _m in _HEAVY:
    if _m not in sys.modules:
        sys.modules[_m] = mock.MagicMock()

import server as srv  # noqa: E402  (after mocking)
from src.connection_manager import AutoConnectionManager, ConnectionManager, SerialConnectionManager  # noqa: E402


# ── _normalize_start_command (pure) ──────────────────────────

def test_normalize_string():
    assert srv._normalize_start_command("ollama serve") == ["ollama", "serve"]


def test_normalize_list():
    assert srv._normalize_start_command(["a", "b"]) == ["a", "b"]


def test_normalize_none():
    assert srv._normalize_start_command(None) is None


def test_normalize_empty():
    assert srv._normalize_start_command("") is None


# ── _ollama_health_check ─────────────────────────────────────

def test_health_check_success():
    resp = mock.MagicMock()
    resp.status = 200
    cm = mock.MagicMock()
    cm.__enter__ = mock.Mock(return_value=resp)
    cm.__exit__ = mock.Mock(return_value=False)
    with mock.patch("server.urllib.request.urlopen", return_value=cm):
        assert srv._ollama_health_check("http://localhost:11434") is True


def test_health_check_failure():
    with mock.patch("server.urllib.request.urlopen", side_effect=OSError):
        assert srv._ollama_health_check("http://localhost:11434") is False


# ── ensure_ollama_running ────────────────────────────────────

def test_ensure_already_up():
    with mock.patch("server._ollama_health_check", return_value=True):
        assert srv.ensure_ollama_running("http://localhost:11434", {}) is True


def test_ensure_auto_start_disabled():
    with mock.patch("server._ollama_health_check", return_value=False):
        assert srv.ensure_ollama_running("http://localhost:11434", {"auto_start": False}) is False


def test_start_web_dashboard_returns_local_and_lan_urls():
    with mock.patch.object(srv, "_discover_local_ip_addresses", return_value=["192.168.0.24"]):
        urls = srv._start_web_dashboard(
            {
                "enabled": True,
                "host": "0.0.0.0",
                "port": 8005,
                "auth_token": "",
                "log_tail_lines": 50,
            },
            agent_fn=lambda: None,
            robot_fn=lambda: None,
            mode_fn=lambda: "agent",
            start_web_server_fn=lambda **kwargs: mock.sentinel.thread,
            configure_auth_fn=lambda token: None,
            install_log_handler_fn=lambda max_lines: None,
        )

    assert urls == [
        "http://localhost:8005",
        "http://192.168.0.24:8005",
    ]


def test_start_web_dashboard_skips_optional_dependency_error():
    def _missing(**kwargs):
        raise ModuleNotFoundError("No module named 'uvicorn'", name="uvicorn")

    urls = srv._start_web_dashboard(
        {
            "enabled": True,
            "host": "127.0.0.1",
            "port": 8005,
            "auth_token": "",
            "log_tail_lines": 50,
        },
        agent_fn=lambda: None,
        robot_fn=lambda: None,
        mode_fn=lambda: "agent",
        start_web_server_fn=_missing,
        configure_auth_fn=lambda token: None,
        install_log_handler_fn=lambda max_lines: None,
    )

    assert urls == []


def test_telegram_respond_prefers_runtime_controller():
    runtime_controller = mock.Mock()
    runtime_controller.handle_text_command.return_value = "runtime-updated"
    agent = mock.Mock()

    response = srv._telegram_respond(agent, runtime_controller, "42", "@@우선순위 상태")

    assert response == "runtime-updated"
    agent.generate_response.assert_not_called()


def test_telegram_respond_uses_agent_with_chat_scoped_speaker_id():
    runtime_controller = mock.Mock()
    runtime_controller.handle_text_command.return_value = None
    agent = mock.Mock()
    agent.generate_response.return_value = ("안녕하세요", "chat")

    response = srv._telegram_respond(agent, runtime_controller, "42", "안녕")

    assert response == "안녕하세요"
    agent.generate_response.assert_called_once_with("안녕", speaker_id="telegram:42")


def test_start_telegram_channel_builds_and_starts_worker():
    class _FakeClient:
        def __init__(self, bot_token):
            self.bot_token = bot_token

    class _FakeAdapter:
        def __init__(self, client):
            self.client = client

    class _FakeService:
        def __init__(self, adapter, allowed_chat_ids, min_interval_sec):
            self.adapter = adapter
            self.allowed_chat_ids = allowed_chat_ids
            self.min_interval_sec = min_interval_sec

    class _FakeWorker:
        def __init__(self, client, channel_service, llm_respond, poll_interval_sec, long_poll_timeout_sec):
            self.client = client
            self.channel_service = channel_service
            self.llm_respond = llm_respond
            self.poll_interval_sec = poll_interval_sec
            self.long_poll_timeout_sec = long_poll_timeout_sec
            self.started = False

        def start(self):
            self.started = True
            return True

    runtime_controller = mock.Mock()
    runtime_controller.handle_text_command.return_value = None
    agent = mock.Mock()
    agent.generate_response.return_value = ("응답", "chat")

    worker = srv._start_telegram_channel(
        {
            "enabled": True,
            "bot_token": "123:abc",
            "allowed_chat_ids": ["42", "99"],
            "min_interval_sec": 1.5,
            "poll_interval_sec": 2.0,
            "long_poll_timeout_sec": 15.0,
        },
        agent=agent,
        runtime_controller=runtime_controller,
        client_cls=_FakeClient,
        adapter_cls=_FakeAdapter,
        service_cls=_FakeService,
        worker_cls=_FakeWorker,
    )

    assert worker is not None
    assert worker.started is True
    assert worker.client.bot_token == "123:abc"
    assert worker.channel_service.allowed_chat_ids == {"42", "99"}
    assert worker.channel_service.min_interval_sec == 1.5
    assert worker.poll_interval_sec == 2.0
    assert worker.long_poll_timeout_sec == 15.0
    assert worker.llm_respond("42", "테스트") == "응답"


# ── load_commands_config ─────────────────────────────────────

def test_load_commands_valid(tmp_path):
    p = tmp_path / "cmds.yaml"
    p.write_text(yaml.dump({"commands": [{"name": "nod"}]}))
    srv.load_commands_config(str(p))
    assert srv.ACTIONS_CONFIG == [{"name": "nod"}]


def test_load_commands_missing():
    srv.load_commands_config("/nonexistent/path.yaml")
    assert srv.ACTIONS_CONFIG == []


class _FakeConfig:
    def __init__(self, data):
        self.data = data

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value


def test_build_connection_manager_modes():
    base = {"server": {"host": "127.0.0.1", "port": 5001}, "connection": {"socket_timeout": 0.5}}
    wifi_cfg = _FakeConfig({**base, "connection": {"mode": "wifi", "socket_timeout": 0.5}})
    wired_cfg = _FakeConfig({**base, "connection": {"mode": "wired", "socket_timeout": 0.5}})
    auto_cfg = _FakeConfig({**base, "connection": {"mode": "auto", "socket_timeout": 0.5}})

    assert isinstance(srv.build_connection_manager(wifi_cfg, lambda *_: None), ConnectionManager)
    assert isinstance(srv.build_connection_manager(wired_cfg, lambda *_: None), SerialConnectionManager)
    assert isinstance(srv.build_connection_manager(auto_cfg, lambda *_: None), AutoConnectionManager)


def test_send_connection_greeting_sends_audio_once():
    class _FakeAgent:
        def __init__(self):
            self.greeting_calls = 0
            self.tts_calls = 0
            self.events = []

        def generate_connection_greeting(self):
            self.greeting_calls += 1
            return "콜리 연결됐어요! 아직 일하고 계세요?"

        def text_to_audio(self, text, trim_pad_ms=140.0):
            self.tts_calls += 1
            self.events.append("tts")
            assert "콜리 연결됐어요!" in text
            assert trim_pad_ms == srv.CONNECTION_GREETING_TTS_PAD_MS
            return b"\x00\x01" * 32

    state = {"connection_greeting_sent": False}
    agent = _FakeAgent()

    with (
        mock.patch.object(srv, "current_mode", "agent"),
        mock.patch.object(
            srv,
            "send_action",
            side_effect=lambda *_args, **_kwargs: agent.events.append("cmd") or True,
        ) as send_action,
        mock.patch.object(srv, "send_audio", return_value=True) as send_audio,
    ):
        assert srv._send_connection_greeting(mock.sentinel.conn, mock.sentinel.lock, agent, state) is True
        assert srv._send_connection_greeting(mock.sentinel.conn, mock.sentinel.lock, agent, state) is False

    send_audio.assert_called_once()
    assert send_action.call_args_list == [
        mock.call(mock.sentinel.conn, {"action": "MIC_LOCK"}, mock.sentinel.lock),
        mock.call(mock.sentinel.conn, {"action": "MIC_UNLOCK"}, mock.sentinel.lock),
    ]
    assert agent.events == ["tts", "cmd", "cmd"]
    assert state["connection_greeting_sent"] is True
    assert agent.greeting_calls == 1
    assert agent.tts_calls == 1


def test_send_connection_greeting_skips_when_input_stream_active():
    class _FakeAgent:
        def generate_connection_greeting(self):
            raise AssertionError("should not generate greeting while input is active")

        def text_to_audio(self, _text, trim_pad_ms=140.0):
            raise AssertionError("should not synthesize greeting while input is active")

    gate = srv.InputGate()
    assert gate.start_stream() is True

    with (
        mock.patch.object(srv, "current_mode", "agent"),
        mock.patch.object(srv, "send_action") as send_action,
        mock.patch.object(srv, "send_audio") as send_audio,
    ):
        assert srv._send_connection_greeting(
            mock.sentinel.conn,
            mock.sentinel.lock,
            _FakeAgent(),
            {"connection_greeting_sent": False},
            gate,
        ) is False

    send_action.assert_not_called()
    send_audio.assert_not_called()


def test_send_connection_greeting_waits_for_ready_event():
    class _FakeAgent:
        def generate_connection_greeting(self):
            raise AssertionError("should not generate greeting before handshake")

        def text_to_audio(self, _text, trim_pad_ms=140.0):
            raise AssertionError("should not synthesize greeting before handshake")

    ready = srv.threading.Event()

    with (
        mock.patch.object(srv, "current_mode", "agent"),
        mock.patch.object(srv, "CONNECTION_GREETING_READY_TIMEOUT_S", 0.0),
        mock.patch.object(srv, "send_action") as send_action,
        mock.patch.object(srv, "send_audio") as send_audio,
    ):
        assert srv._send_connection_greeting(
            mock.sentinel.conn,
            mock.sentinel.lock,
            _FakeAgent(),
            {"connection_greeting_sent": False},
            ready_event=ready,
        ) is False

    send_action.assert_not_called()
    send_audio.assert_not_called()


def test_send_connection_greeting_unlocks_when_audio_send_fails():
    class _FakeAgent:
        def generate_connection_greeting(self):
            return "콜리 연결됐어요!"

        def text_to_audio(self, text, trim_pad_ms=140.0):
            assert "콜리 연결됐어요!" in text
            return b"\x00\x01" * 32

    calls = []

    def _record_send_action(conn, action_dict, lock=None):
        calls.append(action_dict)
        return True

    with (
        mock.patch.object(srv, "current_mode", "agent"),
        mock.patch.object(srv, "send_action", side_effect=_record_send_action),
        mock.patch.object(srv, "send_audio", return_value=False),
    ):
        assert srv._send_connection_greeting(
            mock.sentinel.conn,
            mock.sentinel.lock,
            _FakeAgent(),
            {"connection_greeting_sent": False},
        ) is False

    assert calls == [{"action": "MIC_LOCK"}, {"action": "MIC_UNLOCK"}]


def test_send_tts_chunks_locks_once_and_sends_all_audio():
    calls = []

    def _record_send_action(conn, action_dict, lock=None):
        calls.append(action_dict)
        return True

    with (
        mock.patch.object(srv, "send_action", side_effect=_record_send_action),
        mock.patch.object(srv, "send_audio", return_value=True) as send_audio,
    ):
        ok = srv._send_tts_chunks(
            mock.sentinel.conn,
            mock.sentinel.lock,
            [b"\x00\x01" * 8, b"\x00\x01" * 4],
        )

    assert ok is True
    assert calls == [{"action": "MIC_LOCK"}, {"action": "MIC_UNLOCK"}]
    assert send_audio.call_count == 2


def test_send_tts_chunks_skips_before_ready_event():
    ready = srv.threading.Event()

    with (
        mock.patch.object(srv, "send_action") as send_action,
        mock.patch.object(srv, "send_audio") as send_audio,
    ):
        ok = srv._send_tts_chunks(
            mock.sentinel.conn,
            mock.sentinel.lock,
            [b"\x00\x01" * 8],
            ready,
        )

    assert ok is False
    send_action.assert_not_called()
    send_audio.assert_not_called()


def test_send_tts_chunks_unlocks_when_audio_send_fails():
    calls = []

    def _record_send_action(conn, action_dict, lock=None):
        calls.append(action_dict)
        return True

    with (
        mock.patch.object(srv, "send_action", side_effect=_record_send_action),
        mock.patch.object(srv, "send_audio", side_effect=[True, False]),
    ):
        ok = srv._send_tts_chunks(
            mock.sentinel.conn,
            mock.sentinel.lock,
            [b"\x00\x01" * 8, b"\x00\x01" * 4],
        )

    assert ok is False
    assert calls == [{"action": "MIC_LOCK"}, {"action": "MIC_UNLOCK"}]


def test_build_tts_audio_payloads_merges_multiple_chunks():
    calls = []

    class _FakeAgent:
        def prepare_tts_chunks(self, text, max_chunks=3):
            assert text == "응답 본문"
            assert max_chunks == 3
            return ["첫 번째 문장", "두 번째 문장"]

        def text_to_audio(self, text, trim_pad_ms=140.0):
            calls.append((text, trim_pad_ms))
            return text.encode("utf-8")

        def merge_audio_chunks(self, chunks, sr=16000, crossfade_ms=12.0):
            assert sr == 16000
            assert crossfade_ms == 12.0
            assert chunks == ["첫 번째 문장".encode("utf-8"), "두 번째 문장".encode("utf-8")]
            return b"merged-audio"

    payloads = srv._build_tts_audio_payloads(_FakeAgent(), "응답 본문", max_chunks=3)

    assert payloads == [b"merged-audio"]
    assert sorted(calls) == sorted([("첫 번째 문장", srv.TTS_CHUNK_EDGE_PAD_MS), ("두 번째 문장", srv.TTS_CHUNK_EDGE_PAD_MS)])


def test_build_tts_audio_payloads_retries_single_pass_after_chunk_failure():
    calls = []

    class _FakeAgent:
        def prepare_tts_chunks(self, text, max_chunks=3):
            assert text == "응답 본문"
            return ["앞부분", "뒷부분"]

        def text_to_audio(self, text, trim_pad_ms=140.0):
            calls.append((text, trim_pad_ms))
            if text == "앞부분":
                return b"front"
            if text == "뒷부분":
                return b""
            if text == "앞부분 뒷부분":
                return b"fallback"
            raise AssertionError(text)

        def merge_audio_chunks(self, chunks, sr=16000, crossfade_ms=12.0):
            raise AssertionError("merge should not run when chunk fallback is needed")

    payloads = srv._build_tts_audio_payloads(_FakeAgent(), "응답 본문", max_chunks=3)

    assert payloads == [b"fallback"]
    assert sorted(calls[:2]) == sorted([("앞부분", srv.TTS_CHUNK_EDGE_PAD_MS), ("뒷부분", srv.TTS_CHUNK_EDGE_PAD_MS)])
    assert calls[2:] == [("앞부분 뒷부분", srv.TTS_FALLBACK_PAD_MS)]


def test_warm_up_runtime_assets_loads_stt_and_tts():
    class _FakeSTT:
        def __init__(self):
            self.model = None
            self.ensure_calls = 0

        def ensure_model(self):
            self.ensure_calls += 1
            self.model = object()

    class _FakeAgent:
        def __init__(self):
            self.calls = []

        def text_to_audio(self, text, trim_pad_ms=140.0):
            self.calls.append((text, trim_pad_ms))
            return b"\x00\x01" * 16

    stt = _FakeSTT()
    agent = _FakeAgent()

    status = srv._warm_up_runtime_assets(stt, agent)

    assert status == {"stt_ready": True, "tts_ready": True}
    assert stt.ensure_calls == 1
    assert agent.calls == [("준비됐어요.", 0.0)]


def test_prime_connection_sends_initial_pong_for_serial():
    with mock.patch.object(srv, "send_pong", return_value=True) as send_pong:
        assert srv._prime_connection(mock.sentinel.conn, ("serial", "/dev/cu.usbserial-test"), mock.sentinel.lock) is True

    send_pong.assert_called_once_with(mock.sentinel.conn, mock.sentinel.lock)


def test_prime_connection_skips_non_serial_addr():
    with mock.patch.object(srv, "send_pong") as send_pong:
        assert srv._prime_connection(mock.sentinel.conn, ("127.0.0.1", 5001), mock.sentinel.lock) is False

    send_pong.assert_not_called()


def test_start_connection_greeting_spawns_background_thread():
    fake_thread = mock.Mock()
    gate = mock.sentinel.input_gate
    ready = mock.sentinel.ready_event

    with mock.patch.object(srv.threading, "Thread", return_value=fake_thread) as thread_cls:
        result = srv._start_connection_greeting(
            mock.sentinel.conn,
            mock.sentinel.lock,
            mock.sentinel.agent,
            {"connection_greeting_sent": False},
            gate,
            ready,
        )

    assert result is fake_thread
    fake_thread.start.assert_called_once_with()
    thread_cls.assert_called_once()
    _, kwargs = thread_cls.call_args
    assert kwargs["target"] is srv._send_connection_greeting
    assert kwargs["args"] == (
        mock.sentinel.conn,
        mock.sentinel.lock,
        mock.sentinel.agent,
        {"connection_greeting_sent": False},
        gate,
        ready,
    )
    assert kwargs["daemon"] is True
    assert kwargs["name"] == "connection-greeting"


def test_build_interrupt_handler_prints_stats_and_raises():
    perf = mock.Mock()
    handler = srv._build_interrupt_handler(perf)

    with mock.patch.object(builtins, "__import__") as import_mock:
        fake_logger = mock.Mock()
        import_mock.return_value.getLogger.return_value = fake_logger
        try:
            handler(signal.SIGINT, None)
        except KeyboardInterrupt:
            pass
        else:
            assert False, "KeyboardInterrupt expected"

    perf.print_stats.assert_called_once()
    fake_logger.info.assert_called()


def test_voice_latency_uses_monotonic_clock_and_existing_metrics(caplog):
    recorder = mock.Mock()
    with mock.patch.object(srv.time, "perf_counter", return_value=12.345), mock.patch.object(srv.time, "time", return_value=900000.0):
        with caplog.at_level("INFO", logger="server"):
            srv._log_voice_latency("stt", 7, 10.0, recorder)
    recorder.assert_called_once()
    assert abs(recorder.call_args.args[0] - 2.345) < 0.000001
    assert "VOICE_LATENCY sid=7 stage=stt duration_ms=2345.0" in caplog.text


def test_send_tts_records_time_to_send_only_after_handshake_and_mic_lock(caplog):
    ready = __import__("threading").Event()
    ready.set()
    with mock.patch.object(srv, "send_action", return_value=True), mock.patch.object(srv, "send_audio", return_value=True) as audio, mock.patch.object(srv.time, "perf_counter", return_value=8.0):
        with caplog.at_level("INFO", logger="server"):
            assert srv._send_tts_chunks(object(), mock.Mock(), [b"pcm"], ready, turn_started=3.0, sid=4)
    audio.assert_called_once()
    assert "stage=end_to_send duration_ms=5000.0" in caplog.text
    caplog.clear()
    ready.clear()
    with caplog.at_level("INFO", logger="server"):
        assert not srv._send_tts_chunks(object(), mock.Mock(), [b"pcm"], ready, turn_started=3.0, sid=4)
    assert "VOICE_LATENCY" not in caplog.text


def test_tts_chunks_run_concurrently_but_merge_in_original_order():
    import threading
    barrier = threading.Barrier(3)
    last_finished = threading.Event()
    seen = {}

    class Agent:
        def prepare_tts_chunks(self, text, max_chunks=3):
            return ['first', 'middle', 'last']

        def text_to_audio(self, text, trim_pad_ms):
            seen[text] = trim_pad_ms
            barrier.wait(timeout=5)
            if text == 'last':
                last_finished.set()
            else:
                assert last_finished.wait(timeout=5)
            return text.encode()

        def merge_audio_chunks(self, chunks, **kwargs):
            assert chunks == [b'first', b'middle', b'last']
            return b'merged'

    assert srv._build_tts_audio_payloads(Agent(), 'response') == [b'merged']
    assert seen == {'first': srv.TTS_CHUNK_EDGE_PAD_MS,
                    'middle': srv.TTS_CHUNK_MIDDLE_PAD_MS,
                    'last': srv.TTS_CHUNK_EDGE_PAD_MS}


def test_parallel_tts_failure_waits_for_chunks_and_closes_worker_loops():
    import asyncio
    import threading
    barrier = threading.Barrier(3)
    completed = set()
    loops = []
    lock = threading.Lock()

    class Agent:
        def prepare_tts_chunks(self, text, max_chunks=3):
            return ['one', 'two', 'three']

        def text_to_audio(self, text, trim_pad_ms):
            if text == 'one two three':
                assert completed == {'one', 'two', 'three'}
                assert all(loop.is_closed() for loop in loops)
                return b'fallback'
            with lock:
                loops.append(asyncio.get_event_loop())
            barrier.wait(timeout=5)
            with lock:
                completed.add(text)
            return b'' if text == 'two' else text.encode()

        def merge_audio_chunks(self, chunks, **kwargs):
            raise AssertionError('failed chunks must use full-text fallback')

    assert srv._build_tts_audio_payloads(Agent(), 'response') == [b'fallback']
    assert len({id(loop) for loop in loops}) == 3


def test_parallel_tts_exception_falls_back_without_logging_private_text(caplog):
    class Agent:
        def prepare_tts_chunks(self, text, max_chunks=3):
            return ['private first', 'private middle', 'private last']

        def text_to_audio(self, text, trim_pad_ms):
            if text == 'private middle':
                raise RuntimeError('private middle')
            if text == 'private first private middle private last':
                return b'fallback'
            return text.encode()

        def merge_audio_chunks(self, chunks, **kwargs):
            raise AssertionError('failed chunk must trigger a full-text fallback')

    with caplog.at_level('INFO', logger='server'):
        assert srv._build_tts_audio_payloads(Agent(), 'request') == [b'fallback']
    assert 'private' not in caplog.text

def test_tts_partial_chunks_are_not_played_when_full_fallback_fails(caplog):
    class Agent:
        def prepare_tts_chunks(self, text, max_chunks=3):
            return ["첫 문장", "둘째 문장"]

        def text_to_audio(self, text, trim_pad_ms):
            return b"first-pcm" if text == "첫 문장" else b""

        def merge_audio_chunks(self, chunks, **kwargs):
            raise AssertionError("partial audio must not be merged")

    with caplog.at_level("WARNING", logger="server"):
        payloads = srv._build_tts_audio_payloads(Agent(), "전체 응답")
    assert payloads == []
    assert "incomplete TTS" in caplog.text

def test_voice_rejection_diagnostics_are_bounded_and_private(caplog):
    assert srv._voice_rejection_reason(0.44) == "too_short"
    assert srv._voice_rejection_reason(0.68, -46.0) == "too_quiet"
    assert srv._voice_rejection_reason(0.68, -44.0) is None
    with caplog.at_level("INFO", logger="server"):
        srv._log_voice_rejection(2, "too_quiet", 0.68, rms_db=-46.0)
    assert "VOICE_INPUT sid=2 status=filtered reason=too_quiet" in caplog.text
    assert "duration_ms=680.0 rms_db=-46.0" in caplog.text
    assert "payload" not in caplog.text


def test_long_quiet_capture_with_sustained_local_voice_is_not_rejected():
    pcm = np.zeros(srv.SR * 8, dtype=np.float32)
    pcm[2 * srv.SR : 2 * srv.SR + srv.SR // 2] = 0.01
    rms_db = 20 * np.log10(np.sqrt(np.mean(pcm * pcm)))
    assert rms_db < -45.0
    assert srv._voice_rejection_reason(8.0, rms_db, pcm) is None


def test_continuous_quiet_capture_stays_filtered():
    pcm = np.full(srv.SR * 8, 0.002, dtype=np.float32)
    assert srv._voice_rejection_reason(8.0, -54.0, pcm) == "too_quiet"


def test_one_loud_window_is_not_treated_as_sustained_voice():
    pcm = np.zeros(srv.SR * 8, dtype=np.float32)
    pcm[2 * srv.SR : 2 * srv.SR + srv.SR // 10] = 0.02
    rms_db = 20 * np.log10(np.sqrt(np.mean(pcm * pcm)))
    assert rms_db < -45.0
    assert srv._voice_rejection_reason(8.0, rms_db, pcm) == "too_quiet"


def test_sustained_voice_crossing_window_boundary_is_not_rejected():
    pcm = np.zeros(srv.SR * 8, dtype=np.float32)
    pcm[int(0.005 * srv.SR) : int(0.215 * srv.SR)] = 0.006
    rms_db = 20 * np.log10(np.sqrt(np.mean(pcm * pcm)))
    assert rms_db < -45.0
    assert srv._voice_rejection_reason(8.0, rms_db, pcm) is None

def test_quiet_speech_with_brief_low_energy_closures_is_not_rejected():
    pcm = np.zeros(srv.SR * 8, dtype=np.float32)
    for offset in range(0, 25, 5):
        start = (srv.SR // 50) * offset
        pcm[start : start + (srv.SR // 50) * 4] = 0.01
    rms_db = 20 * np.log10(np.sqrt(np.mean(pcm * pcm)))
    assert rms_db < -45.0
    assert srv._voice_rejection_reason(8.0, rms_db, pcm) is None

def test_home_setup_activation_changes_actual_tool_client_without_disclosing_token(tmp_path):
    import threading
    from types import SimpleNamespace
    from src.integrations.home_assistant import HomeAssistantIntegration
    home=HomeAssistantIntegration('http://home.local:8123','synthetic-private-token',['light.desk'])
    tool=SimpleNamespace(home=home,_home_turn_lock=threading.RLock())
    agent=SimpleNamespace(tool_agent=tool)
    service=srv._attach_home_setup(agent,tmp_path/'private-home.json')
    assert service is agent.home_setup_service
    assert service.status()['active'] is True
    assert 'synthetic-private-token' not in str(service.status())
    service.disconnect()
    assert tool.home is None


def test_home_setup_does_not_claim_activation_without_tool_runtime(tmp_path):
    from types import SimpleNamespace
    from src.integrations.home_assistant_setup import HomeSetupError
    import pytest
    agent=SimpleNamespace(tool_agent=None)
    service=srv._attach_home_setup(agent,tmp_path/'private-home.json')
    assert service.status()['active'] is False
    with pytest.raises(HomeSetupError):
        service._apply_home(object())
