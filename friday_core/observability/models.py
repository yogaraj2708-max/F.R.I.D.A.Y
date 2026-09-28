"""
F.R.I.D.A.Y. 3.0 — Structured Event Observability Models
Defines immutable operational audit events for complete post-execution transparency.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class StructuredEvent(BaseModel):
    """
    Immutable event record capturing operational telemetry, status, and verification evidence.
    """
    event_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    mission_id: Optional[str] = None
    step_id: Optional[str] = None
    tool: str
    action: str
    parameters: Dict[str, Any] = Field(default_factory=dict)  # Redacted
    result: Optional[Any] = None
    duration_ms: float = 0.0
    status: str = "SUCCESS"  # SUCCESS, FAILED, BLOCKED, CANCELLED
    error: Optional[str] = None
    verification_result: Optional[Dict[str, Any]] = None
