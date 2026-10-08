"""
ESP32와 서버 간 TCP 통신 프로토콜 모듈
- 패킷 송수신 및 프로토콜 타입 정의
- 안정적인 데이터 전송을 위한 유틸리티 함수들
"""
import json
import logging
import socket
import struct
import time
from typing import Optional

log = logging.getLogger(__name__)

# 프로토콜 타입 정의 - ESP32와 서버 간 통신 메시지 타입
PTYPE_START = 0x01          # 음성 녹음 시작 신호
PTYPE_AUDIO = 0x02          # 오디오 데이터 전송
PTYPE_END = 0x03            # 음성 녹음 종료 신호
PTYPE_PING = 0x10           # 연결 상태 확인 (ESP32 → 서버)
PTYPE_PONG = 0x1F           # 연결 응답 (서버 → ESP32)
PTYPE_CMD = 0x11            # 명령 전송 (서버 → ESP32)
PTYPE_AUDIO_OUT = 0x12      # 오디오 출력 데이터 (서버 → ESP32)
PTYPE_BUFFER_STATUS = 0x13  # 버퍼 상태 보고 (선택적)

_ZERO_PAYLOAD_PACKET_TYPES = {
    PTYPE_START,
    PTYPE_END,
    PTYPE_PING,
}
_MAX_INCOMING_AUDIO_PAYLOAD = 16_384
_MAX_INCOMING_BUFFER_STATUS_PAYLOAD = 1_024
# Largest payload the ESP32 will accept in one frame.
# Mirrors RX_MAX_PACKET_PAYLOAD in arduino/atom_echo_m5stack_esp32_ino/config.h;
# the device drops longer frames as serial noise, so never emit one.
DEVICE_MAX_PACKET_PAYLOAD = 2_048
WIRED_TTS_SAMPLE_RATE = 8_000
WIRED_TTS_BYTES_PER_SAMPLE = 1
WIRED_TTS_AUDIO_CHUNK = 512
_MULAW_BIAS = 0x84
_MULAW_CLIP = 32635


def _is_serial_like_connection(conn: socket.socket) -> bool:
    return hasattr(conn, "serial") and hasattr(conn, "port_name")


def _linear16_to_mulaw(sample: int) -> int:
    if sample < 0:
        sign = 0x80
        sample = -sample
    else:
        sign = 0x00

    if sample > _MULAW_CLIP:
        sample = _MULAW_CLIP

    sample += _MULAW_BIAS
    exponent = 7
    mask = 0x4000
    while exponent > 0 and (sample & mask) == 0:
        exponent -= 1
        mask >>= 1
    mantissa = (sample >> (exponent + 3)) & 0x0F
    return (~(sign | (exponent << 4) | mantissa)) & 0xFF


def _mulaw_to_linear16(value: int) -> int:
    value = (~value) & 0xFF
    sign = value & 0x80
    exponent = (value >> 4) & 0x07
    mantissa = value & 0x0F
    sample = ((_MULAW_BIAS + (mantissa << 3)) << exponent) - _MULAW_BIAS
    return -sample if sign else sample


def _encode_serial_audio_payload(pcm_bytes: bytes) -> bytes:
    """
    Transcode PCM16LE/16kHz mono to G.711 mu-law/8kHz mono for wired USB links.

    This halves the sample rate and compresses each sample to 8-bit so 115200
    baud can carry wired audio without starving microphone capture.

    Averaging each input pair is the anti-aliasing step: a 2-tap FIR at 16kHz
    has its null exactly at 8kHz, the output Nyquist frequency. Nothing is
    filtered after decimation — a low-pass at the 8kHz rate would attenuate the
    2-4kHz band that carries Korean consonants, and the firmware's uplink
    encoder does the same plain averaging, so both directions stay symmetric.
    """
    usable = len(pcm_bytes) - (len(pcm_bytes) % 2)
    if usable <= 0:
        return b""

    n_samples = usable // 2
    samples = []
    for i in range(0, usable, 2):
        samples.append(int.from_bytes(pcm_bytes[i : i + 2], "little", signed=True))

    out_len = n_samples // 2
    encoded = bytearray(out_len)
    for i in range(out_len):
        idx = i * 2
        avg = (samples[idx] + samples[idx + 1]) // 2
        encoded[i] = _linear16_to_mulaw(avg)
    return bytes(encoded)


def _decode_serial_audio_payload(payload: bytes) -> bytes:
    """
    Expand wired G.711 mu-law/8kHz payloads back to PCM16LE/16kHz.

    The server keeps the rest of the STT path at 16kHz, so each decoded sample
    is duplicated once after mu-law expansion.
    """
    if not payload:
        return b""

    decoded = bytearray(len(payload) * 4)
    offset = 0
    for value in payload:
        sample = _mulaw_to_linear16(value)
        struct.pack_into("<hh", decoded, offset, sample, sample)
        offset += 4
    return bytes(decoded)


def recv_exact(
    conn: socket.socket,
    n: int,
    max_timeouts: int = 120,
    log_timeout_warning: bool = True,
) -> Optional[bytes]:
    """
    정확히 n바이트를 수신하는 함수
    - 타임아웃 발생 시 재시도하며, 최대 횟수 초과 시 None 반환
    - 연결 오류 발생 시 즉시 None 반환
    """
    buf = b""
    timeout_count = 0
    # 요청된 바이트 수만큼 수신할 때까지 반복
    while len(buf) < n:
        try:
            chunk = conn.recv(n - len(buf))
        except socket.timeout:
            # 타임아웃 발생 시 카운터 증가 및 재시도
            timeout_count += 1
            if timeout_count >= max_timeouts:
                if log_timeout_warning:
                    log.warning("recv_exact timeout - connection may be dead")
                return None
            continue
        except (ConnectionResetError, ConnectionAbortedError, OSError) as exc:
            # 연결 오류 발생 시 즉시 종료
            log.warning("recv_exact connection error: %s", exc)
            return None
        if not chunk:
            return None
        timeout_count = 0  # 성공적으로 데이터 수신 시 타임아웃 카운터 리셋
        buf += chunk
    return buf


def _is_valid_incoming_packet_header(ptype: int, plen: int, serial_like: bool = False) -> bool:
    if ptype in _ZERO_PAYLOAD_PACKET_TYPES:
        return plen == 0

    if ptype == PTYPE_AUDIO:
        if serial_like:
            return 0 < plen <= _MAX_INCOMING_AUDIO_PAYLOAD
        return 0 < plen <= _MAX_INCOMING_AUDIO_PAYLOAD and plen % 2 == 0

    if ptype == PTYPE_BUFFER_STATUS:
        return 0 < plen <= _MAX_INCOMING_BUFFER_STATUS_PAYLOAD

    return False


def recv_packet(
    conn: socket.socket,
    header_timeouts: int = 120,
    payload_timeouts: int = 4,
) -> Optional[tuple[int, bytes]]:
    """
    Read one ESP32 -> server packet and resync when serial noise corrupts framing.

    Wired USB devices can emit boot chatter when the host opens the port, so the
    first few bytes are not always a valid protocol frame. We slide over invalid
    headers until we find a plausible packet boundary, then read the payload.
    """
    header = bytearray()
    skipped_bytes = 0
    serial_like = _is_serial_like_connection(conn)

    while True:
        chunk = recv_exact(conn, 1, max_timeouts=header_timeouts)
        if chunk is None:
            return None

        header.extend(chunk)
        if len(header) < 3:
            continue
        if len(header) > 3:
            del header[:-3]

        ptype = header[0]
        plen = int.from_bytes(header[1:3], "little")
        if not _is_valid_incoming_packet_header(ptype, plen, serial_like=serial_like):
            skipped_bytes += 1
            del header[0]
            continue

        if skipped_bytes:
            log.warning(
                "Skipped %d out-of-sync byte(s) before packet resync",
                skipped_bytes,
            )
            skipped_bytes = 0

        if plen == 0:
            return ptype, b""

        payload = recv_exact(
            conn,
            plen,
            max_timeouts=payload_timeouts,
            log_timeout_warning=False,
        )
        if payload is None:
            log.warning(
                "Dropping incomplete packet while resyncing stream: ptype=0x%02X plen=%d",
                ptype,
                plen,
            )
            header.clear()
            continue

        if serial_like and ptype == PTYPE_AUDIO:
            payload = _decode_serial_audio_payload(payload)

        return ptype, payload


def send_packet(
    conn: socket.socket,
    ptype: int,
    payload: Optional[bytes] = b"",
    lock=None,
    audio_chunk: int = 2048,
    audio_sleep_s: float = 0.0,
    audio_sample_rate: int = 16000,
    audio_bytes_per_sample: int = 2,
    audio_max_ahead_s: float = 0.35,
) -> bool:
    """
    안정적인 패킷 전송 함수
    - 패킷 타입과 페이로드를 헤더와 함께 전송
    - 오디오 데이터의 경우 샘플 경계를 유지하며 청크 단위로 전송
    - 스레드 안전성을 위한 락 지원
    """
    try:
        if payload is None:
            payload = b""

        # Never frame more than the device's receive buffer can hold.
        audio_chunk = max(1, min(int(audio_chunk), DEVICE_MAX_PACKET_PAYLOAD))

        def _send():
            offset = 0
            total = len(payload)
            # 페이로드가 없는 경우 헤더만 전송
            if total == 0:
                conn.sendall(struct.pack("<BH", ptype & 0xFF, 0))
                return True

            # 오디오 출력 데이터의 경우 특별 처리
            if ptype == PTYPE_AUDIO_OUT:
                bytes_per_second = max(1.0, float(audio_sample_rate * audio_bytes_per_sample))
                sample_bytes = max(1, int(audio_bytes_per_sample))
                send_t0 = time.perf_counter()
                sent_audio_bytes = 0
                while offset < total:
                    remaining = total - offset
                    if remaining < sample_bytes:
                        break
                    chunk_size = min(remaining, audio_chunk)
                    chunk_size -= chunk_size % sample_bytes
                    if chunk_size <= 0:
                        break
                    chunk = payload[offset : offset + chunk_size]
                    header = struct.pack("<BH", ptype & 0xFF, len(chunk))
                    conn.sendall(header + chunk)
                    offset += chunk_size
                    sent_audio_bytes += chunk_size

                    # 재생 속도 기준 pacing: 송신이 재생보다 과도하게 앞서가지 않도록 제한
                    if offset < total:
                        elapsed = time.perf_counter() - send_t0
                        sent_audio_s = sent_audio_bytes / bytes_per_second
                        ahead_s = sent_audio_s - elapsed
                        sleep_s = max(float(audio_sleep_s), ahead_s - float(audio_max_ahead_s))
                        if sleep_s > 0:
                            time.sleep(sleep_s)
            else:
                # 비오디오 페이로드(CMD 등)는 나눌 수 없다.
                # 조각마다 헤더가 붙어 디바이스에는 서로 다른 패킷으로 보이고,
                # 쪼개진 JSON은 어느 쪽도 파싱되지 않는다.
                if total > DEVICE_MAX_PACKET_PAYLOAD:
                    log.error(
                        "Refusing to send oversized ptype=0x%02X payload: %d > %d bytes",
                        ptype,
                        total,
                        DEVICE_MAX_PACKET_PAYLOAD,
                    )
                    return False
                conn.sendall(struct.pack("<BH", ptype & 0xFF, total) + payload)
            return True

        # 락이 제공된 경우 스레드 안전 전송
        if lock:
            with lock:
                return _send()
        return _send()

    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError) as exc:
        log.warning("send_packet error ptype=0x%02X: %s", ptype, exc)
        return False
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("send_packet failed ptype=0x%02X: %s", ptype, exc)
        return False


def send_action(conn: socket.socket, action_dict: dict, lock=None) -> bool:
    """
    ESP32에 액션 명령을 JSON 형태로 전송
    - 딕셔너리를 JSON으로 직렬화하여 CMD 패킷으로 전송
    """
    payload = json.dumps(action_dict, ensure_ascii=False).encode("utf-8")
    ok = send_packet(conn, PTYPE_CMD, payload, lock=lock)
    if ok:
        log.info("CMD to ESP32 action=%s sid=%s", action_dict.get("action"), action_dict.get("sid"))
    return ok


def send_audio(
    conn: socket.socket,
    pcm_bytes: bytes,
    lock=None,
    audio_chunk: int = 2048,
    audio_sleep_s: float = 0.0,
    audio_sample_rate: int = 16000,
    audio_bytes_per_sample: int = 2,
    audio_max_ahead_s: float = 0.35,
) -> bool:
    """
    ESP32에 오디오 데이터 전송
    - PCM 바이트 데이터를 AUDIO_OUT 패킷으로 전송
    - audio_chunk/audio_sleep_s로 스트리밍 전송 속도 제어
    """
    payload = pcm_bytes
    serial_like = _is_serial_like_connection(conn)
    if serial_like:
        payload = _encode_serial_audio_payload(pcm_bytes)
        audio_chunk = min(audio_chunk, WIRED_TTS_AUDIO_CHUNK)
        audio_sample_rate = WIRED_TTS_SAMPLE_RATE
        audio_bytes_per_sample = WIRED_TTS_BYTES_PER_SAMPLE

    ok = send_packet(
        conn,
        PTYPE_AUDIO_OUT,
        payload,
        lock=lock,
        audio_chunk=audio_chunk,
        audio_sleep_s=audio_sleep_s,
        audio_sample_rate=audio_sample_rate,
        audio_bytes_per_sample=audio_bytes_per_sample,
        audio_max_ahead_s=audio_max_ahead_s,
    )
    if ok:
        if serial_like:
            log.info(
                "AUDIO to ESP32: %s bytes (wired mu-law@8kHz from %s-byte PCM16)",
                len(payload),
                len(pcm_bytes),
            )
        else:
            log.info("AUDIO to ESP32: %s bytes", len(payload))
    return ok


def send_pong(conn: socket.socket, lock=None) -> bool:
    """
    ESP32의 PING에 대한 PONG 응답 전송
    - 연결 상태 확인을 위한 응답 패킷
    """
    return send_packet(conn, PTYPE_PONG, b"", lock=lock)
