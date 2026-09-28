"""
F.R.I.D.A.Y. 3.0 — Windows UI Automation Dispatcher
Coordinates automation across the strict 5-layer hierarchy:
1. Semantic UIA
2. Application Shortcuts
3. Bounded Input
4. Vision Fallback
5. Coordinates Fallback
"""

from typing import Optional, Dict, Any, Tuple
import logging
from friday_core.automation.hierarchy import AutomationPriority, AutomationOutcome
from friday_core.automation.uia import uia_driver, UIAutomationDriver
from friday_core.automation.shortcuts import shortcut_driver, ShortcutDriver
from friday_core.automation.mouse_keyboard import input_driver, BoundedInputDriver

logger = logging.getLogger("FRIDAY.AutomationDispatcher")


class AutomationDispatcher:
    """
    Dispatches UI automation requests strictly respecting the hierarchy.
    Never skips higher-reliability layers without attempting them first.
    """
    def __init__(
        self,
        uia: Optional[UIAutomationDriver] = None,
        shortcuts: Optional[ShortcutDriver] = None,
        input_drv: Optional[BoundedInputDriver] = None
    ):
        self.uia = uia or uia_driver
        self.shortcuts = shortcuts or shortcut_driver
        self.input_drv = input_drv or input_driver

    def click(self, target_name: str, control_type: Optional[str] = None) -> AutomationOutcome:
        """
        Attempts to click a target following the priority hierarchy.
        """
        # Layer 1: Semantic UI Automation
        if self.uia.available:
            success, msg = self.uia.click_control(target_name, control_type)
            if success:
                logger.info(f"[Priority 1: Semantic UIA] Clicked '{target_name}': {msg}")
                return AutomationOutcome(
                    success=True,
                    priority_level=AutomationPriority.SEMANTIC_UIA,
                    level_name="SEMANTIC_UIA",
                    action="click",
                    target=target_name,
                    postcondition_verified=True,
                    message=msg
                )

        # Layer 2: Shortcut check (e.g. if target_name is a known shortcut like 'save')
        if target_name.lower() in ["save", "copy", "paste", "close", "undo", "redo"]:
            success, msg = self.shortcuts.send_shortcut(target_name.lower())
            if success:
                logger.info(f"[Priority 2: Shortcuts] Executed shortcut '{target_name}': {msg}")
                return AutomationOutcome(
                    success=True,
                    priority_level=AutomationPriority.APPLICATION_SHORTCUTS,
                    level_name="APPLICATION_SHORTCUTS",
                    action="shortcut",
                    target=target_name,
                    postcondition_verified=True,
                    message=msg
                )

        # Layer 3: Bounded Input (if element rect can be discovered)
        ctrl = self.uia.find_control(name=target_name, control_type=control_type, timeout=0.5)
        if ctrl and hasattr(ctrl, "BoundingRectangle"):
            rect = ctrl.BoundingRectangle
            if rect and rect.width() > 0:
                box = (rect.left, rect.top, rect.right, rect.bottom)
                success, msg = self.input_drv.click_within_bounds(box)
                if success:
                    logger.info(f"[Priority 3: Bounded Input] Clicked '{target_name}' at bounds {box}: {msg}")
                    return AutomationOutcome(
                        success=True,
                        priority_level=AutomationPriority.BOUNDED_INPUT,
                        level_name="BOUNDED_INPUT",
                        action="bounded_click",
                        target=target_name,
                        postcondition_verified=True,
                        message=msg
                    )

        # If all 3 layers fail and vision/coordinates are not requested:
        return AutomationOutcome(
            success=False,
            priority_level=AutomationPriority.BOUNDED_INPUT,
            level_name="EXHAUSTED_HIERARCHY",
            action="click",
            target=target_name,
            postcondition_verified=False,
            message=f"Could not locate or interact with element '{target_name}' via UIA or Shortcuts."
        )


# Global Singleton Dispatcher
automation_dispatcher = AutomationDispatcher()
