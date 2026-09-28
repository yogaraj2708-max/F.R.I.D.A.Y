"""
F.R.I.D.A.Y. 3.0 — Context Models & Permission Definitions
Defines DesktopContext snapshots and explicit permission gates.
"""

from enum import Enum
from typing import Optional, List, Tuple
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ContextPermission(str, Enum):
    SCREEN = "permission_screen_access"
    CLIPBOARD = "permission_clipboard_access"
    FILE_INDEXING = "permission_file_indexing"
    MEMORY = "permission_memory"
    BACKGROUND_CONTEXT = "permission_background_context"


class ContextPermissionError(PermissionError):
    """Raised when an attempt is made to access a context source the user has disabled."""
    def __init__(self, permission: ContextPermission, message: str = ""):
        self.permission = permission
        msg = f"Access to '{permission.value}' is disabled by user settings."
        if message:
            msg += f" {message}"
        super().__init__(msg)


class DesktopContext(BaseModel):
    """
    Structured snapshot of permitted desktop context sources.
    FRIDAY must not silently use context the user has disabled.
    """
    active_window: Optional[str] = None
    active_process: Optional[str] = None
    selected_text: Optional[str] = None
    clipboard_text: Optional[str] = None
    screen_dimensions: Optional[Tuple[int, int]] = None
    recent_files: List[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
