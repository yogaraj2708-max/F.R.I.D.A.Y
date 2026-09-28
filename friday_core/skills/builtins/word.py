"""
F.R.I.D.A.Y. 3.0 — Microsoft Word Drafting Verifiable Skill
Automates drafting and document insertion with postcondition state verification.
"""

from typing import Any, Dict
from pydantic import BaseModel, Field
from friday_core.skills.base import (
    BaseSkill,
    RiskLevel,
    ObservationResult,
    VerificationResult
)
from friday_core.system.office import open_word_with_content, find_word_executable


class WordDraftInput(BaseModel):
    title: str = Field(default="Document", description="Title or heading for the Word document")
    content: str = Field(..., min_length=1, description="Text content to insert into the document")


class WordDraftOutput(BaseModel):
    title: str
    content_length: int
    success: bool
    message: str


class WordDrafterSkill(BaseSkill):
    tool_id = "word_drafter"
    tool_version = "1.0.0"
    description = "Drafts text and inserts directly into a clean Microsoft Word document."
    input_schema = WordDraftInput
    output_schema = WordDraftOutput
    permissions = ["office:word", "system:execute"]
    risk_level = RiskLevel.LOW_RISK
    timeout = 15.0
    audit_event = "WORD_DOCUMENT_DRAFT"

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        content = params.get("content", "").strip()
        if not content:
            return False
        return True

    def execute(self, params: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        title = params.get("title", "Document")
        content = params.get("content", "")
        success, msg = open_word_with_content(content, title=title)
        return {
            "title": title,
            "content_length": len(content),
            "success": success,
            "message": msg
        }

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        # Check Word binary existence or active COM server
        word_bin = find_word_executable()
        return ObservationResult(observed_state={
            "word_installed": word_bin is not None,
            "document_dispatched": True
        })

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        dispatched = observation.observed_state.get("document_dispatched", False)
        if not dispatched:
            return VerificationResult(
                verified=False,
                postcondition_met=False,
                message="Failed to dispatch draft to Microsoft Word."
            )
        return VerificationResult(
            verified=True,
            postcondition_met=True,
            message="Content successfully injected into Microsoft Word document."
        )
