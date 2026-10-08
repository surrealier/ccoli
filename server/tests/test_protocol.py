import socket
import struct
import threading
import time
from unittest import mock

import numpy as np

from src import protocol


def read_packet(sock):
    ptype = sock.recv(1)
    if not ptype:
        return None, None
    length = sock.recv(2)
    plen = int.from_bytes(length, "little")
    payload = sock.recv(plen) if plen else b""
    return ptype[0], payload


def test_send_packet_basic():
    s1, s2 = socket.socketpair()
    try:
        payload = b"abc"
        ok = protocol.send_packet(s1, protocol.PTYPE_CMD, payload)
        assert ok
        ptype, recv_payload = read_packet(s2)
        assert ptype == protocol.PTYPE_CMD
        assert recv_payload == payload
    finally:
        s1.close()
        s2.close()


def test_send_packet_audio_even_bytes():
    s1, s2 = socket.socketpair()
    try:
        payload = b"\x01\x02\x03"  # odd length, last byte should be dropped
        ok = protocol.send_packet(s1, protocol.PTYPE_AUDIO_OUT, payload, audio_chunk=4, audio_sleep_s=0)
        assert ok
        ptype, recv_payload = read_packet(s2)
        assert ptype == protocol.PTYPE_AUDIO_OUT
        assert len(recv_payload) == 2
    finally:
        s1.close()
        s2.close()


def test_send_packet_audio_allows_one_byte_samples():
    s1, s2 = socket.socketpair()
    try:
        payload = b"\x81\x7f\x00"
        ok = protocol.send_packet(
            s1,
            protocol.PTYPE_AUDIO_OUT,
            payload,
            audio_chunk=4,
            audio_sleep_s=0,
            audio_bytes_per_sample=1,
        )
        assert ok
        ptype, recv_payload = read_packet(s2)
        assert ptype == protocol.PTYPE_AUDIO_OUT
        assert recv_payload == payload
    finally:
        s1.close()
        s2.close()


def test_send_audio_splits_default_packets_to_2kb_or_less():
    s1, s2 = socket.socketpair()
    try:
        payload = b"\x00\x01" * 2500
        ok = protocol.send_audio(s1, payload, audio_sleep_s=0)
        assert ok

        packets = []
        total = 0
        while total < len(payload):
            ptype, recv_payload = read_packet(s2)
            packets.append((ptype, recv_payload))
            total += len(recv_payload)

        assert total == len(payload)
        assert all(ptype == protocol.PTYPE_AUDIO_OUT for ptype, _payload in packets)
        assert all(len(recv_payload) <= 2048 for _ptype, recv_payload in packets)
    finally:
        s1.close()
        s2.close()


def test_send_audio_uses_smaller_chunks_for_serial_links():
    fake_conn = mock.Mock()
    fake_conn.serial = object()
    fake_conn.port_name = "/dev/cu.test"

    with mock.patch.object(protocol, "send_packet", return_value=True) as send_packet:
        ok = protocol.send_audio(fake_conn, b"\x00\x01" * 1000)

    assert ok is True
    assert send_packet.call_args.kwargs["audio_chunk"] == 512
    assert send_packet.call_args.kwargs["audio_sample_rate"] == 8000
    assert send_packet.call_args.kwargs["audio_bytes_per_sample"] == 1
    assert len(send_packet.call_args.args[2]) == 500


def test_encode_serial_audio_payload_downsamples_to_wired_codec():
    pcm16 = b"\x00\x80\x00\x80\x00\x00\xff\x7f"
    encoded = protocol._encode_serial_audio_payload(pcm16)
    assert len(encoded) == 2
    decoded = protocol._decode_serial_audio_payload(encoded)
    restored = np.frombuffer(decoded, dtype=np.int16)
    assert restored.shape == (4,)
    assert restored[0] < -1000
    assert restored[1] < -1000
    assert restored[2] > 1000
    assert restored[3] > 1000


def test_encode_serial_audio_payload_does_not_attenuate_the_signal():
    # A post-decimation low-pass used to bleed one sample into the next, so the
    # first encoded sample came back at ~56% amplitude and speech sounded muffled.
    # Averaging pairs is the only filtering step, so a steady block must survive
    # within mu-law quantization error.
    level = 12000
    pcm = np.full(8, level, dtype=np.int16).tobytes()

    restored = np.frombuffer(
        protocol._decode_serial_audio_payload(protocol._encode_serial_audio_payload(pcm)),
        dtype=np.int16,
    )

    assert restored.size == 8
    assert np.all(np.abs(restored.astype(np.int32) - level) < level * 0.1)


def test_send_packet_refuses_command_payloads_larger_than_the_device_buffer():
    # Splitting a CMD gives each fragment its own header, so the device sees two
    # packets and parses neither. Failing loudly beats emitting garbage frames.
    s1, s2 = socket.socketpair()
    try:
        s2.settimeout(0.1)
        oversized = b"x" * (protocol.DEVICE_MAX_PACKET_PAYLOAD + 1)

        assert protocol.send_packet(s1, protocol.PTYPE_CMD, oversized) is False

        try:
            leaked = s2.recv(1)
        except socket.timeout:
            leaked = b""
        assert leaked == b"", "no partial frame should reach the device"
    finally:
        s1.close()
        s2.close()


def test_send_packet_clamps_audio_frames_to_the_device_buffer():
    s1, s2 = socket.socketpair()
    try:
        payload = b"\x00\x01" * 4000
        ok = protocol.send_packet(
            s1,
            protocol.PTYPE_AUDIO_OUT,
            payload,
            audio_chunk=60000,  # caller asks for more than the ESP32 can hold
            audio_sleep_s=0,
        )
        assert ok

        received = 0
        while received < len(payload):
            _ptype, chunk = read_packet(s2)
            assert len(chunk) <= protocol.DEVICE_MAX_PACKET_PAYLOAD
            received += len(chunk)
        assert received == len(payload)
    finally:
        s1.close()
        s2.close()


def test_recv_packet_decodes_serial_audio_payload_back_to_pcm16():
    class _FakeSerialConn:
        def __init__(self, data: bytes):
            self._data = bytearray(data)
            self.serial = object()
            self.port_name = "/dev/cu.test"

        def recv(self, n: int) -> bytes:
            if not self._data:
                return b""
            take = min(n, len(self._data))
            chunk = bytes(self._data[:take])
            del self._data[:take]
            return chunk

    pcm = (np.array([-30000, -30000, 12000, 12000], dtype=np.int16)).tobytes()
    encoded = protocol._encode_serial_audio_payload(pcm)
    packet_bytes = struct.pack("<BH", protocol.PTYPE_AUDIO, len(encoded)) + encoded

    packet = protocol.recv_packet(_FakeSerialConn(packet_bytes), header_timeouts=1, payload_timeouts=1)

    assert packet is not None
    ptype, payload = packet
    assert ptype == protocol.PTYPE_AUDIO
    restored = np.frombuffer(payload, dtype=np.int16)
    assert restored.shape == (4,)
    assert restored[0] < -1000
    assert restored[1] < -1000
    assert restored[2] > 1000
    assert restored[3] > 1000


def test_recv_packet_skips_garbage_before_ping():
    s1, s2 = socket.socketpair()
    try:
        s2.settimeout(0.1)
        s1.sendall(b"boot\r\n" + struct.pack("<BH", protocol.PTYPE_PING, 0))

        packet = protocol.recv_packet(s2, header_timeouts=2, payload_timeouts=1)

        assert packet == (protocol.PTYPE_PING, b"")
    finally:
        s1.close()
        s2.close()


def test_recv_packet_resyncs_after_incomplete_false_header():
    s1, s2 = socket.socketpair()
    sender = None
    try:
        s2.settimeout(0.05)

        def _send_script():
            s1.sendall(struct.pack("<BH", protocol.PTYPE_AUDIO, 6) + b"\x01\x02")
            time.sleep(0.08)
            s1.sendall(struct.pack("<BH", protocol.PTYPE_PING, 0))

        sender = threading.Thread(target=_send_script, daemon=True)
        sender.start()

        packet = protocol.recv_packet(s2, header_timeouts=4, payload_timeouts=1)

        assert packet == (protocol.PTYPE_PING, b"")
    finally:
        if sender is not None:
            sender.join(timeout=1)
        s1.close()
        s2.close()


def test_device_command_log_does_not_include_private_payload(monkeypatch, caplog):
    sent = []

    def fake_send_packet(conn, ptype, payload, lock=None):
        sent.append(payload)
        return True

    monkeypatch.setattr(protocol, 'send_packet', fake_send_packet)
    caplog.set_level('INFO', logger='src.protocol')
    assert protocol.send_action(None, {'action': 'DISPLAY', 'sid': 7, 'text': '비밀 응답 문장'})
    assert b'DISPLAY' in sent[0]
    assert '비밀 응답 문장' not in caplog.text