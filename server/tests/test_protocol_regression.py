import socket
import time

import pytest

from src import protocol


def _read_packet(sock):
    ptype = sock.recv(1)
    if not ptype:
        return None, None
    length = sock.recv(2)
    plen = int.from_bytes(length, "little")
    payload = sock.recv(plen) if plen else b""
    return ptype[0], payload


@pytest.mark.protocol
def test_protocol_regression_normal_payload():
    s1, s2 = socket.socketpair()
    try:
        payload = b"hello-regression"
        assert protocol.send_packet(s1, protocol.PTYPE_CMD, payload)
        ptype, recv_payload = _read_packet(s2)
        assert ptype == protocol.PTYPE_CMD
        assert recv_payload == payload
    finally:
        s1.close()
        s2.close()


@pytest.mark.protocol
def test_protocol_regression_delayed_retry_flow():
    s1, s2 = socket.socketpair()
    try:
        payload = b"\x01\x02" * 200
        assert protocol.send_packet(s1, protocol.PTYPE_AUDIO_OUT, payload, audio_chunk=80, audio_sleep_s=0.001)
        packets = []
        while sum(len(item[1]) for item in packets) < len(payload):
            packets.append(_read_packet(s2))
        assert all(ptype == protocol.PTYPE_AUDIO_OUT for ptype, _ in packets)
        assert sum(len(item[1]) for item in packets) == len(payload)
    finally:
        s1.close()
        s2.close()


@pytest.mark.protocol
def test_protocol_regression_invalid_payload_is_trimmed_for_audio():
    s1, s2 = socket.socketpair()
    try:
        invalid_audio = b"\x01\x02\x03"
        assert protocol.send_packet(s1, protocol.PTYPE_AUDIO_OUT, invalid_audio, audio_chunk=10, audio_sleep_s=0)
        ptype, recv_payload = _read_packet(s2)
        assert ptype == protocol.PTYPE_AUDIO_OUT
        assert recv_payload == b"\x01\x02"
    finally:
        s1.close()
        s2.close()
