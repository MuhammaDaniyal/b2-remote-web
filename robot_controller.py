from __future__ import annotations

import queue
import signal
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.b2.sport.sport_client import SportClient


@dataclass(frozen=True)
class MotionPulse:
    vx: float
    vy: float
    vyaw: float
    duration_seconds: float


class B2Controller:
    """
    Serializes all robot commands through one worker thread.

    A command is a short high-level velocity pulse followed by StopMove().
    New commands are rejected while one is running or already queued.
    """

    COMMANDS: Dict[str, MotionPulse] = {
        "forward": MotionPulse(vx=+0.08, vy=0.00, vyaw=0.00, duration_seconds=0.45),
        "backward": MotionPulse(vx=-0.08, vy=0.00, vyaw=0.00, duration_seconds=0.45),
        "left": MotionPulse(vx=0.00, vy=+0.08, vyaw=0.00, duration_seconds=0.45),
        "right": MotionPulse(vx=0.00, vy=-0.08, vyaw=0.00, duration_seconds=0.45),
        "yaw_left": MotionPulse(vx=0.00, vy=0.00, vyaw=+0.25, duration_seconds=0.80),
        "yaw_right": MotionPulse(vx=0.00, vy=0.00, vyaw=-0.25, duration_seconds=0.80),
    }

    def __init__(self, interface: str) -> None:
        self.interface = interface
        self.client: Optional[SportClient] = None
        self._queue: queue.Queue[str] = queue.Queue(maxsize=1)
        self._worker: Optional[threading.Thread] = None
        self._shutdown = threading.Event()
        self._stop_requested = threading.Event()
        self._busy_lock = threading.Lock()
        self._busy = False
        self._ready = False
        self._last_command: Optional[str] = None

    @property
    def allowed_commands(self):
        return frozenset(self.COMMANDS.keys())

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def busy(self) -> bool:
        with self._busy_lock:
            return self._busy

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    @property
    def last_command(self) -> Optional[str]:
        return self._last_command

    def start(self) -> None:
        ChannelFactoryInitialize(0, self.interface)

        client = SportClient()
        client.SetTimeout(2.0)
        client.Init()

        code, version = client.GetServerApiVersion()
        if code != 0:
            raise RuntimeError(f"B2 sport service did not respond successfully: code={code}")

        self.client = client
        self._ready = True

        self._worker = threading.Thread(
            target=self._worker_loop,
            name="b2-motion-worker",
            daemon=True,
        )
        self._worker.start()

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        print(f"B2 controller ready on {self.interface}; server API {version}")

    def enqueue(self, command_name: str) -> Tuple[bool, str]:
        if not self._ready or self.client is None:
            return False, "not_ready"

        if command_name not in self.COMMANDS:
            return False, "invalid_command"

        if self.busy or not self._queue.empty():
            return False, "busy"

        try:
            self._queue.put_nowait(command_name)
        except queue.Full:
            return False, "busy"

        return True, "accepted"

    def emergency_stop(self) -> None:
        self._stop_requested.set()

        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break

        self._safe_stop()

    def shutdown(self) -> None:
        self._shutdown.set()
        self.emergency_stop()

        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=2.0)

        self._ready = False

    def _handle_signal(self, *_args) -> None:
        self.shutdown()

    def _worker_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                command_name = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            self._set_busy(True)
            self._stop_requested.clear()
            self._last_command = command_name

            try:
                self._execute(self.COMMANDS[command_name])
            except Exception as exc:
                print(f"Command {command_name!r} failed: {exc}")
            finally:
                self._safe_stop()
                self._set_busy(False)
                self._queue.task_done()

    def _execute(self, pulse: MotionPulse) -> None:
        assert self.client is not None

        result = self.client.Move(
            pulse.vx,
            pulse.vy,
            pulse.vyaw,
        )
        if result != 0:
            raise RuntimeError(f"Move returned {result}")

        deadline = time.monotonic() + pulse.duration_seconds

        while time.monotonic() < deadline:
            if self._shutdown.is_set() or self._stop_requested.is_set():
                break
            time.sleep(0.02)

    def _safe_stop(self) -> None:
        if self.client is None:
            return

        try:
            result = self.client.StopMove()
            if result != 0:
                print(f"Warning: StopMove returned {result}")
        except Exception as exc:
            print(f"Warning: StopMove failed: {exc}")

    def _set_busy(self, value: bool) -> None:
        with self._busy_lock:
            self._busy = value
