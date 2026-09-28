"""
F.R.I.D.A.Y. 3.0 — 5-Tier Persistent Memory Models
Defines the five cognitive memory tiers:
Tier 1: Working Memory (active conversation context)
Tier 2: Task Memory (active mission DAG & checkpoints)
Tier 3: Episodic Memory (past completed workflows & documented failures)
Tier 4: Preference Memory (user-confirmed preferences)
Tier 5: Semantic Memory (indexed knowledge & entity facts)
"""

from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class MemoryTier(str, Enum):
    TIER_1_WORKING = "TIER_1_WORKING"
    TIER_2_TASK = "TIER_2_TASK"
    TIER_3_EPISODIC = "TIER_3_EPISODIC"
    TIER_4_PREFERENCE = "TIER_4_PREFERENCE"
    TIER_5_SEMANTIC = "TIER_5_SEMANTIC"


class MemoryDomain(str, Enum):
    PROJECT = "PROJECT"
    PERSONAL = "PERSONAL"
    TECHNICAL = "TECHNICAL"
    RESEARCH = "RESEARCH"


class MemoryItem(BaseModel):
    """
    Individual atomic memory record across Tiers 3, 4, and 5.
    Must be user inspectable, editable, and deletable with complete provenance.
    """
    id: str
    tier: MemoryTier
    key: str
    value: Any
    source: str = "assistant"
    confirmed_by_user: bool = False
    session_id: Optional[str] = None
    scope: str = "global"  # "global" or "session" or specific session ID
    domain: str = MemoryDomain.PERSONAL.value
    version: int = 1
    confidence: float = 1.0
    retention_status: str = "active"  # "active", "historical", "deleted"
    verification_state: str = "verified"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
