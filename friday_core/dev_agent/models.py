"""
F.R.I.D.A.Y. 3.0 — Developer / Coding Agent Models
Defines code change proposals, unified diffs, syntax verification, and test execution reports.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class CodeFileChange(BaseModel):
    file_path: str
    original_content: str
    proposed_content: str
    diff: str = ""
    is_new: bool = False
    is_deletion: bool = False


class CodeChangePlan(BaseModel):
    plan_id: str
    task_description: str
    changes: List[CodeFileChange] = Field(default_factory=list)
    requires_human_approval: bool = True
    is_approved: bool = False
    status: str = "PROPOSED"  # PROPOSED, APPROVED, APPLIED, REVERTED, REJECTED
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CodeVerificationReport(BaseModel):
    syntax_valid: bool
    tests_passed: bool
    syntax_errors: List[str] = Field(default_factory=list)
    test_output: str = ""
    exit_code: int = 0
    duration_sec: float = 0.0
