from __future__ import annotations

import queue
import math

try:
    import tkinter as tk
except Exception:  # pragma: no cover
    tk = None


class ListeningStatusWindow:
    def __init__(self) -> None:
        self.root = None
        self.label = None
        self.wave_canvas = None
        self._wave_bars = []
        self._phase = 0.0
        self._listening = False
        self._actions: queue.Queue[tuple[str, str]] = queue.Queue()

    def show(self, text: str = "RAHU is listening...") -> None:
        self._actions.put(("show", text))

    def start(self) -> bool:
        if tk is None:
            return False
        if self.root is not None:
            return True

        try:
            self.root = tk.Tk()
            self.root.title("RAHU Assistant")
            self.root.geometry("340x150")
            self.root.configure(bg="#0f172a")
            self.root.attributes("-topmost", True)
            self.root.overrideredirect(True)

            frame = tk.Frame(self.root, bg="#111827", padx=18, pady=18)
            frame.pack(fill="both", expand=True)

            self.label = tk.Label(
                frame,
                text="RAHU is ready",
                fg="#dbeafe",
                bg="#111827",
                font=("Segoe UI", 12, "bold"),
            )
            self.label.pack(anchor="center", pady=4)

            self.wave_canvas = tk.Canvas(
                frame,
                width=264,
                height=36,
                bg="#111827",
                highlightthickness=0,
            )
            self.wave_canvas.pack(anchor="center", pady=2)
            self._wave_bars = [
                self.wave_canvas.create_line(x, 18, x, 18, fill="#475569", width=3, capstyle="round")
                for x in range(8, 264, 9)
            ]

            sub = tk.Label(
                frame,
                text="Listening for your next command",
                fg="#86efac",
                bg="#111827",
                font=("Segoe UI", 9),
            )
            sub.pack(anchor="center")

            self.root.withdraw()
            self.root.after(50, self._process_actions)
            self.root.after(70, self._animate_wave)
            return True
        except Exception:
            if self.root is not None:
                try:
                    self.root.destroy()
                except Exception:
                    pass
            self.root = None
            self.label = None
            self.wave_canvas = None
            self._wave_bars = []
            return False

    def run(self) -> None:
        if self.root is not None:
            self.root.mainloop()

    def _process_actions(self) -> None:
        if self.root is None:
            return

        while True:
            try:
                action, text = self._actions.get_nowait()
            except queue.Empty:
                break

            if action == "show" and self.label is not None:
                self.label.config(text=text)
                self._listening = "listening" in text.casefold()
                self.root.deiconify()
                self.root.lift()
            elif action == "hide":
                self._listening = False
                self.root.withdraw()
            elif action == "stop":
                self._listening = False
                self.root.destroy()
                self.root = None
                self.label = None
                self.wave_canvas = None
                self._wave_bars = []
                return

        self.root.after(50, self._process_actions)

    def _animate_wave(self) -> None:
        if self.root is None or self.wave_canvas is None:
            return

        self._phase += 0.38
        for index, bar in enumerate(self._wave_bars):
            height = 3 + abs(math.sin(self._phase + index * 0.34)) * 14 if self._listening else 2
            self.wave_canvas.coords(bar, 8 + index * 9, 18 - height, 8 + index * 9, 18 + height)
            self.wave_canvas.itemconfigure(bar, fill="#38bdf8" if self._listening else "#475569")
        self.root.after(70, self._animate_wave)

    def set_text(self, text: str) -> None:
        self.show(text)

    def close(self) -> None:
        self._actions.put(("hide", ""))

    def stop(self) -> None:
        self._actions.put(("stop", ""))
