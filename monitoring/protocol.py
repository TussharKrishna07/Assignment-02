"""
Protocol helpers – mirrors the C++ protocol.h so Python test clients
can talk to the discovery server and the threaded chat server.
"""

import socket
import struct

# ── Message types (must match protocol.h) ─────────────────────────────────────
REGISTRATION = 1
LOGIN        = 2
BROADCAST    = 3
PRIVATE_MSG  = 4
QUERY_USER   = 5

# ── Header format: int32 type, int32 payload_length, char[32] sender, char[32] target
HEADER_FMT  = "ii32s32s"          # native byte-order, 72 bytes
HEADER_SIZE = struct.calcsize(HEADER_FMT)   # should be 72

DISCOVERY_IP   = "127.0.0.1"
DISCOVERY_PORT = 5000
CHAT_IP        = "127.0.0.1"
CHAT_PORT      = 6000


def _pad(s: str, length: int = 32) -> bytes:
    """Encode a string into a fixed-width zero-padded bytes field."""
    b = s.encode("utf-8")[:length]
    return b + b"\x00" * (length - len(b))


def pack_header(msg_type: int, payload: bytes,
                sender: str, target: str = "") -> bytes:
    """Build a 72-byte header followed by the payload."""
    hdr = struct.pack(HEADER_FMT,
                      msg_type,
                      len(payload),
                      _pad(sender),
                      _pad(target))
    return hdr + payload


def unpack_header(data: bytes):
    """Return (type, payload_length, sender, target) from 72 raw bytes."""
    t, pl, s, tg = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
    sender = s.split(b"\x00", 1)[0].decode()
    target = tg.split(b"\x00", 1)[0].decode()
    return t, pl, sender, target


def recv_exact(sock: socket.socket, n: int) -> bytes:
    """Read exactly n bytes from a socket (blocking)."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Socket closed while reading")
        buf += chunk
    return buf


def recv_message(sock: socket.socket):
    """Read one full message.  Returns (type, sender, target, payload_str)."""
    hdr_bytes = recv_exact(sock, HEADER_SIZE)
    msg_type, plen, sender, target = unpack_header(hdr_bytes)
    payload = recv_exact(sock, plen).decode() if plen > 0 else ""
    return msg_type, sender, target, payload


# ── High-level client helpers ─────────────────────────────────────────────────

def register_user(username: str, password: str) -> bool:
    """Register with the discovery server.  Returns True on success."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((DISCOVERY_IP, DISCOVERY_PORT))
        sock.sendall(pack_header(REGISTRATION, password.encode(),
                                 username, ""))
        _, _, _, payload = recv_message(sock)
        return "OK" in payload
    except Exception as e:
        print(f"[register] {username}: {e}")
        return False
    finally:
        sock.close()


def login_user(username: str, password: str) -> socket.socket | None:
    """Login to the chat server.  Returns the connected socket or None."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((CHAT_IP, CHAT_PORT))
        sock.sendall(pack_header(LOGIN, password.encode(), username, ""))
        _, _, _, payload = recv_message(sock)
        if "OK" in payload:
            return sock
        sock.close()
        return None
    except Exception as e:
        print(f"[login] {username}: {e}")
        sock.close()
        return None


def send_broadcast(sock: socket.socket, username: str, message: str):
    """Send a broadcast message through an already-authenticated socket."""
    sock.sendall(pack_header(BROADCAST, message.encode(), username, "all"))


def send_private(sock: socket.socket, username: str,
                 target: str, message: str):
    """Send a private message through an already-authenticated socket."""
    sock.sendall(pack_header(PRIVATE_MSG, message.encode(), username, target))
