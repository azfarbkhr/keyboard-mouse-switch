"""Run on the PC: python receiver.py"""
import datetime
import hmac
import ipaddress
import json
import secrets
import socket
import ssl
import threading
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pynput import keyboard, mouse

from common import PORT, fingerprint, messages, send

DATA = Path(__file__).resolve().parent / "receiver-data"


def setup():
    DATA.mkdir(exist_ok=True)
    cert, key, config = DATA / "cert.pem", DATA / "key.pem", DATA / "config.json"
    if not cert.exists() or not key.exists():
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Keyboard Mouse Switch")])
        now = datetime.datetime.now(datetime.timezone.utc)
        certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                       .public_key(private.public_key()).serial_number(x509.random_serial_number())
                       .not_valid_before(now - datetime.timedelta(minutes=5))
                       .not_valid_after(now + datetime.timedelta(days=3650))
                       .sign(private, hashes.SHA256()))
        key.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
        cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    if not config.exists():
        config.write_text(json.dumps({"secret": secrets.token_urlsafe(24)}), encoding="utf-8")
    secret = json.loads(config.read_text(encoding="utf-8"))["secret"]
    certificate = x509.load_pem_x509_certificate(cert.read_bytes())
    return cert, key, secret, fingerprint(certificate.public_bytes(serialization.Encoding.DER))


def local_ips():
    try:
        return sorted({info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
                       if not ipaddress.ip_address(info[4][0]).is_loopback})
    except OSError:
        return []


def serve_client(sock, secret):
    kb, ms = keyboard.Controller(), mouse.Controller()
    held_keys, held_buttons = set(), set()
    buttons = {"left": mouse.Button.left, "right": mouse.Button.right, "middle": mouse.Button.middle,
               "x1": mouse.Button.x1, "x2": mouse.Button.x2}
    try:
        sock.settimeout(10)
        stream = messages(sock)
        first = next(stream)
        if first.get("type") != "auth" or not isinstance(first.get("secret"), str) or not hmac.compare_digest(first["secret"], secret):
            send(sock, {"type": "denied"})
            return
        send(sock, {"type": "ok"})
        sock.settimeout(None)
        print("Laptop connected.", flush=True)
        for event in stream:
            kind = event.get("type")
            if kind == "key":
                vk = event.get("vk")
                down = event.get("down")
                if type(vk) is not int or not 0 < vk < 256 or type(down) is not bool:
                    raise ValueError("Invalid key")
                key = keyboard.KeyCode.from_vk(vk)
                if down:
                    kb.press(key)
                    held_keys.add(vk)
                else:
                    kb.release(key)
                    held_keys.discard(vk)
            elif kind == "move":
                dx, dy = event.get("dx"), event.get("dy")
                if type(dx) is not int or type(dy) is not int or abs(dx) > 10000 or abs(dy) > 10000:
                    raise ValueError("Invalid movement")
                ms.move(dx, dy)
            elif kind == "button":
                name, down = event.get("button"), event.get("down")
                if name not in buttons or type(down) is not bool:
                    raise ValueError("Invalid button")
                if down:
                    ms.press(buttons[name]); held_buttons.add(name)
                else:
                    ms.release(buttons[name]); held_buttons.discard(name)
            elif kind == "scroll":
                dx, dy = event.get("dx"), event.get("dy")
                if type(dx) is not int or type(dy) is not int or abs(dx) > 100 or abs(dy) > 100:
                    raise ValueError("Invalid scroll")
                ms.scroll(dx, dy)
            elif kind == "release":
                for vk in list(held_keys):
                    kb.release(keyboard.KeyCode.from_vk(vk))
                for name in list(held_buttons):
                    ms.release(buttons[name])
                held_keys.clear(); held_buttons.clear()
            else:
                raise ValueError("Unknown message")
    except (OSError, ValueError, TypeError, KeyError, StopIteration) as exc:
        print(f"Connection ended: {exc}", flush=True)
    finally:
        for vk in held_keys:
            kb.release(keyboard.KeyCode.from_vk(vk))
        for name in held_buttons:
            ms.release(buttons[name])
        sock.close()
        print("Laptop disconnected; held inputs released.", flush=True)


def main():
    cert, key, secret, pin = setup()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cert, key)
    print("PC receiver ready. Keep this window open.")
    print("PC IP address(es):", ", ".join(local_ips()) or "Run ipconfig to find IPv4 address")
    print("Port:", PORT)
    print("Certificate fingerprint:", pin)
    print("Pairing secret:", secret, flush=True)
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", PORT))
        server.listen(1)
        while True:
            raw, address = server.accept()
            try:
                raw.settimeout(10)
                client = ctx.wrap_socket(raw, server_side=True)
                serve_client(client, secret)
            except (OSError, ssl.SSLError) as exc:
                print(f"Connection from {address[0]} failed: {exc}", flush=True)
                raw.close()


if __name__ == "__main__":
    main()
