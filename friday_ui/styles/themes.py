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

# ── 3. Complete Warm Editorial 60-30-10 Palettes ───────────────────────
# 60% Dominant Cream (#FDFBF7), 30% Warm Espresso (#2B2625), 10% Terracotta (#D9745B) & Sage (#6B8E78)
WARM_EDITORIAL_LIGHT: Dict[str, str] = {
    # 60% Dominant Background
    "bg_canvas":        "#FDFBF7",
    "bg_sidebar":       "rgba(253, 251, 247, 0.95)",
    "bg_card":          "#F7F4EE",
    "bg_card_hover":    "#EFECE5",
    "bg_surface":       "#FFFFFF",
    "bg_input":         "#FFFFFF",
    "input_bg":         "#FFFFFF",
    "bg_dock":          "rgba(247, 244, 238, 0.95)",
    "bg_pill":          "#EFECE5",
    "bg_pill_active":   "#2B2625",

    # 30% Structural Elements & Borders
    "border_subtle":    "rgba(43, 38, 37, 0.08)",
    "border_card":      "rgba(43, 38, 37, 0.12)",
    "border_hover":     "rgba(43, 38, 37, 0.25)",
    "border_focus":     "#D9745B",

    # Typography (High-contrast WCAG AAA/AA)
    "text_primary":     "#2B2625",
    "text_secondary":   "#5C5552",
    "text_muted":       "#827A76",
    "text_dim":         "#A8A19C",
    "text_inverted":    "#FDFBF7",

    # 10% Accent Interaction Points
    "accent":           "#D9745B",
    "accent_hover":     "#C66249",
    "accent_pressed":   "#B25039",
    "accent_bg":        "rgba(217, 116, 91, 0.12)",
    "accent_border":    "rgba(217, 116, 91, 0.35)",
    "accent_text":      "#FFFFFF",

    # Secondary Accent: Muted Sage
    "live_green":       "#6B8E78",
    "live_green_bg":    "rgba(107, 142, 120, 0.14)",
    "live_green_border":"rgba(107, 142, 120, 0.35)",

    "danger_red":       "#D9745B",
    "danger_red_bg":    "rgba(217, 116, 91, 0.14)",
    "danger_red_border":"rgba(217, 116, 91, 0.35)",

    "cyan_tag":         "#6B8E78",
    "cyan_tag_bg":      "rgba(107, 142, 120, 0.12)",
    "cyan_tag_border":  "rgba(107, 142, 120, 0.30)",

    "amber_tag":        "#D9745B",
    "amber_tag_bg":     "rgba(217, 116, 91, 0.12)",
    "amber_tag_border": "rgba(217, 116, 91, 0.30)",

    # Scrollbars
    "scrollbar_handle": "#DDD6CE",
    "scrollbar_hover":  "#C2B9AF",

    # Chat Bubbles (Heavily rounded editorial cards)
    "bubble_user":      "#2B2625",
    "bubble_assistant":  "#F7F4EE",
    "bubble_system":    "#EFECE5",

    # Code Blocks
    "code_bg":          "#EFECE5",
    "code_block_bg":    "#2B2625",
    "code_text":        "#7FA88D",
    "code_border":      "rgba(43, 38, 37, 0.14)",

    # Chips & Quick Actions (Pills >= 16px)
    "chip_bg":          "#F7F4EE",
    "chip_hover":       "#EFECE5",
    "chip_pressed":     "#E3DDD4",
    "chip_text":        "#5C5552",
    "chip_text_hover":  "#2B2625",

    # Navigation & Dock
    "nav_bg":           "rgba(253, 251, 247, 0.95)",
    "nav_border":       "rgba(43, 38, 37, 0.08)",

    # Selection & Send
    "selection_bg":     "rgba(217, 116, 91, 0.25)",
    "send_bg":          "#D9745B",
    "send_hover":       "#C66249",
    "send_pressed":     "#B25039",
    "send_text":        "#FFFFFF",

    # Combo Box
    "combo_bg":         "#FFFFFF",
    "combo_hover_bg":   "#F7F4EE",
    "combo_border":     "rgba(43, 38, 37, 0.14)",
    "combo_hover_border": "#D9745B",

    # Header Card
    "header_bg":        "rgba(247, 244, 238, 0.90)",
}

# 60% Dominant Espresso Charcoal (#1C1917), 30% Warm Cream Typography (#FDFBF7), 10% Soft Terracotta (#E07A5F) & Sage (#7FA88D)
WARM_EDITORIAL_DARK: Dict[str, str] = {
    # 60% Dominant Background
    "bg_canvas":        "#1C1917",
    "bg_sidebar":       "#151312",
    "bg_card":          "rgba(38, 33, 31, 0.75)",
    "bg_card_hover":    "#322B29",
    "bg_surface":       "#25201E",
    "bg_input":         "#171514",
    "input_bg":         "#171514",
    "bg_dock":          "rgba(23, 20, 19, 0.90)",
    "bg_pill":          "#322B29",
    "bg_pill_active":   "#FDFBF7",

    # 30% Structural Elements & Borders
    "border_subtle":    "rgba(253, 251, 247, 0.08)",
    "border_card":      "rgba(253, 251, 247, 0.12)",
    "border_hover":     "rgba(253, 251, 247, 0.25)",
    "border_focus":     "#E07A5F",

    # Typography (High-contrast Warm Cream)
    "text_primary":     "#FDFBF7",
    "text_secondary":   "#C4BCB5",
    "text_muted":       "#8E8681",
    "text_dim":         "#5E5652",
    "text_inverted":    "#1C1917",

    # 10% Accent Interaction Points
    "accent":           "#E07A5F",
    "accent_hover":     "#EB8C72",
    "accent_pressed":   "#C9674D",
    "accent_bg":        "rgba(224, 122, 95, 0.15)",
    "accent_border":    "rgba(224, 122, 95, 0.35)",
    "accent_text":      "#FFFFFF",

    # Secondary Accent: Muted Sage
    "live_green":       "#7FA88D",
    "live_green_bg":    "rgba(127, 168, 141, 0.14)",
    "live_green_border":"rgba(127, 168, 141, 0.35)",

    "danger_red":       "#E07A5F",
    "danger_red_bg":    "rgba(224, 122, 95, 0.14)",
    "danger_red_border":"rgba(224, 122, 95, 0.35)",

    "cyan_tag":         "#7FA88D",
    "cyan_tag_bg":      "rgba(127, 168, 141, 0.12)",
    "cyan_tag_border":  "rgba(127, 168, 141, 0.30)",

    "amber_tag":        "#E07A5F",
    "amber_tag_bg":     "rgba(224, 122, 95, 0.12)",
    "amber_tag_border": "rgba(224, 122, 95, 0.30)",

    # Scrollbars
    "scrollbar_handle": "#3A3330",
    "scrollbar_hover":  "#4D4440",

    # Chat Bubbles (Heavily rounded editorial cards)
    "bubble_user":      "#322B29",
    "bubble_assistant":  "#1F1A19",
    "bubble_system":    "#181514",

    # Code Blocks
    "code_bg":          "#282321",
    "code_block_bg":    "#12100F",
    "code_text":        "#7FA88D",
    "code_border":      "rgba(253, 251, 247, 0.12)",

    # Chips & Quick Actions (Pills >= 16px)
    "chip_bg":          "#25201E",
    "chip_hover":       "#322B29",
    "chip_pressed":     "#3D3532",
    "chip_text":        "#C4BCB5",
    "chip_text_hover":  "#FDFBF7",

    # Navigation & Dock
    "nav_bg":           "rgba(21, 19, 18, 0.95)",
    "nav_border":       "rgba(253, 251, 247, 0.08)",

    # Selection & Send
    "selection_bg":     "rgba(224, 122, 95, 0.30)",
    "send_bg":          "#E07A5F",
    "send_hover":       "#EB8C72",
    "send_pressed":     "#C9674D",
    "send_text":        "#FFFFFF",

    # Combo Box
    "combo_bg":         "#25201E",
    "combo_hover_bg":   "#322B29",
    "combo_border":     "rgba(253, 251, 247, 0.14)",
    "combo_hover_border": "#E07A5F",

    # Header Card
    "header_bg":        "rgba(32, 28, 26, 0.85)",
}

# Aliases for compatibility
LIGHT_THEME = WARM_EDITORIAL_LIGHT
STARK_DARK = MONO_DARK

def get_theme_palette(theme_mode: str = "dark") -> Dict[str, str]:
    mode = str(theme_mode).lower()
    if "warm_light" in mode or "editorial_light" in mode or mode == "light":
        return WARM_EDITORIAL_LIGHT
    elif "warm_dark" in mode or "editorial_dark" in mode or "warm" in mode or "editorial" in mode:
        return WARM_EDITORIAL_DARK
    elif "tactical" in mode:
        return TACTICAL_DARK
    elif "neon" in mode:
        return MONO_DARK
    elif "void" in mode or "mono" in mode:
        return MONO_DARK
    # Default to Warm Editorial Dark for soothing, calming experience
    return WARM_EDITORIAL_DARK


def get_current_palette() -> Dict[str, str]:
    """Returns the active palette based on the persisted theme_mode setting."""
    try:
        from friday_core.settings import settings
        mode = settings.get("theme_mode", "dark")
    except Exception:
        mode = "dark"
    return get_theme_palette(mode)


def generate_global_qss(theme_mode: str = "dark") -> str:
    """Generates the unified desktop stylesheet with 60-30-10 tokens, 16px+ rounded corners and clean typography."""
    p = get_theme_palette(theme_mode)
    is_light = "light" in str(theme_mode).lower()

    # Use appropriate accent/status colors for HUD labels
    hud_listening = p.get("live_green", LIVE_GREEN)
    hud_idle = p.get("danger_red", DANGER_RED)
    hud_thinking = p.get("amber_tag", AMBER_WARN)
    hud_speaking = p.get("accent", STARK_CYAN)

    return f"""
        QWidget {{
            font-family: 'Plus Jakarta Sans', 'Inter', 'Segoe UI', -apple-system, sans-serif;
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

        /* ── Inputs & Buttons (16px+ Soft Heavily-Rounded Corners) ── */
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: {p['bg_input']};
            color: {p['text_primary']};
            border: 1px solid {p['border_card']};
            border-radius: 16px;
            selection-background-color: {p['selection_bg']};
            padding: 8px 12px;
        }}
        QLineEdit:focus, QTextEdit:focus {{
            border: 1.5px solid {p['border_focus']};
        }}

        /* ── CardWidget (QFluentWidgets with 18px radius) ── */
        CardWidget {{
            background-color: {p['bg_surface']};
            border: 1px solid {p['border_card']};
            border-radius: 18px;
        }}
        CardWidget:hover {{
            border: 1px solid {p['border_hover']};
        }}

        /* ── Buttons & Action Controls (16px+ Heavily-Rounded Corners) ── */
        PrimaryPushButton {{
            background-color: {p['send_bg']};
            color: {p['send_text']};
            border-radius: 16px;
            font-weight: bold;
            font-size: 12px;
            border: none;
            padding: 6px 18px;
            letter-spacing: 0.3px;
        }}
        PrimaryPushButton:hover {{
            background-color: {p['send_hover']};
        }}
        PrimaryPushButton:pressed {{
            background-color: {p['send_pressed']};
        }}

        PushButton {{
            background-color: {p['chip_bg']};
            color: {p['chip_text']};
            border: 1px solid {p['border_card']};
            border-radius: 16px;
            font-weight: 500;
            font-size: 11px;
            padding: 5px 14px;
        }}
        PushButton:hover {{
            background-color: {p['chip_hover']};
            border: 1px solid {p['border_hover']};
            color: {p['chip_text_hover']};
        }}
        PushButton:pressed {{
            background-color: {p['chip_pressed']};
        }}

        ComboBox {{
            background-color: {p['combo_bg']};
            border: 1px solid {p['combo_border']};
            border-radius: 14px;
            color: {p['text_primary']};
            font-size: 11px;
            font-weight: 500;
            padding: 4px 10px;
        }}
        ComboBox:hover {{
            border: 1px solid {p['combo_hover_border']};
            background-color: {p['combo_hover_bg']};
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
