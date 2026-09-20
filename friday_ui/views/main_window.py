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
from friday_ui.styles.themes import generate_global_qss, MONO_DARK, fade_in
from friday_core.gatekeeper.gatekeeper import gatekeeper
from friday_core.settings import settings
from friday_core.system import get_battery_info, get_memory_info


class HUDDockWidget(GlassPanel):
    """
    Bottom HUD status bar with integrated audio visualizer,
    acoustic status, and telemetry indicators. Renders as a
    sleek glassmorphic bar at the bottom of the main window.
    """
    def __init__(self, parent=None):
        super().__init__(
            parent=parent,
            bg_color="rgba(14, 14, 18, 0.75)",
            border_color="rgba(255, 255, 255, 0.08)",
            radius=0,
            enable_shadow=False
        )
        self.setObjectName("hudDock")
        self.setFixedHeight(46)
        self._phase = 0.0

        dock_layout = QHBoxLayout(self)
        dock_layout.setContentsMargins(18, 4, 18, 4)
        dock_layout.setSpacing(16)

        # ── Left: Single glanceable state readout chip (no duplicate "ACOUSTIC HUD" label) ──
        self.hud_state_label = QLabel("ACTIVE // STANDBY")
        self.hud_state_label.setObjectName("hudStateLabel")
        self.hud_state_label.setProperty("state", "standby")
        self.hud_state_label.setFont(QFont("Segoe UI", 8))
        self.hud_state_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        dock_layout.addWidget(self.hud_state_label)

        # ── Center: Audio Visualizer ──
        self.visualizer = AudioVisualizerWidget(self)
        self.visualizer.setFixedHeight(36)
        dock_layout.addWidget(self.visualizer, 1)

        # ── Stop Voice Button (Prominently visible across all views during active speech) ──
        self.stop_voice_btn = PushButton("■ Stop Voice", self)
        self.stop_voice_btn.setFixedSize(104, 28)
        self.stop_voice_btn.setCursor(Qt.PointingHandCursor)
        self.stop_voice_btn.setToolTip("Immediately stop vocal playback (Esc)")
        self.stop_voice_btn.setStyleSheet("""
            PushButton {
                background-color: #DC2626;
                border: 1px solid #EF4444;
                font-weight: bold;
                font-size: 11px;
                border-radius: 6px;
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
        self.stop_voice_btn.hide()
        dock_layout.addWidget(self.stop_voice_btn)

        # ── Right: Single glanceable Telemetry chip ──
        self.telemetry_label = QLabel("⚡ NOMINAL")
        self.telemetry_label.setObjectName("hudTelemetryLabel")
        self.telemetry_label.setProperty("variant", "nominal")
        self.telemetry_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.telemetry_label.setMinimumWidth(140)
        dock_layout.addWidget(self.telemetry_label)


class FridayMainWindow(FluentWindow):
    """
    Main Reactive Desktop Application for F.R.I.D.A.Y. 2.0.
    Full-width layout with HUD dock at the bottom.
    """
    def __init__(self):
        super().__init__()
        setTheme(Theme.DARK)

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

    def _on_global_escape_pressed(self):
        if getattr(self.tts, "is_speaking", False) or (getattr(self, '_current_command_task', None) and not self._current_command_task.done()):
            self.handle_stop_requested()

    def _create_task(self, coro):
        """Standard fire-and-forget task tracker to prevent premature garbage collection."""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def _init_window(self):
        self.setObjectName("FridayMainWindow")
        self.setWindowTitle("F.R.I.D.A.Y. 2.0 - Tactical Personal Assistant")
        self.resize(1200, 800)
        self.setMinimumSize(950, 650)
        self.setAttribute(Qt.WA_AcceptTouchEvents, False)
        self.setMicaEffectEnabled(True)
        try:
            from friday_ui.app import get_app_icon
            self.setWindowIcon(get_app_icon())
        except Exception:
            pass

        # Global Hotkey Ctrl+M for Microphone Mute / Unmute
        self.mic_shortcut = QShortcut(QKeySequence("Ctrl+M"), self)
        self.mic_shortcut.activated.connect(self.toggle_voice_loop)

        # Ctrl+Space is deliberately NOT bound here. FloatingCommandBar already
        # registers an OS-wide hotkey and its own local shortcut; binding it a
        # third time on the main window meant one keypress fired two toggles and
        # the bar appeared to do nothing while the app had focus.


    def _apply_global_style(self):
        """Apply Centralized Monochrome / Tactical Desktop Styling with transparent backing."""
        theme_mode = settings.get("theme_mode", "dark")
        # This used to append to the existing sheet. Every theme switch bolted on
        # another full copy, so the sheet kept growing and Qt re-parsed all of it
        # on each repaint -- the app got visibly slower the more you toggled.
        self.setStyleSheet(generate_global_qss(theme_mode) + """
            #FridayMainWindow, #content_container, #chat_view, #rag_view, #research_view, #settings_view, #workspace_container {
                background-color: transparent;
            }
            NavigationInterface {
                background-color: rgba(9, 9, 11, 0.85);
                border-right: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)

    def _init_sub_interfaces(self):
        # 1. Chat View (Default)
        self.chat_view = ChatView(self)
        self.chat_view.setObjectName("chat_view")
        self.addSubInterface(self.chat_view, FluentIcon.CHAT, "Tactical Chat")

        # 2. Knowledge Base (RAG)
        self.rag_view = RAGView(self)
        self.rag_view.setObjectName("rag_view")
        self.addSubInterface(self.rag_view, FluentIcon.FOLDER, "Knowledge Base")

        # 3. Autonomous Deep Research
        self.research_view = ResearchView(self)
        self.research_view.setObjectName("research_view")
        self.addSubInterface(self.research_view, FluentIcon.GLOBE, "Deep Research")

        # 4. Settings
        self.settings_view = SettingsView(self)
        self.settings_view.setObjectName("settings_view")
        self.addSubInterface(
            self.settings_view,
            FluentIcon.SETTING,
            "Settings",
            NavigationItemPosition.BOTTOM
        )
        if hasattr(self, 'stackedWidget'):
            self.stackedWidget.setAnimationEnabled(False)

    def _init_hud_dock(self):
        """
        Creates the bottom HUD dock and 3-pane workspace with OperationsPanel.
        """
        self.hud_dock = HUDDockWidget(self)
        self.operations_panel = OperationsPanel(self)

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
        self.operations_panel.quick_command_triggered.connect(self.handle_user_command)
        self.rag_view.document_ingested.connect(self.handle_doc_ingest)
        self.rag_view.query_requested.connect(self.handle_rag_query)
        self.research_view.research_requested.connect(self.handle_research)
        self.settings_view.settings_saved.connect(self.handle_settings_update)

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
        if st in ["listening", "standby"]:
            self.hud_dock.hud_state_label.setText("ACTIVE // LISTENING")
            self.hud_dock.hud_state_label.setProperty("state", "listening")
            self.hud_dock.visualizer.set_active(True)
            self.hud_dock.stop_voice_btn.hide()
        elif st == "idle":
            self.hud_dock.hud_state_label.setText("MUTED // OFFLINE")
            self.hud_dock.hud_state_label.setProperty("state", "idle")
            self.hud_dock.visualizer.set_active(False)
            self.hud_dock.stop_voice_btn.hide()
        elif st == "thinking":
            self.hud_dock.hud_state_label.setText("ACTIVE // THINKING")
            self.hud_dock.hud_state_label.setProperty("state", "thinking")
            self.hud_dock.visualizer.set_active(True)
            self.hud_dock.stop_voice_btn.hide()
        elif st == "speaking":
            self.hud_dock.hud_state_label.setText("ACTIVE // TRANSMITTING")
            self.hud_dock.hud_state_label.setProperty("state", "speaking")
            self.hud_dock.visualizer.set_active(True)
            self.hud_dock.stop_voice_btn.show()
        else:
            self.hud_dock.hud_state_label.setText(f"ACTIVE // {st.upper()}")
            self.hud_dock.hud_state_label.setProperty("state", "standby")
            self.hud_dock.visualizer.set_active(False)
            self.hud_dock.stop_voice_btn.hide()

        self.hud_dock.hud_state_label.style().unpolish(self.hud_dock.hud_state_label)
        self.hud_dock.hud_state_label.style().polish(self.hud_dock.hud_state_label)
        self.hud_dock.visualizer.set_state(st)

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
        """Cancels running command task and aborts brain generation and TTS speech."""
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
            # If an attached image is present, route to vision pipeline
            if "[Attached Image:" in command:
                img_match = re.search(r"\[Attached Image:\s*([^\]|]+)\s*\|\s*Path:\s*([^\]]+)\]", command)
                if img_match:
                    img_name = img_match.group(1).strip()
                    img_path = img_match.group(2).strip()
                    user_prompt = command
                    directive_split = command.split("Boss Directive:\n")
                    if len(directive_split) > 1:
                        user_prompt = directive_split[1].strip()
                    await self.brain.analyze_image_file(img_path, user_prompt, img_name)
                    return

            # If an attached document is present, route directly to LLM for in-depth analysis
            if "[Attached Document:" in command or "Boss Directive:" in command:
                await self.brain.query_llm(command, stream_to_ui=True, stream_to_speech=True)
                return

            # Check for Deep Web Research intent in direct chat
            research_match = (
                re.search(r"^(?:do\s+(?:a\s+)?)?deep\s+(?:web\s+)?research\s+(?:on|about|web\s+and\s+tell\s+about|web\s+about)?\s*(.+)$", command, re.IGNORECASE) or
                re.search(r"^(?:search\s+the\s+web\s+deeply\s+for|deeply\s+research\s+web\s+and\s+tell\s+about|deeply\s+research)\s+(.+)$", command, re.IGNORECASE)
            )
            if research_match:
                topic = research_match.group(1).strip()
                if topic:
                    await self._run_research(topic, "Deep Comprehensive")
                    return

            # 1. Smart Skills & Desktop Launching
            skill_res = await self.brain.execute_smart_skill(command)
            if skill_res:
                if skill_res != "__STREAMED__":
                    await self.tts.speak(skill_res)
            else:
                # 2. Check local vector knowledge base
                kb_results = await self.vector_store.query_async(command, top_k=1)
                kb_context = ""
                if kb_results and kb_results[0]["score"] > 0.12:
                    kb_context = f"\n[Relevant Local Knowledge: {kb_results[0]['content'][:300]}]"

                prompt_text = command + kb_context if kb_context else command
                # 3. Local Ollama LLM with real-time streaming to UI and speech
                await self.brain.query_llm(prompt_text, stream_to_ui=True, stream_to_speech=True)
        except Exception as e:
            import logging
            logging.getLogger("FRIDAY.MainWindow").exception(f"Command execution error: {e}")
            self.chat_view.add_message(
                "friday",
                f"⚠️ **Neural Alert**: An anomaly occurred while processing directive:\n`{e}`\n\nAll subsystem diagnostics remain operational."
            )
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
        self._create_task(self._run_research(topic, depth))

    async def _run_research(self, topic: str, depth: str):
        loop = asyncio.get_running_loop()
        num_results = 8 if "Deep" in depth else 4

        # Clean topic: remove prompt prefixes like "deep research web and tell about", etc.
        clean_topic = re.sub(
            r"^(?:(?:do\s+(?:a\s+)?)?deep\s+(?:web\s+)?research\s+(?:web\s+and\s+tell\s+about|web\s+about|on|about)?|research\s+(?:web\s+and\s+tell\s+about|on|about)?|tell\s+(?:me\s+)?about\s+(?:company\s+named\s+)?|deep\s+search\s+(?:on|about)?)\s*",
            "",
            topic,
            flags=re.IGNORECASE
        ).strip()
        if not clean_topic:
            clean_topic = topic

        self.signals.state_changed.emit("thinking")
        self.signals.stream_started.emit("friday", f"Conducting deep research on '{clean_topic}' across live web telemetry...")

        def fetch_ddg():
            from friday_ui.core.engine import fetch_web_results
            res = fetch_web_results(clean_topic, max_results=num_results)
            if not res and clean_topic != topic:
                res = fetch_web_results(topic, max_results=num_results)
            return res

        sources = await loop.run_in_executor(None, fetch_ddg)

        report_md = f"# Tactical Intelligence Report: {clean_topic.title()}\n\n"
        report_md += f"**Investigation Scope**: {depth} | **Timestamp**: Modernization Run 2026\n\n"
        report_md += "## Executive Synthesis\n\n"

        if sources:
            for i, s in enumerate(sources, 1):
                title = s.get("title", f"Source {i}")
                body = s.get("body", "No description available.")
                link = s.get("href", "#")
                report_md += f"### {i}. [{title}]({link})\n"
                report_md += f"{body}\n\n"
        else:
            report_md += "> No direct external sources were returned by web telemetry.\n\n"

        report_md += "## Strategic Conclusions\n\n"
        report_md += "- Multi-source correlation confirms active operational viability.\n"
        report_md += "- Telemetry synthesized for Boss.\n"

        # Update dedicated Research Tab
        self.research_view.update_report(clean_topic, report_md)

        # Synthesize in-chat Executive Summary
        executive_summary = ""
        if sources:
            try:
                synth_prompt = (
                    f"Boss requested deep research on: '{clean_topic}'.\n"
                    f"Here are the live multi-source web search findings:\n{report_md}\n\n"
                    "Provide a well-structured, professional Executive Intelligence Summary in Markdown. "
                    "Include:\n"
                    "1. Executive Overview (who/what it is, core operations, key facts)\n"
                    "2. Key Strategic Findings & Developments (bullet points with numbers/dates if available)\n"
                    "3. Strategic Takeaway for Boss.\n"
                    "Be direct, insightful, and authoritative. Do not include introductory conversational filler."
                )
                executive_summary = await self.brain.query_llm(synth_prompt, stream_to_ui=False, stream_to_speech=False)
            except Exception as e:
                import logging
                logging.getLogger("FRIDAY.MainWindow").debug(f"LLM synthesis error for research: {e}")

        # Construct comprehensive in-chat briefing message
        chat_msg = f"### 🌐 Executive Intelligence Dossier: **{clean_topic.title()}**\n\n"
        chat_msg += f"**Investigation Scope**: `{depth}` | **Verified Sources**: `{len(sources)}`\n\n"

        if executive_summary and executive_summary.strip():
            chat_msg += f"{executive_summary.strip()}\n\n"
        elif sources:
            chat_msg += "#### Key Intelligence Findings\n"
            for i, s in enumerate(sources[:4], 1):
                t = s.get("title", f"Source {i}")
                b = s.get("body", "")
                chat_msg += f"- **{t}**: {b}\n"
            chat_msg += "\n"
        else:
            chat_msg += "> No live telemetry was retrieved for this topic. Dossier initialized in the Research tab.\n\n"

        if sources:
            chat_msg += "#### 🔗 Primary Intelligence Sources\n"
            for i, s in enumerate(sources[:4], 1):
                t = s.get("title", f"Source {i}")
                h = s.get("href", "#")
                chat_msg += f"{i}. [{t}]({h})\n"
            chat_msg += "\n*Full unredacted dossier available in the Research tab.*"

        self.chat_view.add_message("friday", chat_msg)

        # Spoken briefing via TTS
        spoken_brief = f"Boss, I have completed deep research on {clean_topic}."
        if executive_summary:
            spoken_brief += f" {self.tts.extract_spoken_summary(executive_summary)}"
        elif sources:
            first_body = sources[0].get("body", "")
            if first_body:
                spoken_brief += f" {first_body[:150]}."
        await self.tts.speak(spoken_brief)

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


