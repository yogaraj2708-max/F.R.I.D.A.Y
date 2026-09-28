"""
F.R.I.D.A.Y. 3.0 — Skill Registry & Dispatcher
Manages registration, discovery, capability exposure, and lifecycle execution of skills.
"""

from typing import Any, Dict, List, Optional, Type
import logging
from friday_core.skills.base import BaseSkill, SkillResult, RiskLevel

logger = logging.getLogger("FRIDAY.SkillRegistry")


class SkillRegistry:
    """
    Central registry for all verifiable tools and skills.
    Ensures safe dispatching, schema exposure, and lifecycle management.
    """
    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        """Register a skill instance."""
        if not isinstance(skill, BaseSkill):
            raise TypeError(f"Skill must inherit from BaseSkill, got {type(skill)}")
        if not skill.tool_id:
            raise ValueError("Skill must define a non-empty tool_id")
        self._skills[skill.tool_id] = skill
        logger.info(f"Registered skill '{skill.tool_id}' v{skill.tool_version} [Risk: {skill.risk_level.value}]")

    def unregister(self, tool_id: str) -> None:
        """Unregister a skill by ID."""
        if tool_id in self._skills:
            del self._skills[tool_id]
            logger.info(f"Unregistered skill '{tool_id}'")

    def _ensure_builtins(self):
        """Auto-registers built-in skills directly into this registry."""
        try:
            from friday_core.skills.builtins.telemetry import SystemTelemetrySkill
            from friday_core.skills.builtins.volume import VolumeControlSkill
            from friday_core.skills.builtins.apps import AppLauncherSkill
            from friday_core.skills.builtins.organizer import FileOrganizerSkill
            from friday_core.skills.builtins.word import WordDrafterSkill
            from friday_core.skills.builtins.ui_automation import (
                UITypeTextSkill,
                AppSearchSkill,
                AppNavigateSkill,
                UIKeyPressSkill,
                SaveFileSkill,
                UIFocusSkill,
                UIVerifyContentSkill
            )
            from friday_core.skills.builtins.content import ContentGenerationSkill
            from friday_core.skills.builtins.calculator import CalculatorSkill
            from friday_core.browser.skills import BrowserNavigateSkill, BrowserDownloadSkill
            from friday_core.skills.builtins.desktop_action import ScreenshotSkill, ClipboardSkill
            from friday_core.skills.builtins.file_ops import FileSearchSkill, FileSelectorSkill, CreateFileSkill
            from friday_core.skills.builtins.timer import TimerSkill
            from friday_core.skills.builtins.memory import MemorySkill

            builtin_classes = [
                SystemTelemetrySkill, VolumeControlSkill, AppLauncherSkill,
                FileOrganizerSkill, WordDrafterSkill, CalculatorSkill,
                UITypeTextSkill, AppSearchSkill, AppNavigateSkill,
                UIKeyPressSkill, SaveFileSkill, UIFocusSkill,
                UIVerifyContentSkill, ContentGenerationSkill,
                BrowserNavigateSkill, BrowserDownloadSkill,
                ScreenshotSkill, ClipboardSkill,
                FileSearchSkill, FileSelectorSkill, CreateFileSkill,
                TimerSkill, MemorySkill
            ]
            for cls in builtin_classes:
                try:
                    inst = cls()
                    if inst.tool_id not in self._skills:
                        self.register(inst)
                except Exception as ex:
                    logger.debug(f"Failed to register builtin {cls}: {ex}")
        except Exception as e:
            logger.debug(f"Skill builtins auto-import note: {e}")

    def get(self, tool_id: str) -> Optional[BaseSkill]:
        """Retrieve a registered skill by ID."""
        if tool_id not in self._skills:
            self._ensure_builtins()
        return self._skills.get(tool_id)

    def get_skill(self, tool_id: str) -> Optional[BaseSkill]:
        """Alias for get(tool_id)."""
        return self.get(tool_id)

    def list_skills(self) -> List[Dict[str, Any]]:
        """Return structured manifest of all registered skills for the Planner."""
        if not self._skills:
            self._ensure_builtins()
        manifest = []
        for s in self._skills.values():
            in_schema = {}
            out_schema = {}
            try:
                if hasattr(s.input_schema, "model_json_schema"):
                    in_schema = s.input_schema.model_json_schema()
            except Exception:
                in_schema = {}
            try:
                if hasattr(s.output_schema, "model_json_schema"):
                    out_schema = s.output_schema.model_json_schema()
            except Exception:
                out_schema = {}

            manifest.append({
                "tool_id": s.tool_id,
                "tool_version": s.tool_version,
                "description": s.description,
                "risk_level": s.risk_level.value,
                "permissions": s.permissions,
                "timeout": s.timeout,
                "input_schema": in_schema,
                "output_schema": out_schema,
                "required_capabilities": s.required_capabilities,
            })
        return manifest

    def execute_skill(
        self,
        tool_id: str,
        params: Dict[str, Any],
        context: Any = None,
        operation_id: Optional[str] = None
    ) -> SkillResult:
        """
        Execute a skill through its 9-stage verification lifecycle.
        """
        skill = self.get(tool_id)
        if not skill:
            logger.error(f"Skill '{tool_id}' not found in registry.")
            return SkillResult(
                tool_id=tool_id,
                operation_id=operation_id or f"{tool_id}-unknown",
                success=False,
                error=f"Skill '{tool_id}' is not registered in F.R.I.D.A.Y. registry.",
                audit_record={"event": "DISPATCH_FAILED", "tool_id": tool_id}
            )
        return skill.run_lifecycle(params, context=context, operation_id=operation_id)


# Global Singleton Registry
skill_registry = SkillRegistry()
