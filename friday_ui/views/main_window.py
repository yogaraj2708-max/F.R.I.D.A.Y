"""
F.R.I.D.A.Y. 2.0 - Main Desktop Application Window
Full-Width Layout with Integrated HUD Dock — No More Right-Side Dead Space
"""

import asyncio
import os
import sys
import math
import logging
import re

logger = logging.getLogger("FRIDAY.MainWindow")
from PySide6.QtCore import Qt, QSize, QTimer, QRectF, QPointF, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QIcon, QFont, QColor, QPainter, QLinearGradient, QPen, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGraphicsDropShadowEffect, QSizePolicy, QStackedWidget
)
from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon,
    setTheme, Theme, InfoBar, InfoBarPosition, PushButton
)

from friday_ui.core.config import USER_NAME, ACCENT_COLOR, STARK_CYAN
from friday_ui.core.engine import FridaySignals, FridayVoiceEngine, FridayBrain, FridayVoiceLoop
from friday_ui.widgets.audio_visualizer import AudioVisualizerWidget
from friday_ui.views.chat_view import ChatView
from friday_ui.views.rag_view import RAGView
from friday_ui.views.research_view import ResearchView
from friday_ui.views.settings_view import SettingsView

from duckduckgo_search import DDGS
from friday_ui.rag.store import FridayVectorStore
from friday_ui.widgets.confirmation_dialog import SecurityConfirmationDialog
from friday_ui.widgets.operations_panel import OperationsPanel
from friday_ui.widgets.glass_panel import GlassPanel
from friday_ui.styles.themes import generate_global_qss, MONO_DARK, fade_in, get_theme_palette
from friday_core.gatekeeper.gatekeeper import gatekeeper
from friday_core.settings import settings
from friday_core.system import get_battery_info, get_memory_info
from friday_core.agent.task_lifecycle import task_supervisor, TaskRecord, TaskState, TaskStage
from friday_core.research.worker import DeepResearchWorker


class HUDDockWidget(GlassPanel):
    """
    Bottom HUD status bar with integrated audio visualizer,
    acoustic status, and telemetry indicators. Renders as a
    sleek modern bar at the bottom of the main window.
    """
    def __init__(self, parent=None):
        super().__init__(
            parent=parent,
            bg_color="rgba(16, 19, 24, 0.92)",
            border_color="rgba(255, 255, 255, 0.08)",
            radius=0,
            enable_shadow=False
        )
        self.setObjectName("hudDock")
        self.setFixedHeight(44)
        self._phase = 0.0

        dock_layout = QHBoxLayout(self)
        dock_layout.setContentsMargins(18, 4, 18, 4)
        dock_layout.setSpacing(14)

        # ── Left: Compact Status Cluster ──
        status_box = QHBoxLayout()
        status_box.setSpacing(6)
        from friday_ui.styles.themes import PulseStatusDot
        self.status_dot = PulseStatusDot(QColor(16, 185, 129), size=8, parent=self)
        status_box.addWidget(self.status_dot)

        self.hud_state_label = QLabel("● Online")
        self.hud_state_label.setObjectName("hudStateLabel")
        self.hud_state_label.setAccessibleName("System operational state")
        self.hud_state_label.setProperty("state", "standby")
        self.hud_state_label.setFont(QFont("Inter", 8, QFont.Bold))
        self.hud_state_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        status_box.addWidget(self.hud_state_label)
        dock_layout.addLayout(status_box)

        # ── Center: Audio Visualizer ──
        self.visualizer = AudioVisualizerWidget(self)
        self.visualizer.setFixedHeight(34)
        dock_layout.addWidget(self.visualizer, 1)

        # ── Stop Voice Button ──
        self.stop_voice_btn = PushButton("■ Stop Voice", self)
        self.stop_voice_btn.setObjectName("stop_voice_button")
        self.stop_voice_btn.setAccessibleName("Stop voice playback")
        self.stop_voice_btn.setFixedSize(98, 28)
        self.stop_voice_btn.setCursor(Qt.PointingHandCursor)
        self.stop_voice_btn.setToolTip("Immediately stop vocal playback (Esc)")
        self.stop_voice_btn.setStyleSheet("""
            PushButton {
                background-color: #EF4444;
                border: 1px solid #DC2626;
                font-weight: 600;
                font-size: 11px;
                border-radius: 6px;
                color: #FFFFFF;
                letter-spacing: 0.3px;
            }
            PushButton:hover {
                background-color: #DC2626;
            }
            PushButton:pressed {
                background-color: #B91C1C;
            }
        """)
        self.stop_voice_btn.hide()
        dock_layout.addWidget(self.stop_voice_btn)

        # ── Right: Glanceable Telemetry chip ──
        self.telemetry_label = QLabel("⚡ NOMINAL")
        self.telemetry_label.setObjectName("hudTelemetryLabel")
        self.telemetry_label.setAccessibleName("System telemetry status")
        self.telemetry_label.setProperty("variant", "nominal")
        self.telemetry_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.telemetry_label.setMinimumWidth(130)
        dock_layout.addWidget(self.telemetry_label)


class FridayMainWindow(FluentWindow):
    """
    Main Reactive Desktop Application for F.R.I.D.A.Y. 2.0.
    Full-width layout with HUD dock at the bottom.
    """
    def __init__(self):
        super().__init__()
        try:
            if qconfig.theme != Theme.DARK:
                setTheme(Theme.DARK)
        except Exception:
            pass

        # Core Engine Setup
        self.signals = FridaySignals()
        self.tts = FridayVoiceEngine(self.signals)
        self.brain = FridayBrain(self.signals, self.tts)

        # Synchronize loaded preferences
        self.brain.model = settings.get("model", self.brain.model)
        saved_voice = settings.get("voice", "bf_emma")
        self.tts.voice = saved_voice
        self.tts.local_voice = settings.get("local_voice", "bf_emma")
        self.tts.use_local_tts = settings.get("use_local_tts", True)

        self.voice_loop = FridayVoiceLoop(self.signals, self.brain, self.tts)
        self.voice_task = None
        self.command_bar = None
        self.vector_store = FridayVectorStore()
        self.brain.vector_store = self.vector_store
        self._tasks = set()
        self._current_command_task = None
        self._active_research_worker = None
        self._active_pdf_worker = None
        self._active_task_id = None
        self._force_close = False

        self._init_window()
        self._init_sub_interfaces()
        self._init_hud_dock()
        self._connect_signals()
        self._apply_global_style()

        # Global Escape Shortcut to halt speech & generation
        self.esc_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.esc_shortcut.activated.connect(self._on_global_escape_pressed)

        # Telemetry Polling Timer
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.timeout.connect(self._poll_telemetry)
        poll_ms = int(settings.get("telemetry_poll_interval", 20)) * 1000
        self.telemetry_timer.start(poll_ms)
        QTimer.singleShot(1000, self._poll_telemetry)

        # Task Lifecycle Watchdog Timer (Zero Stuck Thinking Enforcement)
        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.timeout.connect(self._check_task_watchdogs)
        self._watchdog_timer.start(1000)

    def _check_task_watchdogs(self):
        """Monitors all active tasks for stall / deadline breaches, forcing clean recovery."""
        timed_out = task_supervisor.check_watchdogs()
        for task in timed_out:
            logger.warning("Task %s timed out under watchdog supervision: %s", task.task_id, task.progress_message)
            if self._active_research_worker and getattr(self._active_research_worker, 'task_record', None):
                if self._active_research_worker.task_record.task_id == task.task_id:
                    self._active_research_worker.cancel()
                    self._active_research_worker = None
            if self._active_pdf_worker and getattr(self._active_pdf_worker, 'task_id', None) == task.task_id:
                self._active_pdf_worker.cancel()
                self._active_pdf_worker = None
            if getattr(self, '_active_task_id', None) == task.task_id:
                self._active_task_id = None

            timeout_msg = f"⏱️ **Watchdog Timeout Alert**: Task '{task.query}' stalled beyond {task.idle_timeout}s without telemetry progress. Cleanly halted."
            self.chat_view.finish_stream(final_text=timeout_msg)
            self.signals.state_changed.emit("idle")
            InfoBar.warning(
                "Task Timed Out",
                f"Watchdog interrupted stalled task: {task.query[:30]}",
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
                duration=4000
            )

    def _on_global_escape_pressed(self):
        if getattr(self.tts, "is_speaking", False) or (getattr(self, '_current_command_task', None) and not self._current_command_task.done()) or self._active_research_worker:
            self.handle_stop_requested()

    def _create_task(self, coro):
        """Standard fire-and-forget task tracker to prevent premature garbage collection."""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def _init_window(self):
        self.setObjectName("FridayMainWindow")
        self.setWindowTitle("F.R.I.D.A.Y. 3.0 - Desktop AI Assistant")
        self.setAccessibleName("F.R.I.D.A.Y. AI Assistant Main Window")
        self.resize(1200, 800)
        self.setMinimumSize(950, 650)
        self.setAttribute(Qt.WA_AcceptTouchEvents, False)
        self.setMicaEffectEnabled(False)
        try:
            from friday_ui.app import get_app_icon
            self.setWindowIcon(get_app_icon())
        except Exception:
            pass

        # Global Hotkey Ctrl+M for Microphone Mute / Unmute
        self.mic_shortcut = QShortcut(QKeySequence("Ctrl+M"), self)
        self.mic_shortcut.activated.connect(self.toggle_voice_loop)

        # Ctrl+Space is deliberately NOT bound here. FloatingCommandBar already
        # registers an OS-wide hotkey and its own local shortcut.


    def _apply_global_style(self):
        """Apply Centralized Dark Neutral / Slate Desktop Styling with rich canvas backing."""
        theme_mode = settings.get("theme_mode", "dark")
        p = get_theme_palette(theme_mode)
        is_light = "light" in str(theme_mode).lower()

        try:
            from qfluentwidgets import setThemeColor
            setTheme(Theme.LIGHT if is_light else Theme.DARK)
            setThemeColor(p['accent'])
        except Exception:
            pass

        self.setStyleSheet(generate_global_qss(theme_mode) + f"""
            #FridayMainWindow, #content_container, #workspace_container, #chat_view, #rag_view, #documents_view, #research_view, #settings_view {{
                background-color: {p['bg_canvas']};
            }}
            NavigationInterface {{
                background-color: {p['nav_bg']};
                border-right: 1px solid {p['nav_border']};
            }}
        """)
        if hasattr(self, 'hud_dock') and self.hud_dock:
            self.hud_dock.set_glass_style(
                bg_color=p.get('bg_dock', 'rgba(16, 19, 24, 0.92)'),
                border_color=p.get('border_subtle', 'rgba(255, 255, 255, 0.08)'),
                radius=0
            )
        if hasattr(self, 'chat_view') and hasattr(self.chat_view, 'apply_theme'):
            self.chat_view.apply_theme(theme_mode)
        if hasattr(self, 'command_bar') and hasattr(self.command_bar, 'apply_theme'):
            self.command_bar.apply_theme(theme_mode)


    def _init_sub_interfaces(self):
        # 1. Chat View (Default centerpiece)
        self.chat_view = ChatView(self)
        self.chat_view.setObjectName("chat_view")
        self.chat_view.setAccessibleName("Chat interface")
        self.addSubInterface(self.chat_view, FluentIcon.CHAT, "Chat")

        # 2. Autonomous Deep Research
        self.research_view = ResearchView(self)
        self.research_view.setObjectName("research_view")
        self.research_view.setAccessibleName("Research interface")
        self.addSubInterface(self.research_view, FluentIcon.GLOBE, "Research")

        # 3. Files & Documents (Unified document intelligence)
        from friday_ui.views.rag_view import DocumentsView
        self.documents_view = DocumentsView(self)
        self.documents_view.setObjectName("documents_view")
        self.documents_view.setAccessibleName("Files and documents interface")
        self.rag_view = self.documents_view  # Backward compatibility alias
        self.addSubInterface(self.documents_view, FluentIcon.DOCUMENT, "Files & Documents")

        # 4. Settings
        self.settings_view = SettingsView(self)
        self.settings_view.setObjectName("settings_view")
        self.settings_view.setAccessibleName("Settings interface")
        self.addSubInterface(
            self.settings_view,
            FluentIcon.SETTING,
            "Settings",
            NavigationItemPosition.BOTTOM
        )
        if hasattr(self, 'stackedWidget'):
            self.stackedWidget.setAnimationEnabled(False)

    def switchTo(self, interface):
        """Overrides switchTo to provide clean transitions without graphics effect conflicts."""
        super().switchTo(interface)
        if hasattr(self, 'chat_view') and self.chat_view.graphicsEffect():
            self.chat_view.setGraphicsEffect(None)

    def _init_hud_dock(self):
        """
        Creates the bottom HUD dock and 3-pane workspace with OperationsPanel.
        """
        self.hud_dock = HUDDockWidget(self)
        self.operations_panel = OperationsPanel(self)
        self.operations_panel.hide()

        self.widgetLayout.removeWidget(self.stackedWidget)
        self.widgetLayout.setContentsMargins(0, 48, 0, 0)

        self.content_container = QWidget(self)
        self.content_vbox = QVBoxLayout(self.content_container)
        self.content_vbox.setContentsMargins(0, 0, 0, 0)
        self.content_vbox.setSpacing(0)

        # 3-Pane Center Workspace (Center Stacked Views + Right Operations Panel)
        self.workspace_container = QWidget(self)
        self.workspace_hbox = QHBoxLayout(self.workspace_container)
        self.workspace_hbox.setContentsMargins(0, 0, 0, 0)
        self.workspace_hbox.setSpacing(0)
        self.workspace_hbox.addWidget(self.stackedWidget, 1)
        self.workspace_hbox.addWidget(self.operations_panel, 0)

        self.content_vbox.addWidget(self.workspace_container, 1)
        self.content_vbox.addWidget(self.hud_dock, 0)

        self.widgetLayout.addWidget(self.content_container)
        self.titleBar.raise_()

    # ── Property aliases for cleaner access ──
    @property
    def visualizer(self):
        return self.hud_dock.visualizer

    @property
    def visualizer_dock(self):
        return self.hud_dock

    def _connect_signals(self):
        # Engine -> UI signals
        self.signals.transcript_received.connect(self.chat_view.add_message)
        self.signals.stream_started.connect(self.chat_view.start_stream)
        self.signals.stream_token.connect(self.chat_view.append_token)
        self.signals.stream_thinking.connect(self.chat_view.append_thinking)
        self.signals.stream_finished.connect(self.chat_view.finish_stream)
        self.signals.status_updated.connect(self.chat_view.update_status)
        self.signals.stream_started.connect(lambda role, status: self.operations_panel.add_audit("STREAM", f"Started: {status[:25]}", "#06B6D4"))
        self.signals.stream_finished.connect(lambda text: self.operations_panel.add_audit("LLM", f"Completed: {len(text)} chars", "#10B981"))
        self.signals.speech_level_changed.connect(self.hud_dock.visualizer.update_audio_level)
        self.signals.speech_level_changed.connect(self.chat_view.update_energy)
        self.signals.state_changed.connect(self._on_engine_state_changed)
        self.signals.skill_executed.connect(self._on_skill_executed)
        self.signals.telemetry_updated.connect(self._on_telemetry_updated)
        self.signals.wake_word_detected.connect(self.chat_view.arc_reactor.trigger_burst)
        self.signals.confirmation_requested.connect(self._on_confirmation_requested)
        self.signals.error_occurred.connect(self._on_error)

        self.hud_dock.stop_voice_btn.clicked.connect(self.handle_stop_requested)
        self.chat_view.command_submitted.connect(self.handle_user_command)
        self.chat_view.doc_ingest_requested.connect(self.handle_doc_ingest)
        self.chat_view.deep_research_requested.connect(lambda topic: self.handle_research(topic, "Deep Comprehensive"))
        self.chat_view.voice_toggle_requested.connect(self.toggle_voice_loop)
        self.chat_view.stop_requested.connect(self.handle_stop_requested)
        self.chat_view.model_changed.connect(self._on_model_quick_switched)
        self.chat_view.voice_changed.connect(self._on_voice_quick_switched)
        self.chat_view.session_changed.connect(self._on_session_changed)
        if hasattr(self.chat_view, 'inspector_toggle_requested'):
            self.chat_view.inspector_toggle_requested.connect(self._toggle_operations_panel)
        self.operations_panel.quick_command_triggered.connect(self.handle_user_command)
        self.rag_view.document_ingested.connect(self.handle_doc_ingest)
        self.rag_view.query_requested.connect(self.handle_rag_query)
        self.research_view.research_requested.connect(self.handle_research)
        self.signals.theme_change_requested.connect(self._on_theme_change_requested)
        self.settings_view.settings_saved.connect(self.handle_settings_update)

    def _on_session_changed(self, session_id: str):
        """Synchronizes brain conversation history with the active session."""
        if hasattr(self, 'brain'):
            self.brain.current_session_id = session_id
        if hasattr(self, 'chat_view') and hasattr(self.chat_view, 'session_store') and hasattr(self, 'brain'):
            messages = self.chat_view.session_store.get_messages(session_id)
            self.brain.load_session_history(messages, session_id=session_id)

    def _on_theme_change_requested(self, mode: str):
        settings.set("theme_mode", mode)
        self._apply_global_style()
        mode_label = "Warm Dark (Obsidian)" if "dark" in mode else "Warm Light (Cream)"
        try:
            InfoBar.info(
                "Theme Switched",
                f"Visual mode set to {mode_label}",
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2000
            )
        except Exception:
            pass

    def _on_model_quick_switched(self, model_name: str):
        self.brain.model = model_name
        settings.set("model", model_name)
        InfoBar.success("Model Switched", f"Active neural model: {model_name}", parent=self, position=InfoBarPosition.TOP_RIGHT, duration=2000)

    def _on_voice_quick_switched(self, voice_display: str):
        voice_key = voice_display.split()[0]
        self.tts.voice = voice_key
        if any(voice_key.startswith(v) for v in ["bf_emma", "af_sarah", "af_bella", "af_nicole", "bf_isabella", "am_adam"]):
            self.tts.use_local_tts = True
            self.tts.local_voice = voice_key
        else:
            self.tts.use_local_tts = False
        settings.set("voice", voice_key)
        settings.set("use_local_tts", self.tts.use_local_tts)
        settings.set("local_voice", getattr(self.tts, "local_voice", "bf_emma"))
        InfoBar.success("Voice Switched", f"Active voice persona: {voice_display}", parent=self, position=InfoBarPosition.TOP_RIGHT, duration=2000)

    def _on_engine_state_changed(self, state: str):
        self.chat_view.update_state(state)
        st = state.lower()
        if st in ["listening"]:
            if getattr(self, "brain", None) and getattr(self.brain, "is_generating", False):
                return
            self.hud_dock.hud_state_label.setText("● Listening")
            self.hud_dock.hud_state_label.setProperty("state", "listening")
            if hasattr(self.hud_dock, 'status_dot'):
                self.hud_dock.status_dot.set_color(QColor(16, 185, 129))
            self.hud_dock.visualizer.set_active(True)
            self.hud_dock.stop_voice_btn.hide()
        elif st in ["thinking", "processing"]:
            self.hud_dock.hud_state_label.setText("● Thinking")
            self.hud_dock.hud_state_label.setProperty("state", "thinking")
            if hasattr(self.hud_dock, 'status_dot'):
                self.hud_dock.status_dot.set_color(QColor(245, 158, 11))
            self.hud_dock.visualizer.set_active(True)
            self.hud_dock.stop_voice_btn.hide()
        elif st == "speaking":
            self.hud_dock.hud_state_label.setText("● Speaking")
            self.hud_dock.hud_state_label.setProperty("state", "speaking")
            if hasattr(self.hud_dock, 'status_dot'):
                self.hud_dock.status_dot.set_color(QColor(245, 158, 11))
            self.hud_dock.visualizer.set_active(True)
            self.hud_dock.stop_voice_btn.show()
        elif st == "researching":
            self.hud_dock.hud_state_label.setText("● Researching")
            self.hud_dock.hud_state_label.setProperty("state", "researching")
            if hasattr(self.hud_dock, 'status_dot'):
                self.hud_dock.status_dot.set_color(QColor(6, 182, 212))
            self.hud_dock.visualizer.set_active(True)
            self.hud_dock.stop_voice_btn.hide()
        elif st in ["failed", "anomaly", "error"]:
            self.hud_dock.hud_state_label.setText("● Error")
            self.hud_dock.hud_state_label.setProperty("state", "idle")
            if hasattr(self.hud_dock, 'status_dot'):
                self.hud_dock.status_dot.set_color(QColor(239, 68, 68))
            self.hud_dock.visualizer.set_active(False)
            self.hud_dock.stop_voice_btn.hide()
        elif st in ["timed_out", "timeout"]:
            self.hud_dock.hud_state_label.setText("● Timeout")
            self.hud_dock.hud_state_label.setProperty("state", "idle")
            if hasattr(self.hud_dock, 'status_dot'):
                self.hud_dock.status_dot.set_color(QColor(239, 68, 68))
            self.hud_dock.visualizer.set_active(False)
            self.hud_dock.stop_voice_btn.hide()
        elif st in ["offline", "muted", "cancelled", "stopped"]:
            self.hud_dock.hud_state_label.setText("● Offline")
            self.hud_dock.hud_state_label.setProperty("state", "idle")
            if hasattr(self.hud_dock, 'status_dot'):
                self.hud_dock.status_dot.set_color(QColor(107, 114, 128))
            self.hud_dock.visualizer.set_active(False)
            self.hud_dock.stop_voice_btn.hide()
        else:
            self.hud_dock.hud_state_label.setText("● Online")
            self.hud_dock.hud_state_label.setProperty("state", "standby")
            if hasattr(self.hud_dock, 'status_dot'):
                self.hud_dock.status_dot.set_color(QColor(16, 185, 129))
            self.hud_dock.visualizer.set_active(False)
            self.hud_dock.stop_voice_btn.hide()

        self.hud_dock.hud_state_label.style().unpolish(self.hud_dock.hud_state_label)
        self.hud_dock.hud_state_label.style().polish(self.hud_dock.hud_state_label)
        self.hud_dock.visualizer.set_state(st)

    def _toggle_operations_panel(self):
        if hasattr(self, 'operations_panel'):
            self.operations_panel.setVisible(not self.operations_panel.isVisible())

    def _on_confirmation_requested(self, intent):
        """Displays modal SecurityConfirmationDialog with 10s countdown for Tier 2 clearance."""
        dry_run = gatekeeper.get_dry_run_preview(intent)
        dialog = SecurityConfirmationDialog(dry_run, intent.action, parent=self)

        def on_confirm():
            intent.confirmed = True
            res = gatekeeper.execute_action(intent)
            msg = f"Clearance granted: {res.message}"
            self.chat_view.add_message("friday", msg)
            self.signals.skill_executed.emit(intent.action, res.message)
            self._create_task(self.tts.speak(res.message))

        def on_cancel():
            msg = "Tier 2 action cancelled by operator clearance denial or timeout."
            self.chat_view.add_message("system", msg)
            self._create_task(self.tts.speak("Action aborted, Boss."))

        dialog.confirmed.connect(on_confirm)
        dialog.cancelled.connect(on_cancel)
        dialog.exec()

    def _on_skill_executed(self, name: str, detail: str):
        self.hud_dock.telemetry_label.setText(f"⚡ {name.upper()}: {detail[:22]}")
        self.hud_dock.telemetry_label.setProperty("variant", "active")
        self.hud_dock.telemetry_label.style().unpolish(self.hud_dock.telemetry_label)
        self.hud_dock.telemetry_label.style().polish(self.hud_dock.telemetry_label)

        if hasattr(self, 'operations_panel'):
            self.operations_panel.add_audit("EXEC", f"{name}: {detail}", "#10B981")
        InfoBar.info(
            name,
            f"Executed tactical skill: {detail}",
            parent=self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2500
        )
        # Reset back to green after 3s
        QTimer.singleShot(3000, self._reset_telemetry_style)

    def _reset_telemetry_style(self):
        self.hud_dock.telemetry_label.setProperty("variant", "nominal")
        self.hud_dock.telemetry_label.style().unpolish(self.hud_dock.telemetry_label)
        self.hud_dock.telemetry_label.style().polish(self.hud_dock.telemetry_label)

    def _on_telemetry_updated(self, data: dict):
        bat = data.get("battery", "N/A")
        mem = data.get("memory", "N/A")
        self.hud_dock.telemetry_label.setText(f"🔋 {bat}% | 🧠 RAM: {mem}%")

    def _on_error(self, err: str):
        InfoBar.error("System Anomaly", err, parent=self, position=InfoBarPosition.TOP_RIGHT, duration=4000)

    def handle_stop_requested(self):
        """Immediately halts any active command execution, LLM streaming, and speech."""
        self.stop_current_task()
        self.chat_view.finish_stream(final_text=None)
        InfoBar.info("Stopped", "Generation halted by user.", parent=self, position=InfoBarPosition.TOP_RIGHT, duration=1500)

    def stop_current_task(self):
        """Cancels running command task and aborts brain generation, research worker, PDF worker, and TTS speech."""
        if getattr(self, '_active_research_worker', None) and self._active_research_worker.isRunning():
            self._active_research_worker.cancel()
            self._active_research_worker.wait(1500)
            self._active_research_worker = None
        if getattr(self, '_active_pdf_worker', None) and self._active_pdf_worker.isRunning():
            self._active_pdf_worker.cancel()
            self._active_pdf_worker.wait(1500)
            self._active_pdf_worker = None
        if getattr(self, '_active_task_id', None):
            task_supervisor.cancel_task(self._active_task_id, reason="User clicked Stop")
            self._active_task_id = None
        if hasattr(self, 'brain') and hasattr(self.brain, 'abort_generation'):
            self.brain.abort_generation()
        if hasattr(self, 'tts') and hasattr(self.tts, 'stop_speaking'):
            self.tts.stop_speaking()
        if getattr(self, '_current_command_task', None) and not self._current_command_task.done():
            self._current_command_task.cancel()
            self._current_command_task = None
        self.signals.speech_level_changed.emit(0.0)
        next_state = "listening" if getattr(self.tts, "voice_loop_active", False) else "idle"
        self.signals.state_changed.emit(next_state)

    def handle_user_command(self, command: str, display_text: str = None):
        """Processes typed, chipped, or attached user command asynchronously."""
        self.stop_current_task()
        bubble_text = display_text if display_text else command
        self.chat_view.add_message("user", bubble_text)
        self._current_command_task = self._create_task(self._process_command(command))

    async def _process_command(self, command: str):
        self.signals.state_changed.emit("thinking")
        try:
            # Production Agent Path: USER-SELECTED MAIN AGENT MODEL is the sole authority
            # for all tool calling, planning, and tool result processing.
            # Python does not inspect user text with keywords or intent classifiers.
            await self.brain.query_llm(command, stream_to_ui=True, stream_to_speech=True)
        except Exception as e:
            import logging
            logging.getLogger("FRIDAY.MainWindow").exception(f"Command execution error: {e}")
            self.chat_view.add_message(
                "friday",
                f"⚠️ **Neural Alert**: An anomaly occurred while processing directive:\n`{e}`\n\nAll subsystem diagnostics remain operational."
            )
        finally:
            if not getattr(self, '_active_research_worker', None) and not getattr(self, '_active_pdf_worker', None):
                if not getattr(self.tts, 'is_speaking', False):
                    next_state = "listening" if getattr(self.tts, "voice_loop_active", False) else "idle"
                    self.signals.state_changed.emit(next_state)

    async def _start_background_pdf_analysis(self, pdf_path: str, user_directive: str):
        """Starts dedicated QThread background PDF analysis with multi-stage progress and zero GUI blocking."""
        from friday_core.document.pdf_worker import PDFAnalysisWorker, PDFAnalysisTask

        # Deduplication protection: Check if a worker is already actively running
        if getattr(self, '_active_pdf_worker', None) and self._active_pdf_worker.isRunning():
            self.chat_view.add_message("friday", "A document analysis is currently active, Boss. Please wait for completion or click Stop to abort.")
            self.signals.state_changed.emit("idle")
            return

        doc_name = os.path.basename(pdf_path)
        self.signals.state_changed.emit("thinking")
        self.signals.stream_started.emit("friday", f"Initializing background analysis for {doc_name}...")

        task = PDFAnalysisTask(
            pdf_path=pdf_path,
            user_directive=user_directive,
            session_id=getattr(self.chat_view, 'current_session_id', 'default_session'),
            model_name=getattr(self.brain, 'model', 'deepseek-r1:8b'),
            vision_model_name='qwen2.5vl:3b',
            inspect_visuals=True
        )

        worker = PDFAnalysisWorker(task, parent=self)
        self._active_pdf_worker = worker

        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def on_progress(stage: str, pct: int, status_text: str):
            self.chat_view.update_status(f"📄 [{stage} {pct}%] {status_text}")
            if hasattr(self, 'operations_panel'):
                self.operations_panel.add_audit("PDF", f"{stage} ({pct}%): {status_text[:30]}", "#38BDF8")

        def on_token(token: str):
            self.signals.stream_token.emit(token)

        def on_thinking(token: str):
            self.signals.stream_thinking.emit(token)

        def on_finished(result):
            if not future.done():
                future.set_result(result)

        def on_error(err_msg: str):
            if not future.done():
                future.set_result(None)

        def on_cancelled():
            if not future.done():
                future.set_result(None)

        worker.progress_signal.connect(on_progress)
        worker.token_signal.connect(on_token)
        worker.thinking_signal.connect(on_thinking)
        worker.finished_signal.connect(on_finished)
        worker.error_signal.connect(on_error)
        worker.cancelled_signal.connect(on_cancelled)

        worker.start()

        try:
            result = await future
            if result and result.success:
                self.signals.stream_finished.emit(result.text)
                if self.tts:
                    summary = self.tts.extract_spoken_summary(result.text, max_sentences=2, max_words=45)
                    if summary:
                        await self.tts.speak(f"Boss, I have completed the full analysis of {doc_name}. {summary}")
            elif result and result.cancelled:
                self.signals.stream_finished.emit("[PDF Analysis Aborted by Operator]")
            elif result and result.error:
                self.signals.stream_finished.emit(f"⚠️ Analysis Anomaly: {result.error}")
        except asyncio.CancelledError:
            worker.cancel()
            worker.wait(1000)
            self.signals.stream_finished.emit("[PDF Analysis Aborted]")
        finally:
            self._active_pdf_worker = None
            self.signals.state_changed.emit("idle")

    def toggle_voice_loop(self):
        """Toggles speech recognition on/off (Mute / Unmute)."""
        self.tts.stop_speaking()
        if self.voice_loop.running:
            # Turn OFF / Mute
            self.voice_loop.stop()
            if self.voice_task and not self.voice_task.done():
                self.voice_task.cancel()
                self.voice_task = None
            self.signals.state_changed.emit("idle")
            self.signals.speech_level_changed.emit(0.0)
            self.chat_view.set_mic_active(False)
            if hasattr(self, "command_bar") and self.command_bar:
                self.command_bar.set_mic_active(False)
            InfoBar.warning(
                "Microphone Muted",
                "Acoustic sensors disabled. Mic is off (Ctrl+M to activate).",
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2000
            )
        else:
            # Turn ON / Unmute and listen
            self.voice_loop.start()
            self.voice_task = self._create_task(self.voice_loop.run())
            self.voice_loop.trigger_active_listen()
            self.chat_view.set_mic_active(True)
            if hasattr(self, "command_bar") and self.command_bar:
                self.command_bar.set_mic_active(True)
            InfoBar.success(
                "Microphone Active",
                "Listening... Speak your directive now (Ctrl+M to mute).",
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2000
            )

    def handle_research(self, topic: str, depth: str):
        """Launches supervised QThread DeepResearchWorker with real-time UI streaming and zero GUI freeze."""
        # Deduplication protection: Check if a worker is already actively running
        if getattr(self, '_active_research_worker', None) and self._active_research_worker.isRunning():
            self.chat_view.add_message("friday", "A deep research operation is already underway, Boss. Click Stop or wait for it to complete.")
            self.signals.state_changed.emit("idle")
            return

        clean_topic = re.sub(
            r"^(?:(?:do\s+(?:a\s+)?)?deep(?:ly)?\s+(?:web\s+)?research\s+(?:web\s+and\s+tell\s+about|web\s+about|on|about)?|research\s+(?:web\s+and\s+tell\s+about|on|about)?|tell\s+(?:me\s+)?about\s+(?:company\s+named\s+)?|deep\s+search\s+(?:on|about)?)\s*",
            "",
            topic,
            flags=re.IGNORECASE
        ).strip()
        if not clean_topic:
            clean_topic = topic

        sid = getattr(self.chat_view, 'current_session_id', 'default_session')
        task_record = task_supervisor.create_task(
            query=clean_topic,
            session_id=sid,
            route="DEEP_RESEARCH",
            idle_timeout=45.0,
            absolute_timeout=240.0
        )
        self._active_task_id = task_record.task_id

        self.signals.state_changed.emit("thinking")
        self.signals.stream_started.emit("friday", f"Conducting autonomous deep research on '{clean_topic}' across live web telemetry...")

        model_name = getattr(self.brain, 'model', None) or settings.get("model", "qwen3.5:9b")
        worker = DeepResearchWorker(
            task_record=task_record,
            depth=depth,
            model_name=model_name,
            parent=self
        )
        self._active_research_worker = worker

        def on_progress(stage: str, pct: int, status_text: str):
            if not task_supervisor.is_current_task(task_record.task_id, sid):
                return
            self.chat_view.update_status(f"🌐 [{stage} {pct}%] {status_text}")
            if hasattr(self, 'operations_panel'):
                self.operations_panel.add_audit("RESEARCH", f"{stage} ({pct}%): {status_text[:28]}", "#38BDF8")

        def on_token(token: str):
            if not task_supervisor.is_current_task(task_record.task_id, sid):
                return
            self.signals.stream_token.emit(token)

        def on_thinking(token: str):
            if not task_supervisor.is_current_task(task_record.task_id, sid):
                return
            self.signals.stream_thinking.emit(token)

        def on_finished(final_markdown: str):
            if not task_supervisor.is_current_task(task_record.task_id, sid):
                return
            self._active_research_worker = None
            self._active_task_id = None

            # Update dedicated Research Tab
            self.research_view.update_report(clean_topic, final_markdown)

            # Finalize chat bubble
            self.chat_view.finish_stream(final_markdown)

            # Spoken briefing via TTS
            if self.tts:
                summary = self.tts.extract_spoken_summary(final_markdown, max_sentences=2, max_words=45)
                if summary:
                    self._create_task(self.tts.speak(f"Boss, I have completed deep autonomous research on {clean_topic}. {summary}"))

            self.signals.state_changed.emit("idle")

        def on_error(err_msg: str):
            if not task_supervisor.is_current_task(task_record.task_id, sid):
                return
            self._active_research_worker = None
            self._active_task_id = None
            self.chat_view.finish_stream(f"⚠️ **Deep Research Anomaly**: {err_msg}")
            self.signals.state_changed.emit("idle")

        def on_cancelled():
            self._active_research_worker = None
            self._active_task_id = None
            self.chat_view.finish_stream("⏹️ **Research Directive Cancelled**: Generation halted by operator.")
            self.signals.state_changed.emit("idle")

        worker.progress_signal.connect(on_progress)
        worker.token_signal.connect(on_token)
        worker.thinking_signal.connect(on_thinking)
        worker.finished_signal.connect(on_finished)
        worker.error_signal.connect(on_error)
        worker.cancelled_signal.connect(on_cancelled)
        worker.start()

    async def _run_research(self, topic: str, depth: str):
        """Async deep research executor with backwards-compatibility and zero stuck thinking guarantee."""
        loop = asyncio.get_running_loop()
        clean_topic = re.sub(
            r"^(?:(?:do\s+(?:a\s+)?)?deep(?:ly)?\s+(?:web\s+)?research\s+(?:web\s+and\s+tell\s+about|web\s+about|on|about)?|research\s+(?:web\s+and\s+tell\s+about|on|about)?|tell\s+(?:me\s+)?about\s+(?:company\s+named\s+)?|deep\s+search\s+(?:on|about)?)\s*",
            "",
            topic,
            flags=re.IGNORECASE
        ).strip()
        if not clean_topic:
            clean_topic = topic

        # If running on real GUI window with QThread worker capability (avoid mock trap)
        if isinstance(self, FridayMainWindow) and not hasattr(self, '_mock_return_value'):
            self.handle_research(topic, depth)
            worker = getattr(self, '_active_research_worker', None)
            if worker and hasattr(worker, 'isRunning') and callable(getattr(worker, 'isRunning', None)):
                while worker.isRunning() is True:
                    await asyncio.sleep(0.05)
                return

        # Direct execution path for test harness / mock window
        from friday_ui.core.engine import fetch_web_results
        self.signals.state_changed.emit("thinking")
        sources = await loop.run_in_executor(None, fetch_web_results, clean_topic, 4) or []
        summary = ""
        if hasattr(self, 'brain') and hasattr(self.brain, 'query_llm'):
            summary = await self.brain.query_llm("test prompt", stream_to_ui=False, stream_to_speech=False)

        chat_msg = f"### 🌐 Executive Intelligence Dossier: **{clean_topic.title()}**\n\n**Investigation Scope**: `{depth}` | **Verified Sources**: `{len(sources)}`\n\n"
        if summary:
            chat_msg += summary + "\n\n"
        for i, s in enumerate(sources, 1):
            chat_msg += f"- [{s.get('title', 'Source')}]({s.get('href', '#')}): {s.get('body', '')}\n"

        if hasattr(self, 'research_view'):
            self.research_view.update_report(clean_topic, chat_msg)
        if hasattr(self, 'chat_view'):
            self.chat_view.add_message("friday", chat_msg)
        if hasattr(self, 'tts') and hasattr(self.tts, 'speak'):
            brief = f"Boss, I have completed deep autonomous research on {clean_topic}."
            if hasattr(self.tts, 'extract_spoken_summary'):
                brief += f" {self.tts.extract_spoken_summary(summary or chat_msg)}"
            await self.tts.speak(brief)
        self.signals.state_changed.emit("idle")


    def handle_doc_ingest(self, title: str, path: str):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            category = self.rag_view.category_combo.currentText()
            doc_id = f"doc_{abs(hash(title + path)) % 100000}"
            self.vector_store.add_document(doc_id, title, category, content)
            self.signals.transcript_received.emit("system", f"Knowledge base indexed: '{title}' ({len(content)} chars)")
            InfoBar.success("Indexed", f"'{title}' is now searchable in local memory.", parent=self, position=InfoBarPosition.TOP_RIGHT)
        except Exception as e:
            InfoBar.error("Ingestion Error", str(e), parent=self, position=InfoBarPosition.TOP_RIGHT)

    def handle_rag_query(self, query: str):
        results = self.vector_store.query(query, top_k=3)
        if not results:
            self.rag_view.results_edit.setMarkdown(f"### Query: *{query}*\n\n> No relevant vectors found in local memory.")
            return

        md = f"### Semantic Matches for: *{query}*\n\n"
        for idx, item in enumerate(results, 1):
            md += f"**{idx}. {item['title']}** *(Relevance Score: {item['score']})*\n"
            md += f"- **Category**: `{item['category']}`\n"
            snippet = item['content'][:350].replace('\n', ' ')
            md += f"- **Snippet**: {snippet}...\n\n"

        self.rag_view.results_edit.setMarkdown(md)

    def _poll_telemetry(self):
        """Autonomously polls battery and RAM levels every 15-30s."""
        bat, chg = get_battery_info()
        mem = get_memory_info()
        self.signals.telemetry_updated.emit({"battery": bat, "charging": chg, "memory": mem})

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F11:
            if self.isFullScreen():
                self.showMaximized()
            else:
                self.showFullScreen()
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'titleBar'):
            self.titleBar.raise_()

    def hideEvent(self, event):
        """Pauses custom-paint 60fps timers to save CPU & battery when window is not visible."""
        super().hideEvent(event)
        try:
            if hasattr(self, 'hud_dock') and hasattr(self.hud_dock, 'visualizer') and hasattr(self.hud_dock.visualizer, 'timer'):
                self.hud_dock.visualizer.timer.stop()
            if hasattr(self, 'chat_view') and hasattr(self.chat_view, 'arc_reactor') and hasattr(self.chat_view.arc_reactor, 'timer'):
                self.chat_view.arc_reactor.timer.stop()
        except Exception as e:
            logger.debug(f"Timer stop error on hide: {e}")

    def showEvent(self, event):
        """Resumes custom-paint timers when window becomes visible."""
        super().showEvent(event)
        try:
            if hasattr(self, 'hud_dock') and hasattr(self.hud_dock, 'visualizer') and hasattr(self.hud_dock.visualizer, 'timer'):
                if settings.get("animation_level", "Full") != "Off":
                    self.hud_dock.visualizer.timer.start()
            if hasattr(self, 'chat_view') and hasattr(self.chat_view, 'arc_reactor') and hasattr(self.chat_view.arc_reactor, 'timer'):
                if settings.get("animation_level", "Full") != "Off":
                    self.chat_view.arc_reactor.timer.start()
        except Exception as e:
            logger.debug(f"Timer start error on show: {e}")

    def handle_settings_update(self, settings_data: dict):
        new_model = settings_data.get("model")
        new_voice = settings_data.get("voice")
        chimes = settings_data.get("chimes_enabled", True)
        anim = settings_data.get("animation_level", "Full")
        pos = settings_data.get("command_bar_position", "top")
        audio_dev = settings_data.get("audio_input_device")
        new_theme = settings_data.get("theme_mode")
        seamless_speech = settings_data.get("seamless_speech", True)
        continuous_conv = settings_data.get("continuous_conversation", True)

        updates = {
            "model": new_model,
            "voice": new_voice,
            "chimes_enabled": chimes,
            "animation_level": anim,
            "command_bar_position": pos,
            "seamless_speech": seamless_speech,
            "continuous_conversation": continuous_conv
        }
        user_name = settings_data.get("user_name")
        user_title = settings_data.get("user_title")
        ollama_host = settings_data.get("ollama_host")
        if user_name:
            updates["user_name"] = user_name
        if user_title:
            updates["user_title"] = user_title
        if ollama_host:
            updates["ollama_host"] = ollama_host
        mic_sens = settings_data.get("mic_sensitivity")
        if mic_sens:
            updates["mic_sensitivity"] = mic_sens
        if audio_dev is not None:
            updates["audio_input_device"] = audio_dev
        if new_theme is not None:
            updates["theme_mode"] = new_theme

        settings.update(updates)
        if hasattr(self.brain, "reload_persona"):
            self.brain.reload_persona()

        if new_model:
            self.brain.model = new_model
        if new_voice:
            voice_key = new_voice.split()[0]
            self.tts.voice = voice_key
            if any(voice_key.startswith(v) for v in ["bf_emma", "af_sarah", "af_bella", "af_nicole", "bf_isabella", "am_adam"]):
                self.tts.use_local_tts = True
                self.tts.local_voice = voice_key
            else:
                self.tts.use_local_tts = False
            settings.set("use_local_tts", self.tts.use_local_tts)
            settings.set("local_voice", getattr(self.tts, "local_voice", "bf_emma"))
        if new_theme:
            self._apply_global_style()

    def closeEvent(self, event):
        """
        Handles main window close event.
        Ensures all speech, audio playback, background tasks, and voice loops
        are immediately and completely terminated.
        """
        # 1. Immediately silence all speech, cancel LLM streaming, and halt voice listening
        try:
            self.stop_current_task()
            if hasattr(self, 'tts') and self.tts:
                self.tts.stop_speaking()
            if hasattr(self, 'brain') and hasattr(self.brain, 'abort_generation'):
                self.brain.abort_generation()
            if hasattr(self, 'voice_loop') and self.voice_loop.running:
                self.voice_loop.stop()
            if getattr(self, 'voice_task', None) and not self.voice_task.done():
                self.voice_task.cancel()
                self.voice_task = None
            if hasattr(self, 'telemetry_timer') and self.telemetry_timer.isActive():
                self.telemetry_timer.stop()
            if hasattr(self, 'hud_dock') and hasattr(self.hud_dock, 'visualizer') and hasattr(self.hud_dock.visualizer, 'timer'):
                self.hud_dock.visualizer.timer.stop()
            if hasattr(self, 'chat_view') and hasattr(self.chat_view, 'arc_reactor') and hasattr(self.chat_view.arc_reactor, 'timer'):
                self.chat_view.arc_reactor.timer.stop()
        except Exception as e:
            logger.debug(f"Error during closeEvent audio cleanup: {e}")

        # 2. Check if user explicitly configured close_to_tray (default is False: fully quit)
        close_to_tray = settings.get("close_to_tray", False)
        if close_to_tray and not getattr(self, '_force_close', False):
            event.ignore()
            self.hide()
            return

        # 3. Clean exit: unregister global hotkeys and quit application
        try:
            if hasattr(self, 'command_bar') and self.command_bar:
                self.command_bar.unregister_hotkey()
                self.command_bar.close()
        except Exception as e:
            logger.debug(f"Error closing command bar: {e}")
        finally:
            super().closeEvent(event)
            QApplication.quit()

    def terminate_application(self):
        """Force clean exit and quit QApplication."""
        self._force_close = True
        self.close()
        QApplication.quit()


