"""
F.R.I.D.A.Y. 3.0 — Windows UI Automation Subsystem Package
Provides decoupled hierarchical automation (Semantic UIA -> Shortcuts -> Bounded Input -> Vision -> Coordinates).
"""

try:
    import ctypes
    user32 = ctypes.windll.user32
    user32.OpenDesktopW.restype = ctypes.c_void_p
    user32.OpenDesktopW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_bool, ctypes.c_uint]
    user32.SetThreadDesktop.argtypes = [ctypes.c_void_p]
    user32.SetThreadDesktop.restype = ctypes.c_bool
    h_desk = user32.OpenDesktopW("default", 0, False, 0x01FF)
    if h_desk:
        user32.SetThreadDesktop(h_desk)
except Exception:
    pass

from friday_core.automation.hierarchy import AutomationPriority, AutomationOutcome
from friday_core.automation.uia import UIAutomationDriver, uia_driver
from friday_core.automation.shortcuts import ShortcutDriver, shortcut_driver
from friday_core.automation.mouse_keyboard import BoundedInputDriver, input_driver
from friday_core.automation.dispatcher import AutomationDispatcher, automation_dispatcher

__all__ = [
    "AutomationPriority",
    "AutomationOutcome",
    "UIAutomationDriver",
    "uia_driver",
    "ShortcutDriver",
    "shortcut_driver",
    "BoundedInputDriver",
    "input_driver",
    "AutomationDispatcher",
    "automation_dispatcher"
]
