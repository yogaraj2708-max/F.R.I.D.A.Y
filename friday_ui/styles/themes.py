"""
F.R.I.D.A.Y. 2.0 - Centralized Design System & Animation Toolkit
Complete dual-mode palette (Dark & Light) with shared animation utilities.

Dark mode:  Pitch-black monochrome canvas with cyan accents.
Light mode: Slate-white canvas with blue accents and warm readability.

Restricted semantic colors (shared across both modes):
- live_green (#10B981): Live voice loop, microphone active, nominal health
- danger_red (#EF4444): Errors, muted mic, destructive confirmations
- subtle_cyan (#06B6D4) / subtle_amber (#F59E0B): Sparse contextual tags
"""

from typing import Dict, Optional, List
from PySide6.QtCore import (
    QObject, QEvent, QPropertyAnimation, QEasingCurve, QRect,
    QParallelAnimationGroup, QTimer, Qt, Property, QPoint
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget, QGraphicsOpacityEffect, QGraphicsDropShadowEffect

# ── 1. Shared Semantic Constants ────────────────────────────────────────
STARK_CYAN = "#00F0FF"
LIVE_GREEN = "#10B981"
DANGER_RED = "#EF4444"
AMBER_WARN = "#F59E0B"
PURPLE_ACCENT = "#7B2CBF"

TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#A1A1AA"
TEXT_MUTED = "#71717A"
TEXT_DIM = "#52525B"

# ── 2. Complete Dark Palette ────────────────────────────────────────────
MONO_DARK: Dict[str, str] = {
    # Canvas & Backgrounds
    "bg_canvas":        "#000000",
    "bg_sidebar":       "#09090B",
    "bg_card":          "rgba(18, 18, 22, 0.60)",
    "bg_card_hover":    "#18181B",
    "bg_surface":       "#141416",
    "bg_input":         "#0A0A0C",
    "input_bg":         "#0A0A0C",
    "bg_dock":          "rgba(14, 14, 18, 0.75)",
    "bg_pill":          "#18181B",
    "bg_pill_active":   "#FFFFFF",

    # Borders
    "border_subtle":    "rgba(255, 255, 255, 0.08)",
    "border_card":      "rgba(255, 255, 255, 0.10)",
    "border_hover":     "rgba(255, 255, 255, 0.22)",
    "border_focus":     "rgba(255, 255, 255, 0.45)",

    # Typography
    "text_primary":     TEXT_PRIMARY,
    "text_secondary":   TEXT_SECONDARY,
    "text_muted":       TEXT_MUTED,
    "text_dim":         TEXT_DIM,
    "text_inverted":    "#000000",

    # Restricted Status Colors
    "live_green":       LIVE_GREEN,
    "live_green_bg":    "rgba(16, 185, 129, 0.12)",
    "live_green_border":"rgba(16, 185, 129, 0.35)",

    "danger_red":       DANGER_RED,
    "danger_red_bg":    "rgba(239, 68, 68, 0.12)",
    "danger_red_border":"rgba(239, 68, 68, 0.35)",

    # Contextual Sparse Highlights
    "cyan_tag":         STARK_CYAN,
    "cyan_tag_bg":      "rgba(0, 240, 255, 0.12)",
    "cyan_tag_border":  "rgba(0, 240, 255, 0.30)",

    "amber_tag":        AMBER_WARN,
    "amber_tag_bg":     "rgba(245, 158, 11, 0.12)",
    "amber_tag_border": "rgba(245, 158, 11, 0.30)",

    # Accent
    "accent":           "#00F0FF",
    "accent_hover":     "#22D3EE",
    "accent_pressed":   "#0891B2",
    "accent_bg":        "rgba(0, 240, 255, 0.10)",
    "accent_border":    "rgba(0, 240, 255, 0.30)",
    "accent_text":      "#000000",

    # Scrollbars
    "scrollbar_handle": "#27272A",
    "scrollbar_hover":  "#3F3F46",

    # Chat Bubbles
    "bubble_user":      "#18181B",
    "bubble_assistant":  "#0C0C0E",
    "bubble_system":    "#09090B",

    # Code Blocks
    "code_bg":          "#18181B",
    "code_block_bg":    "#000000",
    "code_text":        "#10B981",
    "code_border":      "rgba(255, 255, 255, 0.12)",

    # Chips & Quick Actions
    "chip_bg":          "#121214",
    "chip_hover":       "#1E1E22",
    "chip_pressed":     "#27272A",
    "chip_text":        "#D4D4D8",
    "chip_text_hover":  "#FFFFFF",

    # Navigation
    "nav_bg":           "rgba(9, 9, 11, 0.85)",
    "nav_border":       "rgba(255, 255, 255, 0.08)",

    # Selection
    "selection_bg":     "rgba(0, 240, 255, 0.30)",

    # Send Button
    "send_bg":          "#06B6D4",
    "send_hover":       "#22D3EE",
    "send_pressed":     "#0891B2",
    "send_text":        "#000000",

    # Combo Box
    "combo_bg":         "rgba(22, 24, 34, 0.85)",
    "combo_hover_bg":   "rgba(30, 34, 48, 0.95)",
    "combo_border":     "rgba(255, 255, 255, 0.14)",
    "combo_hover_border": "rgba(0, 240, 255, 0.40)",

    # Header card
    "header_bg":        "rgba(18, 18, 24, 0.65)",
}

TACTICAL_DARK: Dict[str, str] = {
    **MONO_DARK,
    "bg_card": "rgba(12, 16, 24, 0.70)",
    "border_card": "rgba(0, 240, 255, 0.15)",
    "border_subtle": "rgba(0, 240, 255, 0.08)",
}

# ── 3. Complete Light Palette ───────────────────────────────────────────
LIGHT_THEME: Dict[str, str] = {
    # Canvas & Backgrounds
    "bg_canvas":        "#F8FAFC",
    "bg_sidebar":       "#FFFFFF",
    "bg_card":          "rgba(255, 255, 255, 0.88)",
    "bg_card_hover":    "#F1F5F9",
    "bg_surface":       "#FFFFFF",
    "bg_input":         "#F1F5F9",
    "input_bg":         "#F1F5F9",
    "bg_dock":          "rgba(248, 250, 252, 0.88)",
    "bg_pill":          "#E2E8F0",
    "bg_pill_active":   "#0F172A",

    # Borders
    "border_subtle":    "rgba(15, 23, 42, 0.08)",
    "border_card":      "rgba(15, 23, 42, 0.10)",
    "border_hover":     "rgba(15, 23, 42, 0.18)",
    "border_focus":     "rgba(37, 99, 235, 0.50)",

    # Typography
    "text_primary":     "#0F172A",
    "text_secondary":   "#475569",
    "text_muted":       "#94A3B8",
    "text_dim":         "#CBD5E1",
    "text_inverted":    "#FFFFFF",

    # Restricted Status Colors
    "live_green":       LIVE_GREEN,
    "live_green_bg":    "rgba(16, 185, 129, 0.10)",
    "live_green_border":"rgba(16, 185, 129, 0.30)",

    "danger_red":       DANGER_RED,
    "danger_red_bg":    "rgba(239, 68, 68, 0.10)",
    "danger_red_border":"rgba(239, 68, 68, 0.30)",

    # Contextual Sparse Highlights
    "cyan_tag":         "#0891B2",
    "cyan_tag_bg":      "rgba(8, 145, 178, 0.08)",
    "cyan_tag_border":  "rgba(8, 145, 178, 0.25)",

    "amber_tag":        "#D97706",
    "amber_tag_bg":     "rgba(217, 119, 6, 0.08)",
    "amber_tag_border": "rgba(217, 119, 6, 0.25)",

    # Accent — richer blue for light backgrounds
    "accent":           "#2563EB",
    "accent_hover":     "#3B82F6",
    "accent_pressed":   "#1D4ED8",
    "accent_bg":        "rgba(37, 99, 235, 0.08)",
    "accent_border":    "rgba(37, 99, 235, 0.25)",
    "accent_text":      "#FFFFFF",

    # Scrollbars
    "scrollbar_handle": "#CBD5E1",
    "scrollbar_hover":  "#94A3B8",

    # Chat Bubbles
    "bubble_user":      "#E2E8F0",
    "bubble_assistant":  "#FFFFFF",
    "bubble_system":    "#F1F5F9",

    # Code Blocks
    "code_bg":          "#F1F5F9",
    "code_block_bg":    "#F8FAFC",
    "code_text":        "#059669",
    "code_border":      "rgba(15, 23, 42, 0.10)",

    # Chips & Quick Actions
    "chip_bg":          "#F1F5F9",
    "chip_hover":       "#E2E8F0",
    "chip_pressed":     "#CBD5E1",
    "chip_text":        "#475569",
    "chip_text_hover":  "#0F172A",

    # Navigation
    "nav_bg":           "rgba(255, 255, 255, 0.92)",
    "nav_border":       "rgba(15, 23, 42, 0.08)",

    # Selection
    "selection_bg":     "rgba(37, 99, 235, 0.20)",

    # Send Button
    "send_bg":          "#2563EB",
    "send_hover":       "#3B82F6",
    "send_pressed":     "#1D4ED8",
    "send_text":        "#FFFFFF",

    # Combo Box
    "combo_bg":         "rgba(241, 245, 249, 0.90)",
    "combo_hover_bg":   "rgba(226, 232, 240, 0.95)",
    "combo_border":     "rgba(15, 23, 42, 0.12)",
    "combo_hover_border": "rgba(37, 99, 235, 0.40)",

    # Header card
    "header_bg":        "rgba(255, 255, 255, 0.75)",
}

STARK_DARK = MONO_DARK

def get_theme_palette(theme_mode: str = "dark") -> Dict[str, str]:
    mode = str(theme_mode).lower()
    if "tactical" in mode:
        return TACTICAL_DARK
    elif "light" in mode:
        return LIGHT_THEME
    return MONO_DARK


def get_current_palette() -> Dict[str, str]:
    """Returns the active palette based on the persisted theme_mode setting."""
    try:
        from friday_core.settings import settings
        mode = settings.get("theme_mode", "dark")
    except Exception:
        mode = "dark"
    return get_theme_palette(mode)


def generate_global_qss(theme_mode: str = "dark") -> str:
    """Generates the unified desktop stylesheet with dynamic property selectors."""
    p = get_theme_palette(theme_mode)
    is_light = "light" in str(theme_mode).lower()

    # Use appropriate accent/status colors for HUD labels
    hud_listening = p.get("live_green", LIVE_GREEN)
    hud_idle = p.get("danger_red", DANGER_RED)
    hud_thinking = p.get("amber_tag", AMBER_WARN)
    hud_speaking = p.get("accent", STARK_CYAN)

    return f"""
        QWidget {{
            font-family: 'Inter', 'Segoe UI', -apple-system, sans-serif;
            color: {p['text_primary']};
        }}

        /* ── Global Scrollbars ── */
        QScrollBar:vertical {{
            width: 6px;
            background: transparent;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {p['scrollbar_handle']};
            border-radius: 3px;
            min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {p['scrollbar_hover']};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
        QScrollBar:horizontal {{
            height: 6px;
            background: transparent;
        }}
        QScrollBar::handle:horizontal {{
            background: {p['scrollbar_handle']};
            border-radius: 3px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {p['scrollbar_hover']};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: transparent;
        }}

        /* ── Inputs & Buttons ── */
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: {p['bg_input']};
            color: {p['text_primary']};
            border: 1px solid {p['border_card']};
            border-radius: 8px;
            selection-background-color: {p['selection_bg']};
        }}
        QLineEdit:focus, QTextEdit:focus {{
            border: 1px solid {p['border_focus']};
        }}

        /* ── CardWidget (QFluentWidgets) ── */
        CardWidget {{
            background-color: {p['bg_surface']};
            border: 1px solid {p['border_card']};
            border-radius: 10px;
        }}
        CardWidget:hover {{
            border: 1px solid {p['border_hover']};
        }}

        /* ── HUD State Label ── */
        QLabel#hudStateLabel {{
            font-family: 'Consolas', 'Segoe UI', monospace;
            font-size: 10px;
            letter-spacing: 0.8px;
            color: {p['text_muted']};
        }}
        QLabel#hudStateLabel[state="listening"], QLabel#hudStateLabel[state="standby"] {{
            color: {hud_listening};
            font-weight: bold;
        }}
        QLabel#hudStateLabel[state="idle"] {{
            color: {hud_idle};
            font-weight: bold;
        }}
        QLabel#hudStateLabel[state="thinking"] {{
            color: {hud_thinking};
            font-weight: bold;
        }}
        QLabel#hudStateLabel[state="speaking"] {{
            color: {hud_speaking};
            font-weight: bold;
        }}

        /* ── HUD Telemetry Label ── */
        QLabel#hudTelemetryLabel {{
            padding: 3px 8px;
            border-radius: 6px;
            font-family: 'Consolas', 'Segoe UI', monospace;
            font-size: 9px;
            letter-spacing: 0.5px;
            color: {p['live_green']};
            background: {p['live_green_bg']};
            border: 1px solid {p['live_green_border']};
        }}
        QLabel#hudTelemetryLabel[variant="nominal"] {{
            color: {p['live_green']};
            background: {p['live_green_bg']};
            border: 1px solid {p['live_green_border']};
        }}
        QLabel#hudTelemetryLabel[variant="active"] {{
            color: {p['accent']};
            background: {p['accent_bg']};
            border: 1px solid {p['accent_border']};
        }}
        QLabel#hudTelemetryLabel[variant="warning"] {{
            color: {p['amber_tag']};
            background: {p['amber_tag_bg']};
            border: 1px solid {p['amber_tag_border']};
        }}
    """

# ── 4. Reusable Animation Toolkit ──────────────────────────────────────

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
