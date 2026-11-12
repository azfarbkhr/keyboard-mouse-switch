"""Shared TLS and newline-delimited JSON helpers."""
import hashlib
import json
import socket
import ssl

PORT = 45839
MAX_LINE = 8192


def fingerprint(der):
    return hashlib.sha256(der).hexdigest().upper()


def normalize_fingerprint(value):
    return value.replace(":", "").replace(" ", "").strip().upper()


def send(sock, data):
    send_batch(sock, (data,))


def send_batch(sock, events):
    lines = "".join(json.dumps(event, separators=(",", ":")) + "\n" for event in events)
    sock.sendall(lines.encode())


def messages(sock):
    buf = b""
    while True:
        part = sock.recv(4096)
        if not part:
            return
        buf += part
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if len(line) > MAX_LINE:
                raise ValueError("Message too large")
            yield json.loads(line)
        if len(buf) > MAX_LINE:
            raise ValueError("Message too large")


def connect(host, port, pin, secret):
    pin = normalize_fingerprint(pin)
    if len(pin) != 64 or any(c not in "0123456789ABCDEF" for c in pin):
        raise ValueError("Certificate fingerprint must contain 64 hex characters")
    raw = socket.create_connection((host, port), timeout=5)
    try:
        raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # Trust is established by the fingerprint below.
        sock = ctx.wrap_socket(raw, server_hostname=host)
        if fingerprint(sock.getpeercert(binary_form=True)) != pin:
            raise ValueError("Certificate fingerprint does not match the receiver")
        send(sock, {"type": "auth", "secret": secret})
        stream = messages(sock)
        reply = next(stream)
        if reply.get("type") != "ok":
            raise ValueError("Pairing secret rejected")
        sock.settimeout(None)
        return sock, stream
    except BaseException:
        raw.close()
        raise
