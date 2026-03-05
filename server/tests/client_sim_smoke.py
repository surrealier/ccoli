import socket
import struct
import threading
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mock_esp32 import MockESP32
from src.protocol import PTYPE_AUDIO, PTYPE_END, PTYPE_PING, PTYPE_START


def _recv_packet(conn: socket.socket):
    header = conn.recv(3)
    if len(header) < 3:
        return None, b""
    ptype, plen = struct.unpack("<BH", header)
    payload = conn.recv(plen) if plen else b""
    return ptype, payload


def main() -> int:
    packets: list[tuple[int, bytes]] = []

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    host, port = server.getsockname()

    def _accept_once():
        conn, _addr = server.accept()
        with conn:
            while True:
                ptype, payload = _recv_packet(conn)
                if ptype is None:
                    break
                packets.append((ptype, payload))
                if ptype == PTYPE_END:
                    break

    t = threading.Thread(target=_accept_once, daemon=True)
    t.start()

    esp = MockESP32(host=host, port=port)
    esp.connect()
    esp.send_ping()
    esp.send_audio_session(b"\x00\x01" * 200)
    esp.close()

    t.join(timeout=2)
    server.close()

    types = [ptype for ptype, _ in packets]
    assert PTYPE_PING in types
    assert PTYPE_START in types
    assert PTYPE_AUDIO in types
    assert PTYPE_END in types
    print("client-sim smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
