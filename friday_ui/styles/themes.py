"""
F.R.I.D.A.Y. 2.0 - Centralized Monochrome Design System & Animation Toolkit
Strict monochrome palette (black/white/zinc) inspired by ChatGPT, Claude, and Cursor desktop apps.
Restricts color to:
- live_green (#10B981): Live voice loop, microphone active, nominal health, online
- danger_red (#EF4444): Errors, muted mic, destructive Tier 2/3 confirmations
- subtle_cyan (#06B6D4) / subtle_amber (#F59E0B): Sparse contextual tags
"""

from typing import Dict, Optional, List
from PySide6.QtCore import (
    QObject, QEvent, QPropertyAnimation, QEasingCurve, QRect,
    QParallelAnimationGroup, QTimer, Qt, Property, QPoint
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget, QGraphicsOpacityEffect, QGraphicsDropShadowEffect

# ── 1. Centralized Palette & Named Tokens ──────────────────────────────
STARK_CYAN = "#00F0FF"
LIVE_GREEN = "#10B981"
DANGER_RED = "#EF4444"
AMBER_WARN = "#F59E0B"
PURPLE_ACCENT = "#7B2CBF"

TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#A1A1AA"
TEXT_MUTED = "#71717A"
TEXT_DIM = "#52525B"

MONO_DARK: Dict[str, str] = {
    # Canvas & Backgrounds
    "bg_canvas": "#000000",        # True pitch black app canvas
    "bg_sidebar": "#09090B",       # Zinc-950 sidebar
    "bg_card": "rgba(18, 18, 22, 0.60)", # Glassmorphic cards
    "bg_card_hover": "#18181B",    # Zinc-800 interactive card hover
    "bg_surface": "#141416",       # Input and dialog surface
    "bg_input": "#0A0A0C",         # Deep input frame
    "bg_dock": "rgba(14, 14, 18, 0.65)", # Minimal glass status footer
    "bg_pill": "#18181B",          # Default chip/pill background
    "bg_pill_active": "#FFFFFF",   # Inverted active navigation pill

    # Borders
    "border_subtle": "rgba(255, 255, 255, 0.08)",
    "border_card": "rgba(255, 255, 255, 0.10)",
    "border_hover": "rgba(255, 255, 255, 0.22)",
    "border_focus": "rgba(255, 255, 255, 0.45)",

    # Typography
    "text_primary": TEXT_PRIMARY,
    "text_secondary": TEXT_SECONDARY,
    "text_muted": TEXT_MUTED,
    "text_dim": TEXT_DIM,
    "text_inverted": "#000000",

    # Restricted Status Colors
    "live_green": LIVE_GREEN,
    "live_green_bg": "rgba(16, 185, 129, 0.12)",
    "live_green_border": "rgba(16, 185, 129, 0.35)",

    "danger_red": DANGER_RED,
    "danger_red_bg": "rgba(239, 68, 68, 0.12)",
    "danger_red_border": "rgba(239, 68, 68, 0.35)",

    # Contextual Sparse Highlights
    "cyan_tag": STARK_CYAN,
    "cyan_tag_bg": "rgba(0, 240, 255, 0.12)",
    "cyan_tag_border": "rgba(0, 240, 255, 0.30)",

    "amber_tag": AMBER_WARN,
    "amber_tag_bg": "rgba(245, 158, 11, 0.12)",
    "amber_tag_border": "rgba(245, 158, 11, 0.30)",
}

TACTICAL_DARK: Dict[str, str] = {
    **MONO_DARK,
    "bg_card": "rgba(12, 16, 24, 0.70)",
    "border_card": "rgba(0, 240, 255, 0.15)",
    "border_subtle": "rgba(0, 240, 255, 0.08)",
}

LIGHT_THEME: Dict[str, str] = {
    **MONO_DARK,
    "bg_canvas": "#F4F4F5",
    "bg_sidebar": "#FFFFFF",
    "bg_card": "rgba(255, 255, 255, 0.85)",
    "bg_surface": "#FFFFFF",
    "bg_input": "#FAFAFA",
    "text_primary": "#09090B",
    "text_secondary": "#52525B",
    "text_muted": "#71717A",
    "border_subtle": "rgba(0, 0, 0, 0.08)",
    "border_card": "rgba(0, 0, 0, 0.12)",
}

STARK_DARK = MONO_DARK

def get_theme_palette(theme_mode: str = "dark") -> Dict[str, str]:
    mode = str(theme_mode).lower()
    if "tactical" in mode:
        return TACTICAL_DARK
    elif "light" in mode:
        return LIGHT_THEME
    return MONO_DARK

def generate_global_qss(theme_mode: str = "dark") -> str:
    """Generates the unified desktop stylesheet with dynamic property selectors."""
    p = get_theme_palette(theme_mode)
    return f"""
        QWidget {{
            font-family: 'Inter', 'Segoe UI', -apple-system, sans-serif;
            color: {p['text_primary']};
        }}
        /* Global Scrollbars */
        QScrollBar:vertical {{
            width: 5px;
            background: transparent;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: #27272A;
            border-radius: 2px;
            min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: #3F3F46;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
        QScrollBar:horizontal {{
            height: 5px;
            background: transparent;
        }}
        QScrollBar::handle:horizontal {{
            background: #27272A;
            border-radius: 2px;
        }}
        /* Inputs & Buttons */
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: {p['bg_input']};
            color: {p['text_primary']};
            border: 1px solid {p['border_card']};
            border-radius: 8px;
            selection-background-color: rgba(0, 240, 255, 0.30);
        }}
        QLineEdit:focus, QTextEdit:focus {{
            border: 1px solid {p['border_focus']};
        }}

        /* Dynamic Property Selectors for HUD Status & Telemetry */
        QLabel#hudStateLabel {{
            font-family: 'Consolas', 'Segoe UI', monospace;
            font-size: 10px;
            letter-spacing: 0.8px;
            color: {TEXT_MUTED};
        }}
        QLabel#hudStateLabel[state="listening"], QLabel#hudStateLabel[state="standby"] {{
            color: {LIVE_GREEN};
            font-weight: bold;
        }}
        QLabel#hudStateLabel[state="idle"] {{
            color: {DANGER_RED};
            font-weight: bold;
        }}
        QLabel#hudStateLabel[state="thinking"] {{
            color: {AMBER_WARN};
            font-weight: bold;
        }}
        QLabel#hudStateLabel[state="speaking"] {{
            color: {STARK_CYAN};
            font-weight: bold;
        }}

        QLabel#hudTelemetryLabel {{
            padding: 3px 8px;
            border-radius: 6px;
            font-family: 'Consolas', 'Segoe UI', monospace;
            font-size: 9px;
            letter-spacing: 0.5px;
            color: {LIVE_GREEN};
            background: rgba(16, 185, 129, 0.08);
            border: 1px solid rgba(16, 185, 129, 0.20);
        }}
        QLabel#hudTelemetryLabel[variant="nominal"] {{
            color: {LIVE_GREEN};
            background: rgba(16, 185, 129, 0.08);
            border: 1px solid rgba(16, 185, 129, 0.20);
        }}
        QLabel#hudTelemetryLabel[variant="active"] {{
            color: {STARK_CYAN};
            background: rgba(0, 240, 255, 0.08);
            border: 1px solid rgba(0, 240, 255, 0.25);
        }}
        QLabel#hudTelemetryLabel[variant="warning"] {{
            color: {AMBER_WARN};
            background: rgba(245, 158, 11, 0.08);
            border: 1px solid rgba(245, 158, 11, 0.25);
        }}
    """

# ── 2. Reusable Animation Toolkit ──────────────────────────────────────

def fade_in(widget: QWidget, duration: int = 200, start_opacity: float = 0.0, end_opacity: float = 1.0) -> QPropertyAnimation:
    """Applies a smooth fade-in entrance to any widget."""
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(start_opacity)
    anim.setEndValue(end_opacity)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.start(QPropertyAnimation.DeleteWhenStopped)
    return anim


class SlideFadeEntrance:
    """Helper for combined slide-up/down + opacity fade entrance."""
    @staticmethod
    def play(widget: QWidget, duration: int = 220, offset_y: int = 12) -> QParallelAnimationGroup:
        effect = widget.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)

        group = QParallelAnimationGroup(widget)
        
        fade = QPropertyAnimation(effect, b"opacity")
        fade.setDuration(duration)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        group.addAnimation(fade)
        
        group.start(QParallelAnimationGroup.DeleteWhenStopped)
        return group


class ButtonMicroInteractionFilter(QObject):
    """Event filter that scales widget on press (spring effect) and restores on release (~80ms)."""
    def __init__(self, target_widget: QWidget):
        super().__init__(target_widget)
        self.target = target_widget
        self._orig_geo = None

    def eventFilter(self, watched, event):
        if event.type() == QEvent.MouseButtonPress:
            if not self._orig_geo:
                self._orig_geo = self.target.geometry()
            g = self.target.geometry()
            dx = max(1, int(g.width() * 0.025))
            dy = max(1, int(g.height() * 0.025))
            self.target.setGeometry(g.x() + dx, g.y() + dy, g.width() - 2*dx, g.height() - 2*dy)
        elif event.type() == QEvent.MouseButtonRelease:
            if self._orig_geo:
                self.target.setGeometry(self._orig_geo)
                self._orig_geo = None
        return super().eventFilter(watched, event)


def install_button_micro_interaction(button: QWidget):
    """Installs spring micro-press animation on a button or clickable widget."""
    btn_filter = ButtonMicroInteractionFilter(button)
    button.installEventFilter(btn_filter)
    return btn_filter


class HoverRevealFilter(QObject):
    """Reveals hidden child controls (e.g. copy button, options) when the parent card is hovered."""
    def __init__(self, parent_widget: QWidget, targets: List[QWidget]):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget
        self.targets = targets
        for t in self.targets:
            t.setVisible(False)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Enter:
            for t in self.targets:
                t.setVisible(True)
                fade_in(t, duration=150)
        elif event.type() == QEvent.Leave:
            for t in self.targets:
                t.setVisible(False)
        return super().eventFilter(watched, event)


def install_hover_reveal(parent_widget: QWidget, targets: List[QWidget]):
    """Installs hover-reveal filter on a parent container."""
    rev_filter = HoverRevealFilter(parent_widget, targets)
    parent_widget.installEventFilter(rev_filter)
    return rev_filter


class PulsingGlowWidget(QWidget):
    """Pulsing ambient glow ring or status dot with configurable color and period."""
    def __init__(self, color: QColor = QColor(16, 185, 129), size: int = 12, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._color = color
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)  # ~30 FPS pulse

    def set_color(self, color: QColor):
        self._color = color
        self.update()

    def _tick(self):
        import math
        self._phase = (self._phase + 0.08) % (2 * math.pi)
        self.update()

    def paintEvent(self, event):
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        r = min(cx, cy) - 1

        # Outer breathing halo
        alpha = int(40 + 50 * (0.5 + 0.5 * math.sin(self._phase)))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self._color.red(), self._color.green(), self._color.blue(), alpha))
        p.drawEllipse(QPoint(int(cx), int(cy)), int(r), int(r))

        # Solid core dot
        core_r = max(2.0, r * 0.45)
        p.setBrush(self._color)
        p.drawEllipse(QPoint(int(cx), int(cy)), int(core_r), int(core_r))
