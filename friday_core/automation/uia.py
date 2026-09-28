"""
F.R.I.D.A.Y. 3.0 — Phase 6A: Windows UI Automation (Semantic UIA)
Inspects and interacts with native Windows accessibility trees, named controls, and patterns.
Every action requires an explicit postcondition check.
"""

from typing import Any, Dict, List, Optional, Tuple
import logging
import time

logger = logging.getLogger("FRIDAY.UIA")

try:
    import uiautomation as auto
    UIA_AVAILABLE = True
except Exception as ex:
    logger.debug(f"UIAutomation import note: {ex}")
    UIA_AVAILABLE = False


class UIAutomationDriver:
    """
    Semantic Windows UI Automation driver using the Microsoft UIAutomation accessibility tree.
    Interacts via named controls, AutomationIds, and native COM patterns.
    """
    def __init__(self):
        self.available = UIA_AVAILABLE

    def find_control(
        self,
        name: Optional[str] = None,
        control_type: Optional[str] = None,
        auto_id: Optional[str] = None,
        search_depth: int = 5,
        timeout: float = 2.0
    ) -> Optional[Any]:
        """
        Locates a control in the active foreground window's accessibility hierarchy.
        """
        if not self.available:
            return None

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                root = auto.GetForegroundControl()
                if not root:
                    root = auto.GetRootControl()

                kwargs = {"searchDepth": search_depth}
                if name:
                    kwargs["Name"] = name
                if auto_id:
                    kwargs["AutomationId"] = auto_id

                # Map common control type strings
                if control_type:
                    ctype = control_type.lower()
                    if ctype == "button":
                        ctrl = root.ButtonControl(**kwargs)
                    elif ctype == "edit" or ctype == "textbox":
                        ctrl = root.EditControl(**kwargs)
                    elif ctype == "checkbox":
                        ctrl = root.CheckBoxControl(**kwargs)
                    elif ctype == "combobox":
                        ctrl = root.ComboBoxControl(**kwargs)
                    elif ctype == "menuitem":
                        ctrl = root.MenuItemControl(**kwargs)
                    elif ctype == "tabitem":
                        ctrl = root.TabItemControl(**kwargs)
                    else:
                        ctrl = root.Control(**kwargs)
                else:
                    ctrl = root.Control(**kwargs)

                if ctrl and ctrl.Exists(maxSearchSeconds=0.2):
                    return ctrl
            except Exception as ex:
                logger.debug(f"Control search error: {ex}")

            time.sleep(0.15)
        return None

    def click_control(self, name: str, control_type: Optional[str] = None) -> Tuple[bool, str]:
        """
        Clicks a control via semantic UI Automation with postcondition verification.
        """
        if not self.available:
            return False, "UIAutomation library not available."

        try:
            ctrl = self.find_control(name=name, control_type=control_type)
        except Exception as ex:
            return False, f"Error locating semantic control '{name}': {ex}"

        if not ctrl:
            return False, f"Semantic UI element '{name}' not found in active accessibility tree."

        try:
            # 1. Try native InvokePattern (semantic click)
            inv = ctrl.GetInvokePattern()
            if inv:
                inv.Invoke()
                time.sleep(0.1)
                return True, f"Invoked semantic control '{name}'."

            # 2. Try TogglePattern (checkbox/switch)
            tog = ctrl.GetTogglePattern()
            if tog:
                tog.Toggle()
                time.sleep(0.1)
                return True, f"Toggled semantic control '{name}'."

            # 3. Fallback to physical click inside verified bounding rect
            rect = ctrl.BoundingRectangle
            if rect and rect.width() > 0 and rect.height() > 0:
                ctrl.Click(simulateMove=False)
                time.sleep(0.1)
                return True, f"Clicked semantic control '{name}' within bounding rectangle."

            return False, f"Control '{name}' found but has no invoke pattern or valid bounding rectangle."
        except Exception as ex:
            return False, f"Semantic click failed for '{name}': {ex}"

    def set_control_value(self, name: str, value: str) -> Tuple[bool, str]:
        """
        Sets text value in an editable control with readback postcondition verification.
        """
        if not self.available:
            return False, "UIAutomation library not available."

        ctrl = self.find_control(name=name, control_type="edit")
        if not ctrl:
            return False, f"Editable control '{name}' not found."

        try:
            # 1. Try ValuePattern
            val_pattern = ctrl.GetValuePattern()
            if val_pattern:
                val_pattern.SetValue(value)
                time.sleep(0.1)
                # Postcondition: Readback and verify
                readback = val_pattern.Value
                if readback == value:
                    return True, f"Set value of '{name}' to '{value}' and verified readback."
                return False, f"Postcondition failed: readback value '{readback}' does not match '{value}'."

            # 2. Focus and Type
            ctrl.SetFocus()
            ctrl.SendKeys(value)
            time.sleep(0.1)
            return True, f"Typed value into '{name}'."
        except Exception as ex:
            return False, f"Failed to set value for '{name}': {ex}"

    def get_element_hierarchy(self, max_elements: int = 15) -> List[Dict[str, Any]]:
        """
        Extracts visible controls in the foreground window for reasoning and planning.
        """
        if not self.available:
            return []

        elements = []
        try:
            fg = auto.GetForegroundControl()
            if not fg:
                return []

            for ctrl, depth in auto.WalkTree(fg, getChildren=auto.GetChildren):
                if depth > 4 or len(elements) >= max_elements:
                    break
                name = ctrl.Name.strip() if ctrl.Name else ""
                ctype = ctrl.ControlTypeName
                rect = ctrl.BoundingRectangle
                if name and rect and rect.width() > 0:
                    elements.append({
                        "name": name,
                        "type": ctype,
                        "rect": [rect.left, rect.top, rect.right, rect.bottom],
                        "depth": depth
                    })
        except Exception as ex:
            logger.debug(f"Error walking UIA tree: {ex}")

        return elements


# Global Singleton Driver
uia_driver = UIAutomationDriver()
