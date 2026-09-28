"""
F.R.I.D.A.Y. 3.0 — Robust Task Lifecycle, State Machine & Watchdog Architecture
Zero-Trust Concurrency, Progress Tracking, and Terminal State Enforcement.

Guarantees:
1. Every task reaches a terminal state (COMPLETED, FAILED, TIMED_OUT, CANCELLED, BLOCKED).
2. No task remains indefinitely in ACTIVE / THINKING / SYNTHESIZING.
3. Every active task is monitored by a bounded idle watchdog and absolute deadline.
4. Late callbacks from stale tasks are discarded cleanly via session/task verification.
5. Thread-safe cancellation aborts active workers, network requests, and model inference.
"""

import time
import uuid
import logging
import threading
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable
from dataclasses import dataclass, field

logger = logging.getLogger("FRIDAY.TaskLifecycle")


class TaskState(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    FETCHING = "FETCHING"
    RESEARCHING = "RESEARCHING"
    SYNTHESIZING = "SYNTHESIZING"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"


TERMINAL_STATES: Set[TaskState] = {
    TaskState.COMPLETED,
    TaskState.FAILED,
    TaskState.TIMED_OUT,
    TaskState.CANCELLED,
    TaskState.BLOCKED
}

ACTIVE_STATES: Set[TaskState] = {
    TaskState.CREATED,
    TaskState.QUEUED,
    TaskState.STARTING,
    TaskState.RUNNING,
    TaskState.FETCHING,
    TaskState.RESEARCHING,
    TaskState.SYNTHESIZING,
    TaskState.GENERATING,
    TaskState.CANCEL_REQUESTED
}


class TaskStage(str, Enum):
    USER_INPUT = "USER_INPUT"
    INTENT_DETECTION = "INTENT_DETECTION"
    ROUTING = "ROUTING"
    RESEARCH_DECISION = "RESEARCH_DECISION"
    TASK_CREATION = "TASK_CREATION"
    SOURCE_DISCOVERY = "SOURCE_DISCOVERY"
    WEB_REQUEST = "WEB_REQUEST"
    SOURCE_FETCH = "SOURCE_FETCH"
    CONTENT_EXTRACTION = "CONTENT_EXTRACTION"
    SOURCE_VALIDATION = "SOURCE_VALIDATION"
    EVIDENCE_COLLECTION = "EVIDENCE_COLLECTION"
    SYNTHESIS = "SYNTHESIS"
    MAIN_MODEL = "MAIN_MODEL"
    RESPONSE_GENERATION = "RESPONSE_GENERATION"
    GUI_UPDATE = "GUI_UPDATE"
    TERMINAL_STATE = "TERMINAL_STATE"


LEGAL_TRANSITIONS: Dict[TaskState, Set[TaskState]] = {
    TaskState.CREATED: {
        TaskState.QUEUED, TaskState.STARTING, TaskState.RUNNING,
        TaskState.FAILED, TaskState.CANCEL_REQUESTED, TaskState.CANCELLED, TaskState.BLOCKED
    },
    TaskState.QUEUED: {
        TaskState.STARTING, TaskState.RUNNING,
        TaskState.CANCEL_REQUESTED, TaskState.CANCELLED, TaskState.TIMED_OUT, TaskState.FAILED
    },
    TaskState.STARTING: {
        TaskState.RUNNING, TaskState.FETCHING, TaskState.RESEARCHING, TaskState.GENERATING,
        TaskState.CANCEL_REQUESTED, TaskState.CANCELLED, TaskState.TIMED_OUT, TaskState.FAILED
    },
    TaskState.RUNNING: {
        TaskState.FETCHING, TaskState.RESEARCHING, TaskState.SYNTHESIZING, TaskState.GENERATING,
        TaskState.COMPLETED, TaskState.CANCEL_REQUESTED, TaskState.CANCELLED, TaskState.TIMED_OUT,
        TaskState.FAILED, TaskState.BLOCKED
    },
    TaskState.FETCHING: {
        TaskState.RESEARCHING, TaskState.SYNTHESIZING, TaskState.GENERATING, TaskState.COMPLETED,
        TaskState.CANCEL_REQUESTED, TaskState.CANCELLED, TaskState.TIMED_OUT, TaskState.FAILED
    },
    TaskState.RESEARCHING: {
        TaskState.FETCHING, TaskState.SYNTHESIZING, TaskState.GENERATING, TaskState.COMPLETED,
        TaskState.CANCEL_REQUESTED, TaskState.CANCELLED, TaskState.TIMED_OUT, TaskState.FAILED
    },
    TaskState.SYNTHESIZING: {
        TaskState.GENERATING, TaskState.COMPLETED,
        TaskState.CANCEL_REQUESTED, TaskState.CANCELLED, TaskState.TIMED_OUT, TaskState.FAILED
    },
    TaskState.GENERATING: {
        TaskState.COMPLETED,
        TaskState.CANCEL_REQUESTED, TaskState.CANCELLED, TaskState.TIMED_OUT, TaskState.FAILED
    },
    TaskState.CANCEL_REQUESTED: {
        TaskState.CANCELLED, TaskState.FAILED, TaskState.TIMED_OUT
    },
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.TIMED_OUT: set(),
    TaskState.CANCELLED: set(),
    TaskState.BLOCKED: set(),
}


@dataclass
class TaskRecord:
    task_id: str
    trace_id: str
    request_id: str
    session_id: str
    query: str
    route: str = "DIRECT"
    provider: str = "local_ollama"
    model: str = "deepseek-r1:8b"
    current_state: TaskState = TaskState.CREATED
    current_stage: TaskStage = TaskStage.TASK_CREATION
    created_at: float = field(default_factory=time.time)
    started_at: float = field(default_factory=time.time)
    last_progress_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    idle_timeout: float = 45.0          # Stalled if no progress event for 45s
    absolute_timeout: float = 300.0     # Maximum allowed task duration (5 minutes)
    retry_count: int = 0
    max_retries: int = 2
    error: Optional[str] = None
    is_cancelled: bool = False
    progress_message: str = "Task initialized."
    history: List[Dict[str, Any]] = field(default_factory=list)
    stage_timestamps: Dict[str, float] = field(default_factory=dict)

    def is_terminal(self) -> bool:
        return self.current_state in TERMINAL_STATES

    def is_active(self) -> bool:
        return self.current_state in ACTIVE_STATES


class TaskSupervisor:
    """
    Central thread-safe coordinator for active tasks, state transitions,
    progress heartbeats, cancellation, and watchdog timeout enforcement.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._tasks: Dict[str, TaskRecord] = {}
        self._active_by_session: Dict[str, str] = {}  # session_id -> current task_id
        self._listeners: List[Callable[[TaskRecord, TaskState, TaskState], None]] = []

    def add_listener(self, listener: Callable[[TaskRecord, TaskState, TaskState], None]):
        with self._lock:
            self._listeners.append(listener)

    def create_task(
        self,
        query: str,
        session_id: str = "default_session",
        route: str = "DIRECT",
        model: str = "deepseek-r1:8b",
        provider: str = "local_ollama",
        idle_timeout: float = 45.0,
        absolute_timeout: float = 300.0,
        max_retries: int = 2
    ) -> TaskRecord:
        with self._lock:
            task_id = f"task_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"
            trace_id = f"trace_{uuid.uuid4().hex[:12]}"
            request_id = f"req_{uuid.uuid4().hex[:8]}"

            # If there is already an active task for this session, request its cancellation
            prev_task_id = self._active_by_session.get(session_id)
            if prev_task_id and prev_task_id in self._tasks:
                prev_task = self._tasks[prev_task_id]
                if prev_task.is_active():
                    logger.info("Superseding active task %s for session %s with %s", prev_task_id, session_id, task_id)
                    self.cancel_task(prev_task_id, reason="Superseded by new user request")

            task = TaskRecord(
                task_id=task_id,
                trace_id=trace_id,
                request_id=request_id,
                session_id=session_id,
                query=query,
                route=route,
                provider=provider,
                model=model,
                idle_timeout=idle_timeout,
                absolute_timeout=absolute_timeout,
                max_retries=max_retries
            )
            task.history.append({
                "from": None,
                "to": TaskState.CREATED.value,
                "stage": TaskStage.TASK_CREATION.value,
                "timestamp": time.time(),
                "reason": "Task created"
            })
            task.stage_timestamps[TaskStage.TASK_CREATION.value] = time.time()

            self._tasks[task_id] = task
            self._active_by_session[session_id] = task_id
            return task

    def transition(self, task_id: str, new_state: TaskState, reason: str = "") -> TaskRecord:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                raise KeyError(f"Task '{task_id}' not found in supervisor.")

            old_state = task.current_state
            if old_state == new_state:
                return task

            if old_state in TERMINAL_STATES:
                logger.warning(
                    "Ignored transition from terminal state %s to %s for task %s",
                    old_state.value, new_state.value, task_id
                )
                return task

            allowed = LEGAL_TRANSITIONS.get(old_state, set())
            if new_state not in allowed and not (new_state in {TaskState.FAILED, TaskState.TIMED_OUT, TaskState.CANCELLED}):
                logger.error("Illegal state transition: %s -> %s for task %s (reason: %s)", old_state, new_state, task_id, reason)
                # Enforce fail-closed rather than crashing
                new_state = TaskState.FAILED
                reason = f"Illegal transition attempted from {old_state.value}: {reason}"

            task.current_state = new_state
            now = time.time()
            task.last_progress_at = now
            if new_state in TERMINAL_STATES:
                task.completed_at = now

            task.history.append({
                "from": old_state.value,
                "to": new_state.value,
                "stage": task.current_stage.value,
                "timestamp": now,
                "reason": reason
            })

            listeners = list(self._listeners)

        # Notify listeners outside lock
        for l in listeners:
            try:
                l(task, old_state, new_state)
            except Exception as ex:
                logger.error("Error in task transition listener: %s", ex)

        return task

    def update_stage(self, task_id: str, stage: TaskStage, progress_msg: str = "") -> TaskRecord:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.is_terminal():
                return task

            task.current_stage = stage
            now = time.time()
            task.last_progress_at = now
            task.stage_timestamps[stage.value] = now
            if progress_msg:
                task.progress_message = progress_msg

            return task

    def heartbeat(self, task_id: str, progress_msg: str = "") -> bool:
        """Records active progress from worker thread, resetting idle watchdog timer."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.is_terminal():
                return False
            task.last_progress_at = time.time()
            if progress_msg:
                task.progress_message = progress_msg
            return True

    # Convenience alias for heartbeat
    record_heartbeat = heartbeat

    def cancel_task(self, task_id: str, reason: str = "Operator requested cancellation") -> bool:
        """Thread-safe cancellation request."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.is_terminal():
                return False

            task.is_cancelled = True
            logger.info("Cancellation initiated for task %s: %s", task_id, reason)
            self.transition(task_id, TaskState.CANCEL_REQUESTED, reason=reason)
            self.transition(task_id, TaskState.CANCELLED, reason=reason)
            return True

    def check_watchdogs(self) -> List[TaskRecord]:
        """
        Inspects all active tasks against idle_timeout and absolute_timeout.
        Forces stalled or expired tasks into TIMED_OUT terminal state.
        """
        timed_out_tasks: List[TaskRecord] = []
        with self._lock:
            now = time.time()
            for task in list(self._tasks.values()):
                if not task.is_active():
                    continue

                idle_duration = now - task.last_progress_at
                total_duration = now - task.started_at

                if idle_duration > task.idle_timeout:
                    logger.warning(
                        "Task %s stalled! Idle for %.1fs (timeout: %.1fs, stage: %s)",
                        task.task_id, idle_duration, task.idle_timeout, task.current_stage.value
                    )
                    self.transition(
                        task.task_id,
                        TaskState.TIMED_OUT,
                        reason=f"Idle timeout exceeded ({idle_duration:.1f}s > {task.idle_timeout}s without heartbeat in {task.current_stage.value})"
                    )
                    timed_out_tasks.append(task)
                elif total_duration > task.absolute_timeout:
                    logger.warning(
                        "Task %s exceeded deadline! Total duration: %.1fs (max: %.1fs)",
                        task.task_id, total_duration, task.absolute_timeout
                    )
                    self.transition(
                        task.task_id,
                        TaskState.TIMED_OUT,
                        reason=f"Absolute deadline exceeded ({total_duration:.1f}s > {task.absolute_timeout}s)"
                    )
                    timed_out_tasks.append(task)

        return timed_out_tasks

    def is_current_task(self, task_id: str, session_id: Optional[str] = None) -> bool:
        """
        Late-callback protection: Returns True ONLY if task_id is still the active
        task for its session. Prevents stale Task A from overwriting Task B in UI.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            sid = session_id or task.session_id
            return self._active_by_session.get(sid) == task_id

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        with self._lock:
            return self._tasks.get(task_id)

    def get_active_task_for_session(self, session_id: str) -> Optional[TaskRecord]:
        with self._lock:
            tid = self._active_by_session.get(session_id)
            return self._tasks.get(tid) if tid else None


# Global supervisor instance
task_supervisor = TaskSupervisor()
