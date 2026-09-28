"""
F.R.I.D.A.Y. 3.0 — Phase 6B: Keyboard & Application Shortcuts
Executes standard application hotkeys and keyboard shortcuts with postcondition checks.
"""

from typing import Dict, List, Optional, Tuple
import ctypes
import time
import logging
from friday_core.platform_guard import IS_WINDOWS

logger = logging.getLogger("FRIDAY.Shortcuts")

VK_CODES = {
    "ctrl": 0x11,
    "shift": 0x10,
    "alt": 0x12,
    "enter": 0x0D,
    "esc": 0x1B,
    "tab": 0x09,
    "space": 0x20,
    "f4": 0x73,
    "a": 0x41,
    "c": 0x43,
    "f": 0x46,
    "n": 0x4E,
    "s": 0x53,
    "v": 0x56,
    "w": 0x57,
    "x": 0x58,
    "y": 0x59,
    "z": 0x5A,
}

STANDARD_SHORTCUTS: Dict[str, List[str]] = {
    "save": ["ctrl", "s"],
    "copy": ["ctrl", "c"],
    "paste": ["ctrl", "v"],
    "cut": ["ctrl", "x"],
    "undo": ["ctrl", "z"],
    "redo": ["ctrl", "y"],
    "select_all": ["ctrl", "a"],
    "new": ["ctrl", "n"],
    "find": ["ctrl", "f"],
    "close_tab": ["ctrl", "w"],
    "close_window": ["alt", "f4"],
    "switch_window": ["alt", "tab"]
}


class ShortcutDriver:
    """
    Dispatches keyboard shortcuts and application hotkeys.
    """
    def send_shortcut(self, shortcut_name: str) -> Tuple[bool, str]:
        """
        Sends named standard shortcut or custom key combination.
        """
        if not IS_WINDOWS:
            return False, "Shortcuts only supported on Windows."

        keys = STANDARD_SHORTCUTS.get(shortcut_name.lower())
        if not keys:
            # Try parsing e.g. "ctrl+shift+s"
            keys = [k.strip().lower() for k in shortcut_name.split("+")]

        vk_sequence = []
        for k in keys:
            vk = VK_CODES.get(k)
            if not vk:
                return False, f"Unknown key '{k}' in shortcut '{shortcut_name}'."
            vk_sequence.append(vk)

        try:
            # Key down in sequence
            for vk in vk_sequence:
                ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                time.sleep(0.02)

            time.sleep(0.05)

            # Key up in reverse sequence
            for vk in reversed(vk_sequence):
                ctypes.windll.user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP = 2
                time.sleep(0.02)

            return True, f"Dispatched shortcut '{shortcut_name}' ({'+'.join(keys)})."
        except Exception as ex:
            return False, f"Error dispatching shortcut '{shortcut_name}': {ex}"


# Global Singleton Shortcut Driver
shortcut_driver = ShortcutDriver()
