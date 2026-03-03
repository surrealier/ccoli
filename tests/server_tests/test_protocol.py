from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from server.protocol import (
    PTYPE_AUDIO,
    PTYPE_CMD,
    decode_header,
    decode_packet,
    encode_cmd,
    encode_packet,
    frame_size_bytes,
)


def test_encode_decode_roundtrip():
    payload = b"abc123"
    packet = encode_packet(PTYPE_AUDIO, payload)
    ptype, out = decode_packet(packet)
    assert ptype == PTYPE_AUDIO
    assert out == payload


def test_decode_header_size_validation():
    try:
        decode_header(b"\x01")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_encode_cmd_packet_type_and_json_bytes():
    packet = encode_cmd({"action": "SERVO_SET", "angle": 90, "sid": 1})
    ptype, payload = decode_packet(packet)
    assert ptype == PTYPE_CMD
    assert b"SERVO_SET" in payload


def test_frame_size_matches_20ms_pcm16_mono_16k():
    assert frame_size_bytes(20, 16000, 1, 2) == 640
