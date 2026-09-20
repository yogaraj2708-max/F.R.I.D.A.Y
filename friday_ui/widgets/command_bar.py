"""
F.R.I.D.A.Y. 2.0 - Floating Tactical Command Bar
Frameless, translucent floating HUD bar with global hotkey activation (Ctrl+Space),
translucent expanding results panel, model selector, mic toggle, and draggable positioning.
"""

import sys
import os
import time
import ctypes
from ctypes import wintypes
import asyncio
import logging
import threading
from typing import Optional, List

logger = logging.getLogger("FRIDAY.CommandBar")

from PySide6.QtCore import (
    Qt, Signal, QPoint, QSize, QTimer, QPropertyAnimation, QEasingCurve,
    QAbstractNativeEventFilter, QRect, QObject
)
from PySide6.QtGui import (
    QFont, QColor, QPainter, QBrush, QPen, QLinearGradient, QMouseEvent,
    QKeySequence, QShortcut
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser,
    QFrame, QApplication, QGraphicsOpacityEffect, QSizePolicy
)
from qfluentwidgets import (
    LineEdit, ToolButton, PushButton, PrimaryPushButton, ComboBox,
    FluentIcon, PillPushButton, TransparentToolButton
)

from friday_core.settings import settings
from friday_ui.widgets.arc_reactor import ArcReactorWidget

HOTKEY_ID = 9119
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_SPACE = 0x20
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

class GlobalHotKeyFilter(QAbstractNativeEventFilter):
    """Intercepts Windows WM_HOTKEY messages directly in the Qt event loop."""
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, eventType, message):
        try:
            if eventType in (b"windows_generic_MSG", b"windows_dispatcher_MSG") and message:
                msg_addr = int(message)
                if msg_addr != 0:
                    msg = wintypes.MSG.from_address(msg_addr)
                    if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                        # Defer GUI activation to next Qt event loop iteration to avoid
                        # re-entrant Win32 native event dispatch crash (Access Violation 0xC0000005)
                        QTimer.singleShot(0, self._trigger_callback)
                        return True, 0
        except Exception as e:
            logger.debug(f"WM_HOTKEY message interception exception: {e}")
        return False, 0

    def _trigger_callback(self):
        try:
            if callable(self.callback):
                self.callback()
        except Exception as e:
            logger.warning(f"Error executing hotkey callback: {e}")

class GlobalHotKeyListener(QObject):
    """
    Dedicated background Win32 thread listening for OS-wide Ctrl+Space hotkey.
    Uses GetMessageW for zero CPU overhead and emits a thread-safe Qt Signal
    to activate the command bar on the main UI thread.
    """
    hotkey_triggered = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._thread_id = None
        self._is_running = False
        self._hotkey_registered = False

    def start(self):
        if self._is_running:
            return
        self._is_running = True
        self._thread = threading.Thread(target=self._run, name="FridayGlobalHotkeyListener", daemon=True)
        self._thread.start()

    def stop(self):
        self._is_running = False
        if self._thread_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception as e:
                logger.debug(f"Error posting WM_QUIT to hotkey thread: {e}")
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)

    def _run(self):
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        try:
            # First clear any stale hotkey on this thread
            ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)

            # Register Ctrl+Space with MOD_NOREPEAT
            res = ctypes.windll.user32.RegisterHotKey(
                None, HOTKEY_ID, MOD_CONTROL | MOD_NOREPEAT, VK_SPACE
            )
            if not res:
                # Fallback without MOD_NOREPEAT if unsupported
                res = ctypes.windll.user32.RegisterHotKey(
                    None, HOTKEY_ID, MOD_CONTROL, VK_SPACE
                )

            if res:
                self._hotkey_registered = True
                logger.info("Global hotkey Ctrl+Space registered successfully.")
            else:
                err = ctypes.GetLastError()
                logger.warning(f"RegisterHotKey Ctrl+Space failed with Win32 error code: {err}")

            msg = wintypes.MSG()
            while self._is_running:
                # GetMessage blocks until a message is received (0% CPU)
                r = ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if r > 0:
                    if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                        logger.debug("Global Ctrl+Space hotkey detected, triggering command bar toggle.")
                        self.hotkey_triggered.emit()
                    ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
                    ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    # WM_QUIT (r == 0) or error (r == -1)
                    break
        except Exception as e:
            logger.warning(f"Exception in global hotkey listener thread: {e}")
        finally:
            if self._hotkey_registered:
                try:
                    ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
                except Exception:
                    pass
                self._hotkey_registered = False
            logger.debug("Global hotkey listener thread terminated cleanly.")


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
        self._last_toggle_time = 0.0

        self._init_window_flags()
        self._init_ui()
        self._setup_position()
        self._register_global_hotkey()

    def _init_window_flags(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Window
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.setAttribute(Qt.WA_AcceptTouchEvents, False)

    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(8)

        # 1. Main Horizontal Floating Bar Card
        self.bar_card = QFrame(self)
        self.bar_card.setFixedHeight(56)

        bar_layout = QHBoxLayout(self.bar_card)
        bar_layout.setContentsMargins(14, 6, 14, 6)
        bar_layout.setSpacing(10)

        # Left [+] Action / Mini Reactor Icon
        self.mini_reactor = ArcReactorWidget(size=36, parent=self.bar_card)
        bar_layout.addWidget(self.mini_reactor)

        # Prompt Input Field
        self.prompt_input = LineEdit(self.bar_card)
        self.prompt_input.setPlaceholderText("Ask F.R.I.D.A.Y. anything or enter tactical command...")
        self.prompt_input.returnPressed.connect(self._on_submit)
        bar_layout.addWidget(self.prompt_input, 1)

        # Model Selector ComboBox
        self.model_combo = ComboBox(self.bar_card)
        self.model_combo.setFixedWidth(145)
        self._refreshing_models = False
        saved_model = settings.get("model", "llama3.2:3b")
        initial_models = [saved_model]
        fallback_models = [
            "llama3.2:3b", "llama3.1:8b", "qwen2.5:3b",
            "qwen2.5-coder:latest", "mistral:7b", "deepseek-r1:8b"
        ]
        for fm in fallback_models:
            if fm not in initial_models:
                initial_models.append(fm)
        self.model_combo.addItems(initial_models)
        self.model_combo.setCurrentText(saved_model)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        settings.add_listener(self._on_settings_model_sync)
        settings.add_listener(self._on_settings_theme_sync)
        # Schedule asynchronous discovery of local Ollama models without blocking GUI thread
        QTimer.singleShot(150, self.refresh_models)
        bar_layout.addWidget(self.model_combo)

        # Voice Trigger Button (Mic)
        self.mic_btn = ToolButton(FluentIcon.MICROPHONE, self.bar_card)
        self.mic_btn.setFixedSize(36, 36)
        self.mic_btn.clicked.connect(self.voice_toggle_requested.emit)
        bar_layout.addWidget(self.mic_btn)

        # Mode Chip (Tactical / Speed / Deep)
        self.mode_btn = PillPushButton("⚡ Tactical", self.bar_card)
        self.mode_btn.setFixedWidth(88)
        self.mode_btn.clicked.connect(self._cycle_mode)
        bar_layout.addWidget(self.mode_btn)

        # Stop Button in Floating Bar
        self.stop_btn = PillPushButton("■ Stop", self.bar_card)
        self.stop_btn.setFixedWidth(68)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setToolTip("Immediately halt voice playback (Esc)")
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
        self.response_layout = QVBoxLayout(self.response_card)
        self.response_layout.setContentsMargins(14, 12, 14, 12)
        self.response_layout.setSpacing(6)

        # Status & Header row
        resp_header = QHBoxLayout()
        self.resp_title = QLabel("F.R.I.D.A.Y. RESPONSE")
        self.resp_title.setFont(QFont("Segoe UI", 9, QFont.Bold))
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
        self.response_text.setMinimumHeight(60)
        self.response_text.setMaximumHeight(220)
        self.response_layout.addWidget(self.response_text)

        self.response_card.setVisible(False)
        self.main_layout.addWidget(self.response_card)

        self.setFixedWidth(740)
        self.mic_shortcut = QShortcut(QKeySequence("Ctrl+M"), self)
        self.mic_shortcut.activated.connect(self.voice_toggle_requested.emit)
        self._mic_active = False

        # Apply active theme dynamically
        self.apply_theme()


    def _setup_position(self):
        """Places the bar on screen according to user settings or last saved coords."""
        try:
            primary = QApplication.primaryScreen()
            screen = primary.availableGeometry() if primary else QRect(0, 0, 1920, 1080)
        except Exception:
            screen = QRect(0, 0, 1920, 1080)

        pos_mode = settings.get("command_bar_position", "top")
        last_x = settings.get("last_x", -1)
        last_y = settings.get("last_y", -1)

        w = 740
        if pos_mode == "last" and last_x >= 0 and last_y >= 0:
            x = min(max(0, screen.width() - w), max(0, last_x))
            y = min(max(0, screen.height() - 100), max(0, last_y))
        elif pos_mode == "bottom":
            x = max(0, (screen.width() - w) // 2)
            y = max(0, screen.height() - 140)
        else: # Default: Top
            x = max(0, (screen.width() - w) // 2)
            y = 70

        self.move(x, y)

    def _on_hotkey_triggered(self):
        """Debounces physical hotkey presses (250ms) to prevent race conditions."""
        now = time.monotonic()
        if hasattr(self, '_last_hotkey_time') and (now - self._last_hotkey_time < 0.25):
            return
        self._last_hotkey_time = now
        self.toggle_visibility()

    def _register_global_hotkey(self):
        """Registers global Ctrl+Space hotkey with background listener thread and local shortcut."""
        # 1. Local in-app shortcut for immediate response when bar has focus
        try:
            self.local_shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
            self.local_shortcut.activated.connect(self._on_hotkey_triggered)
        except Exception as e:
            logger.debug(f"Local shortcut init note: {e}")

        # 2. Global background hotkey listener for OS-wide activation
        try:
            self._hotkey_listener = GlobalHotKeyListener(self)
            self._hotkey_listener.hotkey_triggered.connect(self._on_hotkey_triggered)
            self._hotkey_listener.start()
            self._hotkey_registered = True
        except Exception as e:
            logger.warning(f"Failed to initialize GlobalHotKeyListener: {e}")

        # Note: GlobalHotKeyFilter is deliberately NOT installed on QApplication.
        # GlobalHotKeyListener already receives WM_HOTKEY via Win32 GetMessageW
        # in a dedicated worker thread with 0% CPU. Installing a native event filter
        # on QApplication intercepts thousands of messages per second in Qt's
        # internal dispatch loop and causes access violations / event loop deadlocks.
        self._event_filter = None

    def unregister_hotkey(self):
        """Unregisters global hotkey and stops listener thread on shutdown."""
        if hasattr(self, '_hotkey_listener') and self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
                self._hotkey_listener = None
            except Exception as e:
                logger.debug(f"Failed to stop hotkey listener: {e}")
        if self._event_filter is not None:
            try:
                app = QApplication.instance()
                if app is not None:
                    app.removeNativeEventFilter(self._event_filter)
            except Exception as e:
                logger.debug(f"Failed to remove native event filter: {e}")
            finally:
                self._event_filter = None
        try:
            ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
            self._hotkey_registered = False
        except Exception as e:
            logger.debug(f"Failed to unregister global hotkey: {e}")

    def toggle_visibility(self):
        """Toggles display and brings command bar to foreground with robust input focus."""
        try:
            if self.isVisible():
                self.hide()
            else:
                self._setup_position()
                self.show()
                self.raise_()
                self.activateWindow()

                # Force input focus transfer so the user can type immediately without freezing
                try:
                    hwnd = int(self.winId())
                    user32 = ctypes.windll.user32

                    # Explicitly set AppUserModelID on this window handle so taskbar displays custom identity
                    try:
                        from win32com.propsys import propsys, pscon
                        import pythoncom
                        store = propsys.SHGetPropertyStoreForWindow(hwnd, propsys.IID_IPropertyStore)
                        pv = propsys.PROPVARIANTType("StarkIndustries.FRIDAY.Assistant.2.0", pythoncom.VT_LPWSTR)
                        store.SetValue(pscon.PKEY_AppUserModel_ID, pv)
                        store.Commit()
                        del store
                    except Exception:
                        pass

                    cur_fg = user32.GetForegroundWindow()
                    if cur_fg and cur_fg != hwnd:
                        cur_thread = ctypes.windll.kernel32.GetCurrentThreadId()
                        fg_thread = user32.GetWindowThreadProcessId(cur_fg, None)
                        if cur_thread != fg_thread:
                            user32.AttachThreadInput(cur_thread, fg_thread, True)
                            user32.SetForegroundWindow(hwnd)
                            user32.BringWindowToTop(hwnd)
                            user32.AttachThreadInput(cur_thread, fg_thread, False)
                        else:
                            user32.SetForegroundWindow(hwnd)
                            user32.BringWindowToTop(hwnd)
                    else:
                        user32.SetForegroundWindow(hwnd)
                        user32.BringWindowToTop(hwnd)
                except Exception as ex:
                    logger.debug(f"Foreground window activation note: {ex}")

                QTimer.singleShot(0, self.prompt_input.setFocus)
                QTimer.singleShot(0, self.prompt_input.selectAll)
        except Exception as e:
            logger.warning(f"Error toggling command bar visibility: {e}")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

    def show_response(self, text: str):
        """Displays output in the expanding response card with smooth easing animation."""
        self.response_text.setMarkdown(text)
        if not self.isVisible():
            self._setup_position()
            self.show()
            self.raise_()
            self.activateWindow()

        if not self.response_card.isVisible():
            self.response_card.setVisible(True)
            self.is_expanded = True
            eff = self.response_card.graphicsEffect()
            if not isinstance(eff, QGraphicsOpacityEffect):
                eff = QGraphicsOpacityEffect(self.response_card)
                self.response_card.setGraphicsEffect(eff)
            if hasattr(self, '_resp_anim') and self._resp_anim:
                self._resp_anim.stop()
            self._resp_anim = QPropertyAnimation(eff, b"opacity", self)
            self._resp_anim.setDuration(240)
            self._resp_anim.setStartValue(0.0)
            self._resp_anim.setEndValue(1.0)
            self._resp_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._resp_anim.start()
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
            if hasattr(self, '_resp_anim') and self._resp_anim:
                self._resp_anim.stop()
            self._resp_anim = QPropertyAnimation(eff, b"opacity", self)
            self._resp_anim.setDuration(180)
            self._resp_anim.setStartValue(1.0)
            self._resp_anim.setEndValue(0.0)
            self._resp_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._resp_anim.finished.connect(self._on_hide_resp_finished)
            self._resp_anim.start()

    def _on_hide_resp_finished(self):
        self.response_card.setVisible(False)
        self.is_expanded = False
        self.adjustSize()


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
            QTimer.singleShot(0, self.refresh_models)

    def _on_settings_theme_sync(self, key: str, value):
        if key in ("theme_mode", "theme"):
            QTimer.singleShot(0, lambda: self.apply_theme(str(value)))

    def apply_theme(self, theme_mode: str = None):
        """Dynamically styles the floating bar, combo, mode pill, response card, and mic button."""
        from friday_ui.styles.themes import get_theme_palette, get_current_palette
        p = get_theme_palette(theme_mode) if theme_mode else get_current_palette()
        mode_str = str(theme_mode or settings.get("theme_mode", "warm_light")).lower()
        is_light = "light" in mode_str or "cream" in mode_str

        # 1. Bar Card (Pill Container)
        bar_bg = "rgba(253, 251, 247, 0.96)" if is_light else ("rgba(28, 25, 23, 0.94)" if "warm" in mode_str else "rgba(18, 22, 32, 0.94)")
        bar_border = p.get("accent_border", "rgba(0, 240, 255, 0.35)")
        self.bar_card.setStyleSheet(f"""
            QFrame {{
                background-color: {bar_bg};
                border: 1.5px solid {bar_border};
                border-radius: 28px;
            }}
        """)

        # 2. Prompt Input
        self.prompt_input.setStyleSheet(f"""
            LineEdit {{
                background-color: transparent;
                border: none;
                color: {p['text_primary']};
                font-size: 13px;
                font-weight: 500;
                padding-left: 4px;
            }}
        """)

        # 3. Model Selector ComboBox
        self.model_combo.setStyleSheet(f"""
            ComboBox {{
                background-color: {p['combo_bg']};
                border: 1px solid {p['combo_border']};
                border-radius: 14px;
                color: {p['accent']};
                font-size: 11px;
                font-weight: 600;
                padding: 4px 10px;
            }}
            ComboBox:hover {{
                background-color: {p.get('combo_hover_bg', p['combo_bg'])};
                border: 1px solid {p['combo_hover_border']};
            }}
        """)

        # 4. Mode Chip
        self.mode_btn.setStyleSheet(f"""
            PillPushButton {{
                background-color: {p['accent_bg']};
                border: 1px solid {p['accent_border']};
                color: {p['accent']};
                font-size: 11px;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 14px;
            }}
            PillPushButton:hover {{
                background-color: {p['accent']};
                color: {p.get('accent_text', '#FFFFFF')};
                border: 1px solid {p['accent_hover']};
            }}
        """)

        # 5. Stop Button
        self.stop_btn.setStyleSheet(f"""
            PillPushButton {{
                background-color: {p['danger_red']};
                border: 1px solid {p['danger_red']};
                color: #FFFFFF;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 14px;
            }}
            PillPushButton:hover {{
                background-color: #DC2626;
                border: 1px solid #EF4444;
            }}
        """)

        # 6. Response Panel Card
        resp_bg = "rgba(247, 244, 238, 0.96)" if is_light else ("rgba(23, 20, 19, 0.96)" if "warm" in mode_str else "rgba(14, 18, 28, 0.96)")
        self.response_card.setStyleSheet(f"""
            QFrame {{
                background-color: {resp_bg};
                border: 1px solid {p['accent_border']};
                border-radius: 14px;
            }}
        """)
        self.resp_title.setStyleSheet(f"color: {p['accent']}; letter-spacing: 1px;")
        self.response_text.setStyleSheet(f"""
            QTextBrowser {{
                background-color: transparent;
                border: none;
                color: {p['text_primary']};
                font-size: 12px;
                line-height: 1.4;
            }}
        """)

        # 7. Close button subtle hover
        self.close_btn.setStyleSheet(f"""
            TransparentToolButton {{
                color: {p['text_muted']};
                border-radius: 14px;
            }}
            TransparentToolButton:hover {{
                background-color: {p['border_subtle']};
                color: {p['text_primary']};
            }}
        """)

        # 8. Update Mic Button with active theme colors
        self.set_mic_active(getattr(self, '_mic_active', False))

        # 9. Update Arc Reactor
        if hasattr(self, 'mini_reactor') and hasattr(self.mini_reactor, 'apply_theme'):
            self.mini_reactor.apply_theme(theme_mode)

    def refresh_models(self):
        """Asynchronously queries Ollama for installed models without blocking UI thread."""
        if getattr(self, "_refreshing_models", False):
            return
        self._refreshing_models = True
        curr = settings.get("model") or self.model_combo.currentText()

        def _fetch():
            try:
                avail = settings.get_available_models()
                QTimer.singleShot(0, lambda: self._apply_refreshed_models(avail, curr))
            except Exception as e:
                logger.debug(f"Async model discovery note: {e}")
            finally:
                self._refreshing_models = False

        threading.Thread(target=_fetch, name="FridayCommandBarModelRefresh", daemon=True).start()

    def _apply_refreshed_models(self, avail: List[str], curr: str):
        if not avail:
            return
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

    def _on_model_changed(self, model: str):
        if getattr(self, "_refreshing_models", False) or not model:
            return
        settings.set("model", model)
        self.model_changed.emit(model)


    def set_mic_active(self, active: bool):
        """Updates mic button appearance in FloatingCommandBar matching active theme."""
        self._mic_active = active
        from friday_ui.styles.themes import get_current_palette
        p = get_current_palette()
        if active:
            self.mic_btn.setToolTip("Mute Microphone (Ctrl+M)")
            self.mic_btn.setStyleSheet(f"""
                ToolButton {{
                    background-color: {p['live_green_bg']};
                    border: 1.5px solid {p['live_green']};
                    border-radius: 18px;
                    color: {p['live_green']};
                }}
                ToolButton:hover {{
                    background-color: {p['live_green_border']};
                }}
            """)
        else:
            self.mic_btn.setToolTip("Unmute Microphone (Ctrl+M)")
            self.mic_btn.setStyleSheet(f"""
                ToolButton {{
                    background-color: {p['danger_red_bg']};
                    border: 1.5px solid {p['danger_red']};
                    border-radius: 18px;
                    color: {p['danger_red']};
                }}
                ToolButton:hover {{
                    background-color: {p['danger_red_border']};
                }}
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
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if hasattr(self, 'stop_btn') and self.stop_btn.isVisible():
                self.stop_requested.emit()
            self.hide()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.unregister_hotkey()
        super().closeEvent(event)

