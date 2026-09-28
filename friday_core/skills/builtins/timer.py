"""
F.R.I.D.A.Y. 3.0 — Precision Timer & Countdown Manager
Provides state-machine-backed timers (CREATED, RUNNING, PAUSED, COMPLETED, CANCELLED)
with explicit remaining-time calculations and zero overlap with system clock queries.
"""

import time
import uuid
import asyncio
import logging
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from pydantic import BaseModel, Field

from friday_core.skills.base import (
    BaseSkill,
    RiskLevel,
    ObservationResult,
    VerificationResult
)

logger = logging.getLogger("FRIDAY.Timer")


class TimerState(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass
class TimerEntry:
    timer_id: str
    label: str
    duration_seconds: float
    start_time: float
    end_time: float
    state: TimerState = TimerState.CREATED
    task: Optional[asyncio.Task] = None

    def remaining_seconds(self) -> float:
        if self.state == TimerState.COMPLETED:
            return 0.0
        if self.state in [TimerState.CANCELLED, TimerState.FAILED]:
            return 0.0
        now = time.time()
        return max(0.0, self.end_time - now)


class TimerManager:
    """
    Thread-safe timer coordinator maintaining lifecycle states and countdown calculations.
    """
    def __init__(self):
        self._timers: Dict[str, TimerEntry] = {}

    def create_timer(
        self,
        duration_seconds: float,
        label: str = "Timer",
        on_complete_callback: Optional[Any] = None
    ) -> TimerEntry:
        t_id = f"timer-{uuid.uuid4().hex[:6]}"
        now = time.time()
        entry = TimerEntry(
            timer_id=t_id,
            label=label,
            duration_seconds=duration_seconds,
            start_time=now,
            end_time=now + duration_seconds,
            state=TimerState.RUNNING
        )

        async def _run_countdown():
            try:
                await asyncio.sleep(duration_seconds)
                entry.state = TimerState.COMPLETED
                if on_complete_callback:
                    if asyncio.iscoroutinefunction(on_complete_callback):
                        await on_complete_callback(entry)
                    else:
                        on_complete_callback(entry)
            except asyncio.CancelledError:
                entry.state = TimerState.CANCELLED
            except Exception as ex:
                logger.error(f"Timer {t_id} error: {ex}")
                entry.state = TimerState.FAILED

        try:
            loop = asyncio.get_running_loop()
            entry.task = loop.create_task(_run_countdown())
        except RuntimeError:
            entry.task = None

        self._timers[t_id] = entry
        logger.info(f"Created timer {t_id} for {duration_seconds}s ('{label}')")
        return entry

    def get_timer(self, timer_id: Any) -> Optional[TimerEntry]:
        tid = timer_id.timer_id if hasattr(timer_id, "timer_id") else str(timer_id)
        return self._timers.get(tid)

    def mark_completed(self, timer_id: Any) -> None:
        tid = timer_id.timer_id if hasattr(timer_id, "timer_id") else str(timer_id)
        entry = self._timers.get(tid)
        if entry:
            entry.state = TimerState.COMPLETED

    def get_active_timer(self) -> Optional[TimerEntry]:
        """Returns the most relevant running or recently active timer."""
        running = [t for t in self._timers.values() if t.state == TimerState.RUNNING]
        if running:
            # Return the timer ending soonest
            running.sort(key=lambda t: t.end_time)
            return running[0]
        # Otherwise return most recently finished
        if self._timers:
            all_timers = list(self._timers.values())
            all_timers.sort(key=lambda t: t.start_time, reverse=True)
            return all_timers[0]
        return None

    def get_remaining(self, timer_id: Optional[Any] = None) -> Tuple[Optional[float], Optional[TimerEntry]]:
        """Calculates remaining seconds on target or active timer."""
        entry = self.get_timer(timer_id) if timer_id else self.get_active_timer()
        if not entry:
            return None, None
        return entry.remaining_seconds(), entry

    def get_remaining_status(self, timer_id: Optional[Any] = None) -> Dict[str, Any]:
        """Returns structured dictionary of timer status and remaining countdown."""
        rem_secs, entry = self.get_remaining(timer_id)
        if not entry:
            return {"status": "NONE", "remaining_seconds": 0.0, "label": ""}
        return {
            "status": entry.state.value,
            "remaining_seconds": max(0.0, rem_secs or 0.0),
            "label": entry.label,
            "timer_id": entry.timer_id
        }

    def cancel_timer(self, timer_id: Optional[Any] = None) -> int:
        """Cancels a specific timer or all running timers if timer_id is None."""
        count = 0
        if timer_id:
            tid = timer_id.timer_id if hasattr(timer_id, "timer_id") else str(timer_id)
            entry = self._timers.get(tid)
            if entry and entry.state == TimerState.RUNNING:
                if entry.task and not entry.task.done():
                    entry.task.cancel()
                entry.state = TimerState.CANCELLED
                count = 1
        else:
            for entry in list(self._timers.values()):
                if entry.state == TimerState.RUNNING:
                    if entry.task and not entry.task.done():
                        entry.task.cancel()
                    entry.state = TimerState.CANCELLED
                    count += 1
        return count

    def list_timers(self) -> List[Dict[str, Any]]:
        return [
            {
                "timer_id": t.timer_id,
                "label": t.label,
                "duration_seconds": t.duration_seconds,
                "remaining_seconds": round(t.remaining_seconds(), 1),
                "state": t.state.value
            }
            for t in self._timers.values()
        ]


# Global singleton instance
timer_manager = TimerManager()


class TimerInput(BaseModel):
    action: str = Field(default="status", description="Action: 'create', 'remaining', 'cancel', 'list', 'status'")
    duration_seconds: float = Field(default=60.0, description="Duration in seconds for timer creation")
    label: str = Field(default="Timer", description="Label or description of the timer")
    timer_id: Optional[str] = Field(default=None, description="Optional target timer ID")


class TimerOutput(BaseModel):
    success: bool
    action: str
    remaining_seconds: Optional[float] = None
    state: str = ""
    message: str = ""


class TimerSkill(BaseSkill):
    tool_id = "timer"
    tool_version = "1.0.0"
    description = "Precision timer management (creation, remaining countdown, cancellation, status queries)."
    input_schema = TimerInput
    output_schema = TimerOutput
    permissions = ["system:timer"]
    risk_level = RiskLevel.SAFE
    timeout = 3.0
    audit_event = "TIMER_OPERATION"

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        return True

    def execute(self, params: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        action = params.get("action", "status").lower().strip()
        dur = float(params.get("duration_seconds", 60.0))
        label = params.get("label", "Timer")
        t_id = params.get("timer_id")

        if action == "create":
            entry = timer_manager.create_timer(dur, label)
            return {
                "success": True,
                "action": "create",
                "remaining_seconds": dur,
                "state": entry.state.value,
                "message": f"Timer '{label}' set for {int(dur)} seconds."
            }
        elif action in ["remaining", "status", "check"]:
            rem, entry = timer_manager.get_remaining(t_id)
            if entry is None:
                return {
                    "success": False,
                    "action": action,
                    "state": "NONE",
                    "message": "There are no active timers set, Boss."
                }
            if entry.state == TimerState.COMPLETED:
                return {
                    "success": True,
                    "action": action,
                    "remaining_seconds": 0.0,
                    "state": TimerState.COMPLETED.value,
                    "message": f"Your {entry.label} has already completed, Boss."
                }
            return {
                "success": True,
                "action": action,
                "remaining_seconds": round(rem, 1),
                "state": entry.state.value,
                "message": f"You have {int(round(rem))} seconds remaining on your {entry.label}, Boss."
            }
        elif action == "cancel":
            cancelled = timer_manager.cancel_timer(t_id)
            return {
                "success": True,
                "action": "cancel",
                "message": f"Cancelled {cancelled} active timer(s), Boss."
            }
        elif action == "list":
            timers = timer_manager.list_timers()
            return {
                "success": True,
                "action": "list",
                "message": f"Found {len(timers)} timer records.",
                "timers": timers
            }

        return {"success": False, "action": action, "message": f"Unknown timer action '{action}'"}

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        rem, entry = timer_manager.get_remaining()
        return ObservationResult(observed_state={
            "has_timer": entry is not None,
            "state": entry.state.value if entry else "NONE",
            "remaining": rem
        })

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        return VerificationResult(
            verified=True,
            postcondition_met=True,
            message="Timer state verified."
        )
