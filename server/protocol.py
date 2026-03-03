"""Protocol helpers for ESP32 <-> server packet framing."""

from __future__ import annotations

import json
import struct
from typing import Tuple

PTYPE_START = 0x01
PTYPE_AUDIO = 0x02
PTYPE_END = 0x03
PTYPE_PING = 0x10
PTYPE_CMD = 0x11
PTYPE_AUDIO_OUT = 0x12
PTYPE_PONG = 0x1F

_HEADER_FMT = "<BH"
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)


def encode_packet(ptype: int, payload: bytes = b"") -> bytes:
    if payload is None:
        payload = b""
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload must be bytes-like")
    payload = bytes(payload)
    return struct.pack(_HEADER_FMT, ptype & 0xFF, len(payload)) + payload


def decode_header(header: bytes) -> Tuple[int, int]:
    if len(header) != _HEADER_SIZE:
        raise ValueError(f"header must be exactly {_HEADER_SIZE} bytes")
    ptype, length = struct.unpack(_HEADER_FMT, header)
    return ptype, length


def decode_packet(packet: bytes) -> Tuple[int, bytes]:
    if len(packet) < _HEADER_SIZE:
        raise ValueError("packet too short")
    ptype, length = decode_header(packet[:_HEADER_SIZE])
    payload = packet[_HEADER_SIZE:]
    if len(payload) != length:
        raise ValueError("payload length mismatch")
    return ptype, payload


def encode_cmd(action_dict: dict) -> bytes:
    payload = json.dumps(action_dict, ensure_ascii=False).encode("utf-8")
    return encode_packet(PTYPE_CMD, payload)


def frame_size_bytes(duration_ms: int = 20, sample_rate: int = 16000, channels: int = 1, sample_bytes: int = 2) -> int:
    samples_per_frame = int(sample_rate * duration_ms / 1000)
    return samples_per_frame * channels * sample_bytes
