import ctypes
import threading
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

from watchdog import WatchdogConfig, WatchdogRuntime, WatchState


class WindowsForegroundAdapter:
    """Conservative V1 actuator for a user-selected foreground ChatGPT browser/app window.

    Safety model:
    - Never searches for or steals focus from another window.
    - ARM captures the currently focused window as the target.
    - Resume is sent only if that exact target is still foreground.
    - Requires the title to contain an allowed ChatGPT marker.
    - V1 cannot reliably infer internal ChatGPT tool activity; the user can DISARM at any time.
    """

    ALLOWED_TITLE_MARKERS = ("chatgpt",)

    def __init__(self) -> None:
        self.user32 = ctypes.windll.user32
        self.target_hwnd = None
        self.target_title = ""

    def _foreground(self):
        return self.user32.GetForegroundWindow()

    def _title(self, hwnd) -> str:
        length = self.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        self.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

    def capture_target(self) -> tuple[bool, str]:
        hwnd = self._foreground()
        title = self._title(hwnd)
        if not title or not any(m in title.lower() for m in self.ALLOWED_TITLE_MARKERS):
            return False, f"Foreground window is not recognized as ChatGPT: {title or '(no title)'}"
        self.target_hwnd = hwnd
        self.target_title = title
        return True, title

    def target_is_foreground(self) -> bool:
        return self.target_hwnd is not None and self._foreground() == self.target_hwnd

    def is_busy(self) -> bool:
        # Conservative V1: UI automation cannot safely infer hidden tool execution.
        # Future browser/Hermes adapters will provide semantic busy-state detection.
        return False

    def task_completed(self) -> bool:
        return False

    def send_resume(self, text: str) -> bool:
        if not self.target_is_foreground():
            return False
        current_title = self._title(self.target_hwnd)
        if not any(m in current_title.lower() for m in self.ALLOWED_TITLE_MARKERS):
            return False

        # Put resume text on clipboard, paste, then submit. Clipboard is restored when possible.
        root = tk._default_root
        if root is None:
            return False
        try:
            old = root.clipboard_get()
        except Exception:
            old = None
        try:
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
            self.user32.keybd_event(0x11, 0, 0, 0)       # Ctrl down
            self.user32.keybd_event(0x56, 0, 0, 0)       # V down
            self.user32.keybd_event(0x56, 0, 2, 0)       # V up
            self.user32.keybd_event(0x11, 0, 2, 0)       # Ctrl up
            time.sleep(0.15)
            self.user32.keybd_event(0x0D, 0, 0, 0)       # Enter down
            self.user32.keybd_event(0x0D, 0, 2, 0)       # Enter up
            return True
        finally:
            if old is not None:
                try:
                    time.sleep(0.1)
                    root.clipboard_clear()
                    root.clipboard_append(old)
                    root.update()
                except Exception:
                    pass


class WatchdogApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ChatGPT Watchdog V1")
        self.geometry("760x560")
        self.minsize(680, 500)
        self.adapter = WindowsForegroundAdapter()
        self.runtime = None
        self.worker = None
        self.stop_event = threading.Event()

        self.timeout_var = tk.StringVar(value="5")
        self.retry_var = tk.StringVar(value="3")
        self.status_var = tk.StringVar(value="DISARMED")
        self.target_var = tk.StringVar(value="No target captured")
        self.resume_text = (
            "go\n"
            "請從上一個未完成步驟繼續執行。\n"
            "不要重做已完成內容。\n"
            "如果目前仍有工具正在執行，則不要重新啟動。"
        )
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        ttk.Label(frame, text="ChatGPT Watchdog", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", **pad)
        ttk.Label(frame, text="V1 Safety-first Windows Controller").grid(row=1, column=0, columnspan=4, sticky="w", **pad)

        ttk.Label(frame, text="Status:").grid(row=2, column=0, sticky="e", **pad)
        ttk.Label(frame, textvariable=self.status_var, font=("Segoe UI", 11, "bold")).grid(row=2, column=1, sticky="w", **pad)
        ttk.Label(frame, text="Target:").grid(row=3, column=0, sticky="e", **pad)
        ttk.Label(frame, textvariable=self.target_var, wraplength=520).grid(row=3, column=1, columnspan=3, sticky="w", **pad)

        ttk.Label(frame, text="Timeout (minutes):").grid(row=4, column=0, sticky="e", **pad)
        ttk.Entry(frame, textvariable=self.timeout_var, width=8).grid(row=4, column=1, sticky="w", **pad)
        ttk.Label(frame, text="Max retries:").grid(row=4, column=2, sticky="e", **pad)
        ttk.Entry(frame, textvariable=self.retry_var, width=8).grid(row=4, column=3, sticky="w", **pad)

        ttk.Button(frame, text="ARM (capture foreground ChatGPT)", command=self.arm).grid(row=5, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Button(frame, text="DISARM / Emergency Stop", command=self.disarm).grid(row=5, column=2, columnspan=2, sticky="ew", **pad)

        ttk.Label(frame, text="Runtime Log").grid(row=6, column=0, columnspan=4, sticky="w", **pad)
        self.log_box = scrolledtext.ScrolledText(frame, height=18, state="disabled", font=("Consolas", 9))
        self.log_box.grid(row=7, column=0, columnspan=4, sticky="nsew", **pad)

        ttk.Label(frame, text="Safety: V1 only sends Resume while the captured ChatGPT window remains foreground.", wraplength=680).grid(row=8, column=0, columnspan=4, sticky="w", **pad)

        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)
        frame.rowconfigure(7, weight=1)

    def ui_log(self, text: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{stamp} | {text}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def arm(self) -> None:
        if self.runtime and self.runtime.armed:
            return
        try:
            timeout_minutes = max(1, int(self.timeout_var.get()))
            max_retries = max(1, int(self.retry_var.get()))
        except ValueError:
            messagebox.showerror("Invalid settings", "Timeout and retry values must be integers.")
            return

        ok, detail = self.adapter.capture_target()
        if not ok:
            messagebox.showwarning("Target not captured", detail + "\n\nBring the ChatGPT window to the foreground, then click ARM again.")
            return

        config = WatchdogConfig(
            timeout_seconds=timeout_minutes * 60,
            max_retries=max_retries,
            poll_seconds=2,
            resume_text=self.resume_text,
        )
        self.runtime = WatchdogRuntime(config=config, adapter=self.adapter, log_dir=Path.home() / "ChatGPT-Watchdog" / "logs")
        self.runtime.arm()
        self.stop_event.clear()
        self.target_var.set(detail)
        self.status_var.set("RUNNING")
        self.ui_log(f"ARMED target={detail} timeout={timeout_minutes}m retries={max_retries}")
        self.worker = threading.Thread(target=self._loop, daemon=True)
        self.worker.start()

    def _loop(self) -> None:
        while not self.stop_event.is_set() and self.runtime and self.runtime.armed:
            state = self.runtime.tick()
            self.after(0, self._update_state, state)
            time.sleep(self.runtime.config.poll_seconds)

    def _update_state(self, state: WatchState) -> None:
        self.status_var.set(state.value)
        if state == WatchState.RECOVERY_REQUIRED:
            self.ui_log("RECOVERY_REQUIRED: retry limit reached or Resume failed repeatedly.")

    def disarm(self) -> None:
        self.stop_event.set()
        if self.runtime and self.runtime.armed:
            self.runtime.disarm()
        self.status_var.set("DISARMED")
        self.ui_log("DISARMED / Emergency Stop")

    def on_close(self) -> None:
        self.disarm()
        self.destroy()


def main() -> None:
    app = WatchdogApp()
    app.mainloop()


if __name__ == "__main__":
    main()
