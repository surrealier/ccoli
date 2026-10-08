"""
Main ESP32 voice streaming server module
- Receives voice data from ESP32 and performs STT
- Supports robot mode and agent mode
- Sends commands and voice responses over TCP socket communication
"""
import logging
import os
import signal
import socket
import threading
import time
import subprocess
import shlex
import urllib.parse
import urllib.request
from pathlib import Path
from queue import Empty
from concurrent.futures import ThreadPoolExecutor
import asyncio
from typing import Callable

import numpy as np
import yaml

from config_loader import get_config
from emotion_system import EmotionSystem
from src.agent_mode import AgentMode
from src.audio_processor import normalize_to_dbfs, qc, save_wav, trim_energy
from src.channels import TelegramBotAdapter, TelegramBotClient, TelegramChannelService, TelegramPollingWorker
from src.connection_manager import build_connection_manager
from src.input_gate import InputGate
from src.job_queue import JobQueue
from src.llm_client import PriorityLLMClient
from src.logging_setup import get_performance_logger, setup_logging
from src.protocol import (
    PTYPE_AUDIO,
    PTYPE_END,
    PTYPE_PING,
    PTYPE_START,
    recv_packet,
    send_action,
    send_audio,
    send_pong,
)
from src.robot_mode import RobotMode
from src.runtime_controller import RuntimeController
from src.stt_engine import STTEngine
from src.voice_id import VoiceIDService
from src.utils import clean_text

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


# Audio processing constants
SR = 16000
UNSURE_POLICY = "NOOP"
CONNECTION_GREETING_TTS_PAD_MS = 180.0
CONNECTION_GREETING_READY_TIMEOUT_S = 3.0
TTS_CHUNK_EDGE_PAD_MS = 180.0
TTS_CHUNK_MIDDLE_PAD_MS = 60.0
TTS_FALLBACK_PAD_MS = 180.0

ACTIONS_CONFIG = []
current_mode = "agent"  # Default mode: agent

# Mode handler instances
robot_handler = None
agent_handler = None
_OPTIONAL_WEB_MODULES = {"uvicorn", "fastapi", "starlette", "pydantic"}


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _describe_connection_addr(addr) -> tuple[str | None, str | None]:
    if isinstance(addr, tuple) and len(addr) >= 2:
        if addr[0] == "serial":
            return "wired", str(addr[1])
        host = str(addr[0])
        port = addr[1]
        return "wifi", f"{host}:{port}"
    return None, None


def _make_dashboard_runtime_state() -> dict:
    return {
        "connection_greeting_sent": False,
        "warmup": {
            "stt_ready": False,
            "tts_ready": False,
        },
        "connection": {
            "connected": False,
            "current_transport": None,
            "current_endpoint": None,
            "last_transport": None,
            "last_endpoint": None,
            "last_connected_at": None,
            "last_disconnected_at": None,
        },
        "last_checks": {},
    }


def _set_dashboard_warmup_state(runtime_state: dict | None, warmup_status: dict) -> None:
    if runtime_state is None:
        return
    runtime_state["warmup"] = {
        "stt_ready": bool(warmup_status.get("stt_ready", False)),
        "tts_ready": bool(warmup_status.get("tts_ready", False)),
        "updated_at": _utc_now_iso(),
    }


def _set_dashboard_connection_state(
    runtime_state: dict | None,
    *,
    connected: bool,
    addr=None,
) -> None:
    if runtime_state is None:
        return

    connection = runtime_state.setdefault("connection", {})
    connection["connected"] = bool(connected)
    if connected:
        transport, endpoint = _describe_connection_addr(addr)
        connection["current_transport"] = transport
        connection["current_endpoint"] = endpoint
        connection["last_transport"] = transport
        connection["last_endpoint"] = endpoint
        connection["last_connected_at"] = _utc_now_iso()
    else:
        connection["current_transport"] = None
        connection["current_endpoint"] = None
        connection["last_disconnected_at"] = _utc_now_iso()


def _build_interrupt_handler(perf_logger):
    def _handler(signum, _frame):
        log = __import__("logging").getLogger("server")
        try:
            sig_name = signal.Signals(signum).name
        except Exception:
            sig_name = str(signum)

        log.info("Shutdown requested via %s", sig_name)
        try:
            perf_logger.print_stats()
        finally:
            raise KeyboardInterrupt

    return _handler


def load_commands_config(path: str = "commands.yaml"):
    global ACTIONS_CONFIG
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            ACTIONS_CONFIG = data.get("commands", [])
    except Exception:
        ACTIONS_CONFIG = []


def _discover_local_ip_addresses() -> list[str]:
    addresses: list[str] = []

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 80))
            candidate = sock.getsockname()[0]
            if candidate and not candidate.startswith("127."):
                addresses.append(candidate)
    except OSError:
        pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, family=socket.AF_INET):
            candidate = info[4][0]
            if candidate and not candidate.startswith("127.") and candidate not in addresses:
                addresses.append(candidate)
    except OSError:
        pass

    return addresses


def _build_dashboard_urls(host: str, port: int) -> list[str]:
    normalized_host = str(host or "").strip().lower()
    display_hosts: list[str] = []

    if normalized_host in {"", "0.0.0.0", "::"}:
        display_hosts.append("localhost")
        display_hosts.extend(_discover_local_ip_addresses())
    elif normalized_host in {"127.0.0.1", "localhost"}:
        display_hosts.append("localhost")
    else:
        display_hosts.append(str(host).strip())

    urls: list[str] = []
    for item in display_hosts:
        formatted_host = item
        if ":" in formatted_host and not formatted_host.startswith("["):
            formatted_host = f"[{formatted_host}]"
        url = f"http://{formatted_host}:{int(port)}"
        if url not in urls:
            urls.append(url)
    return urls


def _runtime_install_hint() -> str:
    return "Run `ccoli setup` or `python3 -m pip install -e .[runtime]` from the repo root."


def _is_optional_web_dependency_error(exc: ModuleNotFoundError) -> bool:
    return (getattr(exc, "name", "") or "") in _OPTIONAL_WEB_MODULES


def _telegram_respond(agent, runtime_controller, chat_id: str, text: str) -> str:
    runtime_response = runtime_controller.handle_text_command(text) if runtime_controller is not None else None
    if runtime_response:
        return runtime_response

    response, _intent = agent.generate_response(text, speaker_id=f"telegram:{chat_id}")
    return response


def _start_telegram_channel(
    telegram_cfg: dict,
    *,
    agent,
    runtime_controller,
    client_cls=TelegramBotClient,
    adapter_cls=TelegramBotAdapter,
    service_cls=TelegramChannelService,
    worker_cls=TelegramPollingWorker,
):
    enabled = bool(telegram_cfg.get("enabled", False))
    if not enabled:
        return None

    log = logging.getLogger("server")
    bot_token = str(telegram_cfg.get("bot_token", "") or "").strip()
    if not bot_token:
        log.warning("Telegram channel enabled but TELEGRAM_BOT_TOKEN is missing; skipping startup.")
        return None

    allowed_chat_ids = {
        str(chat_id).strip()
        for chat_id in telegram_cfg.get("allowed_chat_ids", [])
        if str(chat_id).strip()
    }

    client = client_cls(bot_token=bot_token)
    adapter = adapter_cls(client)
    service = service_cls(
        adapter=adapter,
        allowed_chat_ids=allowed_chat_ids,
        min_interval_sec=float(telegram_cfg.get("min_interval_sec", 0.5) or 0.5),
    )
    worker = worker_cls(
        client=client,
        channel_service=service,
        llm_respond=lambda chat_id, text: _telegram_respond(agent, runtime_controller, chat_id, text),
        poll_interval_sec=float(telegram_cfg.get("poll_interval_sec", 1.0) or 1.0),
        long_poll_timeout_sec=float(telegram_cfg.get("long_poll_timeout_sec", 20.0) or 20.0),
    )
    worker.start()

    allow_list_label = str(len(allowed_chat_ids)) if allowed_chat_ids else "all"
    log.info("Telegram channel started (allow-list=%s, poll=%.1fs)", allow_list_label, worker.poll_interval_sec)
    return worker


def _start_web_dashboard(
    web_cfg: dict,
    *,
    agent_fn,
    robot_fn,
    mode_fn,
    dashboard_state_fn=None,
    start_web_server_fn=None,
    configure_auth_fn=None,
    install_log_handler_fn=None,
) -> list[str]:
    if not web_cfg.get("enabled", True):
        return []

    log = logging.getLogger("server")

    try:
        if start_web_server_fn is None:
            from web import start_web_server as start_web_server_fn
        if configure_auth_fn is None:
            from web.auth import configure as configure_auth_fn
        if install_log_handler_fn is None:
            from web.log_handler import install as install_log_handler_fn

        install_log_handler_fn(max_lines=int(web_cfg.get("log_tail_lines", 200)))
        configure_auth_fn(web_cfg.get("auth_token", "") or "")
        start_web_server_fn(
            agent_fn=agent_fn,
            robot_fn=robot_fn,
            mode_fn=mode_fn,
            dashboard_state_fn=dashboard_state_fn,
            host=web_cfg.get("host", "0.0.0.0"),
            port=int(web_cfg.get("port", 8005)),
        )
    except ModuleNotFoundError as exc:
        if _is_optional_web_dependency_error(exc):
            log.warning(
                "Web dashboard disabled because optional dependency `%s` is not installed.",
                exc.name,
            )
            log.warning(_runtime_install_hint())
            return []
        raise

    return _build_dashboard_urls(
        web_cfg.get("host", "0.0.0.0"),
        int(web_cfg.get("port", 8005)),
    )


def _ollama_health_check(base_url: str, timeout: float = 1.0) -> bool:
    try:
        parsed = urllib.parse.urlparse(base_url)
        scheme = parsed.scheme or "http"
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if scheme == "https" else 80)
        path = parsed.path.rstrip("/")
        url = f"{scheme}://{host}:{port}{path}/api/tags"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def _normalize_start_command(start_command):
    if not start_command:
        return None
    if isinstance(start_command, (list, tuple)):
        return [str(part) for part in start_command]
    if isinstance(start_command, str):
        return shlex.split(start_command, posix=False)
    return None


def ensure_ollama_running(base_url: str, llm_config: dict):
    log = logging.getLogger("server")
    if _ollama_health_check(base_url):
        log.info("Ollama already running at %s", base_url)
        return True

    auto_start = llm_config.get("auto_start", True)
    if not auto_start:
        log.warning("Ollama not detected at %s (auto_start disabled)", base_url)
        return False

    start_command = _normalize_start_command(llm_config.get("start_command", "ollama serve"))
    if not start_command:
        log.warning("Ollama not detected at %s (no start command configured)", base_url)
        return False

    log.warning("Ollama not detected at %s. Starting: %s", base_url, " ".join(start_command))
    try:
        subprocess.Popen(
            start_command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    except Exception as exc:
        log.error("Failed to start Ollama: %s", exc)
        return False

    startup_timeout = float(llm_config.get("startup_timeout", 10.0))
    deadline = time.time() + startup_timeout
    while time.time() < deadline:
        if _ollama_health_check(base_url, timeout=1.0):
            log.info("Ollama is up at %s", base_url)
            return True
        time.sleep(0.5)

    log.warning("Ollama did not become ready within %.1fs", startup_timeout)
    return False


def _send_connection_greeting(
    conn,
    send_lock: threading.Lock,
    agent,
    runtime_state: dict | None = None,
    input_gate: InputGate | None = None,
    ready_event: threading.Event | None = None,
) -> bool:
    log = __import__("logging").getLogger("server")

    if current_mode != "agent" or agent is None:
        return False

    if ready_event is not None and not ready_event.wait(CONNECTION_GREETING_READY_TIMEOUT_S):
        log.info("Skipping connection greeting until device handshake is ready")
        return False

    if runtime_state is not None and runtime_state.get("connection_greeting_sent"):
        return False

    if input_gate is not None and (input_gate.has_active_stream() or input_gate.is_busy()):
        log.info("Skipping connection greeting while input stream is active")
        return False

    greeting = agent.generate_connection_greeting()
    if not greeting:
        return False

    wav_bytes = agent.text_to_audio(greeting, trim_pad_ms=CONNECTION_GREETING_TTS_PAD_MS)
    if not wav_bytes:
        log.warning("Connection greeting TTS generation returned empty audio")
        return False

    if input_gate is not None and (input_gate.has_active_stream() or input_gate.is_busy()):
        log.info("Dropping connection greeting because input stream became active")
        return False

    lock_sent = send_action(conn, {"action": "MIC_LOCK"}, send_lock)
    if not lock_sent:
        log.warning("Failed to lock mic before connection greeting")
        return False

    ok = send_audio(conn, wav_bytes, send_lock)
    if ok:
        if runtime_state is not None:
            runtime_state["connection_greeting_sent"] = True
        log.info("Connection greeting sent")
        if not send_action(conn, {"action": "MIC_UNLOCK"}, send_lock):
            log.warning("Failed to unlock mic after connection greeting")
    else:
        log.warning("Failed to send connection greeting audio")
        send_action(conn, {"action": "MIC_UNLOCK"}, send_lock)
    return ok


def _prime_connection(conn, addr, send_lock: threading.Lock) -> bool:
    log = __import__("logging").getLogger("server")

    if not (isinstance(addr, tuple) and len(addr) >= 2 and addr[0] == "serial"):
        return False

    ok = send_pong(conn, send_lock)
    if ok:
        log.info("Primed wired serial link on %s with initial PONG", addr[1])
    else:
        log.warning("Failed to prime wired serial link on %s", addr[1])
    return ok


def _start_connection_greeting(
    conn,
    send_lock: threading.Lock,
    agent,
    runtime_state: dict | None = None,
    input_gate: InputGate | None = None,
    ready_event: threading.Event | None = None,
):
    thread = threading.Thread(
        target=_send_connection_greeting,
        args=(conn, send_lock, agent, runtime_state, input_gate, ready_event),
        daemon=True,
        name="connection-greeting",
    )
    thread.start()
    return thread


def _log_voice_latency(
    stage: str, sid: int, started: float, recorder: Callable[[float], None] | None = None
) -> None:
    """Record elapsed time without including speech, model output, or credentials."""
    duration = time.perf_counter() - started
    if recorder is not None:
        recorder(duration)
    logging.getLogger("server").info(
        "VOICE_LATENCY sid=%s stage=%s duration_ms=%.1f", sid, stage, duration * 1000.0
    )


def _has_sustained_voice_energy(pcm: np.ndarray) -> bool:
    """Allow brief quiet gaps within a local 240 ms voice interval."""
    window_samples = SR // 50
    threshold_power = 10 ** (-45.0 / 10.0)
    active_windows: list[bool] = []
    for offset in range(0, len(pcm) - window_samples + 1, window_samples):
        window = pcm[offset : offset + window_samples]
        active_windows.append(float(np.mean(window * window)) >= threshold_power)
        if len(active_windows) >= 12 and sum(active_windows[-12:]) >= 9:
            return True
    return False


def _voice_rejection_reason(
    duration_s: float, rms_db: float | None = None, pcm: np.ndarray | None = None
) -> str | None:
    """Classify a pre-STT filter without retaining the captured audio."""
    if duration_s < 0.45:
        return "too_short"
    if rms_db is not None and rms_db < -45.0:
        if pcm is None or not _has_sustained_voice_energy(pcm):
            return "too_quiet"
    return None


def _log_voice_rejection(sid: int, reason: str, duration_s: float, rms_db: float | None = None) -> None:
    """Log only numeric input diagnostics and a fixed reason code."""
    log = logging.getLogger("server")
    if rms_db is None:
        log.info("VOICE_INPUT sid=%s status=filtered reason=%s duration_ms=%.1f", sid, reason, duration_s * 1000.0)
    else:
        log.info("VOICE_INPUT sid=%s status=filtered reason=%s duration_ms=%.1f rms_db=%.1f", sid, reason, duration_s * 1000.0, rms_db)


def _send_tts_chunks(
    conn,
    send_lock: threading.Lock,
    audio_payloads: list[bytes],
    ready_event: threading.Event | None = None,
    *,
    turn_started: float | None = None,
    sid: int = 0,
) -> bool:
    log = __import__("logging").getLogger("server")

    payloads = [chunk for chunk in audio_payloads if chunk]
    if not payloads:
        return False

    if ready_event is not None and not ready_event.is_set():
        log.warning("Skipping TTS playback because device handshake is not ready")
        return False

    lock_sent = send_action(conn, {"action": "MIC_LOCK"}, send_lock)
    if not lock_sent:
        log.warning("Failed to lock mic before TTS playback")
        return False

    total_audio_chunks = len(payloads)
    for idx, chunk_bytes in enumerate(payloads, start=1):
        if total_audio_chunks > 1:
            log.info(
                "Sending audio chunk %d/%d: %d bytes",
                idx,
                total_audio_chunks,
                len(chunk_bytes),
            )
        if idx == 1 and turn_started is not None:
            _log_voice_latency("end_to_send", sid, turn_started)
        ok = send_audio(conn, chunk_bytes, send_lock)
        if not ok:
            log.warning("Failed to send audio chunk %d/%d", idx, total_audio_chunks)
            send_action(conn, {"action": "MIC_UNLOCK"}, send_lock)
            return False

    if not send_action(conn, {"action": "MIC_UNLOCK"}, send_lock):
        log.warning("Failed to unlock mic after TTS playback")
    return True


def _build_tts_audio_payloads(agent, response_text: str, max_chunks: int = 3) -> list[bytes]:
    log = __import__("logging").getLogger("server")

    tts_text_chunks = agent.prepare_tts_chunks(response_text, max_chunks=max_chunks)
    if not tts_text_chunks:
        log.error("TTS text chunks are empty after sanitization")
        return []

    if len(tts_text_chunks) > 1:
        log.info("TTS text split into %d chunks", len(tts_text_chunks))

    audio_chunks = []
    total_chunks = len(tts_text_chunks)
    failed_chunks = []

    def synthesize(item: tuple[int, str]) -> bytes:
        idx, tts_text = item
        trim_pad_ms = (
            TTS_CHUNK_MIDDLE_PAD_MS
            if 1 < idx < total_chunks
            else TTS_CHUNK_EDGE_PAD_MS
        )
        # Each pool worker owns its event loop; text_to_audio uses thread-local
        # loops and unique temporary files. Close loops before workers exit.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            try:
                return agent.text_to_audio(tts_text, trim_pad_ms=trim_pad_ms)
            except Exception as exc:
                log.error("TTS chunk raised %s (%d/%d)", type(exc).__name__, idx, total_chunks)
                return b""
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    indexed_chunks = list(enumerate(tts_text_chunks, start=1))
    if total_chunks == 1:
        synthesized = [agent.text_to_audio(
            tts_text_chunks[0], trim_pad_ms=TTS_CHUNK_EDGE_PAD_MS,
        )]
    else:
        with ThreadPoolExecutor(max_workers=min(3, total_chunks), thread_name_prefix="tts") as pool:
            synthesized = list(pool.map(synthesize, indexed_chunks))

    for (idx, tts_text), wav_bytes in zip(indexed_chunks, synthesized):
        if wav_bytes:
            audio_chunks.append(wav_bytes)
        else:
            failed_chunks.append(tts_text)
            log.error("TTS chunk failed (%d/%d)", idx, total_chunks)

    if not audio_chunks:
        log.error("All TTS chunks failed")
        return []

    if failed_chunks:
        fallback_text = " ".join(tts_text_chunks).strip()
        log.warning(
            "Retrying TTS as a single pass after %d chunk failure(s)",
            len(failed_chunks),
        )
        fallback_audio = agent.text_to_audio(fallback_text, trim_pad_ms=TTS_FALLBACK_PAD_MS)
        if fallback_audio:
            return [fallback_audio]
        log.error("Refusing incomplete TTS playback after full fallback failed")
        return []

    if len(audio_chunks) == 1:
        return audio_chunks

    merged_audio = agent.merge_audio_chunks(
        audio_chunks,
        sr=SR,
        crossfade_ms=12.0,
    )
    if not merged_audio:
        log.error("Merged TTS audio is empty")
        return audio_chunks

    log.info("Merged %d TTS chunks into 1 continuous payload", len(audio_chunks))
    return [merged_audio]


def _warm_up_runtime_assets(stt_engine: STTEngine, agent) -> dict[str, bool]:
    log = __import__("logging").getLogger("server")
    status = {"stt_ready": False, "tts_ready": False}

    try:
        log.info("Warming STT model before accepting connections...")
        stt_engine.ensure_model()
        status["stt_ready"] = stt_engine.model is not None
        if status["stt_ready"]:
            log.info("STT warmup complete")
        else:
            log.warning("STT warmup completed without a loaded model")
    except Exception as exc:
        log.warning("STT warmup failed: %s", exc, exc_info=True)

    if agent is None:
        return status

    try:
        log.info("Warming TTS voice before accepting connections...")
        warmup_audio = agent.text_to_audio("준비됐어요.", trim_pad_ms=0.0)
        status["tts_ready"] = bool(warmup_audio)
        if status["tts_ready"]:
            log.info("TTS warmup complete")
        else:
            log.warning("TTS warmup returned empty audio")
    except Exception as exc:
        log.warning("TTS warmup failed: %s", exc, exc_info=True)

    return status


def handle_connection(
    conn,
    addr,
    stt_engine: STTEngine,
    config,
    voice_id_service: VoiceIDService | None = None,
    runtime_state: dict | None = None,
    runtime_controller: RuntimeController | None = None,
):
    global current_mode, robot_handler, agent_handler

    log = __import__("logging").getLogger("server")
    perf_logger = get_performance_logger()

    log.info("Connected: %s", addr)
    _set_dashboard_connection_state(runtime_state, connected=True, addr=addr)
    conn.settimeout(config.get("connection", "socket_timeout", default=0.5))
    try:
        conn.setsockopt(1, 9, 1)
    except Exception:
        pass

    send_lock = threading.Lock()
    _prime_connection(conn, addr, send_lock)

    job_queue = JobQueue(
        stt_maxsize=config.get("queue", "stt_maxsize", default=4),
        tts_maxsize=config.get("queue", "tts_maxsize", default=2),
        command_maxsize=config.get("queue", "command_maxsize", default=10),
    )

    state = {"sid": 0, "current_angle": 90}
    state_lock = threading.Lock()
    stop_event = threading.Event()
    connection_ready = threading.Event()
    input_gate = InputGate()
    connection_greeting_thread = None
    connection_greeting_attempted = False

    def mark_connection_ready(source: str) -> None:
        if connection_ready.is_set():
            return
        connection_ready.set()
        log.info("Device handshake ready via %s; TTS playback enabled", source)

    def worker():
        global current_mode
        while not stop_event.is_set():
            try:
                job = job_queue.stt_queue.get(timeout=1)
            except Empty:
                continue

            if job is None:
                return

            sid, data, turn_started = job
            sec = len(data) / 2 / SR

            try:
                short_reason = _voice_rejection_reason(sec)
                if short_reason is not None:
                    _log_voice_rejection(sid, short_reason, sec)
                    if current_mode == "robot":
                        action = {
                            "action": "NOOP" if UNSURE_POLICY == "NOOP" else "WIGGLE",
                            "sid": sid,
                            "meaningful": False,
                            "recognized": False,
                        }
                        send_action(conn, action, send_lock)
                    continue

                # Convert voice data to PCM and run quality checks
                pcm = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                rms_db, peak, clip = qc(pcm)
                log.debug("QC sid=%s rms=%.1fdBFS peak=%.3f clip=%.2f%%", sid, rms_db, peak, clip)

                quiet_reason = _voice_rejection_reason(sec, rms_db, pcm)
                if quiet_reason is not None:
                    _log_voice_rejection(sid, quiet_reason, sec, rms_db)
                    if current_mode == "robot":
                        action = {
                            "action": "NOOP" if UNSURE_POLICY == "NOOP" else "WIGGLE",
                            "sid": sid,
                            "meaningful": False,
                            "recognized": False,
                        }
                        send_action(conn, action, send_lock)
                    continue

                pcm = trim_energy(pcm, SR)
                pcm = normalize_to_dbfs(pcm, target_dbfs=-22.0)

                # Recording file saving disabled
                # ts = time.strftime("%Y%m%d_%H%M%S")
                # wav_path = f"wav_logs/sid{sid}_{ts}_{len(pcm)/SR:.2f}s.wav"
                # save_wav(wav_path, pcm, SR)
                # log.info("Saved wav: %s", wav_path)

                # STT processing and text cleanup
                text = ""
                try:
                    stt_start = time.perf_counter()
                    segments, _ = stt_engine.safe_transcribe(pcm)
                    text = clean_text("".join(seg.text for seg in segments))
                    _log_voice_latency("stt", sid, stt_start, perf_logger.log_stt)
                except Exception as exc:
                    log.exception("Transcribe failed sid=%s: %s", sid, exc)
                    perf_logger.log_error()
                    continue

                if text:
                    log.info("STT accepted sid=%s characters=%d mode=%s", sid, len(text), current_mode)
                else:
                    log.info("STT: (empty/filtered)")

                if voice_id_service and current_mode == "agent":
                    if text.startswith("@@") and "목소리 등록" in text:
                        user = text.replace("@@", "").replace("목소리 등록", "").strip() or "사용자"
                        msg = voice_id_service.begin_register(user)
                        wav_bytes = agent_handler.text_to_audio(msg)
                        if wav_bytes:
                            _send_tts_chunks(conn, send_lock, [wav_bytes], connection_ready)
                        input_gate.mark_idle()
                        continue
                    if text.startswith("@@") and "화자 인식 켜" in text:
                        voice_id_service.set_enabled(True)
                        wav_bytes = agent_handler.text_to_audio("화자 인식을 켰어요.")
                        if wav_bytes:
                            _send_tts_chunks(conn, send_lock, [wav_bytes], connection_ready)
                        input_gate.mark_idle()
                        continue
                    if text.startswith("@@") and "화자 인식 꺼" in text:
                        voice_id_service.set_enabled(False)
                        wav_bytes = agent_handler.text_to_audio("화자 인식을 껐어요.")
                        if wav_bytes:
                            _send_tts_chunks(conn, send_lock, [wav_bytes], connection_ready)
                        input_gate.mark_idle()
                        continue
                    if text.startswith("@@") and "목소리 삭제" in text:
                        user = text.replace("@@", "").replace("목소리 삭제", "").strip()
                        deleted = voice_id_service.delete_user(user)
                        msg = f"{user} 목소리 정보를 삭제했어요." if deleted else f"{user} 사용자 목소리 정보를 찾지 못했어요."
                        wav_bytes = agent_handler.text_to_audio(msg)
                        if wav_bytes:
                            _send_tts_chunks(conn, send_lock, [wav_bytes], connection_ready)
                        input_gate.mark_idle()
                        continue

                    register_msg = voice_id_service.consume_sample(pcm)
                    if register_msg:
                        wav_bytes = agent_handler.text_to_audio(register_msg)
                        if wav_bytes:
                            _send_tts_chunks(conn, send_lock, [wav_bytes], connection_ready)
                        input_gate.mark_idle()
                        continue

                if runtime_controller is not None:
                    runtime_response = runtime_controller.handle_text_command(text)
                    if runtime_response:
                        log.info("Runtime command applied sid=%s", sid)
                        wav_bytes = agent_handler.text_to_audio(runtime_response)
                        if wav_bytes:
                            _send_tts_chunks(conn, send_lock, [wav_bytes], connection_ready)
                        input_gate.mark_idle()
                        continue

                with state_lock:
                    cur = state["current_angle"]

                # Mode-specific LLM processing (including intent/action-based mode switching)

                def _handle_mode_switch(new_mode):
                    """Common mode switching handler"""
                    global current_mode
                    if new_mode not in ("robot", "agent") or new_mode == current_mode:
                        return
                    old_mode = current_mode
                    current_mode = new_mode
                    log.info("=" * 50)
                    log.info("\ubaa8\ub4dc \ubcc0\uacbd: %s -> %s", old_mode.upper(), current_mode.upper())
                    log.info("=" * 50)
                    notify_text = f"{new_mode} \ubaa8\ub4dc\ub85c \ubcc0\uacbd\ub418\uc5c8\uc2b5\ub2c8\ub2e4."
                    if current_mode == "agent":
                        wav_bytes = agent_handler.text_to_audio(notify_text)
                        if wav_bytes:
                            _send_tts_chunks(conn, send_lock, [wav_bytes], connection_ready)
                    else:
                        send_action(conn, {"action": "WIGGLE", "sid": sid}, send_lock)

                if current_mode == "robot":
                    if not text:
                        send_action(conn, {"action": "NOOP", "sid": sid, "meaningful": False, "recognized": False}, send_lock)
                        continue

                    # Check for mode switch intent first
                    llm_start = time.perf_counter()
                    refined_text, robot_action = robot_handler.process_with_llm(text, cur)
                    _log_voice_latency("llm", sid, llm_start, perf_logger.log_llm)

                    if robot_action.get("action") == "SWITCH_MODE":
                        _handle_mode_switch(robot_action.get("mode"))
                        continue

                    # Generate emotion-aware response
                    llm_start = time.perf_counter()
                    response_text, emotion, emotion_payload = robot_handler.generate_emotion_response(text)
                    _log_voice_latency("llm", sid, llm_start, perf_logger.log_llm)
                    log.info("Robot emotion=%s response_chars=%d", emotion, len(response_text))

                    emotion_payload["sid"] = sid
                    emotion_payload["recognized"] = bool(text)
                    send_action(conn, emotion_payload, send_lock)

                    # TTS for robot response (if agent_handler available)
                    if response_text and agent_handler:
                        wav_bytes = agent_handler.text_to_audio(response_text)
                        if wav_bytes:
                            _send_tts_chunks(conn, send_lock, [wav_bytes], connection_ready)

                elif current_mode == "agent":
                    if not text:
                        continue

                    speaker_id = None
                    if voice_id_service:
                        gate_result = voice_id_service.gate(pcm)
                        if not gate_result.allowed:
                            if gate_result.message:
                                wav_bytes = agent_handler.text_to_audio(gate_result.message)
                                if wav_bytes:
                                    _send_tts_chunks(conn, send_lock, [wav_bytes], connection_ready)
                            input_gate.mark_idle()
                            continue
                        speaker_id = gate_result.user

                    log.info("Agent Mode: processing sid=%s characters=%d identified=%s", sid, len(text), bool(speaker_id))

                    llm_start = time.perf_counter()
                    response, intent = agent_handler.generate_response(text, speaker_id=speaker_id)
                    _log_voice_latency("llm", sid, llm_start, perf_logger.log_llm)

                    # Intent-based mode switching
                    if intent == "mode_robot":
                        _handle_mode_switch("robot")
                        continue
                    if intent == "mode_agent":
                        pass  # Already in agent mode

                    if response:
                        log.info("Agent Response sid=%s characters=%d", sid, len(response))
                        tts_start = time.perf_counter()
                        audio_payloads = _build_tts_audio_payloads(
                            agent_handler,
                            response,
                            max_chunks=3,
                        )
                        _log_voice_latency("tts", sid, tts_start, perf_logger.log_tts)

                        if not audio_payloads:
                            continue

                        if len(audio_payloads) > 1:
                            log.info(
                                "Prepared %d TTS chunks with boundary crossfade",
                                len(audio_payloads),
                            )

                        success = _send_tts_chunks(conn, send_lock, audio_payloads, connection_ready, turn_started=turn_started, sid=sid)
                        if not success:
                            log.error("Failed to send agent response audio")
                    else:
                        log.error("Agent generated empty response")

            except Exception as exc:
                log.exception("Worker error processing sid=%s: %s", sid, exc)
                perf_logger.log_error()
            finally:
                # Allow next voice input after one turn is processed
                input_gate.mark_idle()

    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()

    audio_buf = bytearray()
    active_sid = None
    max_audio_bytes = int(config.get("audio", "max_seconds", default=12) * SR * 2)
    last_status_log = time.time()

    while True:
        try:
            packet = recv_packet(conn)
            if packet is None:
                log.info("Disconnect detected")
                break
            ptype, payload = packet

            # Handle protocol packet types
            if ptype == PTYPE_PING:
                if send_pong(conn, send_lock):
                    mark_connection_ready("PING/PONG")
                if (
                    not connection_greeting_attempted
                    and connection_ready.is_set()
                    and current_mode == "agent"
                    and agent_handler is not None
                    and not input_gate.has_active_stream()
                    and not input_gate.is_busy()
                ):
                    connection_greeting_attempted = True
                    connection_greeting_thread = _start_connection_greeting(
                        conn,
                        send_lock,
                        agent_handler,
                        runtime_state,
                        input_gate,
                        connection_ready,
                    )
                continue

            # Handle voice stream start
            if ptype == PTYPE_START:
                mark_connection_ready("START")
                connection_greeting_attempted = True
                accepted = input_gate.start_stream()
                audio_buf = bytearray()

                if not accepted:
                    active_sid = None
                    log.debug("START ignored: processing in progress")
                    continue

                with state_lock:
                    state["sid"] += 1
                    active_sid = state["sid"]
                log.info("START (sid=%s)", active_sid)

            # Collect voice data
            elif ptype == PTYPE_AUDIO:
                if not input_gate.has_active_stream():
                    log.debug("AUDIO ignored: no active stream")
                    continue

                if not input_gate.can_accept_audio():
                    continue

                audio_buf.extend(payload)
                if len(audio_buf) > max_audio_bytes:
                    log.warning("Buffer too large -> force END")
                    ptype = PTYPE_END

            # Handle voice stream end and enqueue to STT queue
            if ptype == PTYPE_END:
                end_decision = input_gate.end_stream()
                if end_decision == InputGate.DECISION_IGNORE:
                    log.debug("END ignored: no active stream")
                    audio_buf = bytearray()
                    active_sid = None
                    continue

                if end_decision == InputGate.DECISION_DROP:
                    log.debug("Dropped voice stream while processing previous turn")
                    audio_buf = bytearray()
                    active_sid = None
                    continue

                sid = active_sid
                if sid is None:
                    with state_lock:
                        sid = state["sid"]
                data = bytes(audio_buf)
                sec = len(data) / 2 / SR
                log.info("END (sid=%s) bytes=%s sec=%.2f", sid, len(data), sec)

                input_gate.mark_busy()
                queued = job_queue.put(job_queue.stt_queue, (sid, data, time.perf_counter()), drop_oldest=True)
                if not queued:
                    log.warning("Failed to enqueue sid=%s; input gate released", sid)
                    input_gate.mark_idle()
                audio_buf = bytearray()
                active_sid = None

            if time.time() - last_status_log >= 10:
                last_status_log = time.time()
                log.info(
                    "Status: mode=%s busy=%s stt_queue=%s model_loaded=%s",
                    current_mode,
                    input_gate.is_busy(),
                    job_queue.stt_queue.qsize(),
                    stt_engine.model is not None,
                )

        except Exception as exc:
            log.exception("Connection loop error: %s", exc)
            break

    stop_event.set()
    try:
        job_queue.put(job_queue.stt_queue, None, drop_oldest=False)
    except Exception:
        pass

    worker_thread.join(timeout=2)
    if connection_greeting_thread is not None:
        connection_greeting_thread.join(timeout=0.2)
    _set_dashboard_connection_state(runtime_state, connected=False)
    log.info("Connection closed: %s", addr)


def main():
    global robot_handler, agent_handler

    config = get_config()
    logging_config = config.get_logging_config()
    setup_logging(
        level=logging_config.get("level", "INFO"),
        save_to_file=logging_config.get("save_to_file", True),
        log_dir=logging_config.get("log_dir", "logs"),
    )
    log = __import__("logging").getLogger("server")

    load_commands_config()

    host = config.get("server", "host")
    port = config.get("server", "port")
    model_size = config.get("stt", "model_size")
    device = config.get("stt", "device")
    language = config.get("stt", "language", default="ko")

    weather_config = config.get_weather_config()
    assistant_config = config.get_assistant_config()
    tts_config = config.get_tts_config()
    robot_config = config.get_robot_config()
    memory_dir = config.get("memory", "memory_dir", default="memory")
    memory_refresh_interval = int(config.get("memory", "refresh_interval", default=5))

    # Create runtime preference controller + shared LLM client
    llm_config = config.get_llm_config()
    runtime_controller = RuntimeController(config)
    if any(bucket in runtime_controller.preferences.llm_priority for bucket in ("ollama", "ollama_cpu")):
        install_target = config.get("setup", "install_target", default="ollama")
        if install_target != "api":
            ensure_ollama_running(llm_config.get("base_url", "http://localhost:11434"), llm_config)
        else:
            log.info("Skipping Ollama startup (install_target=api)")

    llm_client = PriorityLLMClient(llm_config, runtime_controller.preferences)
    shared_emotion_system = EmotionSystem()
    log.info(
        "LLM Runtime Priority: %s (API: %s)",
        " > ".join(runtime_controller.preferences.llm_priority),
        " > ".join(runtime_controller.preferences.api_priority),
    )
    accelerators = runtime_controller.preferences.hardware.accelerators or ["cpu-only"]
    log.info("Detected Accelerators: %s", ", ".join(accelerators))
    for note in runtime_controller.preferences.audio_runtime_notes():
        log.info("Runtime note: %s", note)

    # Initialize mode handlers
    robot_handler = RobotMode(
        ACTIONS_CONFIG,
        llm_client,
        robot_config=robot_config,
        emotion_system=shared_emotion_system,
    )
    agent_handler = AgentMode(
        llm_client,
        weather_config.get("api_key"),
        lat=weather_config.get("lat", 37.5665),
        lon=weather_config.get("lon", 126.9780),
        proactive_enabled=assistant_config.get("proactive", True),
        proactive_interval=assistant_config.get("proactive_interval", 1800),
        tts_voice=tts_config.get("voice", "ko-KR-SunHiNeural"),
        tts_backend=tts_config.get("backend", "edge_tts"),
        tts_model=tts_config.get("model", "gemini-3.8-flash-lite-tts"),
        tts_gemini_voice=tts_config.get("gemini_voice", "Kore"),
        tts_api_key=llm_config.get("gemini_api_key", ""),
        memory_dir=memory_dir,
        memory_refresh_interval=memory_refresh_interval,
        emotion_system=shared_emotion_system,
        integration_config=config.get("integrations", default={}),
        agent_config=config.get("agent", default={}),
    )

    log.info(
        "Assistant: %s (%s)",
        assistant_config.get("name", "ccoli"),
        assistant_config.get("personality", "witty"),
    )
    log.info(
        "Robot controller: %s (display=%s servo_count=%s)",
        robot_config.get("controller", "legacy_direct"),
        robot_config.get("display", {}).get("type", "ssd1306"),
        robot_config.get("servo", {}).get("count", 2),
    )


    stt_engine = STTEngine(
        model_size=model_size,
        device=device,
        language=language,
        device_priority=runtime_controller.preferences.resolved_stt_devices(),
    )
    runtime_controller.bind(llm_client=llm_client, stt_engine=stt_engine)
    agent_handler.runtime_controller = runtime_controller
    robot_handler.runtime_controller = runtime_controller

    runtime_state = _make_dashboard_runtime_state()
    warmup_status = _warm_up_runtime_assets(stt_engine, agent_handler)
    _set_dashboard_warmup_state(runtime_state, warmup_status)
    log.info(
        "Runtime warmup: stt_ready=%s tts_ready=%s",
        warmup_status["stt_ready"],
        warmup_status["tts_ready"],
    )

    voice_cfg = config.get_voice_id_config() if hasattr(config, "get_voice_id_config") else {}
    voice_id_service = VoiceIDService(
        Path("data/voice_profiles"),
        enabled=bool(voice_cfg.get("enabled", False)),
        threshold=float(voice_cfg.get("threshold", 0.72)),
    )

    perf_logger = get_performance_logger()
    interrupt_handler = _build_interrupt_handler(perf_logger)
    signal.signal(signal.SIGINT, interrupt_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, interrupt_handler)

    web_cfg = config.config.get("web", {})
    dashboard_urls = _start_web_dashboard(
        web_cfg,
        agent_fn=lambda: agent_handler,
        robot_fn=lambda: robot_handler,
        mode_fn=lambda: current_mode,
        dashboard_state_fn=lambda: runtime_state,
    )
    for url in dashboard_urls:
        log.info("Web dashboard: %s", url)
    if dashboard_urls:
        log.info("Web API docs: %s/api/docs", dashboard_urls[0])

    telegram_cfg = config.get_telegram_config() if hasattr(config, "get_telegram_config") else config.get("telegram", default={})
    telegram_worker = _start_telegram_channel(
        telegram_cfg,
        agent=agent_handler,
        runtime_controller=runtime_controller,
    )

    conn_manager = build_connection_manager(
        config,
        handler=lambda conn, addr: handle_connection(
            conn,
            addr,
            stt_engine,
            config,
            voice_id_service,
            runtime_state,
            runtime_controller=runtime_controller,
        ),
        connection_priority_provider=runtime_controller.get_connection_priority,
    )
    log.info("Server started. Default Mode: %s", current_mode)
    try:
        conn_manager.accept_loop()
    except KeyboardInterrupt:
        log.info("Server shutdown complete.")
        return 130
    finally:
        if telegram_worker is not None:
            telegram_worker.stop()
            telegram_worker.join(timeout=2.0)
            telegram_worker.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
