"""
F.R.I.D.A.Y. 3.0 — Proactive Background Scheduler
Executes recurring, interval, and event-driven background tasks.
Integrates with Emergency Stop to immediately pause or halt all execution.
"""

import time
import uuid
import threading
import logging
from typing import Dict, List, Optional, Callable, Any
from friday_core.agent.emergency_stop import emergency_stop
from friday_core.scheduler.models import (
    ScheduledTask,
    ScheduledTaskType,
    TaskPriority
)
from friday_core.scheduler.proactive_monitor import SystemHealthMonitor

logger = logging.getLogger("FRIDAY.Scheduler")


class ProactiveScheduler:
    """
    Background job runner for proactive agent activities and system health checks.
    """
    def __init__(self, check_interval: float = 1.0):
        self.check_interval = check_interval
        self._tasks: Dict[str, ScheduledTask] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self.monitor = SystemHealthMonitor()

        # Register system telemetry task by default (every 60s)
        self.add_interval_task("system_health_monitor", interval_seconds=60.0, callback=self.monitor.check_health)

        # Register with emergency stop
        try:
            emergency_stop.register_handler("scheduler", self.pause_all)
        except Exception:
            pass

    def add_interval_task(
        self,
        name: str,
        interval_seconds: float,
        callback: Callable,
        mission_goal: Optional[str] = None,
        priority: TaskPriority = TaskPriority.NORMAL
    ) -> str:
        """Schedules a recurring task every N seconds."""
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        now = time.time()
        task = ScheduledTask(
            task_id=task_id,
            name=name,
            task_type=ScheduledTaskType.INTERVAL,
            interval_seconds=interval_seconds,
            mission_goal=mission_goal,
            priority=priority,
            next_run=now + interval_seconds
        )
        with self._lock:
            self._tasks[task_id] = task
            self._callbacks[task_id] = callback
        logger.info(f"Scheduled task '{name}' ({task_id}) every {interval_seconds}s.")
        return task_id

    def add_once_task(self, name: str, delay_seconds: float, callback: Callable) -> str:
        """Schedules a one-shot task to execute after delay_seconds."""
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        now = time.time()
        task = ScheduledTask(
            task_id=task_id,
            name=name,
            task_type=ScheduledTaskType.ONCE,
            interval_seconds=delay_seconds,
            next_run=now + delay_seconds
        )
        with self._lock:
            self._tasks[task_id] = task
            self._callbacks[task_id] = callback
        return task_id

    def remove_task(self, task_id: str) -> bool:
        with self._lock:
            removed = self._tasks.pop(task_id, None) is not None
            self._callbacks.pop(task_id, None)
            return removed

    def list_tasks(self) -> List[ScheduledTask]:
        with self._lock:
            return list(self._tasks.values())

    def pause_all(self):
        """Emergency stop handler pausing all scheduled executions."""
        logger.warning("ProactiveScheduler paused due to Emergency Stop.")
        with self._lock:
            for t in self._tasks.values():
                t.is_active = False

    def resume_all(self):
        with self._lock:
            for t in self._tasks.values():
                t.is_active = True

    def tick(self, now: Optional[float] = None) -> List[str]:
        """
        Processes a single evaluation tick across all registered tasks.
        Can be manually called for deterministic unit testing.
        Returns list of executed task_ids.
        """
        if emergency_stop.is_stopped():
            return []

        current_time = now if now is not None else time.time()
        executed = []

        with self._lock:
            tasks_snapshot = list(self._tasks.values())

        for task in tasks_snapshot:
            if not task.is_active:
                continue

            if task.next_run is not None and current_time >= task.next_run:
                callback = self._callbacks.get(task.task_id)
                if callback:
                    try:
                        callback()
                        executed.append(task.task_id)
                    except Exception as e:
                        logger.error(f"Error executing scheduled task '{task.name}': {e}")

                # Update schedule
                task.last_run = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(current_time))
                task.run_count += 1

                if task.task_type == ScheduledTaskType.ONCE:
                    self.remove_task(task.task_id)
                else:
                    task.next_run = current_time + task.interval_seconds

        return executed

    def start(self):
        """Starts background monitoring daemon."""
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._run_loop, daemon=True, name="FRIDAY.Scheduler")
        self._worker_thread.start()
        logger.info("ProactiveScheduler daemon started.")

    def stop(self):
        self._stop_event.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=2.0)
            self._worker_thread = None

    def _run_loop(self):
        while not self._stop_event.is_set():
            self.tick()
            self._stop_event.wait(timeout=self.check_interval)


# Global Singleton Scheduler
proactive_scheduler = ProactiveScheduler()
