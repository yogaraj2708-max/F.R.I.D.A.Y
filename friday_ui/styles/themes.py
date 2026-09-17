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

DARK_PRO: Dict[str, str] = {
    # Canvas & Panes
    "bg_canvas": "#0B0F19",               # Slate-Navy background
    "bg_topbar": "#0B0F19",               # Top bar
    "bg_sidebar": "#0E1322",              # Left sidebar
    "bg_card": "#111827",                 # Card surface
    "bg_card_hover": "#1A2234",           # Hover state
    "bg_surface": "#111827",              # Input & dialog surface
    "bg_input": "#111827",                # Input background
    "bg_dock": "rgba(11, 15, 25, 0.95)",  # Footer dock
    "bg_pill": "#1E293B",                 # Tag / pill
    "bg_pill_active": "#2563EB",          # Active tab / pill
    "bg_badge": "#1F2937",                # Default badge

    # Borders
    "border_subtle": "rgba(255, 255, 255, 0.08)",
    "border_card": "#1E293B",
    "border_hover": "#334155",
    "border_focus": "#2563EB",

    # Typography
    "text_primary": "#FFFFFF",
    "text_secondary": "#94A3B8",
    "text_muted": "#64748B",
    "text_dim": "#475569",
    "text_inverted": "#0B0F19",

    # Accents & Status
    "accent_blue": "#2563EB",
    "accent_blue_hover": "#1D4ED8",
    "accent_cyan": "#00F0FF",
    "live_green": "#10B981",
    "live_green_bg": "rgba(16, 185, 129, 0.12)",
    "danger_red": "#EF4444",
    "danger_red_bg": "rgba(239, 68, 68, 0.12)",
    "amber_warn": "#F59E0B",
    "amber_warn_bg": "rgba(245, 158, 11, 0.12)",
}

LIGHT_PRO: Dict[str, str] = {
    # Canvas & Panes
    "bg_canvas": "#F8FAFC",               # Crisp gray-white
    "bg_topbar": "#FFFFFF",               # Pure white topbar
    "bg_sidebar": "#FFFFFF",              # Pure white sidebar
    "bg_card": "#FFFFFF",                 # Pure white cards
    "bg_card_hover": "#F1F5F9",           # Soft hover
    "bg_surface": "#FFFFFF",              # Surface
    "bg_input": "#FFFFFF",                # Input
    "bg_dock": "rgba(255, 255, 255, 0.95)",
    "bg_pill": "#F1F5F9",                 # Soft pill
    "bg_pill_active": "#2563EB",          # Active tab / pill
    "bg_badge": "#F1F5F9",                # Default badge

    # Borders
    "border_subtle": "#E2E8F0",
    "border_card": "#E2E8F0",
    "border_hover": "#CBD5E1",
    "border_focus": "#2563EB",

    # Typography
    "text_primary": "#0F172A",
    "text_secondary": "#475569",
    "text_muted": "#94A3B8",
    "text_dim": "#CBD5E1",
    "text_inverted": "#FFFFFF",

    # Accents & Status
    "accent_blue": "#2563EB",
    "accent_blue_hover": "#1D4ED8",
    "accent_cyan": "#0284C7",
    "live_green": "#10B981",
    "live_green_bg": "rgba(16, 185, 129, 0.10)",
    "danger_red": "#EF4444",
    "danger_red_bg": "rgba(239, 68, 68, 0.10)",
    "amber_warn": "#F59E0B",
    "amber_warn_bg": "rgba(245, 158, 11, 0.10)",
}

MONO_DARK = DARK_PRO
TACTICAL_DARK = DARK_PRO
LIGHT_THEME = LIGHT_PRO
STARK_DARK = DARK_PRO

def get_theme_palette(theme_mode: str = "dark") -> Dict[str, str]:
    mode = str(theme_mode).lower()
    if "light" in mode:
        return LIGHT_PRO
    return DARK_PRO

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

        /* ── Top Navigation Bar ── */
        #topNavBar {{
            background-color: {p['bg_topbar']};
            border-bottom: 1px solid {p['border_subtle']};
        }}
        #brandLabel {{
            font-family: 'Inter', 'Segoe UI', sans-serif;
            font-size: 15px;
            font-weight: 700;
            letter-spacing: 3.5px;
            color: {p['text_primary']};
        }}
        #navTabButton {{
            background-color: transparent;
            color: {p['text_secondary']};
            font-size: 13px;
            font-weight: 500;
            border: none;
            padding: 8px 16px;
            border-bottom: 2px solid transparent;
        }}
        #navTabButton:hover {{
            color: {p['text_primary']};
        }}
        #navTabButton[active="true"] {{
            color: {p['text_primary']};
            font-weight: 600;
            border-bottom: 2px solid {p['text_primary']};
        }}
        #profileChip {{
            background-color: {p['bg_pill']};
            color: {p['text_primary']};
            border: 1px solid {p['border_subtle']};
            border-radius: 14px;
            font-weight: 600;
            font-size: 11px;
        }}

        /* ── Left Sidebar ── */
        #sidebarView {{
            background-color: {p['bg_sidebar']};
            border-right: 1px solid {p['border_subtle']};
        }}
        #newChatBtn {{
            background-color: transparent;
            color: {p['text_primary']};
            border: 1px solid {p['border_card']};
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            padding: 8px 14px;
            text-align: left;
        }}
        #newChatBtn:hover {{
            background-color: {p['bg_card_hover']};
            border-color: {p['border_hover']};
        }}
        #sidebarSectionLabel {{
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1px;
            color: {p['text_muted']};
            padding: 10px 4px 4px 4px;
        }}
        #chatSessionItem {{
            background-color: transparent;
            color: {p['text_secondary']};
            border-radius: 8px;
            border: none;
            text-align: left;
            padding: 8px 10px;
            font-size: 13px;
        }}
        #chatSessionItem:hover {{
            background-color: {p['bg_card_hover']};
            color: {p['text_primary']};
        }}
        #chatSessionItem[active="true"] {{
            background-color: {p['bg_card_hover']};
            color: {p['text_primary']};
            font-weight: 600;
        }}
        #usageCard {{
            background-color: {p['bg_card']};
            border: 1px solid {p['border_card']};
            border-radius: 10px;
            padding: 12px;
        }}
        #profileFooterCard {{
            background-color: transparent;
            border-top: 1px solid {p['border_subtle']};
            padding: 10px 8px;
        }}

        /* ── Center Canvas & Suggestions ── */
        #centerCanvas {{
            background-color: {p['bg_canvas']};
        }}
        #heroGreeting {{
            font-size: 26px;
            font-weight: 700;
            color: {p['text_primary']};
        }}
        #heroSubtitle {{
            font-size: 14px;
            color: {p['text_secondary']};
        }}
        #promptCard {{
            background-color: {p['bg_card']};
            border: 1px solid {p['border_card']};
            border-radius: 10px;
            padding: 14px 18px;
            text-align: left;
        }}
        #promptCard:hover {{
            background-color: {p['bg_card_hover']};
            border-color: {p['border_hover']};
        }}
        #promptCardText {{
            color: {p['text_primary']};
            font-size: 13px;
            font-weight: 500;
        }}
        #promptCardArrow {{
            color: {p['text_muted']};
            font-size: 14px;
        }}

        /* ── Floating Input Dock ── */
        #inputDock {{
            background-color: {p['bg_card']};
            border: 1px solid {p['border_card']};
            border-radius: 16px;
        }}
        #dockInput {{
            background-color: transparent;
            border: none;
            color: {p['text_primary']};
            font-size: 14px;
            padding: 6px 10px;
        }}
        #dockButton {{
            background-color: transparent;
            border: 1px solid {p['border_subtle']};
            border-radius: 6px;
            color: {p['text_secondary']};
            font-size: 12px;
            padding: 4px 8px;
        }}
        #dockButton:hover {{
            background-color: {p['bg_card_hover']};
            color: {p['text_primary']};
            border-color: {p['border_hover']};
        }}
        #dockSendButton {{
            background-color: {p['accent_blue']};
            border: none;
            border-radius: 8px;
            color: #FFFFFF;
            font-size: 14px;
        }}
        #dockSendButton:hover {{
            background-color: {p['accent_blue_hover']};
        }}
        #disclaimerText {{
            font-size: 11px;
            color: {p['text_muted']};
        }}

        /* ── Right Inspector Panel ── */
        #inspectorView {{
            background-color: {p['bg_sidebar']};
            border-left: 1px solid {p['border_subtle']};
        }}
        #inspectorCard {{
            background-color: {p['bg_card']};
            border: 1px solid {p['border_card']};
            border-radius: 10px;
            padding: 12px;
        }}
        #inspectorLabel {{
            font-size: 11px;
            font-weight: 600;
            color: {p['text_muted']};
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        #specKey {{
            font-size: 12px;
            color: {p['text_muted']};
        }}
        #specVal {{
            font-size: 12px;
            font-weight: 500;
            color: {p['text_primary']};
        }}
        #pinnedFileRow {{
            background-color: transparent;
            border-radius: 6px;
            padding: 6px 8px;
        }}
        #pinnedFileRow:hover {{
            background-color: {p['bg_card_hover']};
        }}
    """

# ── 2. Reusable Animation Toolkit ──────────────────────────────────────

def fade_in(widget: QWidget, duration: int = 200, start_opacity: float = 0.0, end_opacity: float = 1.0) -> QPropertyAnimation:
    """Applies a smooth fade-in entrance to any widget and cleanly restores the effect upon completion."""
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    
    if hasattr(widget, '_fade_anim') and widget._fade_anim:
        widget._fade_anim.stop()

    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(start_opacity)
    anim.setEndValue(end_opacity)
    anim.setEasingCurve(QEasingCurve.OutCubic)

    def _cleanup():
        try:
            if hasattr(widget, 'graphicsEffect') and widget.graphicsEffect() == effect:
                effect.setOpacity(end_opacity)
        except Exception:
            pass

    anim.finished.connect(_cleanup)
    widget._fade_anim = anim
    anim.start()
    return anim


class SlideFadeEntrance:
    """Helper for combined slide-up/down + opacity fade entrance."""
    @staticmethod
    def play(widget: QWidget, duration: int = 220, offset_y: int = 12) -> QParallelAnimationGroup:
        effect = widget.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)

        if hasattr(widget, '_slide_group') and widget._slide_group:
            widget._slide_group.stop()

        group = QParallelAnimationGroup(widget)
        
        fade = QPropertyAnimation(effect, b"opacity", group)
        fade.setDuration(duration)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        group.addAnimation(fade)
        
        widget._slide_group = group
        group.start()
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
        try:
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
        finally:
            p.end()
