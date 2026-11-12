"""Unified entry point: uv run python main.py"""
import tkinter as tk
from tkinter import ttk

from controller import ControllerPanel
from receiver import ReceiverPanel


class SwitchApp:
    """Single window that lets the user choose Controller or Receiver mode."""

    def __init__(self, root):
        self.root = root
        self.root.title("Keyboard & Mouse Switch")
        self.root.resizable(False, False)
        self.active_panel = None
        self.container = ttk.Frame(root)
        self.container.grid(sticky="nsew")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.show_chooser()

    def clear_container(self):
        self.stop_active()
        for child in self.container.winfo_children():
            child.destroy()

    def stop_active(self):
        if self.active_panel is not None:
            self.active_panel.stop()
            self.active_panel = None

    def show_chooser(self):
        self.clear_container()
        self.root.title("Keyboard & Mouse Switch")
        frame = ttk.Frame(self.container, padding=24)
        frame.grid(sticky="nsew")

        ttk.Label(
            frame,
            text="Select how this machine should act:",
            font=("TkDefaultFont", 11, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

        role_cards = [
            (
                "Controller",
                "Share this machine's keyboard and mouse\nwith a receiver.",
                lambda: self.select_role("controller"),
            ),
            (
                "Receiver",
                "Accept keyboard and mouse input from\na controller.",
                lambda: self.select_role("receiver"),
            ),
        ]
        for col, (label, desc, command) in enumerate(role_cards):
            card = ttk.LabelFrame(frame, text=label, padding=14)
            card.grid(row=1, column=col, sticky="nsew", padx=(0, 12) if col == 0 else 0)
            ttk.Label(card, text=desc, justify="left").grid(row=0, column=0, sticky="w", pady=(0, 12))
            ttk.Button(card, text=f"Start as {label}", command=command).grid(row=1, column=0, sticky="ew")

    def select_role(self, role):
        self.clear_container()
        title_role = "Controller" if role == "controller" else "Receiver"
        self.root.title(f"Keyboard & Mouse Switch — {title_role}")

        header = ttk.Frame(self.container, padding=(16, 12, 16, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text=f"Role: {title_role}",
            font=("TkDefaultFont", 10, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Switch Role", command=self.show_chooser).grid(row=0, column=1, sticky="e")

        ttk.Separator(self.container, orient="horizontal").grid(row=1, column=0, sticky="ew")

        panel_cls = ControllerPanel if role == "controller" else ReceiverPanel
        self.active_panel = panel_cls(self.container)
        self.active_panel.grid(row=2, column=0, sticky="nsew")

    def close(self):
        self.stop_active()
        self.root.destroy()


def main():
    root = tk.Tk()
    SwitchApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

