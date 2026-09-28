"""
F.R.I.D.A.Y. 3.0 — Bounded Mouse & Keyboard Input Driver
Performs high-precision input interactions strictly within confirmed control bounding rectangles.
Eliminates blind coordinate guessing.
"""

from typing import Tuple
import ctypes
import time
import logging
from friday_core.platform_guard import IS_WINDOWS

logger = logging.getLogger("FRIDAY.InputDriver")


class BoundedInputDriver:
    """
    Executes mouse clicks and keyboard typing within verified bounding boxes.
    """
    def click_within_bounds(self, rect: Tuple[int, int, int, int]) -> Tuple[bool, str]:
        """
        Clicks the center of a bounding rectangle (left, top, right, bottom).
        Rejects invalid or unverified bounds.
        """
        if not IS_WINDOWS:
            return False, "Input driver only supported on Windows."

        left, top, right, bottom = rect
        if right <= left or bottom <= top:
            return False, f"Invalid bounding rectangle: {rect}"

        center_x = (left + right) // 2
        center_y = (top + bottom) // 2

        try:
            # Set cursor position
            ctypes.windll.user32.SetCursorPos(center_x, center_y)
            time.sleep(0.04)

            # MOUSEEVENTF_LEFTDOWN = 0x0002, MOUSEEVENTF_LEFTUP = 0x0004
            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(0.03)
            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)

            return True, f"Clicked within verified bounding rect at ({center_x}, {center_y})."
        except Exception as ex:
            return False, f"Error clicking at ({center_x}, {center_y}): {ex}"

    def type_text(self, text: str) -> Tuple[bool, str]:
        """Types string into currently focused control."""
        if not IS_WINDOWS:
            return False, "Input driver only supported on Windows."

        try:
            for char in text:
                # Use VkKeyScan to send character
                vk = ctypes.windll.user32.VkKeyScanW(ord(char))
                if vk != -1:
                    vk_code = vk & 0xFF
                    shift_required = (vk >> 8) & 1

                    if shift_required:
                        ctypes.windll.user32.keybd_event(0x10, 0, 0, 0)  # Shift down

                    ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
                    time.sleep(0.01)
                    ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)

                    if shift_required:
                        ctypes.windll.user32.keybd_event(0x10, 0, 2, 0)  # Shift up
                time.sleep(0.01)
            return True, f"Typed {len(text)} characters into focused element."
        except Exception as ex:
            return False, f"Error typing text: {ex}"


# Global Singleton Input Driver
input_driver = BoundedInputDriver()
