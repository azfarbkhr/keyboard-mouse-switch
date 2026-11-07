"""Run on the laptop: python controller.py"""
import ctypes
import queue
import socket
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from pynput import keyboard, mouse
from common import PORT, connect, send

CTRL = {0x11, 0xA2, 0xA3}
ALT = {0x12, 0xA4, 0xA5}
SPACE = 0x20
KEY_DOWN, KEY_UP = {0x100, 0x104}, {0x101, 0x105}


class App:
    def __init__(self, root):
        self.root = root
        self.lock = threading.RLock()
        self.sock = None
        self.remote = False
        self.pressed = set()
        self.swallow_keyups = set()
        self.swallow_buttons = set()
        self.remote_buttons = set()
        self.outgoing = queue.Queue(maxsize=8192)
        self.ui_events = queue.Queue()
        self.hotkey_used = False
        self.status = tk.StringVar(value="Disconnected — laptop has control")
        self.host = tk.StringVar()
        self.port = tk.StringVar(value=str(PORT))
        self.pin = tk.StringVar()
        self.secret = tk.StringVar()
        root.title("Keyboard & Mouse Switch — Laptop")
        root.resizable(False, False)
        frame = ttk.Frame(root, padding=16)
        frame.grid(sticky="nsew")
        for row, (label, var, show) in enumerate([
            ("PC IP address", self.host, ""), ("Port", self.port, ""),
            ("PC certificate fingerprint", self.pin, ""), ("Pairing secret", self.secret, "*")]):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(frame, textvariable=var, width=67, show=show).grid(row=row, column=1, columnspan=3, sticky="ew", padx=(10, 0))
        self.connect_button = ttk.Button(frame, text="Connect", command=self.connect_clicked)
        self.connect_button.grid(row=4, column=1, sticky="w", pady=10)
        ttk.Button(frame, text="Disconnect", command=self.disconnect).grid(row=4, column=2, sticky="w", pady=10)
        ttk.Label(frame, text="Control:").grid(row=5, column=0, sticky="w")
        ttk.Button(frame, text="Laptop", command=self.to_local).grid(row=5, column=1, sticky="w")
        ttk.Button(frame, text="PC", command=self.to_remote).grid(row=5, column=2, sticky="w")
        ttk.Label(frame, textvariable=self.status, wraplength=610).grid(row=6, column=0, columnspan=4, sticky="w", pady=(15, 4))
        ttk.Label(frame, text="Return to laptop: Ctrl + Alt + Space", wraplength=610).grid(row=7, column=0, columnspan=4, sticky="w")
        self.klistener = keyboard.Listener(on_press=lambda key: None, win32_event_filter=self.key_filter)
        self.mlistener = mouse.Listener(on_move=lambda x, y: None, win32_event_filter=self.mouse_filter)
        self.klistener.start(); self.mlistener.start()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.pump_ui)

    def post_status(self, value):
        self.ui_events.put(("status", value))

    def pump_ui(self):
        try:
            while True:
                kind, value = self.ui_events.get_nowait()
                if kind == "status": self.status.set(value)
                elif kind == "connect_enabled": self.connect_button.config(state="normal")
        except queue.Empty:
            pass
        self.root.after(100, self.pump_ui)

    def connect_clicked(self):
        if self.sock:
            return
        try:
            port = int(self.port.get())
            if not self.host.get().strip() or not self.secret.get() or not 1 <= port <= 65535:
                raise ValueError("Enter the PC address, port, fingerprint and secret.")
        except ValueError as exc:
            messagebox.showerror("Connection", str(exc)); return
        self.connect_button.config(state="disabled")
        self.status.set("Connecting…")
        args = (self.host.get().strip(), port, self.pin.get(), self.secret.get())
        threading.Thread(target=self.connect_worker, args=args, daemon=True).start()

    def connect_worker(self, host, port, pin, secret):
        try:
            sock, stream = connect(host, port, pin, secret)
            with self.lock:
                self.sock = sock
                self.outgoing = queue.Queue(maxsize=8192)
                outgoing = self.outgoing
            self.post_status("Connected — laptop has control")
            threading.Thread(target=self.sender, args=(sock, outgoing), daemon=True).start()
            threading.Thread(target=self.reader, args=(sock, stream), daemon=True).start()
        except Exception as exc:
            self.post_status(f"Connection failed: {exc}")
            self.ui_events.put(("connect_enabled", True))

    def sender(self, sock, outgoing):
        try:
            while True:
                msg = outgoing.get()
                if msg is None: return
                send(sock, msg)
        except (OSError, ValueError):
            self.connection_lost(sock)

    def reader(self, sock, stream):
        try:
            for _ in stream: pass
        except (OSError, ValueError):
            pass
        self.connection_lost(sock)

    def connection_lost(self, sock):
        with self.lock:
            if self.sock is not sock: return
            self._local_locked()
            self.sock = None
            try: sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            sock.close()
            try: self.outgoing.put_nowait(None)
            except queue.Full: pass
        self.post_status("Disconnected — laptop has control")
        self.ui_events.put(("connect_enabled", True))

    def disconnect(self):
        with self.lock: sock = self.sock
        if sock: self.connection_lost(sock)

    def enqueue(self, event):
        try:
            self.outgoing.put_nowait(event)
        except queue.Full:
            # Never block a Windows hook; close the connection and fail safe.
            sock = self.sock
            if sock: threading.Thread(target=self.connection_lost, args=(sock,), daemon=True).start()

    def _local_locked(self):
        if self.remote:
            self.swallow_keyups.update(self.pressed)
            self.swallow_buttons.update(self.remote_buttons)
            self.remote_buttons.clear()
            self.remote = False
            self.enqueue({"type": "release"})

    def to_local(self):
        with self.lock:
            self._local_locked()
            connected = self.sock is not None
        self.post_status("Connected — laptop has control" if connected else "Disconnected — laptop has control")

    def to_remote(self):
        with self.lock:
            if not self.sock:
                messagebox.showinfo("Not connected", "Connect to the PC first."); return
            if self.pressed:
                self.post_status("Release all keyboard keys before switching to the PC."); return
            self.remote = True
        self.post_status("Connected — PC has control. Press Ctrl + Alt + Space to return.")

    def key_filter(self, msg, data):
        if data.flags & 0x10: return True  # Ignore injected events.
        vk = data.vkCode
        down = msg in KEY_DOWN
        up = msg in KEY_UP
        if not (down or up): return True
        with self.lock:
            if down: self.pressed.add(vk)
            else: self.pressed.discard(vk)
            if up and vk in self.swallow_keyups:
                self.swallow_keyups.discard(vk)
                self.klistener.suppress_event()
            if self.remote:
                if down and vk == SPACE and self.pressed.intersection(CTRL) and self.pressed.intersection(ALT):
                    self._local_locked()
                    self.post_status("Connected — laptop has control")
                else:
                    self.enqueue({"type": "key", "vk": vk, "down": down})
                self.klistener.suppress_event()
        return True

    def mouse_filter(self, msg, data):
        if data.flags & 1: return True  # Ignore injected events.
        button_map = {0x201: ("left", True), 0x202: ("left", False),
                      0x204: ("right", True), 0x205: ("right", False),
                      0x207: ("middle", True), 0x208: ("middle", False),
                      0x20B: ("x1" if (data.mouseData >> 16) == 1 else "x2", True),
                      0x20C: ("x1" if (data.mouseData >> 16) == 1 else "x2", False)}
        with self.lock:
            if msg in button_map:
                name, down = button_map[msg]
                if not down and name in self.swallow_buttons:
                    self.swallow_buttons.discard(name)
                    self.mlistener.suppress_event()
            if not self.remote: return True
            if msg == 0x200:
                point = ctypes.wintypes.POINT()
                ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
                dx, dy = data.pt.x - point.x, data.pt.y - point.y
                if dx or dy: self.enqueue({"type": "move", "dx": dx, "dy": dy})
            elif msg in button_map:
                name, down = button_map[msg]
                if down: self.remote_buttons.add(name)
                else: self.remote_buttons.discard(name)
                self.enqueue({"type": "button", "button": name, "down": down})
            elif msg in (0x20A, 0x20E):
                delta = ctypes.c_short((data.mouseData >> 16) & 0xffff).value
                steps = int(delta / 120) or (1 if delta > 0 else -1)
                self.enqueue({"type": "scroll", "dx": steps if msg == 0x20E else 0, "dy": steps if msg == 0x20A else 0})
            self.mlistener.suppress_event()
        return True

    def close(self):
        self.disconnect()
        self.klistener.stop(); self.mlistener.stop()
        self.root.destroy()


if __name__ == "__main__":
    import ctypes.wintypes
    root = tk.Tk()
    App(root)
    root.mainloop()
