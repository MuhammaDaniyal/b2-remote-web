from __future__ import annotations

import queue
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

    # These define direction and the UI's initial values.  Every enqueued
    # command receives its own speed and duration, rather than changing a
    # controller-wide motion setting.
    COMMANDS: Dict[str, MotionPulse] = {
        "forward": MotionPulse(vx=+0.15, vy=0.00, vyaw=0.00, duration_seconds=1.00),
        "backward": MotionPulse(vx=-0.15, vy=0.00, vyaw=0.00, duration_seconds=1.00),
        "left": MotionPulse(vx=0.00, vy=+0.15, vyaw=0.00, duration_seconds=1.00),
        "right": MotionPulse(vx=0.00, vy=-0.15, vyaw=0.00, duration_seconds=1.00),
        "yaw_left": MotionPulse(vx=0.00, vy=0.00, vyaw=+0.35, duration_seconds=1.0),
        "yaw_right": MotionPulse(vx=0.00, vy=0.00, vyaw=-0.35, duration_seconds=1.0),
    }

    def __init__(self, interface: str) -> None:
        self.interface = interface
        self.client: Optional[SportClient] = None
        self._queue: queue.Queue[Tuple[str, Optional[MotionPulse]]] = queue.Queue(maxsize=1)
        self._worker: Optional[threading.Thread] = None
        self._shutdown = threading.Event()
        self._stop_requested = threading.Event()
        self._busy_lock = threading.Lock()
        self._busy = False
        self._ready = False
        self._last_command: Optional[str] = None
        self._shutdown_lock = threading.Lock()
        self._shutdown_complete = False

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

        print(f"B2 controller ready on {self.interface}; server API {version}")

    def enqueue(self, command_name: str, speed: float, duration_seconds: float) -> Tuple[bool, str]:
        if not self._ready or self.client is None:
            return False, "not_ready"

        if command_name not in self.COMMANDS:
            return False, "invalid_command"

        if self.busy or not self._queue.empty():
            return False, "busy"

        pulse = self._pulse_for(command_name, speed, duration_seconds)
        try:
            self._queue.put_nowait((command_name, pulse))
        except queue.Full:
            return False, "busy"

        return True, "accepted"

    def enqueue_sit(self) -> Tuple[bool, str]:
        """Queue Unitree's built-in stand-down motion after stopping locomotion."""
        return self._enqueue_action("sit")

    def enqueue_stand(self) -> Tuple[bool, str]:
        """Queue Unitree's built-in stand-up motion."""
        return self._enqueue_action("stand")

    def _enqueue_action(self, action_name: str) -> Tuple[bool, str]:
        if not self._ready or self.client is None:
            return False, "not_ready"

        if self.busy or not self._queue.empty():
            return False, "busy"

        try:
            self._queue.put_nowait((action_name, None))
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
        with self._shutdown_lock:
            if self._shutdown_complete:
                return
            self._shutdown_complete = True

        self._shutdown.set()
        self.emergency_stop()

        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=2.0)

        self._ready = False

    def _worker_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                command_name, pulse = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            self._set_busy(True)
            self._stop_requested.clear()
            self._last_command = command_name

            try:
                if command_name == "sit":
                    self._execute_sit()
                elif command_name == "stand":
                    self._execute_stand()
                else:
                    assert pulse is not None
                    self._execute(pulse)
            except Exception as exc:
                print(f"Command {command_name!r} failed: {exc}")
            finally:
                if command_name not in {"sit", "stand"}:
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

    def _pulse_for(self, command_name: str, speed: float, duration_seconds: float) -> MotionPulse:
        """Apply a per-command magnitude while preserving the selected direction."""
        direction = self.COMMANDS[command_name]
        return MotionPulse(
            vx=(1.0 if direction.vx > 0 else -1.0 if direction.vx < 0 else 0.0) * speed,
            vy=(1.0 if direction.vy > 0 else -1.0 if direction.vy < 0 else 0.0) * speed,
            vyaw=(1.0 if direction.vyaw > 0 else -1.0 if direction.vyaw < 0 else 0.0) * speed,
            duration_seconds=duration_seconds,
        )

    def _execute_sit(self) -> None:
        """Request the robot's native, controlled stand-down motion."""
        assert self.client is not None

        self._safe_stop()
        result = self.client.StandDown()
        if result != 0:
            raise RuntimeError(f"StandDown returned {result}")

    def _execute_stand(self) -> None:
        """Recover the B2 to standing after its native stand-down posture."""
        assert self.client is not None

        result = self.client.RecoveryStand()
        if result != 0:
            raise RuntimeError(f"RecoveryStand returned {result}")

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
