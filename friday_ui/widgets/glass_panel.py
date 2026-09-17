"""
F.R.I.D.A.Y. 2.0 - Tactical GlassPanel Base Component
Provides consistent acrylic/mica glassmorphic depth, soft drop shadow blur,
and border tokens across HUD dock, operations panel, floating command bar, and cards.
"""

import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect


def apply_system_backdrop(hwnd: int, backdrop_type: int = 3) -> bool:
    """
    Applies Windows 11 DWM backdrop blur to native window handle.
    backdrop_type: 2 = Mica, 3 = Acrylic (desktop blur), 4 = Mica Alt
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        DWMWA_SYSTEMBACKDROP_TYPE = 38
        value = ctypes.c_int(backdrop_type)
        hr = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(value),
            ctypes.sizeof(value)
        )
        return hr == 0
    except Exception:
        return False


def ensure_system_gestures(hwnd: int) -> bool:
    """
    Unregisters native window from raw touch capture, allowing Windows 10/11
    Precision Touchpad multi-finger gestures (three-finger swipe up for Task View,
    four-finger desktop switching, etc.) to be handled natively by the OS shell.
    """
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        import ctypes
        res = ctypes.windll.user32.UnregisterTouchWindow(ctypes.c_void_p(hwnd))
        return res != 0
    except Exception:
        return False


class GlassPanel(QFrame):
    """
    Shared glassmorphic card/panel for F.R.I.D.A.Y. 2.0.
    Replaces flat #000000 styling with semi-transparent tinted backdrop,
    subtle 1px border, and smooth drop shadow.
    """
    def __init__(
        self,
        parent=None,
        bg_color: str = "rgba(18, 18, 22, 0.60)",
        border_color: str = "rgba(255, 255, 255, 0.08)",
        radius: int = 12,
        enable_shadow: bool = True,
        shadow_blur: int = 36,
        shadow_alpha: int = 70
    ):
        super().__init__(parent)
        self._bg_color = bg_color
        self._border_color = border_color
        self._radius = radius
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._update_panel_stylesheet()

        if enable_shadow:
            self._shadow = QGraphicsDropShadowEffect(self)
            self._shadow.setBlurRadius(shadow_blur)
            self._shadow.setColor(QColor(0, 0, 0, shadow_alpha))
            self._shadow.setOffset(0, 4)
            self.setGraphicsEffect(self._shadow)

    def _update_panel_stylesheet(self):
        obj_name = self.objectName() or "GlassPanel"
        self.setStyleSheet(f"""
            QFrame#{obj_name}, GlassPanel#{obj_name} {{
                background-color: {self._bg_color};
                border: 1px solid {self._border_color};
                border-radius: {self._radius}px;
            }}
        """)

    def set_glass_style(self, bg_color: str, border_color: str = None, radius: int = None):
        self._bg_color = bg_color
        if border_color:
            self._border_color = border_color
        if radius is not None:
            self._radius = radius
        self._update_panel_stylesheet()
