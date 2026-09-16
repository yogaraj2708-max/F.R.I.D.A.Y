"""
F.R.I.D.A.Y. 2.0 - Security Action Models & Intent Classification
Defines ActionIntent, ActionResult, and permission Tiers (0..3).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional

@dataclass
class ActionIntent:
    """Structured representation of any system or external action."""
    action: str                        # e.g. 'open_app', 'delete_file', 'kill_process', 'get_telemetry'
    target: str = ""                   # e.g. file path, app name, URL, process name
    params: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""                   # plain-language justification
    source: str = "typed"              # 'voice', 'typed', 'llm'
    tier: Optional[int] = None         # 0, 1, 2, or 3 (auto-classified if None)
    confirmed: bool = False            # True if explicit confirmation received
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass
class ActionResult:
    """Outcome of action execution by the Gatekeeper."""
    success: bool
    message: str
    tier: int
    audit_id: str
    data: Optional[Any] = None
    dry_run_text: str = ""
    requires_confirmation: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
