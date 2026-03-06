"""
Main ESP32 voice streaming server module
- Receives voice data from ESP32 and performs STT
- Supports robot mode and agent mode
- Sends commands and voice responses over TCP socket communication
"""
import os
import signal
import threading
import time
import subprocess
import shlex
import urllib.parse
import urllib.request
from pathlib import Path
from queue import Empty

import numpy as np
import yaml

from config_loader import get_config
from src.agent_mode import AgentMode
from src.audio_processor import normalize_to_dbfs, qc, save_wav, trim_energy
from src.connection_manager import ConnectionManager
from src.input_gate import InputGate
from src.job_queue import JobQueue
from src.llm_client import LLMClient
from src.logging_setup import get_performance_logger, setup_logging
from src.protocol import (
    PTYPE_AUDIO,
    PTYPE_END,
    PTYPE_PING,
    PTYPE_START,
    recv_exact,
    send_action,
    send_audio,
    send_pong,
)
from src.robot_mode import RobotMode
from src.stt_engine import STTEngine
from src.voice_id import VoiceIDService
from src.utils import clean_text

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


# Audio processing constants
SR = 16000
UNSURE_POLICY = "NOOP"

ACTIONS_CONFIG = []
current_mode = "agent"  # Default mode: agent

# Mode handler instances
robot_handler = None
agent_handler = None


def load_commands_config(path: str = "commands.yaml"):
    global ACTIONS_CONFIG
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            ACTIONS_CONFIG = data.get("commands", [])
    except Exception:
        ACTIONS_CONFIG = []


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
    log = __import__("logging").getLogger("server")
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


def handle_connection(conn, addr, stt_engine: STTEngine, config, voice_id_service: VoiceIDService | None = None):
    global current_mode, robot_handler, agent_handler

    log = __import__("logging").getLogger("server")
    perf_logger = get_performance_logger()

    log.info("Connected: %s", addr)
    conn.settimeout(config.get("connection", "socket_timeout", default=0.5))
    try:
        conn.setsockopt(1, 9, 1)
    except Exception:
        pass

    send_lock = threading.Lock()
    job_queue = JobQueue(
        stt_maxsize=config.get("queue", "stt_maxsize", default=4),
        tts_maxsize=config.get("queue", "tts_maxsize", default=2),
        command_maxsize=config.get("queue", "command_maxsize", default=10),
    )

    state = {"sid": 0, "current_angle": 90}
    state_lock = threading.Lock()
    stop_event = threading.Event()
    input_gate = InputGate()

    def worker():
        global current_mode
        while not stop_event.is_set():
            try:
                job = job_queue.stt_queue.get(timeout=1)
            except Empty:
                continue

            if job is None:
                return

            sid, data = job
            sec = len(data) / 2 / SR

            try:
                if sec < 0.45:
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

                if rms_db < -45.0:
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
                    stt_start = time.time()
                    segments, _ = stt_engine.safe_transcribe(pcm)
                    text = clean_text("".join(seg.text for seg in segments))
                    perf_logger.log_stt(time.time() - stt_start)
                except Exception as exc:
                    log.exception("Transcribe failed sid=%s: %s", sid, exc)
                    perf_logger.log_error()
                    continue

                if text:
                    log.info("STT: %s (Mode: %s)", text, current_mode)
                else:
                    log.info("STT: (empty/filtered)")

                if voice_id_service and current_mode == "agent":
                    if text.startswith("@@") and "목소리 등록" in text:
                        user = text.replace("@@", "").replace("목소리 등록", "").strip() or "사용자"
                        msg = voice_id_service.begin_register(user)
                        wav_bytes = agent_handler.text_to_audio(msg)
                        if wav_bytes:
                            send_audio(conn, wav_bytes, send_lock)
                        input_gate.mark_idle()
                        continue
                    if text.startswith("@@") and "화자 인식 켜" in text:
                        voice_id_service.set_enabled(True)
                        wav_bytes = agent_handler.text_to_audio("화자 인식을 켰어요.")
                        if wav_bytes:
                            send_audio(conn, wav_bytes, send_lock)
                        input_gate.mark_idle()
                        continue
                    if text.startswith("@@") and "화자 인식 꺼" in text:
                        voice_id_service.set_enabled(False)
                        wav_bytes = agent_handler.text_to_audio("화자 인식을 껐어요.")
                        if wav_bytes:
                            send_audio(conn, wav_bytes, send_lock)
                        input_gate.mark_idle()
                        continue
                    if text.startswith("@@") and "목소리 삭제" in text:
                        user = text.replace("@@", "").replace("목소리 삭제", "").strip()
                        deleted = voice_id_service.delete_user(user)
                        msg = f"{user} 목소리 정보를 삭제했어요." if deleted else f"{user} 사용자 목소리 정보를 찾지 못했어요."
                        wav_bytes = agent_handler.text_to_audio(msg)
                        if wav_bytes:
                            send_audio(conn, wav_bytes, send_lock)
                        input_gate.mark_idle()
                        continue

                    register_msg = voice_id_service.consume_sample(pcm)
                    if register_msg:
                        wav_bytes = agent_handler.text_to_audio(register_msg)
                        if wav_bytes:
                            send_audio(conn, wav_bytes, send_lock)
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
                            send_audio(conn, wav_bytes, send_lock)
                    else:
                        send_action(conn, {"action": "WIGGLE", "sid": sid}, send_lock)

                if current_mode == "robot":
                    if not text:
                        send_action(conn, {"action": "NOOP", "sid": sid, "meaningful": False, "recognized": False}, send_lock)
                        continue

                    # Check for mode switch intent first
                    llm_start = time.time()
                    refined_text, robot_action = robot_handler.process_with_llm(text, cur)
                    perf_logger.log_llm(time.time() - llm_start)

                    if robot_action.get("action") == "SWITCH_MODE":
                        _handle_mode_switch(robot_action.get("mode"))
                        continue

                    # Generate emotion-aware response
                    llm_start = time.time()
                    response_text, emotion, emotion_payload = robot_handler.generate_emotion_response(text)
                    perf_logger.log_llm(time.time() - llm_start)
                    log.info("Robot emotion: %s, response: %s", emotion, response_text)

                    emotion_payload["sid"] = sid
                    emotion_payload["recognized"] = bool(text)
                    send_action(conn, emotion_payload, send_lock)

                    # TTS for robot response (if agent_handler available)
                    if response_text and agent_handler:
                        wav_bytes = agent_handler.text_to_audio(response_text)
                        if wav_bytes:
                            send_audio(conn, wav_bytes, send_lock)

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
                                    send_audio(conn, wav_bytes, send_lock)
                            input_gate.mark_idle()
                            continue
                        speaker_id = gate_result.user

                    log.info("Agent Mode: Processing text: %s (speaker=%s)", text, speaker_id or "unknown")

                    llm_start = time.time()
                    response, intent = agent_handler.generate_response(text, speaker_id=speaker_id)
                    perf_logger.log_llm(time.time() - llm_start)

                    # Intent-based mode switching
                    if intent == "mode_robot":
                        _handle_mode_switch("robot")
                        continue
                    if intent == "mode_agent":
                        pass  # Already in agent mode

                    if response:
                        log.info("Agent Response: %s", response)
                        tts_text_chunks = agent_handler.prepare_tts_chunks(response, max_chunks=3)
                        if not tts_text_chunks:
                            log.error("TTS text chunks are empty after sanitization")
                            continue
                        if len(tts_text_chunks) > 1:
                            log.info("TTS text split into %d chunks", len(tts_text_chunks))

                        tts_start = time.time()
                        audio_payloads = []
                        total_chunks = len(tts_text_chunks)
                        for idx, tts_text in enumerate(tts_text_chunks, start=1):
                            trim_pad_ms = 140.0
                            if total_chunks > 1:
                                if idx == 1 or idx == total_chunks:
                                    trim_pad_ms = 80.0
                                else:
                                    trim_pad_ms = 40.0
                            wav_bytes = agent_handler.text_to_audio(
                                tts_text,
                                trim_pad_ms=trim_pad_ms,
                            )
                            if wav_bytes:
                                audio_payloads.append(wav_bytes)
                            else:
                                log.error(
                                    "TTS chunk failed (%d/%d): %s",
                                    idx,
                                    total_chunks,
                                    tts_text,
                                )
                        perf_logger.log_tts(time.time() - tts_start)

                        if not audio_payloads:
                            log.error("All TTS chunks failed")
                            continue

                        audio_payloads = agent_handler.crossfade_audio_boundaries(
                            audio_payloads,
                            sr=SR,
                            crossfade_ms=12.0,
                        )
                        audio_payloads = [chunk for chunk in audio_payloads if chunk]
                        if not audio_payloads:
                            log.error("Crossfaded TTS audio is empty")
                            continue

                        if len(audio_payloads) > 1:
                            log.info(
                                "Prepared %d TTS chunks with boundary crossfade",
                                len(audio_payloads),
                            )

                        total_audio_chunks = len(audio_payloads)
                        for idx, chunk_bytes in enumerate(audio_payloads, start=1):
                            log.info(
                                "Sending audio chunk %d/%d: %d bytes",
                                idx,
                                total_audio_chunks,
                                len(chunk_bytes),
                            )
                            success = send_audio(conn, chunk_bytes, send_lock)
                            if not success:
                                log.error("Failed to send audio chunk %d/%d", idx, total_audio_chunks)
                                break
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
            t = recv_exact(conn, 1)
            if t is None:
                log.info("Disconnect detected")
                break
            ptype = t[0]

            raw_len = recv_exact(conn, 2)
            if raw_len is None:
                log.info("Disconnect (len)")
                break
            (plen,) = __import__("struct").unpack("<H", raw_len)

            payload = b""
            if plen:
                payload = recv_exact(conn, plen)
                if payload is None:
                    log.info("Disconnect (payload)")
                    break

            # Handle protocol packet types
            if ptype == PTYPE_PING:
                send_pong(conn, send_lock)
                continue

            # Handle voice stream start
            if ptype == PTYPE_START:
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
                queued = job_queue.put(job_queue.stt_queue, (sid, data), drop_oldest=True)
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

    # Create a single shared LLM client
    llm_config = config.get_llm_config()
    provider = (llm_config.get("provider", "ollama") or "ollama").lower()
    if provider == "ollama":
        ensure_ollama_running(llm_config.get("base_url", "http://localhost:11434"), llm_config)

    api_key = ""
    if provider == "chatgpt":
        api_key = llm_config.get("openai_api_key") or os.getenv("OPENAI_API_KEY", "")
    elif provider == "claude":
        api_key = llm_config.get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY", "")
    elif provider == "gemini":
        api_key = llm_config.get("gemini_api_key") or os.getenv("GEMINI_API_KEY", "")

    llm_client = LLMClient(
        base_url=llm_config.get("base_url", "http://localhost:11434"),
        model=llm_config.get("model", "qwen2.5:0.5b"),
        default_think=llm_config.get("think", False),
        provider=provider,
        api_key=api_key,
    )
    log.info(
        "LLM Client: %s (%s, default_think=%s)",
        llm_client.base_url,
        llm_client.model,
        llm_client.default_think,
    )

    # Initialize mode handlers
    robot_handler = RobotMode(ACTIONS_CONFIG, llm_client)
    agent_handler = AgentMode(
        llm_client,
        weather_config.get("api_key"),
        lat=weather_config.get("lat", 37.5665),
        lon=weather_config.get("lon", 126.9780),
        proactive_enabled=assistant_config.get("proactive", True),
        proactive_interval=assistant_config.get("proactive_interval", 1800),
        tts_voice=tts_config.get("voice", "ko-KR-SunHiNeural"),
    )

    log.info(
        "Assistant: %s (%s)",
        assistant_config.get("name", "ccoli"),
        assistant_config.get("personality", "witty"),
    )

    stt_engine = STTEngine(model_size=model_size, device=device, language=language)

    voice_cfg = config.get_voice_id_config() if hasattr(config, "get_voice_id_config") else {}
    voice_id_service = VoiceIDService(
        Path("data/voice_profiles"),
        enabled=bool(voice_cfg.get("enabled", False)),
        threshold=float(voice_cfg.get("threshold", 0.72)),
    )

    perf_logger = get_performance_logger()
    signal.signal(signal.SIGINT, lambda *_: perf_logger.print_stats())

    conn_manager = ConnectionManager(
        host=host,
        port=port,
        handler=lambda conn, addr: handle_connection(conn, addr, stt_engine, config, voice_id_service),
    )
    log.info("Server started. Default Mode: %s", current_mode)
    conn_manager.accept_loop()


if __name__ == "__main__":
    main()
