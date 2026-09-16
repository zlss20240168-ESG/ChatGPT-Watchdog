import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Protocol


class WatchState(str, Enum):
    DISARMED = "DISARMED"
    RUNNING = "RUNNING"
    STALLED = "STALLED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


class Adapter(Protocol):
    def is_busy(self) -> bool: ...
    def task_completed(self) -> bool: ...
    def send_resume(self, text: str) -> bool: ...


@dataclass
class WatchdogConfig:
    timeout_seconds: int = 300
    max_retries: int = 3
    poll_seconds: int = 5
    resume_text: str = (
        "go\n"
        "請從上一個未完成步驟繼續執行。\n"
        "不要重做已完成內容。\n"
        "如果目前仍有工具正在執行，則不要重新啟動。"
    )


@dataclass
class WatchdogRuntime:
    config: WatchdogConfig
    adapter: Adapter
    armed: bool = False
    state: WatchState = WatchState.DISARMED
    retry_count: int = 0
    last_progress_monotonic: float = field(default_factory=time.monotonic)
    log_dir: Path = field(default_factory=lambda: Path("logs"))

    def __post_init__(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _log(self, message: str) -> None:
        ts = datetime.now().isoformat(timespec="seconds")
        line = f"{ts} | {self.state.value} | {message}\n"
        (self.log_dir / "watchdog.log").open("a", encoding="utf-8").write(line)

    def arm(self) -> None:
        self.armed = True
        self.state = WatchState.RUNNING
        self.retry_count = 0
        self.last_progress_monotonic = time.monotonic()
        self._log("Watchdog armed")

    def disarm(self) -> None:
        self.armed = False
        self.state = WatchState.DISARMED
        self._log("Watchdog disarmed")

    def mark_progress(self) -> None:
        self.last_progress_monotonic = time.monotonic()
        self.retry_count = 0
        if self.armed:
            self.state = WatchState.RUNNING
        self._log("Progress heartbeat")

    def tick(self) -> WatchState:
        if not self.armed:
            self.state = WatchState.DISARMED
            return self.state

        if self.adapter.task_completed():
            self.disarm()
            self._log("Task completed")
            return self.state

        if self.adapter.is_busy():
            self.state = WatchState.RUNNING
            self._log("Adapter reports active work")
            return self.state

        idle = time.monotonic() - self.last_progress_monotonic
        if idle < self.config.timeout_seconds:
            self.state = WatchState.RUNNING
            return self.state

        if self.retry_count >= self.config.max_retries:
            self.state = WatchState.RECOVERY_REQUIRED
            self._log("Retry limit reached; manual recovery required")
            return self.state

        self.state = WatchState.STALLED
        self.retry_count += 1
        self._log(f"Stall detected; resume attempt #{self.retry_count}")

        ok = self.adapter.send_resume(self.config.resume_text)
        if ok:
            self.last_progress_monotonic = time.monotonic()
            self.state = WatchState.RUNNING
            self._log("Resume command sent")
        else:
            self._log("Resume command failed")

        return self.state


class DemoAdapter:
    """Safe development adapter. It does not control ChatGPT yet."""

    def __init__(self) -> None:
        self.busy = False
        self.completed = False

    def is_busy(self) -> bool:
        return self.busy

    def task_completed(self) -> bool:
        return self.completed

    def send_resume(self, text: str) -> bool:
        print("=== RESUME COMMAND ===")
        print(text)
        return True


def main() -> None:
    config = WatchdogConfig(timeout_seconds=15, max_retries=3, poll_seconds=2)
    runtime = WatchdogRuntime(config=config, adapter=DemoAdapter())
    runtime.arm()
    print("ChatGPT Watchdog demo armed. Ctrl+C to stop.")
    try:
        while runtime.armed:
            state = runtime.tick()
            print(f"state={state.value} retry={runtime.retry_count}")
            time.sleep(config.poll_seconds)
    except KeyboardInterrupt:
        runtime.disarm()
        print("Stopped.")


if __name__ == "__main__":
    main()
