"""
F.R.I.D.A.Y. 3.0 — Global Emergency Stop Subsystem
Instant, thread-safe cancellation across TTS, STT, Planner, Executor, UI, and child processes.
Triggered via ESC key, Ctrl+Shift+X, or voice command "STOP".
"""

import threading
import logging
import psutil
from typing import Any, Callable, Dict, List, Set, Optional
from datetime import datetime, timezone

logger = logging.getLogger("FRIDAY.EmergencyStop")


class EmergencyStopManager:
    """
    Coordinates global emergency stops.
    Guarantees no new side-effecting step may begin once STOP is triggered.
    """
    def __init__(self):
        self._stop_event = threading.Event()
        self._handlers: Dict[str, Callable[[], None]] = {}
        self._tracked_pids: Set[int] = set()
        self._stop_source: Optional[str] = None
        self._stopped_at: Optional[str] = None
        self._lock = threading.Lock()

    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def register_handler(self, name: str, callback: Callable[[], None]) -> None:
        """Register subsystem cancellation handler (TTS, STT, Executor, etc.)."""
        with self._lock:
            self._handlers[name] = callback

    def unregister_handler(self, name: str) -> None:
        with self._lock:
            self._handlers.pop(name, None)

    def track_pid(self, pid: int) -> None:
        """Register child process PID for emergency kill."""
        with self._lock:
            self._tracked_pids.add(pid)

    def untrack_pid(self, pid: int) -> None:
        with self._lock:
            self._tracked_pids.discard(pid)

    def trigger_stop(self, source: str = "manual") -> Dict[str, Any]:
        """
        Trigger global emergency stop immediately.
        Aborts TTS, STT, active tasks, and terminates child processes.
        """
        with self._lock:
            self._stop_event.set()
            self._stop_source = source
            self._stopped_at = datetime.now(timezone.utc).isoformat()

        logger.warning(f"🛑 [EMERGENCY STOP TRIGGERED] Source: {source} at {self._stopped_at}")

        # 1. Execute all subsystem cancellation handlers
        executed_handlers = []
        for name, handler in list(self._handlers.items()):
            try:
                handler()
                executed_handlers.append(name)
            except Exception as ex:
                logger.error(f"Error in emergency stop handler '{name}': {ex}")

        # 2. Terminate all tracked child processes
        killed_pids = []
        for pid in list(self._tracked_pids):
            try:
                if psutil.pid_exists(pid):
                    proc = psutil.Process(pid)
                    proc.terminate()
                    killed_pids.append(pid)
            except Exception as ex:
                logger.debug(f"Failed to terminate PID {pid}: {ex}")

        with self._lock:
            self._tracked_pids.clear()

        return {
            "status": "STOPPED",
            "source": source,
            "timestamp": self._stopped_at,
            "handlers_executed": executed_handlers,
            "killed_pids": killed_pids
        }

    def reset(self) -> None:
        """Resets emergency stop state back to operational status."""
        with self._lock:
            self._stop_event.clear()
            self._stop_source = None
            self._stopped_at = None
        logger.info("Emergency stop reset. System returning to IDLE.")


# Global Singleton Emergency Stop Manager
emergency_stop = EmergencyStopManager()
