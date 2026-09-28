"""
F.R.I.D.A.Y. 3.0 — Browser Agent Models
Defines structured actions, browser states, observations, and verification schemas.
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class BrowserActionType(str, Enum):
    NAVIGATE = "NAVIGATE"
    CLICK = "CLICK"
    TYPE = "TYPE"
    EXTRACT = "EXTRACT"
    DOWNLOAD = "DOWNLOAD"
    INSPECT = "INSPECT"
    CLOSE = "CLOSE"


class BrowserAction(BaseModel):
    action_type: BrowserActionType
    url: Optional[str] = None
    selector: Optional[str] = None
    text: Optional[str] = None
    target_path: Optional[str] = None
    timeout_sec: float = 15.0


class InteractiveElement(BaseModel):
    tag: str
    text: str = ""
    href: Optional[str] = None
    element_id: Optional[str] = None
    name: Optional[str] = None
    selector: str


class BrowserState(BaseModel):
    url: str
    title: str
    status_code: int = 200
    text_content: str = ""
    interactive_elements: List[InteractiveElement] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BrowserObservation(BaseModel):
    success: bool
    action_type: BrowserActionType
    state: Optional[BrowserState] = None
    downloaded_file: Optional[str] = None
    downloaded_bytes: int = 0
    error: Optional[str] = None
    duration_ms: float = 0.0


class BrowserVerification(BaseModel):
    verified: bool
    details: str
    false_success_detected: bool = False
