"""
F.R.I.D.A.Y. 2.0 - Floating Tactical Command Bar
Frameless, translucent floating HUD bar with global hotkey activation (Ctrl+Space),
translucent expanding results panel, model selector, mic toggle, and draggable positioning.
"""

import sys
import ctypes
from ctypes import wintypes
import asyncio
import logging
from typing import Optional, List

logger = logging.getLogger("FRIDAY.CommandBar")

from PySide6.QtCore import (
    Qt, Signal, QPoint, QSize, QTimer, QPropertyAnimation, QEasingCurve,
    QAbstractNativeEventFilter, QRect, QStringListModel
)
from PySide6.QtGui import (
    QFont, QColor, QPainter, QBrush, QPen, QLinearGradient, QMouseEvent,
    QKeySequence, QShortcut
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser,
    QFrame, QApplication, QGraphicsOpacityEffect, QSizePolicy,
    QCompleter
)
from qfluentwidgets import (
    LineEdit, ToolButton, PushButton, PrimaryPushButton, ComboBox,
    FluentIcon, PillPushButton, TransparentToolButton
)

from friday_core.settings import settings
from friday_ui.widgets.arc_reactor import ArcReactorWidget

HOTKEY_ID = 9119
MOD_CONTROL = 0x0002
VK_SPACE = 0x20
WM_HOTKEY = 0x0312

class GlobalHotKeyFilter(QAbstractNativeEventFilter):
    """Intercepts Windows WM_HOTKEY messages directly in the Qt event loop."""
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, eventType, message):
        try:
            if eventType == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(message.__int__())
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    self.callback()
                    return True, 0
        except Exception as e:
            logger.debug(f"WM_HOTKEY message interception exception: {e}")
        return False, 0

TACTICAL_COMMANDS = [
    "open vs code",
    "open visual studio code",
    "open edge",
    "open chrome",
    "open notepad",
    "open spotify",
    "open terminal",
    "open file explorer",
    "kill process",
    "terminate process",
    "system status telemetry",
    "check battery",
    "check memory ram",
    "weather",
    "screenshot",
    "deep comprehensive research",
    "search youtube",
    "search memory knowledge base",
    "calculate 250 * 18",
    "recycle file",
    "delete file"
]

class FloatingCommandBar(QWidget):
    """
    Floating Tactical Command Bar matching reference layout:
    [+]  [Ask F.R.I.D.A.Y...]  ...stretch...  [Model ▾]  [🎤]  [⚡ Mode]
    Supports expandable response card, draggable repositioning, and settings persistence.
    """
    command_submitted = Signal(str)
    voice_toggle_requested = Signal()
    model_changed = Signal(str)
    stop_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.drag_position = QPoint()
        self.is_expanded = False
        self._hotkey_registered = False
        self._event_filter = None

        self._init_window_flags()
        self._init_ui()
        self._setup_position()
        self._register_global_hotkey()

    def _init_window_flags(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)

    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(8)

        # 1. Main Horizontal Floating Bar Card
        self.bar_card = QFrame(self)
        self.bar_card.setFixedHeight(56)
        self.bar_card.setStyleSheet("""
            QFrame {
                background-color: rgba(18, 22, 32, 0.94);
                border: 1px solid rgba(0, 240, 255, 0.35);
                border-radius: 28px;
            }
        """)

        bar_layout = QHBoxLayout(self.bar_card)
        bar_layout.setContentsMargins(14, 6, 14, 6)
        bar_layout.setSpacing(10)

        # Left [+] Action / Mini Reactor Icon
        self.mini_reactor = ArcReactorWidget(size=36, parent=self.bar_card)
        bar_layout.addWidget(self.mini_reactor)

        # Prompt Input Field
        self.prompt_input = LineEdit(self.bar_card)
        self.prompt_input.setPlaceholderText("Ask F.R.I.D.A.Y. anything or enter tactical command...")
        self.prompt_input.setStyleSheet("""
            LineEdit {
                background-color: transparent;
                border: none;
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 500;
                padding-left: 4px;
            }
        """)
        self.prompt_input.returnPressed.connect(self._on_submit)

        # Fuzzy skill / directive auto-completer
        self.completer_model = QStringListModel(TACTICAL_COMMANDS, self)
        self.completer = QCompleter(self.completer_model, self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        popup = self.completer.popup()
        popup.setStyleSheet("""
            QListView {
                background-color: #0E121C;
                border: 1px solid rgba(0, 240, 255, 0.35);
                border-radius: 8px;
                color: #E2E8F0;
                font-size: 12px;
                padding: 4px;
                selection-background-color: rgba(0, 240, 255, 0.20);
                selection-color: #00F0FF;
            }
        """)
        self.prompt_input.setCompleter(self.completer)
        self.prompt_input.textChanged.connect(self._on_prompt_text_changed)

        bar_layout.addWidget(self.prompt_input, 1)

        # Model Selector ComboBox
        self.model_combo = ComboBox(self.bar_card)
        self.model_combo.setFixedWidth(145)
        self._refreshing_models = False
        avail_models = settings.get_available_models()
        self.model_combo.addItems(avail_models)
        saved_model = settings.get("model", avail_models[0] if avail_models else "llama3.2:3b")
        idx_cb = self.model_combo.findText(saved_model)
        if idx_cb >= 0:
            self.model_combo.setCurrentIndex(idx_cb)
        else:
            self.model_combo.addItem(saved_model)
            self.model_combo.setCurrentText(saved_model)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        settings.add_listener(self._on_settings_model_sync)
        self.model_combo.setStyleSheet("""
            ComboBox {
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 14px;
                color: #00F0FF;
                font-size: 11px;
                padding: 4px 10px;
            }
        """)
        bar_layout.addWidget(self.model_combo)

        # Voice Trigger Button (Mic)
        self.mic_btn = ToolButton(FluentIcon.MICROPHONE, self.bar_card)
        self.mic_btn.setFixedSize(36, 36)
        self.mic_btn.clicked.connect(self.voice_toggle_requested.emit)
        bar_layout.addWidget(self.mic_btn)

        # Mode Chip (Tactical / Speed / Deep)
        self.mode_btn = PillPushButton("⚡ Tactical", self.bar_card)
        self.mode_btn.setFixedWidth(88)
        self.mode_btn.setStyleSheet("""
            PillPushButton {
                background-color: rgba(0, 240, 255, 0.15);
                border: 1px solid #00F0FF;
                color: #00F0FF;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 8px;
            }
            PillPushButton:hover {
                background-color: rgba(0, 240, 255, 0.3);
            }
        """)
        self.mode_btn.clicked.connect(self._cycle_mode)
        bar_layout.addWidget(self.mode_btn)

        # Stop Button in Floating Bar
        self.stop_btn = PillPushButton("■ Stop", self.bar_card)
        self.stop_btn.setFixedWidth(68)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setToolTip("Immediately halt voice playback (Esc)")
        self.stop_btn.setStyleSheet("""
            PillPushButton {
                background-color: #DC2626;
                border: 1px solid #EF4444;
                color: #FFFFFF;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 8px;
            }
            PillPushButton:hover {
                background-color: #EF4444;
            }
            PillPushButton:pressed {
                background-color: #991B1B;
            }
        """)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        self.stop_btn.hide()
        bar_layout.addWidget(self.stop_btn)

        # Close / Dismiss Button
        self.close_btn = TransparentToolButton(FluentIcon.CLOSE, self.bar_card)
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setToolTip("Hide Command Bar (Ctrl+Space to reopen)")
        self.close_btn.clicked.connect(self.hide)
        bar_layout.addWidget(self.close_btn)

        self.main_layout.addWidget(self.bar_card)

        # 2. Expandable Response Panel Card
        self.response_card = QFrame(self)
        self.response_card.setStyleSheet("""
            QFrame {
                background-color: rgba(14, 18, 28, 0.96);
                border: 1px solid rgba(0, 240, 255, 0.25);
                border-radius: 14px;
            }
        """)
        self.response_layout = QVBoxLayout(self.response_card)
        self.response_layout.setContentsMargins(14, 12, 14, 12)
        self.response_layout.setSpacing(6)

        # Status & Header row
        resp_header = QHBoxLayout()
        self.resp_title = QLabel("F.R.I.D.A.Y. RESPONSE")
        self.resp_title.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.resp_title.setStyleSheet("color: #00F0FF; letter-spacing: 1px;")
        resp_header.addWidget(self.resp_title)
        resp_header.addStretch(1)

        self.resp_stop_btn = TransparentToolButton(FluentIcon.CANCEL, self.response_card)
        self.resp_stop_btn.setFixedSize(24, 24)
        self.resp_stop_btn.setToolTip("Halt vocal playback")
        self.resp_stop_btn.clicked.connect(self.stop_requested.emit)
        self.resp_stop_btn.hide()
        resp_header.addWidget(self.resp_stop_btn)

        copy_btn = TransparentToolButton(FluentIcon.COPY, self.response_card)
        copy_btn.setFixedSize(24, 24)
        copy_btn.setToolTip("Copy response")
        copy_btn.clicked.connect(self._copy_response)
        resp_header.addWidget(copy_btn)

        self.response_layout.addLayout(resp_header)

        # Rich text browser for markdown reply
        self.response_text = QTextBrowser(self.response_card)
        self.response_text.setOpenExternalLinks(True)
        self.response_text.setReadOnly(True)
        self.response_text.setStyleSheet("""
            QTextBrowser {
                background-color: transparent;
                border: none;
                color: #E2E8F0;
                font-size: 12px;
                line-height: 1.4;
            }
        """)
        self.response_text.setMinimumHeight(60)
        self.response_text.setMaximumHeight(220)
        self.response_layout.addWidget(self.response_text)

        self.response_card.setVisible(False)
        self.main_layout.addWidget(self.response_card)

        self.setFixedWidth(740)
        self.mic_shortcut = QShortcut(QKeySequence("Ctrl+M"), self)
        self.mic_shortcut.activated.connect(self.voice_toggle_requested.emit)
        self.set_mic_active(False)

    def _setup_position(self):
        """Places the bar on screen according to user settings or last saved coords."""
        screen = QApplication.primaryScreen().availableGeometry()
        pos_mode = settings.get("command_bar_position", "top")
        last_x = settings.get("last_x", -1)
        last_y = settings.get("last_y", -1)

        w = 740
        if pos_mode == "last" and last_x >= 0 and last_y >= 0:
            x = min(screen.width() - w, max(0, last_x))
            y = min(screen.height() - 100, max(0, last_y))
        elif pos_mode == "bottom":
            x = (screen.width() - w) // 2
            y = screen.height() - 140
        else: # Default: Top
            x = (screen.width() - w) // 2
            y = 70

        self.move(x, y)

    def _register_global_hotkey(self):
        """Registers global Ctrl+Space hotkey with Windows API."""
        try:
            res = ctypes.windll.user32.RegisterHotKey(
                None, HOTKEY_ID, MOD_CONTROL, VK_SPACE
            )
            if res:
                self._hotkey_registered = True
                self._event_filter = GlobalHotKeyFilter(self.toggle_visibility)
                QApplication.instance().installNativeEventFilter(self._event_filter)
        except Exception as e:
            logger.warning(f"Failed to register global hotkey Ctrl+Space: {e}")

    def unregister_hotkey(self):
        """Unregisters global hotkey on shutdown."""
        if self._hotkey_registered:
            try:
                ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
                self._hotkey_registered = False
            except Exception as e:
                logger.debug(f"Failed to unregister global hotkey: {e}")

    def toggle_visibility(self):
        """Toggles display and brings command bar to foreground."""
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()
            self.prompt_input.setFocus()
            self.prompt_input.selectAll()

    def show_response(self, text: str):
        """Displays output in the expanding response card with smooth easing animation."""
        self.response_text.setMarkdown(text)
        if not self.response_card.isVisible():
            self.response_card.setVisible(True)
            self.is_expanded = True
            eff = self.response_card.graphicsEffect()
            if not isinstance(eff, QGraphicsOpacityEffect):
                eff = QGraphicsOpacityEffect(self.response_card)
                self.response_card.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", self)
            anim.setDuration(240)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.start(QPropertyAnimation.DeleteWhenStopped)
        else:
            self.is_expanded = True
        self.adjustSize()

    def hide_response(self):
        """Smoothly collapses response panel."""
        if self.response_card.isVisible():
            eff = self.response_card.graphicsEffect()
            if not isinstance(eff, QGraphicsOpacityEffect):
                eff = QGraphicsOpacityEffect(self.response_card)
                self.response_card.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", self)
            anim.setDuration(180)
            anim.setStartValue(1.0)
            anim.setEndValue(0.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.finished.connect(lambda: (self.response_card.setVisible(False), setattr(self, 'is_expanded', False), self.adjustSize()))
            anim.start(QPropertyAnimation.DeleteWhenStopped)

    def _on_prompt_text_changed(self, text: str):
        txt = text.strip()
        if len(txt) >= 2:
            candidates = []
            try:
                from rapidfuzz import process, fuzz
                matches = process.extract(txt, TACTICAL_COMMANDS, scorer=fuzz.partial_ratio, limit=6, score_cutoff=40)
                if matches:
                    candidates = [m[0] for m in matches]
            except Exception:
                import difflib
                matches = difflib.get_close_matches(txt, TACTICAL_COMMANDS, n=5, cutoff=0.3)
                if matches:
                    candidates = matches

            if candidates:
                self.completer_model.setStringList(candidates)
                if self.isVisible() and self.prompt_input.hasFocus():
                    self.completer.complete()

    def set_state(self, state: str):
        """Updates arc reactor and status text."""
        self.mini_reactor.set_state(state)
        st = state.upper()
        self.resp_title.setText(f"F.R.I.D.A.Y. // {st}")
        if state.lower() == "speaking":
            self.stop_btn.show()
            self.resp_stop_btn.show()
        else:
            self.stop_btn.hide()
            self.resp_stop_btn.hide()

    def _on_submit(self):
        text = self.prompt_input.text().strip()
        if text:
            self.prompt_input.clear()
            self.set_state("thinking")
            self.command_submitted.emit(text)

    def _on_settings_model_sync(self, key: str, value):
        if key in ("model", "custom_models"):
            self.refresh_models()

    def refresh_models(self):
        self._refreshing_models = True
        try:
            curr = settings.get("model") or self.model_combo.currentText()
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

    def _on_model_changed(self, model: str):
        if getattr(self, "_refreshing_models", False) or not model:
            return
        settings.set("model", model)
        self.model_changed.emit(model)


    def set_mic_active(self, active: bool):
        """Updates mic button appearance in FloatingCommandBar."""
        self._mic_active = active
        if active:
            self.mic_btn.setToolTip("Mute Microphone (Ctrl+M)")
            self.mic_btn.setStyleSheet("""
                ToolButton {
                    background-color: rgba(0, 240, 255, 0.25);
                    border: 1px solid #00F0FF;
                    border-radius: 18px;
                    color: #00F0FF;
                }
                ToolButton:hover {
                    background-color: rgba(0, 240, 255, 0.4);
                    border: 1px solid #22D3EE;
                }
            """)
        else:
            self.mic_btn.setToolTip("Unmute Microphone (Ctrl+M)")
            self.mic_btn.setStyleSheet("""
                ToolButton {
                    background-color: rgba(239, 68, 68, 0.15);
                    border: 1px solid rgba(239, 68, 68, 0.5);
                    border-radius: 18px;
                    color: #EF4444;
                }
                ToolButton:hover {
                    background-color: rgba(239, 68, 68, 0.3);
                    border: 1px solid #EF4444;
                }
            """)

    def _cycle_mode(self):
        modes = ["⚡ Tactical", "🎯 Deep", "🚀 Turbo"]
        curr = self.mode_btn.text()
        idx = modes.index(curr) if curr in modes else 0
        new_mode = modes[(idx + 1) % len(modes)]
        self.mode_btn.setText(new_mode)

    def _copy_response(self):
        text = self.response_text.toPlainText()
        if text:
            QApplication.clipboard().setText(text)

    # Window Dragging & Position Persistence
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.LeftButton and not self.drag_position.isNull():
            new_pos = event.globalPosition().toPoint() - self.drag_position
            self.move(new_pos)
            settings.update({"last_x": new_pos.x(), "last_y": new_pos.y()}, auto_save=True)
            event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if hasattr(self, 'stop_btn') and self.stop_btn.isVisible():
                self.stop_requested.emit()
            self.hide()
        else:
            super().keyPressEvent(event)
