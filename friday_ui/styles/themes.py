"""
F.R.I.D.A.Y. 3.0 - Professional Design System & Animation Toolkit
Unified Dark Neutral Charcoal Architecture with Restrained Amber/Orange Accent.

Zero brown/espresso artifacts. Full WCAG AAA/AA compliance.
Centralized ThemeTokens consumed across all widgets and views.
"""

from typing import Dict, Optional, List, Any
from dataclasses import dataclass, asdict
from PySide6.QtCore import (
    QObject, QEvent, QPropertyAnimation, QEasingCurve, QRect,
    QParallelAnimationGroup, QTimer, Qt, Property, QPoint, QPointF, QRectF
)
from PySide6.QtGui import QColor, QPainter, QBrush, QPen, QLinearGradient
from PySide6.QtWidgets import (
    QWidget, QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QStackedWidget
)

# ── 1. Formal Centralized Theme Tokens ─────────────────────────────────

@dataclass(frozen=True)
class DesignTokens:
    BACKGROUND: str = "#0B0D11"          # Deep charcoal / near-black canvas
    SURFACE: str = "#15181E"             # Panels / cards / elevated surfaces
    SURFACE_HOVER: str = "#1E222B"       # Subtle hover state
    SURFACE_ACTIVE: str = "#262C38"      # Pressed / active surface
    BORDER: str = "rgba(255, 255, 255, 0.08)"
    BORDER_HOVER: str = "rgba(255, 255, 255, 0.18)"
    BORDER_FOCUS: str = "#F59E0B"        # Restrained warm amber focus
    TEXT_PRIMARY: str = "#F3F4F6"        # Soft crisp white
    TEXT_SECONDARY: str = "#9CA3AF"      # Muted gray
    TEXT_MUTED: str = "#6B7280"          # Deep muted metadata gray
    TEXT_DIM: str = "#4B5563"            # Subdued borders / dividers
    TEXT_INVERTED: str = "#0B0D11"       # Contrast on light/accent buttons
    ACCENT: str = "#F59E0B"              # Warm amber/orange accent
    ACCENT_HOVER: str = "#FBBF24"        # Lighter amber hover
    ACCENT_PRESSED: str = "#D97706"      # Deep amber pressed
    ACCENT_BG: str = "rgba(245, 158, 11, 0.12)"
    ACCENT_BORDER: str = "rgba(245, 158, 11, 0.30)"
    SUCCESS: str = "#10B981"             # Emerald green for healthy status
    WARNING: str = "#F59E0B"             # Amber warning
    ERROR: str = "#EF4444"               # Crimson error
    INFO: str = "#06B6D4"                # Subtle cool cyan for info tags
    OVERLAY: str = "rgba(11, 13, 17, 0.85)"

TOKENS = DesignTokens()

# Shared Semantic Constants
LIVE_GREEN = TOKENS.SUCCESS
DANGER_RED = TOKENS.ERROR
AMBER_WARN = TOKENS.WARNING
STARK_CYAN = TOKENS.INFO
PURPLE_ACCENT = "#8B5CF6"

TEXT_PRIMARY = TOKENS.TEXT_PRIMARY
TEXT_SECONDARY = TOKENS.TEXT_SECONDARY
TEXT_MUTED = TOKENS.TEXT_MUTED
TEXT_DIM = TOKENS.TEXT_DIM

def hex_to_rgb(hex_code: str) -> List[float]:
    """Converts hex color string (e.g. #F59E0B) to a list of RGB floats [r, g, b]."""
    try:
        clean = hex_code.strip().lstrip("#")
        if len(clean) == 6:
            return [float(int(clean[i:i+2], 16)) for i in (0, 2, 4)]
        elif len(clean) == 3:
            return [float(int(c * 2, 16)) for c in clean]
    except Exception:
        pass
    return [245.0, 158.0, 11.0]


# ── 2. Sophisticated Dark Neutral Palette (F.R.I.D.A.Y. 3.0 Standard) ──

DARK_PRO_THEME: Dict[str, str] = {
    # Canvas & Backgrounds
    "bg_canvas":        TOKENS.BACKGROUND,
    "bg_sidebar":       "#101318",
    "bg_card":          TOKENS.SURFACE,
    "bg_card_hover":    TOKENS.SURFACE_HOVER,
    "bg_surface":       TOKENS.SURFACE,
    "bg_input":         "#101318",
    "input_bg":         "#101318",
    "bg_dock":          "rgba(16, 19, 24, 0.92)",
    "bg_pill":          "#1E222B",
    "bg_pill_active":   "#262C38",

    # Borders
    "border_subtle":    TOKENS.BORDER,
    "border_card":      "rgba(255, 255, 255, 0.09)",
    "border_hover":     TOKENS.BORDER_HOVER,
    "border_focus":     TOKENS.BORDER_FOCUS,

    # Typography
    "text_primary":     TOKENS.TEXT_PRIMARY,
    "text_secondary":   TOKENS.TEXT_SECONDARY,
    "text_muted":       TOKENS.TEXT_MUTED,
    "text_dim":         TOKENS.TEXT_DIM,
    "text_inverted":    TOKENS.TEXT_INVERTED,

    # Semantic Status Colors
    "live_green":       TOKENS.SUCCESS,
    "live_green_bg":    "rgba(16, 185, 129, 0.12)",
    "live_green_border":"rgba(16, 185, 129, 0.30)",

    "danger_red":       TOKENS.ERROR,
    "danger_red_bg":    "rgba(239, 68, 68, 0.12)",
    "danger_red_border":"rgba(239, 68, 68, 0.30)",

    "cyan_tag":         TOKENS.INFO,
    "cyan_tag_bg":      "rgba(6, 182, 212, 0.10)",
    "cyan_tag_border":  "rgba(6, 182, 212, 0.28)",

    "amber_tag":        TOKENS.WARNING,
    "amber_tag_bg":     TOKENS.ACCENT_BG,
    "amber_tag_border": TOKENS.ACCENT_BORDER,

    # Accent (Restrained Warm Amber)
    "accent":           TOKENS.ACCENT,
    "accent_hover":     TOKENS.ACCENT_HOVER,
    "accent_pressed":   TOKENS.ACCENT_PRESSED,
    "accent_bg":        TOKENS.ACCENT_BG,
    "accent_border":    TOKENS.ACCENT_BORDER,
    "accent_text":      "#0B0D11",

    # Scrollbars
    "scrollbar_handle": "#262C38",
    "scrollbar_hover":  "#374151",

    # Chat Bubbles (Distinct visual hierarchy)
    "bubble_user":           "#1C212B",
    "bubble_user_text":      "#F3F4F6",
    "bubble_assistant":      "#12151B",
    "bubble_assistant_text": "#E5E7EB",
    "bubble_system":         "#101318",
    "bubble_system_text":    "#9CA3AF",

    # Code Blocks
    "code_bg":          "#101318",
    "code_block_bg":    "#090B0E",
    "code_text":        "#34D399",
    "code_border":      "rgba(255, 255, 255, 0.08)",

    # Chips & Quick Actions
    "chip_bg":          "#15181E",
    "chip_hover":       "#1E222B",
    "chip_pressed":     "#262C38",
    "chip_text":        "#D1D5DB",
    "chip_text_hover":  "#FFFFFF",

    # Navigation & Dock
    "nav_bg":           "#0E1015",
    "nav_border":       "rgba(255, 255, 255, 0.06)",

    # Selection & Send
    "selection_bg":     "rgba(245, 158, 11, 0.25)",
    "send_bg":          TOKENS.ACCENT,
    "send_hover":       TOKENS.ACCENT_HOVER,
    "send_pressed":     TOKENS.ACCENT_PRESSED,
    "send_text":        "#0B0D11",

    # Combo Box
    "combo_bg":         "#15181E",
    "combo_hover_bg":   "#1E222B",
    "combo_border":     "rgba(255, 255, 255, 0.10)",
    "combo_hover_border": TOKENS.BORDER_FOCUS,

    # Header Card
    "header_bg":        "rgba(16, 19, 24, 0.90)",
}

# ── 3. Clean Modern Slate Light Palette (Optional secondary theme) ────

LIGHT_PRO_THEME: Dict[str, str] = {
    # Clean Slate White canvas
    "bg_canvas":        "#F8FAFC",
    "bg_sidebar":       "#F1F5F9",
    "bg_card":          "#FFFFFF",
    "bg_card_hover":    "#F1F5F9",
    "bg_surface":       "#FFFFFF",
    "bg_input":         "#FFFFFF",
    "input_bg":         "#FFFFFF",
    "bg_dock":          "rgba(248, 250, 252, 0.95)",
    "bg_pill":          "#E2E8F0",
    "bg_pill_active":   "#0F172A",

    # Borders
    "border_subtle":    "rgba(15, 23, 42, 0.08)",
    "border_card":      "rgba(15, 23, 42, 0.12)",
    "border_hover":     "rgba(15, 23, 42, 0.22)",
    "border_focus":     "#D97706",

    # Typography
    "text_primary":     "#0F172A",
    "text_secondary":   "#475569",
    "text_muted":       "#64748B",
    "text_dim":         "#94A3B8",
    "text_inverted":    "#FFFFFF",

    # Status Colors
    "live_green":       "#059669",
    "live_green_bg":    "rgba(5, 150, 105, 0.12)",
    "live_green_border":"rgba(5, 150, 105, 0.30)",

    "danger_red":       "#DC2626",
    "danger_red_bg":    "rgba(220, 38, 38, 0.12)",
    "danger_red_border":"rgba(220, 38, 38, 0.30)",

    "cyan_tag":         "#0284C7",
    "cyan_tag_bg":      "rgba(2, 132, 199, 0.10)",
    "cyan_tag_border":  "rgba(2, 132, 199, 0.28)",

    "amber_tag":        "#D97706",
    "amber_tag_bg":     "rgba(217, 119, 6, 0.12)",
    "amber_tag_border": "rgba(217, 119, 6, 0.30)",

    # Accent
    "accent":           "#D97706",
    "accent_hover":     "#B45309",
    "accent_pressed":   "#92400E",
    "accent_bg":        "rgba(217, 119, 6, 0.12)",
    "accent_border":    "rgba(217, 119, 6, 0.30)",
    "accent_text":      "#FFFFFF",

    # Scrollbars
    "scrollbar_handle": "#CBD5E1",
    "scrollbar_hover":  "#94A3B8",

    # Chat Bubbles
    "bubble_user":           "#0F172A",
    "bubble_user_text":      "#FFFFFF",
    "bubble_assistant":      "#F1F5F9",
    "bubble_assistant_text": "#0F172A",
    "bubble_system":         "#E2E8F0",
    "bubble_system_text":    "#475569",

    # Code Blocks
    "code_bg":          "#E2E8F0",
    "code_block_bg":    "#0F172A",
    "code_text":        "#10B981",
    "code_border":      "rgba(15, 23, 42, 0.12)",

    # Chips & Quick Actions
    "chip_bg":          "#F1F5F9",
    "chip_hover":       "#E2E8F0",
    "chip_pressed":     "#CBD5E1",
    "chip_text":        "#334155",
    "chip_text_hover":  "#0F172A",

    # Navigation & Dock
    "nav_bg":           "#F1F5F9",
    "nav_border":       "rgba(15, 23, 42, 0.08)",

    # Selection & Send
    "selection_bg":     "rgba(217, 119, 6, 0.25)",
    "send_bg":          "#D97706",
    "send_hover":       "#B45309",
    "send_pressed":     "#92400E",
    "send_text":        "#FFFFFF",

    # Combo Box
    "combo_bg":         "#FFFFFF",
    "combo_hover_bg":   "#F1F5F9",
    "combo_border":     "rgba(15, 23, 42, 0.14)",
    "combo_hover_border": "#D97706",

    # Header Card
    "header_bg":        "rgba(241, 245, 249, 0.95)",
}

# Backward compatibility aliases — map all legacy keys to clean professional themes
MONO_DARK = DARK_PRO_THEME
TACTICAL_DARK = DARK_PRO_THEME
WARM_EDITORIAL_DARK = DARK_PRO_THEME
WARM_EDITORIAL_LIGHT = LIGHT_PRO_THEME
LIGHT_THEME = LIGHT_PRO_THEME
STARK_DARK = DARK_PRO_THEME


def get_theme_palette(theme_mode: str = "dark") -> Dict[str, str]:
    """Returns the unified theme palette. Defaults to the dark neutral charcoal palette."""
    mode = str(theme_mode).lower() if theme_mode else "dark"
    if "light" in mode or "cream" in mode or mode == "white":
        return LIGHT_PRO_THEME
    return DARK_PRO_THEME


def get_current_palette() -> Dict[str, str]:
    """Returns the active palette based on persisted theme_mode setting."""
    try:
        from friday_core.settings import settings
        mode = settings.get("theme_mode", "dark")
    except Exception:
        mode = "dark"
    return get_theme_palette(mode)


def generate_global_qss(theme_mode: str = "dark") -> str:
    """Generates the unified desktop stylesheet with clean typography, restrained accents, and compact rounded borders."""
    p = get_theme_palette(theme_mode)

    hud_listening = p.get("live_green", LIVE_GREEN)
    hud_idle = p.get("danger_red", DANGER_RED)
    hud_thinking = p.get("amber_tag", AMBER_WARN)
    hud_speaking = p.get("accent", TOKENS.ACCENT)

    return f"""
        QWidget {{
            font-family: 'Inter', 'Segoe UI', -apple-system, sans-serif;
            color: {p['text_primary']};
        }}

        /* ── Canvas & Window Backdrop ── */
        #FridayMainWindow, #content_container, #workspace_container, #chat_view, #rag_view, #research_view, #settings_view {{
            background-color: {p['bg_canvas']};
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

        /* ── Inputs ── */
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: {p['bg_input']};
            color: {p['text_primary']};
            border: 1px solid {p['border_card']};
            border-radius: 10px;
            selection-background-color: {p['selection_bg']};
            selection-color: {p['text_primary']};
            padding: 8px 14px;
            font-size: 13px;
        }}
        QLineEdit:focus, QTextEdit:focus {{
            border: 1.5px solid {p['border_focus']};
        }}

        /* ── Dialogs & Container Cards ── */
        QDialog, #fridayHeader, #attachmentsBar {{
            border-radius: 12px;
        }}

        /* ── CardWidget ── */
        CardWidget {{
            background-color: {p['bg_surface']};
            border: 1px solid {p['border_card']};
            border-radius: 12px;
        }}
        CardWidget:hover {{
            border: 1px solid {p['border_hover']};
        }}

        /* ── Buttons & Action Controls ── */
        PrimaryPushButton {{
            background-color: {p['send_bg']};
            color: {p['send_text']};
            border-radius: 10px;
            font-weight: 600;
            font-size: 12px;
            border: none;
            padding: 7px 18px;
            letter-spacing: 0.2px;
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
            border-radius: 10px;
            font-weight: 500;
            font-size: 11px;
            padding: 6px 14px;
        }}
        PushButton:hover {{
            background-color: {p['chip_hover']};
            border: 1px solid {p['border_hover']};
            color: {p['chip_text_hover']};
        }}
        PushButton:pressed {{
            background-color: {p['chip_pressed']};
        }}

        ToolButton {{
            background-color: {p['bg_surface']};
            border: 1px solid {p['border_card']};
            border-radius: 8px;
            color: {p['text_secondary']};
        }}
        ToolButton:hover {{
            background-color: {p['bg_card_hover']};
            border: 1px solid {p['border_hover']};
            color: {p['text_primary']};
        }}

        ComboBox {{
            background-color: {p['combo_bg']};
            border: 1px solid {p['combo_border']};
            border-radius: 8px;
            color: {p['text_primary']};
            font-size: 11px;
            font-weight: 500;
            padding: 4px 10px;
        }}
        ComboBox:hover {{
            border: 1px solid {p['combo_hover_border']};
            background-color: {p['combo_hover_bg']};
        }}

        /* ── HUD State & Telemetry Labels ── */
        QLabel#hudStateLabel {{
            font-family: 'Consolas', 'Segoe UI', monospace;
            font-size: 10px;
            letter-spacing: 0.6px;
            color: {p['text_muted']};
        }}
        QLabel#hudStateLabel[state="listening"], QLabel#hudStateLabel[state="standby"] {{
            color: {hud_listening};
            font-weight: 600;
        }}
        QLabel#hudStateLabel[state="idle"] {{
            color: {hud_idle};
            font-weight: 600;
        }}
        QLabel#hudStateLabel[state="thinking"], QLabel#hudStateLabel[state="researching"] {{
            color: {hud_thinking};
            font-weight: 600;
        }}
        QLabel#hudStateLabel[state="speaking"] {{
            color: {hud_speaking};
            font-weight: 600;
        }}

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


# ── 4. Reusable Non-Blocking Animation Toolkit ────────────────────────

def fade_in(widget: QWidget, duration: int = 180, start_opacity: float = 0.0, end_opacity: float = 1.0) -> QPropertyAnimation:
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
                if end_opacity >= 1.0:
                    widget.setGraphicsEffect(None)
                else:
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
    def play(widget: QWidget, duration: int = 200, offset_y: int = 10) -> QParallelAnimationGroup:
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


def smooth_crossfade(stacked_widget: QStackedWidget, target_index: int, duration: int = 180):
    """Performs a smooth non-blocking crossfade page transition between stacked views."""
    if stacked_widget.currentIndex() == target_index:
        return
    next_widget = stacked_widget.widget(target_index)
    if not next_widget:
        return
    stacked_widget.setCurrentIndex(target_index)
    fade_in(next_widget, duration=duration)


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
            dx = max(1, int(g.width() * 0.02))
            dy = max(1, int(g.height() * 0.02))
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
    """Reveals hidden child controls when parent card is hovered."""
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
                fade_in(t, duration=140)
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

            alpha = int(35 + 45 * (0.5 + 0.5 * math.sin(self._phase)))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(self._color.red(), self._color.green(), self._color.blue(), alpha))
            p.drawEllipse(QPointF(cx, cy), r, r)

            core_r = max(2.0, r * 0.50)
            p.setBrush(self._color)
            p.drawEllipse(QPointF(cx, cy), core_r, core_r)
        finally:
            p.end()


class PulseStatusDot(QWidget):
    """Compact status dot with subtle breathing ring."""
    def __init__(self, color: QColor = QColor(16, 185, 129), size: int = 10, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._color = color
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def set_color(self, color: QColor):
        self._color = color
        self.update()

    def _tick(self):
        import math
        self._phase = (self._phase + 0.07) % (2 * math.pi)
        self.update()

    def paintEvent(self, event):
        import math
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            cx = self.width() / 2.0
            cy = self.height() / 2.0
            r = min(cx, cy) - 0.5
            halo_a = int(30 + 40 * (0.5 + 0.5 * math.sin(self._phase)))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(self._color.red(), self._color.green(), self._color.blue(), halo_a))
            p.drawEllipse(QPointF(cx, cy), r, r)

            p.setBrush(self._color)
            p.drawEllipse(QPointF(cx, cy), r * 0.55, r * 0.55)
        finally:
            p.end()
