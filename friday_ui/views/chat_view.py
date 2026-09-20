"""
F.R.I.D.A.Y. 2.0 - Chat View
Premium Reactive Desktop Chat Thread — Glassmorphism, Smooth Animations, Full-Width Layout
"""

import os
import asyncio
import math
import logging
from datetime import datetime

logger = logging.getLogger("FRIDAY.ChatView")
from PySide6.QtCore import (
    Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve,
    QParallelAnimationGroup, QSize, Property, QRectF, QPointF
)
from PySide6.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QLinearGradient,
    QRadialGradient, QPainterPath, QGuiApplication, QKeySequence, QShortcut
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QFrame, QSizePolicy, QGraphicsDropShadowEffect, QSpacerItem,
    QFileDialog
)
from qfluentwidgets import (
    PrimaryPushButton, PushButton, LineEdit, ToolButton,
    FluentIcon, PillPushButton, IconWidget, InfoBar, InfoBarPosition,
    ScrollArea, RoundMenu, Action, ComboBox, TransparentToolButton
)

from friday_core.settings import settings
from friday_ui.core.session_store import SessionStore
from friday_ui.widgets.chat_bubble import ChatBubble
from friday_ui.widgets.arc_reactor import ArcReactorWidget
from friday_ui.widgets.glass_panel import GlassPanel
from friday_ui.styles.themes import STARK_CYAN, LIVE_GREEN, DANGER_RED, AMBER_WARN, get_current_palette


class GlowLine(QWidget):
    """Animated horizontal glow line separator."""
    def __init__(self, color: QColor = None, parent=None):
        super().__init__(parent)
        self.setFixedHeight(2)
        p = get_current_palette()
        self._color = color if color is not None else QColor(p.get('accent', '#D9745B'))
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, '_timer') and not self._timer.isActive():
            self._timer.start(33)

    def hideEvent(self, event):
        super().hideEvent(event)
        if hasattr(self, '_timer') and self._timer.isActive():
            self._timer.stop()

    def _tick(self):
        self._phase = (self._phase + 0.04) % (2 * math.pi)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            w = self.width()
            grad = QLinearGradient(0, 0, w, 0)
            shimmer = 0.5 + 0.5 * math.sin(self._phase)
            c = self._color
            grad.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), 20))
            grad.setColorAt(max(0, shimmer - 0.15), QColor(c.red(), c.green(), c.blue(), 40))
            grad.setColorAt(shimmer, QColor(c.red(), c.green(), c.blue(), 200))
            grad.setColorAt(min(1, shimmer + 0.15), QColor(c.red(), c.green(), c.blue(), 40))
            grad.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 20))
            p.setPen(Qt.NoPen)
            p.setBrush(grad)
            p.drawRoundedRect(QRectF(0, 0, w, 2), 1, 1)
        finally:
            p.end()


class TypingIndicator(QWidget):
    """Three-dot pulsating typing indicator."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(60, 24)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._visible = False

    def showEvent(self, event):
        super().showEvent(event)
        if self._visible and hasattr(self, '_timer') and not self._timer.isActive():
            self._timer.start(33)

    def hideEvent(self, event):
        super().hideEvent(event)
        if hasattr(self, '_timer') and self._timer.isActive():
            self._timer.stop()

    def show_indicator(self):
        self._visible = True
        self._timer.start(33)
        self.show()

    def hide_indicator(self):
        self._visible = False
        self._timer.stop()
        self.hide()

    def _tick(self):
        self._phase += 0.10
        self.update()

    def paintEvent(self, event):
        if not self._visible:
            return
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            palette = get_current_palette()
            accent_c = QColor(palette.get('accent', '#D9745B'))
            for i in range(3):
                raw_s = math.sin(self._phase - i * 0.65)
                eased_s = math.copysign(abs(raw_s) ** 1.3, raw_s)
                offset = eased_s * 3.5
                alpha = int(90 + 165 * max(0.0, eased_s))
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(accent_c.red(), accent_c.green(), accent_c.blue(), alpha))
                cx = 12 + i * 18
                cy = 12 + offset
                p.drawEllipse(QPointF(cx, cy), 3.5, 3.5)
        finally:
            p.end()


class ChatView(QWidget):
    """
    Main conversational interface of F.R.I.D.A.Y. 2.0.
    Full-width, glassmorphic, animated chat with smooth scrolling.
    """
    command_submitted = Signal(str, str)  # (full_command, display_text)
    voice_toggle_requested = Signal()
    doc_ingest_requested = Signal(str, str) # (title, path)
    deep_research_requested = Signal(str)   # (topic)
    model_changed = Signal(str)
    voice_changed = Signal(str)
    stop_requested = Signal()
    inspector_toggle_requested = Signal()
    session_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.attached_files = []
        self.deep_research_active = False
        self._current_streaming_bubble = None
        self._streaming_session_id = None
        self._is_generating = False
        self._last_streamed_text = ""
        self.session_store = SessionStore()
        self.current_session_id = None
        self._is_loading_session = False
        self._init_ui()
        self._load_sessions_list()

    def _init_ui(self):
        p = get_current_palette()
        self.setObjectName("chat_view")
        self.setStyleSheet("""
            QWidget#chat_view {
                background-color: transparent;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 14, 24, 12)
        layout.setSpacing(10)

        # ── 1. Editorial Header Banner ─────────────────────────────
        self.header_card = GlassPanel(
            self,
            bg_color=p['header_bg'],
            border_color=p['border_subtle'],
            radius=16,
            enable_shadow=False
        )
        self.header_card.setObjectName("fridayHeader")
        header_card = self.header_card

        header_layout = QHBoxLayout(self.header_card)
        header_layout.setContentsMargins(16, 8, 16, 8)
        header_layout.setSpacing(12)

        # Brand Identity (Warm Monogram + Editorial Title)
        brand_layout = QHBoxLayout()
        brand_layout.setSpacing(10)

        self.brand_avatar = QLabel("F")
        self.brand_avatar.setFixedSize(32, 32)
        self.brand_avatar.setAlignment(Qt.AlignCenter)
        self.brand_avatar.setStyleSheet(f"""
            QLabel {{
                background-color: {p['accent_bg']};
                color: {p['accent']};
                border: 1.5px solid {p['accent_border']};
                border-radius: 16px;
                font-family: 'Plus Jakarta Sans', 'Segoe UI', sans-serif;
                font-size: 14px;
                font-weight: bold;
            }}
        """)
        brand_layout.addWidget(self.brand_avatar)

        titles_box = QVBoxLayout()
        titles_box.setSpacing(1)
        self.title_label = QLabel("F.R.I.D.A.Y.")
        self.title_label.setFont(QFont("Plus Jakarta Sans", 11, QFont.Bold))
        self.title_label.setStyleSheet(f"color: {p['text_primary']}; letter-spacing: 0.5px; border: none; background: transparent;")
        self.subtitle_label = QLabel("Editorial Intelligence")
        self.subtitle_label.setFont(QFont("Plus Jakarta Sans", 8))
        self.subtitle_label.setStyleSheet(f"color: {p['text_muted']}; border: none; background: transparent;")
        titles_box.addWidget(self.title_label)
        titles_box.addWidget(self.subtitle_label)
        brand_layout.addLayout(titles_box)
        header_layout.addLayout(brand_layout)

        header_layout.addStretch(1)

        # Keep arc_reactor hidden for backward compatibility with calls
        self.arc_reactor = ArcReactorWidget(size=1, parent=header_card)
        self.arc_reactor.hide()

        # Quick Switchers (Session & Model pills)
        quick_switcher_layout = QHBoxLayout()
        quick_switcher_layout.setSpacing(8)

        self.session_combo = ComboBox(header_card)
        self.session_combo.setFixedHeight(28)
        self.session_combo.setMinimumWidth(150)
        self.session_combo.currentIndexChanged.connect(self._on_session_combo_changed)
        quick_switcher_layout.addWidget(self.session_combo)

        self.new_session_btn = TransparentToolButton(FluentIcon.ADD, header_card)
        self.new_session_btn.setFixedSize(28, 28)
        self.new_session_btn.setToolTip("Start New Session")
        self.new_session_btn.clicked.connect(self._on_new_session)
        quick_switcher_layout.addWidget(self.new_session_btn)

        self.delete_session_btn = TransparentToolButton(FluentIcon.DELETE, header_card)
        self.delete_session_btn.setFixedSize(28, 28)
        self.delete_session_btn.setToolTip("Delete Current Session")
        self.delete_session_btn.clicked.connect(self._on_delete_session)
        quick_switcher_layout.addWidget(self.delete_session_btn)

        self.model_combo = ComboBox(header_card)
        self.model_combo.setFixedHeight(28)
        self.model_combo.setMinimumWidth(150)
        self._refreshing_models = False
        avail_models = settings.get_available_models()
        self.model_combo.addItems(avail_models)
        saved_model = settings.get("model", avail_models[0] if avail_models else "llama3.2:3b")
        idx_m = self.model_combo.findText(saved_model)
        if idx_m >= 0:
            self.model_combo.setCurrentIndex(idx_m)
        else:
            self.model_combo.addItem(saved_model)
            self.model_combo.setCurrentText(saved_model)
        self.model_combo.currentTextChanged.connect(self._on_model_combo_changed)
        settings.add_listener(self._on_settings_updated)
        quick_switcher_layout.addWidget(self.model_combo)

        self.add_model_btn = TransparentToolButton(FluentIcon.ADD, header_card)
        self.add_model_btn.setFixedSize(28, 28)
        self.add_model_btn.setToolTip("Add / Pull AI Model")
        self.add_model_btn.clicked.connect(self._on_add_model_dialog)
        quick_switcher_layout.addWidget(self.add_model_btn)

        self.voice_combo = ComboBox(header_card)
        self.voice_combo.setFixedHeight(28)
        self.voice_combo.addItems([
            "bf_emma (Local FRIDAY)",
            "af_sarah (Local Sarah)",
            "af_bella (Local Bella)",
            "en-US-AriaNeural (Cloud)",
            "en-IE-EmilyNeural (Cloud)",
            "en-GB-SoniaNeural (Cloud)",
            "en-US-JennyNeural (Cloud)"
        ])
        saved_voice = settings.get("voice", "bf_emma")
        for i in range(self.voice_combo.count()):
            if saved_voice in self.voice_combo.itemText(i):
                self.voice_combo.setCurrentIndex(i)
                break
        self.voice_combo.currentTextChanged.connect(self.voice_changed.emit)
        self.voice_combo.hide()

        header_layout.addLayout(quick_switcher_layout)

        # Status Pill
        self.status_pill = QLabel("● STANDBY")
        self.status_pill.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self.status_pill.setAlignment(Qt.AlignCenter)
        self.status_pill.setMinimumWidth(90)
        self.status_pill.setFixedHeight(26)
        self.status_pill.setStyleSheet(f"""
            color: {p['live_green']};
            background-color: {p['live_green_bg']};
            border: 1px solid {p['live_green_border']};
            border-radius: 13px;
            padding: 2px 10px;
            font-family: monospace;
        """)
        header_layout.addWidget(self.status_pill)

        # Inspector Toggle Button (Show/Hide Audit Feed)
        self.inspector_btn = TransparentToolButton(FluentIcon.HISTORY, self.header_card)
        self.inspector_btn.setFixedSize(28, 28)
        self.inspector_btn.setToolTip("Toggle System Inspector & Telemetry Feed")
        self.inspector_btn.clicked.connect(self.inspector_toggle_requested.emit)
        header_layout.addWidget(self.inspector_btn)

        # Theme Mode Toggle Button (Warm Light ☀️ <-> Warm Dark 🌙)
        self.theme_btn = PushButton("🌙 Dark", self.header_card)
        self.theme_btn.setFixedHeight(28)
        self.theme_btn.setMinimumWidth(76)
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.setToolTip("Switch to Warm Dark Mode (60-30-10 Obsidian)")
        self.theme_btn.clicked.connect(self._toggle_theme)
        header_layout.addWidget(self.theme_btn)

        layout.addWidget(self.header_card)

        # Subtle zero-height spacer (replaces harsh glow line)
        self.glow_line = QWidget(self)
        self.glow_line.setFixedHeight(0)
        self.glow_line.hide()
        layout.addWidget(self.glow_line)

        # ── 2. Chat Scroll Area ──────────────────────────
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: 1px solid {p['border_card']};
                border-radius: 16px;
                background-color: {p['bg_canvas']};
            }}
            QScrollBar:vertical {{
                width: 6px;
                background: transparent;
                margin: 4px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {p['scrollbar_handle']};
                border-radius: 3px;
                min-height: 30px;
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
        """)

        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background: transparent;")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(12, 12, 12, 12)
        self.chat_layout.setSpacing(10)
        self.chat_layout.addStretch(1)

        self.scroll_area.setWidget(self.chat_container)
        layout.addWidget(self.scroll_area, 1)

        # ── Typing indicator ──────────────────────────────
        self.typing_indicator = TypingIndicator(self)
        self.typing_indicator.hide()
        layout.addWidget(self.typing_indicator)

        # ── 3. Quick Action Chips (Scrollable) ───────────
        chips_scroll = QScrollArea(self)
        chips_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        chips_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        chips_scroll.setWidgetResizable(True)
        chips_scroll.setFixedHeight(36)
        chips_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        chips_widget = QWidget()
        chips_widget.setStyleSheet("background: transparent;")
        chips_layout = QHBoxLayout(chips_widget)
        chips_layout.setContentsMargins(0, 0, 0, 0)
        chips_layout.setSpacing(6)

        chip_data = [
            ("☁️  Weather",        "weather"),
            ("💻  VS Code",        "open vs code"),
            ("🌐  Edge",           "open edge"),
            ("⚡  Diagnostics",    "system status telemetry"),
            ("📷  Screenshot",     "screenshot"),
            ("🧮  Calculator",     "what is 250 * 18"),
            ("📁  File Explorer",  "open file explorer"),
            ("🎵  Spotify",        "open spotify"),
        ]

        self.chips_buttons = []
        for label, query in chip_data:
            btn = PushButton(label, self)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                PushButton {{
                    background-color: {p['chip_bg']};
                    border: 1px solid {p['border_subtle']};
                    color: {p['chip_text']};
                    font-size: 11px;
                    font-weight: 500;
                    padding: 3px 12px;
                    border-radius: 16px;
                }}
                PushButton:hover {{
                    background-color: {p['chip_hover']};
                    border: 1px solid {p['border_hover']};
                    color: {p['chip_text_hover']};
                }}
                PushButton:pressed {{
                    background-color: {p['chip_pressed']};
                }}
            """)
            btn.clicked.connect(lambda checked=False, q=query: self._on_chip_clicked(q))
            self.chips_buttons.append(btn)
            chips_layout.addWidget(btn)

        chips_layout.addStretch(1)
        chips_scroll.setWidget(chips_widget)
        layout.addWidget(chips_scroll)

        # ── 4. Attachments Bar (Staged files / active Deep Search) ──
        self.attachments_container = QFrame(self)
        self.attachments_container.setObjectName("attachmentsBar")
        self.attachments_container.setStyleSheet(f"""
            QFrame#attachmentsBar {{
                background: {p['bg_surface']};
                border: 1px solid {p['border_subtle']};
                border-radius: 16px;
            }}
        """)
        self.attachments_layout = QHBoxLayout(self.attachments_container)
        self.attachments_layout.setContentsMargins(8, 4, 8, 4)
        self.attachments_layout.setSpacing(6)
        self.attachments_container.hide()
        layout.addWidget(self.attachments_container)

        # ── 5. Modern Floating Input Controls Bar ──────────
        self.input_frame = QFrame(self)
        self.input_frame.setObjectName("fridayInput")
        self.input_frame.setStyleSheet(f"""
            QFrame#fridayInput {{
                background-color: {p['input_bg']};
                border: 1px solid {p['border_card']};
                border-radius: 18px;
            }}
            QFrame#fridayInput:focus-within {{
                border: 1px solid {p['border_focus']};
            }}
        """)

        input_layout = QHBoxLayout(self.input_frame)
        input_layout.setContentsMargins(8, 6, 8, 6)
        input_layout.setSpacing(8)

        # '+' Action Button — modern rounded tool button
        self.attach_btn = ToolButton(FluentIcon.ADD, self)
        self.attach_btn.setFixedSize(34, 34)
        self.attach_btn.setCursor(Qt.PointingHandCursor)
        self.attach_btn.setToolTip("Attach Code, File, or Deep Research")
        self.attach_btn.setStyleSheet(f"""
            ToolButton {{
                background-color: {p['bg_surface']};
                border: 1px solid {p['border_card']};
                border-radius: 14px;
                color: {p['text_secondary']};
            }}
            ToolButton:hover {{
                background-color: {p['bg_card_hover']};
                border: 1px solid {p['border_hover']};
                color: {p['text_primary']};
            }}
        """)
        self.attach_btn.clicked.connect(self._show_attach_menu)
        input_layout.addWidget(self.attach_btn)

        # Text prompt input (Standard QLineEdit without cyan bottom line)
        from PySide6.QtWidgets import QLineEdit as StandardQLineEdit
        self.prompt_input = StandardQLineEdit(self)
        self.prompt_input.setPlaceholderText("Message F.R.I.D.A.Y. (or press Ctrl+Space)...")
        self.prompt_input.setClearButtonEnabled(True)
        self.prompt_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: transparent;
                border: none;
                color: {p['text_primary']};
                font-size: 13.5px;
                padding: 6px 4px;
                selection-background-color: {p['selection_bg']};
                selection-color: {p['text_primary']};
            }}
        """)
        self.prompt_input.returnPressed.connect(self._submit_prompt)
        input_layout.addWidget(self.prompt_input, 1)

        # Mic Toggle Button — modern rounded tool button
        self.mic_btn = ToolButton(FluentIcon.MICROPHONE, self)
        self.mic_btn.setFixedSize(34, 34)
        self.mic_btn.setCursor(Qt.PointingHandCursor)
        self.mic_btn.setToolTip("Toggle Acoustic Sensor / Voice Loop (Ctrl+M)")
        self.mic_btn.setStyleSheet(f"""
            ToolButton {{
                background-color: {p['bg_surface']};
                border: 1px solid {p['border_card']};
                border-radius: 14px;
                color: {p['text_secondary']};
            }}
            ToolButton:hover {{
                background-color: {p['bg_card_hover']};
                border: 1px solid {p['border_hover']};
                color: {p['text_primary']};
            }}
        """)
        self.mic_btn.clicked.connect(self.voice_toggle_requested.emit)
        input_layout.addWidget(self.mic_btn)

        # Send Button
        self.send_btn = PrimaryPushButton("Send", self)
        self.send_btn.setFixedSize(68, 34)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setStyleSheet(f"""
            PrimaryPushButton {{
                background-color: {p['send_bg']};
                color: {p['send_text']};
                border-radius: 17px;
                font-weight: bold;
                font-size: 12.5px;
                border: none;
                letter-spacing: 0.3px;
            }}
            PrimaryPushButton:hover {{
                background-color: {p['send_hover']};
            }}
            PrimaryPushButton:pressed {{
                background-color: {p['send_pressed']};
            }}
        """)
        self.send_btn.clicked.connect(self._on_send_btn_clicked)
        input_layout.addWidget(self.send_btn)

        # Dedicated Stop Voice Button — Prominent crimson button for interrupting vocal playback immediately
        self.stop_btn = PushButton("■ Stop Voice", self)
        self.stop_btn.setFixedSize(102, 34)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setToolTip("Immediately stop vocal playback and generation (Esc)")
        self.stop_btn.setStyleSheet("""
            PushButton {
                background-color: #DC2626;
                border: 1px solid #EF4444;
                font-weight: bold;
                font-size: 12px;
                border-radius: 16px;
                color: #FFFFFF;
                letter-spacing: 0.5px;
            }
            PushButton:hover {
                background-color: #EF4444;
                border: 1px solid #F87171;
            }
            PushButton:pressed {
                background-color: #991B1B;
            }
        """)
        self.stop_btn.clicked.connect(self.stop_generation)
        self.stop_btn.hide()
        input_layout.addWidget(self.stop_btn)

        self.esc_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.esc_shortcut.activated.connect(self._on_escape_pressed)

        self.prompt_input.setToolTip("Press Ctrl + Space to summon F.R.I.D.A.Y. HUD from anywhere in Windows")
        layout.addWidget(self.input_frame)

    def _toggle_theme(self):
        """Toggles between Warm Light (Cream 60-30-10) and Warm Dark (Obsidian) mode."""
        current = settings.get("theme_mode", "warm_light")
        is_light = "light" in str(current).lower()
        new_mode = "warm_dark" if is_light else "warm_light"
        settings.set("theme_mode", new_mode)
        main_win = self.window()
        if hasattr(main_win, '_apply_global_style'):
            main_win._apply_global_style()
        else:
            self.apply_theme(new_mode)

        mode_label = "Warm Dark (Obsidian)" if new_mode == "warm_dark" else "Warm Light (Cream)"
        try:
            InfoBar.info(
                "Theme Switched",
                f"Visual mode set to {mode_label}",
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
                duration=1500
            )
        except Exception:
            pass

    def apply_theme(self, theme_mode: str = None):
        """Applies theme colors dynamically across all header, chat, input, and child components."""
        from friday_ui.styles.themes import get_theme_palette
        p = get_theme_palette(theme_mode) if theme_mode else get_current_palette()
        is_light = "light" in str(theme_mode or settings.get("theme_mode", "warm_light")).lower()

        # 0. Update Theme Toggle Button
        if hasattr(self, 'theme_btn'):
            self.theme_btn.setText("🌙 Dark" if is_light else "☀️ Light")
            self.theme_btn.setToolTip("Switch to Warm Dark Mode (60-30-10 Obsidian)" if is_light else "Switch to Warm Light Mode (60-30-10 Cream)")
            self.theme_btn.setStyleSheet(f"""
                PushButton {{
                    background-color: {p['chip_bg']};
                    border: 1px solid {p['border_subtle']};
                    color: {p['chip_text']};
                    font-size: 11px;
                    font-weight: 600;
                    padding: 3px 12px;
                    border-radius: 14px;
                }}
                PushButton:hover {{
                    background-color: {p['chip_hover']};
                    border: 1px solid {p['border_hover']};
                    color: {p['chip_text_hover']};
                }}
                PushButton:pressed {{
                    background-color: {p['chip_pressed']};
                }}
            """)

        # 1. Update brand avatar & titles
        if hasattr(self, 'brand_avatar'):
            self.brand_avatar.setStyleSheet(f"""
                QLabel {{
                    background-color: {p['accent_bg']};
                    color: {p['accent']};
                    border: 1.5px solid {p['accent_border']};
                    border-radius: 16px;
                    font-family: 'Plus Jakarta Sans', 'Segoe UI', sans-serif;
                    font-size: 14px;
                    font-weight: bold;
                }}
            """)
        if hasattr(self, 'title_label'):
            self.title_label.setStyleSheet(f"color: {p['text_primary']}; letter-spacing: 0.5px; border: none; background: transparent;")
        if hasattr(self, 'subtitle_label'):
            self.subtitle_label.setStyleSheet(f"color: {p['text_muted']}; border: none; background: transparent;")
        if hasattr(self, 'header_card'):
            self.header_card.set_glass_style(
                bg_color=p['header_bg'],
                border_color=p['border_subtle'],
                radius=16
            )
        if hasattr(self, 'status_pill'):
            self.status_pill.setStyleSheet(f"""
                color: {p['live_green']};
                background-color: {p['live_green_bg']};
                border: 1px solid {p['live_green_border']};
                border-radius: 13px;
                padding: 2px 10px;
                font-family: monospace;
            """)

        # 2. Update Scroll Area & Viewport
        if hasattr(self, 'scroll_area'):
            self.scroll_area.setStyleSheet(f"""
                QScrollArea {{
                    border: 1px solid {p['border_card']};
                    border-radius: 16px;
                    background-color: {p['bg_canvas']};
                }}
                QScrollBar:vertical {{
                    width: 6px;
                    background: transparent;
                    margin: 4px 0;
                }}
                QScrollBar::handle:vertical {{
                    background: {p['scrollbar_handle']};
                    border-radius: 3px;
                    min-height: 30px;
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
            """)
            if self.scroll_area.viewport():
                self.scroll_area.viewport().setStyleSheet(f"background-color: {p['bg_canvas']};")

        # 3. Update Input Frame & Inputs
        if hasattr(self, 'input_frame'):
            self.input_frame.setStyleSheet(f"""
                QFrame#fridayInput {{
                    background-color: {p['input_bg']};
                    border: 1px solid {p['border_card']};
                    border-radius: 18px;
                }}
                QFrame#fridayInput:focus-within {{
                    border: 1px solid {p['border_focus']};
                }}
            """)
        if hasattr(self, 'prompt_input'):
            self.prompt_input.setStyleSheet(f"""
                QLineEdit {{
                    background-color: transparent;
                    border: none;
                    color: {p['text_primary']};
                    font-size: 13.5px;
                    padding: 6px 4px;
                    selection-background-color: {p['selection_bg']};
                    selection-color: {p['text_primary']};
                }}
            """)
        if hasattr(self, 'attach_btn'):
            self.attach_btn.setStyleSheet(f"""
                ToolButton {{
                    background-color: {p['bg_surface']};
                    border: 1px solid {p['border_card']};
                    border-radius: 14px;
                    color: {p['text_secondary']};
                }}
                ToolButton:hover {{
                    background-color: {p['bg_card_hover']};
                    border: 1px solid {p['border_hover']};
                    color: {p['text_primary']};
                }}
            """)
        if hasattr(self, 'send_btn'):
            self.send_btn.setStyleSheet(f"""
                PrimaryPushButton {{
                    background-color: {p['send_bg']};
                    color: {p['send_text']};
                    border-radius: 17px;
                    font-weight: bold;
                    font-size: 12.5px;
                    border: none;
                    letter-spacing: 0.3px;
                }}
                PrimaryPushButton:hover {{
                    background-color: {p['send_hover']};
                }}
                PrimaryPushButton:pressed {{
                    background-color: {p['send_pressed']};
                }}
            """)
        if hasattr(self, 'attachments_container'):
            self.attachments_container.setStyleSheet(f"""
                QFrame#attachmentsBar {{
                    background: {p['bg_surface']};
                    border: 1px solid {p['border_subtle']};
                    border-radius: 16px;
                }}
            """)

        # 4. Update Quick Action Chips
        if hasattr(self, 'chips_buttons'):
            for btn in self.chips_buttons:
                btn.setStyleSheet(f"""
                    PushButton {{
                        background-color: {p['chip_bg']};
                        border: 1px solid {p['border_subtle']};
                        color: {p['chip_text']};
                        font-size: 11px;
                        font-weight: 500;
                        padding: 3px 12px;
                        border-radius: 16px;
                    }}
                    PushButton:hover {{
                        background-color: {p['chip_hover']};
                        border: 1px solid {p['border_hover']};
                        color: {p['chip_text_hover']};
                    }}
                    PushButton:pressed {{
                        background-color: {p['chip_pressed']};
                    }}
                """)

        # 5. Update All Existing Chat Bubbles
        if hasattr(self, 'chat_layout'):
            for i in range(self.chat_layout.count()):
                item = self.chat_layout.itemAt(i)
                if item and item.widget() and isinstance(item.widget(), ChatBubble):
                    item.widget().apply_theme(theme_mode)

    def set_mic_active(self, active: bool):
        """Updates mic button visual appearance based on active listening or muted state."""
        p = get_current_palette()
        self._mic_active = active
        if active:
            self.mic_btn.setToolTip("Mute Microphone (Ctrl+M)")
            self.mic_btn.setStyleSheet(f"""
                ToolButton {{
                    background-color: {p['accent_bg']};
                    border: 1px solid {p['accent']};
                    border-radius: 8px;
                    color: {p['accent']};
                }}
                ToolButton:hover {{
                    background-color: {p['accent_border']};
                    border: 1px solid {p['accent_hover']};
                    color: {p['text_primary']};
                }}
            """)
        else:
            self.mic_btn.setToolTip("Unmute Microphone (Ctrl+M)")
            self.mic_btn.setStyleSheet(f"""
                ToolButton {{
                    background-color: {p['bg_surface']};
                    border: 1px solid {p['danger_red_border']};
                    border-radius: 8px;
                    color: {p['danger_red']};
                }}
                ToolButton:hover {{
                    background-color: {p['danger_red_bg']};
                    border: 1px solid {p['danger_red']};
                    color: {p['danger_red']};
                }}
            """)

    def _on_send_btn_clicked(self):
        if self._is_generating:
            self.stop_generation()
        else:
            self._submit_prompt()

    def _on_escape_pressed(self):
        if self._is_generating or getattr(self, '_current_engine_state', '') == 'speaking':
            self.stop_generation()

    def stop_generation(self):
        """Immediately halts ongoing generation and speech."""
        self.stop_requested.emit()
        self.finish_stream(final_text=None)
        self._set_generating_state(False)

    def _set_generating_state(self, generating: bool):
        self._is_generating = generating
        if generating:
            p = get_current_palette()
            self.stop_btn.show()
            self.send_btn.setText("■ Stop")
            self.send_btn.setToolTip("Halt response generation and speech (Esc)")
            self.send_btn.setStyleSheet(f"""
                PrimaryPushButton {{
                    background-color: {p['danger_red']};
                    border: 1px solid {p['danger_red']};
                    font-weight: bold;
                    font-size: 12px;
                    border-radius: 16px;
                    color: #FFFFFF;
                    letter-spacing: 0.5px;
                }}
                PrimaryPushButton:hover {{
                    background-color: {p['danger_red_border']};
                }}
                PrimaryPushButton:pressed {{
                    background-color: {p['danger_red']};
                }}
            """)
        else:
            p = get_current_palette()
            self.stop_btn.hide()
            self.send_btn.setText("Send")
            self.send_btn.setToolTip("Send directive (Enter)")
            self.send_btn.setStyleSheet(f"""
                PrimaryPushButton {{
                    background-color: {p['send_bg']};
                    border: none;
                    font-weight: bold;
                    font-size: 12px;
                    border-radius: 16px;
                    color: {p['send_text']};
                    letter-spacing: 0.5px;
                }}
                PrimaryPushButton:hover {{
                    background-color: {p['send_hover']};
                }}
                PrimaryPushButton:pressed {{
                    background-color: {p['send_pressed']};
                }}
            """)

    def _show_attach_menu(self):
        """Displays the tactical popup action menu from the '+' button."""
        menu = RoundMenu(parent=self)

        act_attach = Action(FluentIcon.DOCUMENT, "Attach File(s) for Analysis", menu)
        act_attach.triggered.connect(self._pick_files_to_attach)
        menu.addAction(act_attach)

        act_research = Action(FluentIcon.GLOBE, "Deep Web Research", menu)
        act_research.triggered.connect(self._toggle_deep_research)
        menu.addAction(act_research)

        act_kb = Action(FluentIcon.FOLDER, "Add to Knowledge Base / Project", menu)
        act_kb.triggered.connect(self._pick_file_for_kb)
        menu.addAction(act_kb)

        act_snip = Action(FluentIcon.CAMERA, "Snip & Analyze Screen", menu)
        act_snip.triggered.connect(self._capture_screen_snip)
        menu.addAction(act_snip)

        act_folder = Action(FluentIcon.APPLICATION, "Open Project Workspace", menu)
        act_folder.triggered.connect(self._open_project_workspace)
        menu.addAction(act_folder)

        pos = self.attach_btn.mapToGlobal(self.attach_btn.rect().topLeft())
        pos.setY(pos.y() - menu.sizeHint().height() - 8)
        menu.exec(pos)

    def _pick_files_to_attach(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Files for F.R.I.D.A.Y. to Analyze",
            "",
            "Supported Files (*.py *.txt *.md *.json *.csv *.log *.js *.ts *.html *.css *.cpp *.c *.h *.rs *.go *.java *.sql *.yaml *.yml *.xml *.pdf);;All Files (*.*)"
        )
        if files:
            for f in files:
                if f not in self.attached_files:
                    self.attached_files.append(f)
            self._refresh_attachments_ui()

    def _toggle_deep_research(self):
        self.deep_research_active = not self.deep_research_active
        self._refresh_attachments_ui()

    def _pick_file_for_kb(self):
        fpath, _ = QFileDialog.getOpenFileName(
            self,
            "Select Document to Ingest into Project Knowledge Base",
            "",
            "Documents (*.txt *.md *.py *.json *.csv *.log);;All Files (*.*)"
        )
        if fpath:
            fname = os.path.basename(fpath)
            self.doc_ingest_requested.emit(fname, fpath)

    def _capture_screen_snip(self):
        screen = QGuiApplication.primaryScreen()
        if screen:
            pixmap = screen.grabWindow(0)
            from friday_ui.core.config import APP_DATA_DIR
            snip_dir = os.path.join(APP_DATA_DIR, "screenshots")
            os.makedirs(snip_dir, exist_ok=True)
            snip_path = os.path.join(snip_dir, f"snip_{int(datetime.now().timestamp())}.png")
            pixmap.save(snip_path)
            if snip_path not in self.attached_files:
                self.attached_files.append(snip_path)
            self._refresh_attachments_ui()

    def _open_project_workspace(self):
        from friday_ui.core.config import APP_DATA_DIR
        os.startfile(APP_DATA_DIR)

    def _remove_attachment(self, fpath: str):
        if fpath in self.attached_files:
            self.attached_files.remove(fpath)
        self._refresh_attachments_ui()

    def _refresh_attachments_ui(self):
        while self.attachments_layout.count():
            item = self.attachments_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        has_items = bool(self.attached_files) or self.deep_research_active
        if not has_items:
            self.attachments_container.hide()
            return

        self.attachments_container.show()

        p = get_current_palette()
        if self.deep_research_active:
            pill = PushButton("🌐 Deep Research: Active  ✕", self.attachments_container)
            pill.setFixedHeight(26)
            pill.setCursor(Qt.PointingHandCursor)
            pill.setStyleSheet(f"""
                PushButton {{
                    background-color: {p['accent_bg']};
                    border: 1px solid {p['accent_border']};
                    color: {p['accent']};
                    font-size: 11px;
                    font-weight: 600;
                    padding: 2px 10px;
                    border-radius: 12px;
                }}
                PushButton:hover {{
                    background-color: {p['danger_red_bg']};
                    border: 1px solid {p['danger_red']};
                    color: {p['danger_red']};
                }}
            """)
            pill.clicked.connect(self._toggle_deep_research)
            self.attachments_layout.addWidget(pill)

        for fpath in self.attached_files:
            fname = os.path.basename(fpath)
            try:
                sz = os.path.getsize(fpath)
                if sz < 1024:
                    sz_str = f"{sz} B"
                elif sz < 1024 * 1024:
                    sz_str = f"{sz / 1024:.1f} KB"
                else:
                    sz_str = f"{sz / (1024*1024):.1f} MB"
            except Exception:
                sz_str = "File"

            icon_char = "📷" if fname.lower().endswith(('.png', '.jpg', '.jpeg')) else "📄"
            pill = PushButton(f"{icon_char} {fname} ({sz_str})  ✕", self.attachments_container)
            pill.setFixedHeight(26)
            pill.setCursor(Qt.PointingHandCursor)
            pill.setStyleSheet(f"""
                PushButton {{
                    background-color: {p['chip_bg']};
                    border: 1px solid {p['border_subtle']};
                    color: {p['chip_text']};
                    font-size: 11px;
                    font-weight: 500;
                    padding: 2px 10px;
                    border-radius: 12px;
                }}
                PushButton:hover {{
                    background-color: {p['danger_red_bg']};
                    border: 1px solid {p['danger_red']};
                    color: {p['danger_red']};
                }}
            """)
            pill.clicked.connect(lambda checked=False, p=fpath: self._remove_attachment(p))
            self.attachments_layout.addWidget(pill)


        self.attachments_layout.addStretch(1)

    def _submit_prompt(self):
        if self._is_generating:
            return
        text = self.prompt_input.text().strip()

        # 1. If Deep Research is active
        if self.deep_research_active:
            if not text:
                return
            self.prompt_input.clear()
            self.deep_research_active = False
            self._refresh_attachments_ui()
            display_msg = f"🌐 **[Deep Web Research Directive]**\n\n{text}"
            self.add_message("user", display_msg)
            self.deep_research_requested.emit(text)
            return

        # 2. If Files are attached for analysis
        if self.attached_files:
            if not text:
                text = "Please analyze the attached file(s), explain architecture, findings, and actionable details."
            self.prompt_input.clear()

            file_contexts = []
            file_names = []
            image_extensions = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
            for fpath in list(self.attached_files):
                fname = os.path.basename(fpath)
                file_names.append(fname)
                ext = os.path.splitext(fname)[1].lower()
                if ext in image_extensions:
                    file_contexts.append(f"[Attached Image: {fname} | Path: {fpath}]")
                else:
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read(50000)
                        ext_clean = ext.lstrip(".") or "txt"
                        file_contexts.append(f"[Attached Document: {fname}]\n```{ext_clean}\n{content}\n```")
                    except Exception as e:
                        file_contexts.append(f"[Attached Document: {fname} (Could not read: {e})]")

            self.attached_files.clear()
            self._refresh_attachments_ui()

            att_names_str = ", ".join(file_names)
            display_msg = f"📎 **Attached ({len(file_names)}):** `{att_names_str}`\n\n{text}"
            full_prompt = "\n\n".join(file_contexts) + f"\n\nBoss Directive:\n{text}"
            self.command_submitted.emit(full_prompt, display_msg)
            return

        # 3. Standard Text Prompt
        if text:
            self.prompt_input.clear()
            self.command_submitted.emit(text, text)

    def _on_chip_clicked(self, query: str):
        if self._is_generating:
            return
        self.command_submitted.emit(query, query)

    def start_stream(self, role: str = "friday", initial_status: str = "Synthesizing..."):
        """Creates and stages a streaming ChatBubble immediately."""
        self.typing_indicator.hide_indicator()
        self._set_generating_state(True)
        self._streaming_session_id = self.current_session_id

        if self._current_streaming_bubble:
            self._current_streaming_bubble.finish_stream()
            self._current_streaming_bubble = None

        bubble = ChatBubble(role, "", is_streaming=True, status_text=initial_status, parent=self.chat_container)
        insert_idx = max(0, self.chat_layout.count() - 1)
        self.chat_layout.insertWidget(insert_idx, bubble)
        self._current_streaming_bubble = bubble
        QTimer.singleShot(30, self._scroll_to_bottom)

    def append_token(self, token: str):
        """Streams a token chunk into the active streaming bubble with session isolation."""
        if not self._is_generating:
            return
        if self._streaming_session_id != self.current_session_id:
            return
        if not self._current_streaming_bubble:
            return
        self._current_streaming_bubble.append_token(token)
        vsb = self.scroll_area.verticalScrollBar()
        if vsb.maximum() - vsb.value() < 160:
            vsb.setValue(vsb.maximum())

    def append_thinking(self, token: str):
        """Streams a thinking/reasoning token chunk into the active streaming bubble."""
        if not self._is_generating:
            return
        if self._streaming_session_id != self.current_session_id:
            return
        if not self._current_streaming_bubble:
            return
        self._current_streaming_bubble.append_thinking(token)
        vsb = self.scroll_area.verticalScrollBar()
        if vsb.maximum() - vsb.value() < 160:
            vsb.setValue(vsb.maximum())

    def update_status(self, status_text: str):
        """Updates the status description on the active streaming bubble."""
        if not self._is_generating or self._streaming_session_id != self.current_session_id:
            return
        if self._current_streaming_bubble:
            self._current_streaming_bubble.set_status(status_text)

    def _load_sessions_list(self):
        self._is_loading_session = True
        try:
            self.session_combo.blockSignals(True)
            self.session_combo.clear()
            sessions = self.session_store.get_sessions()
            if not sessions:
                self.session_store.create_session("Initial Tactical Session")
                sessions = self.session_store.get_sessions()

            for s in sessions:
                self.session_combo.addItem(s["title"], userData=s["id"])

            if sessions:
                self.session_combo.setCurrentIndex(0)
                self.current_session_id = sessions[0]["id"]
                self._load_session_messages(self.current_session_id)
        finally:
            self.session_combo.blockSignals(False)
            self._is_loading_session = False
        if self.current_session_id:
            self.session_changed.emit(self.current_session_id)

    def _on_session_combo_changed(self, index: int):
        if self._is_loading_session or index < 0:
            return
        session_id = self.session_combo.itemData(index)
        if session_id and session_id != self.current_session_id:
            self.stop_requested.emit()
            self._current_streaming_bubble = None
            self._streaming_session_id = None
            self._set_generating_state(False)
            self.current_session_id = session_id
            self._load_session_messages(session_id)
            self.session_changed.emit(session_id)

    def _on_model_combo_changed(self, text: str):
        if getattr(self, "_refreshing_models", False) or not text:
            return
        settings.set("model", text)
        self.model_changed.emit(text)

    def _on_settings_updated(self, key: str, value):
        if key in ("model", "custom_models"):
            self.refresh_models(selected_model=settings.get("model"))

    def refresh_models(self, selected_model: str = None):
        self._refreshing_models = True
        try:
            curr = selected_model or settings.get("model") or self.model_combo.currentText()
            avail = settings.get_available_models()
            self.model_combo.blockSignals(True)
            self.model_combo.clear()
            self.model_combo.addItems(avail)
            idx = self.model_combo.findText(curr)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
            elif curr:
                self.model_combo.addItem(curr)
                self.model_combo.setCurrentText(curr)
            self.model_combo.blockSignals(False)
        finally:
            self._refreshing_models = False

    def _on_add_model_dialog(self):
        """Shows a dialog allowing the user to add or pull any AI model instantly."""
        try:
            from friday_ui.widgets.add_model_dialog import AddModelDialog
            dlg = AddModelDialog(self)
            if dlg.exec():
                new_model = dlg.selected_model
                if new_model:
                    self.refresh_models(selected_model=new_model)
                    self.model_changed.emit(new_model)
        except Exception as e:
            logger.error(f"Error launching AddModelDialog: {e}")

    def _on_new_session(self):
        self.stop_requested.emit()
        self._current_streaming_bubble = None
        self._streaming_session_id = None
        self._set_generating_state(False)

        # Reuse existing empty session if user is already in an empty session
        if self.current_session_id:
            msgs = self.session_store.get_messages(self.current_session_id)
            if not msgs:
                InfoBar.info("New Session", "Active session is already empty and ready.", parent=self, position=InfoBarPosition.TOP_RIGHT, duration=2000)
                return

        new_id = self.session_store.create_session("New Session")
        self._load_sessions_list()
        InfoBar.success("New Session", "Created new conversation session.", parent=self, position=InfoBarPosition.TOP_RIGHT, duration=2000)

    def _on_delete_session(self):
        """Prompts confirmation and deletes current chat session."""
        if not self.current_session_id:
            return

        from qfluentwidgets import MessageBox
        box = MessageBox("Delete Session", "Are you sure you want to delete this chat session? This action cannot be undone.", self)
        if box.exec():
            self.stop_requested.emit()
            self._current_streaming_bubble = None
            self._streaming_session_id = None
            self._set_generating_state(False)

            self.session_store.delete_session(self.current_session_id)
            self._load_sessions_list()
            InfoBar.success("Session Deleted", "Chat session removed.", parent=self, position=InfoBarPosition.TOP_RIGHT, duration=2000)

    def _load_session_messages(self, session_id: str):
        # Clear existing bubbles (all except stretch item at end)
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        messages = self.session_store.get_messages(session_id)
        if not messages:
            self.add_message("friday", "F.R.I.D.A.Y. 2.0 online. Neural subsystems operational. Ready for your directive, Boss.", persist=False)
        else:
            for msg in messages:
                bubble = ChatBubble(msg["role"], msg["content"], self.chat_container)
                insert_idx = max(0, self.chat_layout.count() - 1)
                self.chat_layout.insertWidget(insert_idx, bubble)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def finish_stream(self, final_text: str = None):
        """Finalizes the active streaming bubble."""
        if getattr(self, '_current_engine_state', '') != 'speaking':
            self._set_generating_state(False)
        if self._current_streaming_bubble:
            self._current_streaming_bubble.finish_stream(final_text)
            self._last_streamed_text = self._current_streaming_bubble.raw_text.strip()
            # If bubble has thinking text, persist complete text including <think> block
            t_text = getattr(self._current_streaming_bubble, 'thinking_text', '').strip()
            if t_text:
                full_persisted = f"<think>\n{t_text}\n</think>\n\n{self._last_streamed_text}"
            else:
                full_persisted = self._last_streamed_text

            if self.current_session_id and self._streaming_session_id == self.current_session_id and full_persisted:
                self.session_store.add_message(self.current_session_id, "friday", full_persisted)
            self._current_streaming_bubble = None
        self._streaming_session_id = None
        QTimer.singleShot(60, self._scroll_to_bottom)

    def add_message(self, role: str, message: str, persist: bool = True):
        """Appends a new chat message bubble and scrolls smoothly to bottom."""
        clean_msg = message.strip()
        if role.lower() == "friday" and getattr(self, '_last_streamed_text', ''):
            if clean_msg and (clean_msg == self._last_streamed_text or self._last_streamed_text.startswith(clean_msg[:60])):
                self._last_streamed_text = ""
                return

        if role.lower() == "friday" and self._current_streaming_bubble:
            self.finish_stream(message)
            return

        self.typing_indicator.hide_indicator()
        bubble = ChatBubble(role, message, self.chat_container)
        insert_idx = max(0, self.chat_layout.count() - 1)
        self.chat_layout.insertWidget(insert_idx, bubble)

        if persist and self.current_session_id:
            self.session_store.add_message(self.current_session_id, role, clean_msg)
            if role.lower() == "user":
                idx = self.session_combo.currentIndex()
                if idx >= 0:
                    sessions = self.session_store.get_sessions()
                    for s in sessions:
                        if s["id"] == self.current_session_id:
                            self.session_combo.setItemText(idx, s["title"])
                            break

        QTimer.singleShot(60, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        vsb = self.scroll_area.verticalScrollBar()
        # Smooth scroll animation
        target = vsb.maximum()
        current = vsb.value()
        if abs(target - current) > 20:
            if hasattr(self, '_scroll_anim') and self._scroll_anim:
                self._scroll_anim.stop()
            self._scroll_anim = QPropertyAnimation(vsb, b"value", self)
            self._scroll_anim.setDuration(250)
            self._scroll_anim.setStartValue(current)
            self._scroll_anim.setEndValue(target)
            self._scroll_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._scroll_anim.start()
        else:
            vsb.setValue(target)

    def update_state(self, state: str):
        """Updates status pill and header indicators with smooth transitions."""
        p = get_current_palette()
        st = state.upper()
        self._current_engine_state = st.lower()
        self.arc_reactor.set_state(state)

        base_style = """
            border-radius: 6px;
            padding: 4px 10px;
            font-weight: bold;
            font-family: monospace;
            font-size: 10px;
        """

        if st == "LISTENING":
            if not self._current_streaming_bubble:
                self._set_generating_state(False)
            self.status_pill.setText("● LISTENING")
            self.status_pill.setStyleSheet(f"""
                color: {p['live_green']};
                background-color: {p['live_green_bg']};
                border: 1px solid {p['live_green_border']};
                {base_style}
            """)
            self.mic_btn.setToolTip("Voice Loop Active — Click to Mute")
            self.mic_btn.setStyleSheet(f"""
                ToolButton {{
                    background-color: {p['live_green_bg']};
                    border: 1px solid {p['live_green']};
                    border-radius: 8px;
                    color: {p['live_green']};
                }}
                ToolButton:hover {{
                    background-color: {p['live_green_border']};
                }}
            """)
        elif st == "THINKING":
            self._set_generating_state(True)
            self.status_pill.setText("● THINKING")
            self.status_pill.setStyleSheet(f"""
                color: {p['amber_tag']};
                background-color: {p['amber_tag_bg']};
                border: 1px solid {p['amber_tag_border']};
                {base_style}
            """)
            self.typing_indicator.show_indicator()
        elif st == "SPEAKING":
            self._set_generating_state(True)
            self.status_pill.setText("● TRANSMITTING")
            self.status_pill.setStyleSheet(f"""
                color: {p['accent']};
                background-color: {p['accent_bg']};
                border: 1px solid {p['accent_border']};
                {base_style}
            """)
        elif st == "IDLE":
            if not self._current_streaming_bubble:
                self._set_generating_state(False)
            self.status_pill.setText("● MIC MUTED")
            self.status_pill.setStyleSheet(f"""
                color: {p['danger_red']};
                background-color: {p['danger_red_bg']};
                border: 1px solid {p['danger_red_border']};
                {base_style}
            """)
            self.typing_indicator.hide_indicator()
            self.mic_btn.setToolTip("Microphone Muted — Click to Activate")
            self.mic_btn.setStyleSheet(f"""
                ToolButton {{
                    background-color: {p['danger_red_bg']};
                    border: 1px solid {p['danger_red_border']};
                    border-radius: 8px;
                    color: {p['danger_red']};
                }}
                ToolButton:hover {{
                    background-color: {p['danger_red_bg']};
                }}
            """)
        else:
            # Standby mode
            if not self._current_streaming_bubble:
                self._set_generating_state(False)
            self.status_pill.setText("● STANDBY")
            self.status_pill.setStyleSheet(f"""
                color: {p['text_secondary']};
                background-color: {p['bg_surface']};
                border: 1px solid {p['border_card']};
                {base_style}
            """)
            self.typing_indicator.hide_indicator()
            self.mic_btn.setToolTip("Voice Loop Ready — Click to Mute")
            self.mic_btn.setStyleSheet(f"""
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
            """)

    def update_energy(self, level: float):
        """Updates arc reactor energy pulse from live audio amplitude."""
        self.arc_reactor.set_energy(level)
