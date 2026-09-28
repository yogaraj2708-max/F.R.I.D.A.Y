"""
F.R.I.D.A.Y. 3.0 — Pluggable Skill Framework Package
Provides the 9-stage verification lifecycle, typed schemas, and built-in system skills.
"""

from friday_core.skills.base import (
    BaseSkill,
    RiskLevel,
    ValidationResult,
    AuthResult,
    ObservationResult,
    VerificationResult,
    RollbackResult,
    SkillResult
)
from friday_core.skills.registry import SkillRegistry, skill_registry
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

# Auto-register standard builtins into global registry
skill_registry.register(SystemTelemetrySkill())
skill_registry.register(VolumeControlSkill())
skill_registry.register(AppLauncherSkill())
skill_registry.register(FileOrganizerSkill())
skill_registry.register(WordDrafterSkill())
skill_registry.register(CalculatorSkill())
skill_registry.register(UITypeTextSkill())
skill_registry.register(AppSearchSkill())
skill_registry.register(AppNavigateSkill())
skill_registry.register(UIKeyPressSkill())
skill_registry.register(SaveFileSkill())
skill_registry.register(UIFocusSkill())
skill_registry.register(UIVerifyContentSkill())
skill_registry.register(ContentGenerationSkill())
skill_registry.register(BrowserNavigateSkill())
skill_registry.register(BrowserDownloadSkill())
skill_registry.register(ScreenshotSkill())
skill_registry.register(ClipboardSkill())
skill_registry.register(FileSearchSkill())
skill_registry.register(FileSelectorSkill())
skill_registry.register(CreateFileSkill())
skill_registry.register(TimerSkill())
skill_registry.register(MemorySkill())

__all__ = [
    "BaseSkill",
    "RiskLevel",
    "ValidationResult",
    "AuthResult",
    "ObservationResult",
    "VerificationResult",
    "RollbackResult",
    "SkillResult",
    "SkillRegistry",
    "skill_registry",
    "SystemTelemetrySkill",
    "VolumeControlSkill",
    "AppLauncherSkill",
    "FileOrganizerSkill",
    "WordDrafterSkill",
    "UIKeyPressSkill",
    "SaveFileSkill",
]
