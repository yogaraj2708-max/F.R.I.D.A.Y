"""
F.R.I.D.A.Y. 3.0 — Browser Agent 9-Stage Pluggable Skills
Registers browser navigation, extraction, and download as verifiable BaseSkill tools.
"""

import os
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from friday_core.skills.base import (
    BaseSkill,
    RiskLevel,
    SkillResult,
    VerificationResult
)
from friday_core.browser.models import (
    BrowserAction,
    BrowserActionType,
    BrowserObservation
)
logger = logging.getLogger("FRIDAY.BrowserSkills")


class BrowserNavigateInput(BaseModel):
    url: str = Field(..., description="Target HTTP/HTTPS URL to navigate to")


class BrowserDownloadInput(BaseModel):
    url: str = Field(..., description="Remote file URL to download")
    target_path: str = Field(..., description="Local file destination path")


class BrowserNavigateSkill(BaseSkill):
    """
    Skill for navigating to web pages and observing title, text, and interactive elements.
    """
    tool_id = "browser_navigate"
    tool_version = "3.0.0"
    description = "Navigates to a URL and inspects page elements, links, and content."
    input_schema = BrowserNavigateInput
    risk_level = RiskLevel.SAFE

    def __init__(self, controller: Optional[Any] = None):
        super().__init__()
        self._controller = controller
        self._last_obs: Optional[BrowserObservation] = None

    @property
    def controller(self):
        if self._controller is not None:
            return self._controller
        from friday_core.browser.controller import browser_controller
        return browser_controller

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        url = params.get("url", "")
        return url.startswith("http://") or url.startswith("https://")

    def execute(self, params: Dict[str, Any], operation_id: str) -> Any:
        action = BrowserAction(action_type=BrowserActionType.NAVIGATE, url=params["url"])
        self._last_obs = self.controller.execute(action)
        return self._last_obs.model_dump()

    def observe(self, operation_id: str) -> Dict[str, Any]:
        if self._last_obs and self._last_obs.state:
            return {
                "title": self._last_obs.state.title,
                "url": self._last_obs.state.url,
                "element_count": len(self._last_obs.state.interactive_elements)
            }
        return {"error": "No observation recorded."}

    def verify(self, observation: Dict[str, Any]) -> bool:
        if self._last_obs is None:
            return False
        action = BrowserAction(action_type=BrowserActionType.NAVIGATE, url=observation.get("url"))
        ver = self.controller.verify_action(action, self._last_obs)
        return ver.verified

    def cancel(self, operation_id: str) -> None:
        self.controller.stop()


class BrowserDownloadSkill(BaseSkill):
    """
    Skill for downloading files with postcondition verification and automatic rollback.
    """
    tool_id = "browser_download"
    tool_version = "3.0.0"
    description = "Downloads a file from the web with disk and integrity verification."
    input_schema = BrowserDownloadInput
    risk_level = RiskLevel.CAUTION

    def __init__(self, controller: Optional[Any] = None):
        super().__init__()
        self._controller = controller
        self._last_obs: Optional[BrowserObservation] = None
        self._target_path: Optional[str] = None

    @property
    def controller(self):
        if self._controller is not None:
            return self._controller
        from friday_core.browser.controller import browser_controller
        return browser_controller

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        url = params.get("url", "")
        dest = params.get("target_path", "")
        if not (url.startswith("http://") or url.startswith("https://")):
            return False
        if not dest:
            return False
        return True

    def execute(self, params: Dict[str, Any], operation_id: str) -> Any:
        self._target_path = params["target_path"]
        action = BrowserAction(
            action_type=BrowserActionType.DOWNLOAD,
            url=params["url"],
            target_path=self._target_path
        )
        self._last_obs = self.controller.execute(action)
        return self._last_obs.model_dump()

    def observe(self, operation_id: str) -> Dict[str, Any]:
        exists = os.path.exists(self._target_path) if self._target_path else False
        size = os.path.getsize(self._target_path) if exists else 0
        return {"file_exists": exists, "file_size": size, "path": self._target_path}

    def verify(self, observation: Dict[str, Any]) -> bool:
        if not observation.get("file_exists") or observation.get("file_size", 0) == 0:
            return False
        if self._last_obs is None:
            return False
        action = BrowserAction(
            action_type=BrowserActionType.DOWNLOAD,
            url="",
            target_path=self._target_path
        )
        ver = self.controller.verify_action(action, self._last_obs)
        return ver.verified

    def rollback(self, operation_id: str) -> bool:
        """Rollback: deletes partially downloaded or corrupted file."""
        if self._target_path and os.path.exists(self._target_path):
            try:
                os.remove(self._target_path)
                return True
            except Exception as e:
                logger.error(f"Failed to rollback download '{self._target_path}': {e}")
                return False
        return True

    def cancel(self, operation_id: str) -> None:
        self.controller.stop()
        self.rollback(operation_id)
