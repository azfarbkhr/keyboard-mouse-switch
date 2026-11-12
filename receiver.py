"""Receiver panel: accepts TLS connections from a controller and injects input."""
import ctypes
import datetime
import hmac
import ipaddress
import json
import queue
import secrets
import socket
import ssl
import threading
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from tkinter import ttk

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pynput import keyboard, mouse
from pynput.mouse._win32 import INPUT, INPUT_union, MOUSEINPUT, SendInput

from common import PORT, fingerprint, messages, send

DATA = Path(__file__).resolve().parent / "receiver-data"
USER32 = ctypes.windll.user32
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE = ctypes.c_void_p(-3)
MONITOR_CALLBACK = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
)
MOVE_ABSOLUTE_ON_VIRTUAL_DESKTOP = MOUSEINPUT.MOVE | 0x8000 | 0x4000
POINTER_IDLE_SECONDS = 0.030

# DPI awareness contexts and monitor handles are pointer-sized on Windows.
USER32.SetThreadDpiAwarenessContext.argtypes = (ctypes.c_void_p,)
USER32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p


def setup():
    DATA.mkdir(exist_ok=True)
    cert, key, config = DATA / "cert.pem", DATA / "key.pem", DATA / "config.json"
    if not cert.exists() or not key.exists():
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Keyboard Mouse Switch")])
        now = datetime.datetime.now(datetime.timezone.utc)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(private.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .sign(private, hashes.SHA256())
        )
        key.write_bytes(
            private.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    if not config.exists():
        config.write_text(json.dumps({"secret": secrets.token_urlsafe(24)}), encoding="utf-8")
    secret = json.loads(config.read_text(encoding="utf-8"))["secret"]
    certificate = x509.load_pem_x509_certificate(cert.read_bytes())
    return cert, key, secret, fingerprint(certificate.public_bytes(serialization.Encoding.DER))


def local_ips():
    try:
        return sorted(
            {
                info[4][0]
                for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
                if not ipaddress.ip_address(info[4][0]).is_loopback
            }
        )
    except OSError:
        return []


class Pointer:
    """Apply the controller's pixel deltas using absolute Windows mouse input."""

    def __init__(self):
        self.last_move = None

    def sync(self):
        point = wintypes.POINT()
        clip = wintypes.RECT()
        monitors = []

        @MONITOR_CALLBACK
        def collect_monitor(_monitor, _dc, bounds, _data):
            rect = bounds.contents
            monitors.append((rect.left, rect.top, rect.right, rect.bottom))
            return True

        if (
            not USER32.GetPhysicalCursorPos(ctypes.byref(point))
            or not USER32.GetClipCursor(ctypes.byref(clip))
            or not USER32.EnumDisplayMonitors(None, None, collect_monitor, 0)
            or not monitors
        ):
            raise OSError("Could not read receiver cursor or display bounds")

        self.x, self.y = point.x, point.y
        self.left = min(left for left, _, _, _ in monitors)
        self.top = min(top for _, top, _, _ in monitors)
        self.width = max(right for _, _, right, _ in monitors) - self.left
        self.height = max(bottom for _, _, _, bottom in monitors) - self.top
        self.bounds = []
        for left, top, right, bottom in monitors:
            left, top = max(left, clip.left), max(top, clip.top)
            right, bottom = min(right, clip.right), min(bottom, clip.bottom)
            if left < right and top < bottom:
                self.bounds.append((left, top, right, bottom))
        if not self.bounds:
            raise OSError("Receiver cursor is confined outside its display bounds")

    def move(self, dx, dy):
        now = time.monotonic()
        if self.last_move is None or now - self.last_move >= POINTER_IDLE_SECONDS:
            self.sync()

        # SendInput queues events. Keep the last target through a burst so the
        # next delta still applies if Windows has yet to move the cursor there.
        x, y = self.x + dx, self.y + dy
        targets = (
            (min(max(x, left), right - 1), min(max(y, top), bottom - 1))
            for left, top, right, bottom in self.bounds
        )
        self.x, self.y = min(targets, key=lambda target: (target[0] - x)**2 + (target[1] - y)**2)

        # Choose the center of each pixel's bin in the normalized 16-bit range.
        event = INPUT(type=INPUT.MOUSE, value=INPUT_union(mi=MOUSEINPUT(
            dx=(2 * (self.x - self.left) + 1) * 32768 // self.width,
            dy=(2 * (self.y - self.top) + 1) * 32768 // self.height,
            dwFlags=MOVE_ABSOLUTE_ON_VIRTUAL_DESKTOP,
        )))
        if SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
            raise OSError("Windows rejected mouse movement")
        self.last_move = now


def serve_client(sock, secret, on_status=None):
    kb, ms = keyboard.Controller(), mouse.Controller()
    pointer = Pointer()
    held_keys, held_buttons = set(), set()
    buttons = {
        "left": mouse.Button.left,
        "right": mouse.Button.right,
        "middle": mouse.Button.middle,
        "x1": mouse.Button.x1,
        "x2": mouse.Button.x2,
    }
    authenticated = False
    previous_dpi_context = None
    try:
        sock.settimeout(10)
        stream = messages(sock)
        first = next(stream)
        if (
            first.get("type") != "auth"
            or not isinstance(first.get("secret"), str)
            or not hmac.compare_digest(first["secret"], secret)
        ):
            send(sock, {"type": "denied"})
            if on_status:
                on_status("Authentication failed — waiting for controller")
            return
        send(sock, {"type": "ok"})
        sock.settimeout(None)
        authenticated = True
        previous_dpi_context = USER32.SetThreadDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE)
        if not previous_dpi_context:
            raise OSError("Could not enable physical screen coordinates on the receiver")
        if on_status:
            on_status("Controller connected")
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
                pointer.move(dx, dy)
            elif kind == "button":
                name, down = event.get("button"), event.get("down")
                if name not in buttons or type(down) is not bool:
                    raise ValueError("Invalid button")
                if down:
                    ms.press(buttons[name])
                    held_buttons.add(name)
                else:
                    ms.release(buttons[name])
                    held_buttons.discard(name)
            elif kind == "scroll":
                dx, dy = event.get("dx"), event.get("dy")
                if type(dx) is not int or type(dy) is not int or abs(dx) > 100 or abs(dy) > 100:
                    raise ValueError("Invalid scroll")
                ms.scroll(dx, dy)
            elif kind == "release":
                pointer.last_move = None
                for vk in list(held_keys):
                    kb.release(keyboard.KeyCode.from_vk(vk))
                for name in list(held_buttons):
                    ms.release(buttons[name])
                held_keys.clear()
                held_buttons.clear()
            else:
                raise ValueError("Unknown message")
    except (OSError, ValueError, TypeError, KeyError, StopIteration) as exc:
        if authenticated and on_status:
            on_status(f"Controller disconnected ({exc}); held inputs released — waiting for controller")
    finally:
        if previous_dpi_context:
            USER32.SetThreadDpiAwarenessContext(previous_dpi_context)
        for vk in held_keys:
            kb.release(keyboard.KeyCode.from_vk(vk))
        for name in held_buttons:
            ms.release(buttons[name])
        try:
            sock.close()
        except OSError:
            pass
        if authenticated and on_status:
            on_status("Controller disconnected; held inputs released — waiting for controller")


class ReceiverPanel(ttk.Frame):
    """Tkinter panel and TLS server lifecycle for the receiver role."""

    def __init__(self, parent):
        super().__init__(parent, padding=16)
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.stopped = False
        self.server_sock = None
        self.client_sock = None
        self.ui_events = queue.Queue()
        self._pump_id = None
        self._copy_after_ids = {}

        self.ips_var = tk.StringVar(value="Loading…")
        self.port_var = tk.StringVar(value=str(PORT))
        self.pin_var = tk.StringVar(value="Loading…")
        self.secret_var = tk.StringVar(value="Loading…")
        self.status_var = tk.StringVar(value="Starting receiver…")

        fields = [
            ("Receiver IP address(es)", self.ips_var),
            ("Port", self.port_var),
            ("Certificate fingerprint", self.pin_var),
            ("Pairing secret", self.secret_var),
        ]
        for row, (label, var) in enumerate(fields):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(self, textvariable=var, width=67, state="readonly").grid(
                row=row, column=1, sticky="ew", padx=(10, 6)
            )
            btn = ttk.Button(self, text="Copy", width=8)
            btn.configure(command=lambda v=var, b=btn: self.copy_value(v, b))
            btn.grid(row=row, column=2, sticky="e", pady=4)

        ttk.Label(self, textvariable=self.status_var, wraplength=610).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(15, 4)
        )
        ttk.Label(
            self,
            text="Keep this window open. Allow Python on private networks if Windows Firewall asks.",
            wraplength=610,
        ).grid(row=5, column=0, columnspan=3, sticky="w")

        self._pump_id = self.after(100, self.pump_ui)
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def copy_value(self, var, button):
        value = var.get()
        if not value or value == "Loading…":
            return
        self.clipboard_clear()
        self.clipboard_append(value)
        button.configure(text="Copied")
        prior = self._copy_after_ids.pop(button, None)
        if prior is not None:
            self.after_cancel(prior)

        def reset():
            self._copy_after_ids.pop(button, None)
            if not self.stopped and button.winfo_exists():
                button.configure(text="Copy")

        self._copy_after_ids[button] = self.after(1500, reset)

    def post_status(self, value):
        if not self.stop_event.is_set():
            self.ui_events.put(("status", value))

    def pump_ui(self):
        if self.stopped:
            return
        try:
            while True:
                kind, value = self.ui_events.get_nowait()
                if kind == "status":
                    self.status_var.set(value)
                elif kind == "config":
                    ips_text, port_text, pin, secret = value
                    self.ips_var.set(ips_text)
                    self.port_var.set(port_text)
                    self.pin_var.set(pin)
                    self.secret_var.set(secret)
        except queue.Empty:
            pass
        self._pump_id = self.after(100, self.pump_ui)

    def serve(self):
        try:
            cert, key, secret, pin = setup()
            ips_text = ", ".join(local_ips()) or "Run ipconfig to find IPv4 address"
            self.ui_events.put(("config", (ips_text, str(PORT), pin, secret)))
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.load_cert_chain(cert, key)
        except Exception as exc:
            self.post_status(f"Failed to initialize receiver: {exc}")
            return

        server = socket.socket()
        try:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("0.0.0.0", PORT))
            server.listen(1)
            server.settimeout(0.5)
            with self.lock:
                if self.stop_event.is_set():
                    server.close()
                    return
                self.server_sock = server
            self.post_status("Listening — waiting for controller")
            while not self.stop_event.is_set():
                try:
                    raw, address = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    raw.settimeout(10)
                    client = ctx.wrap_socket(raw, server_side=True)
                except (OSError, ssl.SSLError) as exc:
                    self.post_status(f"Connection from {address[0]} failed: {exc}")
                    try:
                        raw.close()
                    except OSError:
                        pass
                    continue
                with self.lock:
                    if self.stop_event.is_set():
                        client.close()
                        break
                    self.client_sock = client
                serve_client(client, secret, on_status=self.post_status)
                with self.lock:
                    self.client_sock = None
        except OSError as exc:
            if not self.stop_event.is_set():
                self.post_status(f"Failed to listen on port {PORT}: {exc}")
        finally:
            with self.lock:
                self.server_sock = None
            try:
                server.close()
            except OSError:
                pass

    def stop(self):
        self.stopped = True
        self.stop_event.set()
        if self._pump_id is not None:
            self.after_cancel(self._pump_id)
            self._pump_id = None
        for after_id in list(self._copy_after_ids.values()):
            self.after_cancel(after_id)
        self._copy_after_ids.clear()
        with self.lock:
            client = self.client_sock
            server = self.server_sock
        if client:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                client.close()
            except OSError:
                pass
        if server:
            try:
                server.close()
            except OSError:
                pass
        if self.thread.is_alive():
            self.thread.join(timeout=1.5)


def main():
    root = tk.Tk()
    root.title("Keyboard & Mouse Switch — Receiver")
    root.resizable(False, False)
    panel = ReceiverPanel(root)
    panel.grid(sticky="nsew")
    root.protocol("WM_DELETE_WINDOW", lambda: (panel.stop(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
