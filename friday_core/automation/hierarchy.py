"""
F.R.I.D.A.Y. 3.0 — Windows UI Automation Hierarchy & Policy
Enforces the mandatory execution priority order:
1. Semantic UI Automation (UIA accessibility tree)
2. Application shortcuts / hotkeys
3. Bounded keyboard & mouse interaction
4. Vision-based localization (Phase 7)
5. Coordinate interaction (strictly as final fallback)
"""

from enum import IntEnum, Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel


class AutomationPriority(IntEnum):
    SEMANTIC_UIA = 1
    APPLICATION_SHORTCUTS = 2
    BOUNDED_INPUT = 3
    VISION = 4
    COORDINATES_FALLBACK = 5


class AutomationOutcome(BaseModel):
    success: bool
    priority_level: int
    level_name: str
    action: str
    target: str
    postcondition_verified: bool
    message: str = ""
    details: Dict[str, Any] = {}
