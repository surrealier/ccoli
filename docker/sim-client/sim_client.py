"""Lightweight ESP32 protocol simulator for Docker integration checks."""

import socket
import time

from server.protocol import PTYPE_AUDIO, PTYPE_END, PTYPE_PING, PTYPE_START, decode_header, encode_packet, frame_size_bytes

HOST = "server-tests"
PORT = 5001


def run_once(timeout: float = 1.5) -> int:
    data = b"\x00\x00" * (frame_size_bytes() // 2)
    with socket.create_connection((HOST, PORT), timeout=timeout) as sock:
        sock.sendall(encode_packet(PTYPE_START))
        sock.sendall(encode_packet(PTYPE_AUDIO, data))
        sock.sendall(encode_packet(PTYPE_END))
        sock.sendall(encode_packet(PTYPE_PING))
        sock.settimeout(0.5)
        try:
            header = sock.recv(3)
            if len(header) == 3:
                decode_header(header)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    time.sleep(1)
    raise SystemExit(run_once())
