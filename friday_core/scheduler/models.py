"""
F.R.I.D.A.Y. 3.0 — Proactive Scheduler & Notification Models
Defines scheduled tasks, system event triggers, priorities, and notification payloads.
"""

from enum import Enum
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ScheduledTaskType(str, Enum):
    INTERVAL = "INTERVAL"
    SYSTEM_EVENT = "SYSTEM_EVENT"
    ONCE = "ONCE"


class TaskPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class NotificationMessage(BaseModel):
    id: str
    title: str
    body: str
    urgency: TaskPriority = TaskPriority.NORMAL
    action_button: Optional[str] = None
    action_payload: Optional[Dict[str, Any]] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ScheduledTask(BaseModel):
    task_id: str
    name: str
    task_type: ScheduledTaskType
    interval_seconds: float = 60.0
    mission_goal: Optional[str] = None
    is_active: bool = True
    priority: TaskPriority = TaskPriority.NORMAL
    last_run: Optional[str] = None
    next_run: Optional[float] = None  # epoch timestamp
    run_count: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
