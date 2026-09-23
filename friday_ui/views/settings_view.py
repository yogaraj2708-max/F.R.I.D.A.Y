"""
F.R.I.D.A.Y. 2.0 - Tactical Settings & Hardware View
Controls owner profile, active LLM, dynamic model pulling, TTS voice parameters, animation levels, and system parameters.
"""

import logging
import ollama
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea
)
from qfluentwidgets import (
    ComboBox, SwitchButton, PrimaryPushButton, PushButton, LineEdit,
    CardWidget, InfoBar, InfoBarPosition
)

from friday_core.settings import settings, get_default_owner_name

logger = logging.getLogger("FRIDAY.SettingsView")


class ModelPullWorker(QThread):
    """Background worker for pulling Ollama models asynchronously with progress feedback."""
    progress_signal = Signal(str)
    completed_signal = Signal(bool, str)

    def __init__(self, model_name: str, host: str):
        super().__init__()
        self.model_name = model_name
        self.host = host

    def run(self):
        try:
            client = ollama.Client(host=self.host)
            for status in client.pull(self.model_name, stream=True):
                stat = status.get("status", "")
                completed = status.get("completed", 0)
                total = status.get("total", 0)
                if total > 0:
                    pct = int(completed / total * 100)
                    self.progress_signal.emit(f"{stat} ({pct}%)")
                else:
                    self.progress_signal.emit(stat or "Downloading...")
            self.completed_signal.emit(True, f"Model '{self.model_name}' installed successfully!")
        except Exception as e:
            self.completed_signal.emit(False, str(e))


class SettingsView(QWidget):
    """
    Hardware, Model Routing, Owner Identity & Security Settings.
    Controls active LLM, TTS voice parameters, animation performance, and security posture.
    """
    settings_saved = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pull_worker = None
        self._init_ui()

    def _init_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(20)

        # Header Title
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel("TACTICAL PREFERENCES & HARDWARE")
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title.setStyleSheet("color: #00F0FF; letter-spacing: 1px;")

        subtitle = QLabel("Configure owner identity, local neural models, speech acoustics, power/animation scaling, and security controls")
        subtitle.setFont(QFont("Segoe UI", 9))
        subtitle.setStyleSheet("color: #9CA3AF;")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        layout.addLayout(title_box)

        # 0. Owner Profile & Identity Card
        owner_card = CardWidget(content_widget)
        owner_layout = QVBoxLayout(owner_card)
        owner_layout.setContentsMargins(16, 16, 16, 16)
        owner_layout.setSpacing(12)

        owner_header = QLabel("Owner Profile & Identity")
        owner_header.setFont(QFont("Segoe UI", 11, QFont.Bold))
        owner_header.setStyleSheet("color: #FFFFFF;")
        owner_layout.addWidget(owner_header)

        # Owner Name Row
        name_row = QHBoxLayout()
        name_label = QLabel("Owner Name:")
        name_label.setFixedWidth(140)
        self.owner_name_input = LineEdit(owner_card)
        self.owner_name_input.setPlaceholderText("Enter your name (e.g. Alphin, Renit, Yogi)...")
        self.owner_name_input.setText(settings.get("user_name", get_default_owner_name()))
        name_row.addWidget(name_label)
        name_row.addWidget(self.owner_name_input)
        owner_layout.addLayout(name_row)

        # Preferred Title / Call-Sign Row
        title_row = QHBoxLayout()
        title_label = QLabel("Call-Sign / Title:")
        title_label.setFixedWidth(140)
        self.title_combo = ComboBox(owner_card)
        self.title_combo.addItems(["Boss", "Sir", "Ma'am", "Commander", "Doctor", "Friend", "None"])
        self.title_combo.setFixedWidth(200)
        saved_title = settings.get("user_title", "Boss")
        idx_t = self.title_combo.findText(saved_title)
        if idx_t >= 0:
            self.title_combo.setCurrentIndex(idx_t)
        title_row.addWidget(title_label)
        title_row.addWidget(self.title_combo)
        title_row.addStretch(1)
        owner_layout.addLayout(title_row)

        layout.addWidget(owner_card)

        # 1. Neural LLM Core Selection & Model Manager
        llm_card = CardWidget(content_widget)
        llm_layout = QVBoxLayout(llm_card)
        llm_layout.setContentsMargins(16, 16, 16, 16)
        llm_layout.setSpacing(12)

        llm_header = QLabel("Neural Intelligence Core (Ollama)")
        llm_header.setFont(QFont("Segoe UI", 11, QFont.Bold))
        llm_header.setStyleSheet("color: #FFFFFF;")
        llm_layout.addWidget(llm_header)

        # Active Model Row
        llm_row = QHBoxLayout()
        llm_label = QLabel("Active LLM Model:")
        llm_label.setFixedWidth(140)
        self.model_combo = ComboBox(llm_card)
        self.model_combo.setFixedWidth(280)
        self._populate_models()
        self.refresh_models_btn = PushButton("Refresh Models", llm_card)
        self.refresh_models_btn.clicked.connect(self._on_refresh_models_clicked)
        llm_row.addWidget(llm_label)
        llm_row.addWidget(self.model_combo)
        llm_row.addWidget(self.refresh_models_btn)
        llm_row.addStretch(1)
        llm_layout.addLayout(llm_row)

        # Add Custom Model Row
        custom_row = QHBoxLayout()
        custom_label = QLabel("Add / Pull Model:")
        custom_label.setFixedWidth(140)
        self.new_model_input = LineEdit(llm_card)
        self.new_model_input.setPlaceholderText("e.g. llama3.2:1b, mistral:7b, qwen2.5:3b...")
        self.add_custom_btn = PushButton("Add Model", llm_card)
        self.add_custom_btn.clicked.connect(self._on_add_custom_model)
        self.pull_btn = PrimaryPushButton("Pull via Ollama", llm_card)
        self.pull_btn.clicked.connect(self._on_pull_model)
        custom_row.addWidget(custom_label)
        custom_row.addWidget(self.new_model_input)
        custom_row.addWidget(self.add_custom_btn)
        custom_row.addWidget(self.pull_btn)
        llm_layout.addLayout(custom_row)

        # Pull Progress / Status Label
        self.pull_status_label = QLabel("")
        self.pull_status_label.setFont(QFont("Segoe UI", 9))
        self.pull_status_label.setStyleSheet("color: #00F0FF; font-family: monospace;")
        self.pull_status_label.setVisible(False)
        llm_layout.addWidget(self.pull_status_label)

        # Ollama Server Host URL Row
        host_row = QHBoxLayout()
        host_label = QLabel("Ollama Host URL:")
        host_label.setFixedWidth(140)
        self.ollama_host_input = LineEdit(llm_card)
        self.ollama_host_input.setText(settings.get("ollama_host", "http://localhost:11434"))
        host_row.addWidget(host_label)
        host_row.addWidget(self.ollama_host_input)
        llm_layout.addLayout(host_row)

        # Semantic Intent Router (System 1 Fast Dispatch)
        router_row = QHBoxLayout()
        router_label = QLabel("Semantic Intent Router (System 1 Fast Dispatch):")
        self.semantic_router_switch = SwitchButton(self)
        self.semantic_router_switch.setChecked(settings.get("semantic_routing", True))
        router_row.addWidget(router_label)
        router_row.addWidget(self.semantic_router_switch)
        router_row.addStretch(1)
        llm_layout.addLayout(router_row)

        # Decision Maker Engine Selector
        engine_row = QHBoxLayout()
        engine_label = QLabel("Decision Maker Engine:")
        self.decision_engine_combo = ComboBox(self)
        self.decision_engine_combo.addItem("Ollama (friday-decider, 397MB, ~60ms)", "ollama")
        self.decision_engine_combo.addItem("Laya (Convai System 1, ModernBERT, ~33ms)", "laya")
        self.decision_engine_combo.addItem("Local Vector Only (Sub-2ms, Ultra-Light)", "vector")
        self.decision_engine_combo.setFixedWidth(340)

        saved_engine = settings.get("decision_engine", "ollama")
        for i in range(self.decision_engine_combo.count()):
            if self.decision_engine_combo.itemData(i) == saved_engine:
                self.decision_engine_combo.setCurrentIndex(i)
                break

        engine_row.addWidget(engine_label)
        engine_row.addWidget(self.decision_engine_combo)
        engine_row.addStretch(1)
        llm_layout.addLayout(engine_row)

        layout.addWidget(llm_card)

        # 2. Voice & Speech Acoustics
        voice_card = CardWidget(content_widget)
        voice_layout = QVBoxLayout(voice_card)
        voice_layout.setContentsMargins(16, 16, 16, 16)
        voice_layout.setSpacing(10)

        voice_header = QLabel("Neural Text-To-Speech (TTS)")
        voice_header.setFont(QFont("Segoe UI", 11, QFont.Bold))
        voice_header.setStyleSheet("color: #FFFFFF;")
        voice_layout.addWidget(voice_header)

        voice_row = QHBoxLayout()
        voice_row.addWidget(QLabel("Voice Persona:"))
        self.voice_combo = ComboBox(self)
        self.voice_combo.addItems([
            "bf_emma (Local Offline / British F.R.I.D.A.Y.)",
            "af_sarah (Local Offline / American Female)",
            "af_bella (Local Offline / Warm American)",
            "en-US-AriaNeural (Clear Studio / Microsoft Flagship)",
            "en-IE-EmilyNeural (Kerry Condon / F.R.I.D.A.Y.)",
            "en-GB-SoniaNeural (British Tactical)",
            "en-US-JennyNeural (Natural Conversational)",
            "en-IN-NeerjaNeural (Indian English)",
            "Microsoft Zira Desktop (Offline SAPI)"
        ])
        self.voice_combo.setFixedWidth(360)
        saved_voice = settings.get("voice", "bf_emma")
        for i in range(self.voice_combo.count()):
            if saved_voice in self.voice_combo.itemText(i):
                self.voice_combo.setCurrentIndex(i)
                break
        voice_row.addWidget(self.voice_combo)
        voice_row.addStretch(1)
        voice_layout.addLayout(voice_row)

        layout.addWidget(voice_card)

        # 3. Hardware Audio Input Device
        audio_card = CardWidget(content_widget)
        audio_layout = QVBoxLayout(audio_card)
        audio_layout.setContentsMargins(16, 16, 16, 16)
        audio_layout.setSpacing(10)

        audio_header = QLabel("Hardware Input Microphone")
        audio_header.setFont(QFont("Segoe UI", 11, QFont.Bold))
        audio_header.setStyleSheet("color: #FFFFFF;")
        audio_layout.addWidget(audio_header)

        audio_row = QHBoxLayout()
        audio_row.addWidget(QLabel("Select Input Device:"))
        self.mic_combo = ComboBox(self)
        self.mic_combo.setFixedWidth(360)
        self._populate_audio_devices()
        audio_row.addWidget(self.mic_combo)
        audio_row.addStretch(1)
        audio_layout.addLayout(audio_row)

        sens_row = QHBoxLayout()
        sens_row.addWidget(QLabel("Microphone Sensitivity:"))
        self.sens_combo = ComboBox(self)
        self.sens_combo.addItem("High (Laptop Built-in Mic / Quiet Voice) - Recommended", userData="high")
        self.sens_combo.addItem("Normal (Standard Headset)", userData="normal")
        self.sens_combo.addItem("Low (Noisy Background)", userData="low")
        self.sens_combo.setFixedWidth(360)
        curr_sens = settings.get("mic_sensitivity", "high")
        for i in range(self.sens_combo.count()):
            if self.sens_combo.itemData(i) == curr_sens:
                self.sens_combo.setCurrentIndex(i)
                break
        sens_row.addWidget(self.sens_combo)
        sens_row.addStretch(1)
        audio_layout.addLayout(sens_row)

        layout.addWidget(audio_card)

        # 4. HUD Personalization & Appearance
        ui_card = CardWidget(content_widget)
        ui_layout = QVBoxLayout(ui_card)
        ui_layout.setContentsMargins(16, 16, 16, 16)
        ui_layout.setSpacing(10)

        ui_header = QLabel("HUD Personalization & Appearance")
        ui_header.setFont(QFont("Segoe UI", 11, QFont.Bold))
        ui_header.setStyleSheet("color: #FFFFFF;")
        ui_layout.addWidget(ui_header)

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Visual Theme:"))
        self.theme_combo = ComboBox(self)
        self.theme_combo.addItem("Warm Editorial Cream (60-30-10 Light)", userData="warm_light")
        self.theme_combo.addItem("Warm Espresso Obsidian (60-30-10 Dark)", userData="warm_dark")
        self.theme_combo.addItem("Midnight Void (Pure Dark OLED)", userData="dark")
        self.theme_combo.addItem("Stark Tactical Cyan (Military HUD)", userData="tactical")
        self.theme_combo.addItem("Deep Space Purple (Neon Tech)", userData="neon")
        self.theme_combo.setFixedWidth(320)
        saved_theme = settings.get("theme_mode", "warm_light")
        for i in range(self.theme_combo.count()):
            if self.theme_combo.itemData(i) == saved_theme:
                self.theme_combo.setCurrentIndex(i)
                break
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch(1)
        ui_layout.addLayout(theme_row)

        chimes_row = QHBoxLayout()
        chimes_row.addWidget(QLabel("Stark Auditory Feedback Chimes:"))
        self.chimes_switch = SwitchButton(self)
        self.chimes_switch.setChecked(settings.get("chimes_enabled", True))
        chimes_row.addWidget(self.chimes_switch)
        chimes_row.addStretch(1)
        ui_layout.addLayout(chimes_row)

        auto_voice_row = QHBoxLayout()
        auto_voice_row.addWidget(QLabel("Auto-Start Voice Loop on Launch:"))
        self.auto_voice_switch = SwitchButton(self)
        self.auto_voice_switch.setChecked(settings.get("auto_start_voice_loop", True))
        auto_voice_row.addWidget(self.auto_voice_switch)
        auto_voice_row.addStretch(1)
        ui_layout.addLayout(auto_voice_row)

        seamless_row = QHBoxLayout()
        seamless_row.addWidget(QLabel("Seamless High-Fidelity Speech (Unbroken audio playback):"))
        self.seamless_switch = SwitchButton(self)
        self.seamless_switch.setChecked(settings.get("seamless_speech", True))
        seamless_row.addWidget(self.seamless_switch)
        seamless_row.addStretch(1)
        ui_layout.addLayout(seamless_row)

        conv_row = QHBoxLayout()
        conv_row.addWidget(QLabel("Continuous Conversation Mode (Listen automatically after responses):"))
        self.conv_switch = SwitchButton(self)
        self.conv_switch.setChecked(settings.get("continuous_conversation", True))
        conv_row.addWidget(self.conv_switch)
        conv_row.addStretch(1)
        ui_layout.addLayout(conv_row)

        full_speech_row = QHBoxLayout()
        full_speech_row.addWidget(QLabel("Speak Complete Responses (Deliver full spoken answers without cutting off):"))
        self.full_speech_switch = SwitchButton(self)
        self.full_speech_switch.setChecked(settings.get("speak_full_response", True))
        full_speech_row.addWidget(self.full_speech_switch)
        full_speech_row.addStretch(1)
        ui_layout.addLayout(full_speech_row)


        anim_row = QHBoxLayout()
        anim_row.addWidget(QLabel("Particle & Visualizer Performance:"))
        self.anim_combo = ComboBox(self)
        self.anim_combo.addItems(["Full (60 FPS GPU)", "Reduced (30 FPS Power Saving)", "Off (Static HUD)"])
        self.anim_combo.setFixedWidth(240)
        saved_anim = settings.get("animation_level", "Full")
        for i in range(self.anim_combo.count()):
            if saved_anim in self.anim_combo.itemText(i):
                self.anim_combo.setCurrentIndex(i)
                break
        anim_row.addWidget(self.anim_combo)
        anim_row.addStretch(1)
        ui_layout.addLayout(anim_row)

        pos_row = QHBoxLayout()
        pos_row.addWidget(QLabel("Floating Command Bar Dock Position:"))
        self.pos_combo = ComboBox(self)
        self.pos_combo.addItems(["Top Edge", "Bottom Edge", "Last Remembered Position"])
        self.pos_combo.setFixedWidth(240)
        saved_pos = settings.get("command_bar_position", "top")
        pos_map = {"top": 0, "bottom": 1, "last": 2}
        self.pos_combo.setCurrentIndex(pos_map.get(saved_pos, 0))
        pos_row.addWidget(self.pos_combo)
        pos_row.addStretch(1)
        ui_layout.addLayout(pos_row)

        layout.addWidget(ui_card)

        # 5. Security & Gatekeeper Telemetry
        sec_card = CardWidget(content_widget)
        sec_layout = QVBoxLayout(sec_card)
        sec_layout.setContentsMargins(16, 16, 16, 16)
        sec_layout.setSpacing(10)

        sec_header = QLabel("Security Gatekeeper Policy")
        sec_header.setFont(QFont("Segoe UI", 11, QFont.Bold))
        sec_header.setStyleSheet("color: #FFFFFF;")
        sec_layout.addWidget(sec_header)

        sec_desc = QLabel(
            "Controls autonomous action execution safety fences:\n"
            "• Tier 0: Read-only Telemetry & Diagnostics\n"
            "• Tier 1: Safe Autonomous Actions with Path Fencing (App Launching, Safe File Organization)\n"
            "• Tier 2: Destructive Actions (Process Termination, File Deletion) Requires Modal Confirmation\n"
            "• Tier 3: Critical Danger (Format Disk, Alter System Core) Strictly Blocked"
        )
        sec_desc.setFont(QFont("Segoe UI", 9))
        sec_desc.setStyleSheet("color: #71717A; line-height: 1.4;")
        sec_layout.addWidget(sec_desc)

        layout.addWidget(sec_card)

        # Save Button Bar
        save_bar = QHBoxLayout()
        save_bar.addStretch(1)
        self.save_btn = PrimaryPushButton("APPLY & SAVE SETTINGS", self)
        self.save_btn.setFixedHeight(36)
        self.save_btn.setStyleSheet("""
            PrimaryPushButton {
                background-color: #00F0FF;
                color: #000000;
                font-weight: bold;
                border-radius: 6px;
                padding-left: 20px;
                padding-right: 20px;
            }
            PrimaryPushButton:hover {
                background-color: #38F8FF;
            }
        """)
        self.save_btn.clicked.connect(self._save_settings)
        save_bar.addWidget(self.save_btn)
        layout.addLayout(save_bar)

        scroll.setWidget(content_widget)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def _populate_models(self):
        curr = settings.get("model")
        avail = settings.get_available_models()
        self.model_combo.clear()
        self.model_combo.addItems(avail)
        idx = self.model_combo.findText(curr)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        elif avail:
            self.model_combo.setCurrentIndex(0)

    def _on_refresh_models_clicked(self):
        self._populate_models()
        InfoBar.info(
            "Models Scanned",
            f"Discovered {self.model_combo.count()} available models from Ollama.",
            parent=self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2500
        )

    def _on_add_custom_model(self):
        model_name = self.new_model_input.text().strip()
        if not model_name:
            InfoBar.warning("Input Error", "Please enter a model name.", parent=self, position=InfoBarPosition.TOP_RIGHT)
            return
        settings.add_custom_model(model_name)
        self._populate_models()
        idx = self.model_combo.findText(model_name)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        self.new_model_input.clear()
        InfoBar.success("Model Added", f"Model '{model_name}' added to available models.", parent=self, position=InfoBarPosition.TOP_RIGHT)

    def _on_pull_model(self):
        model_name = self.new_model_input.text().strip()
        if not model_name:
            InfoBar.warning("Input Error", "Enter model name to pull (e.g. llama3.2:1b).", parent=self, position=InfoBarPosition.TOP_RIGHT)
            return
        host = self.ollama_host_input.text().strip() or "http://localhost:11434"
        self.pull_btn.setEnabled(False)
        self.pull_status_label.setVisible(True)
        self.pull_status_label.setText(f"Connecting to Ollama at {host}...")

        self._pull_worker = ModelPullWorker(model_name, host)
        self._pull_worker.progress_signal.connect(lambda msg: self.pull_status_label.setText(f"[Ollama]: {msg}"))
        self._pull_worker.completed_signal.connect(self._on_pull_finished)
        self._pull_worker.start()

    def _on_pull_finished(self, success: bool, message: str):
        self.pull_btn.setEnabled(True)
        if success:
            model_name = self.new_model_input.text().strip()
            settings.add_custom_model(model_name)
            self._populate_models()
            idx = self.model_combo.findText(model_name)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
            self.new_model_input.clear()
            self.pull_status_label.setText(f"✓ {message}")
            InfoBar.success("Ollama Download Complete", message, parent=self, position=InfoBarPosition.TOP_RIGHT)
        else:
            self.pull_status_label.setText(f"✗ Failed: {message}")
            InfoBar.error("Ollama Pull Error", message, parent=self, position=InfoBarPosition.TOP_RIGHT)

    def _populate_audio_devices(self):
        self.mic_combo.clear()
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            default_in = sd.default.device[0]
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    name = dev.get("name", f"Device {idx}")
                    is_def = " (System Default)" if idx == default_in else ""
                    self.mic_combo.addItem(f"{idx}: {name}{is_def}", userData=idx)
        except Exception as e:
            logger.debug(f"Audio devices query skipped: {e}")

        saved_dev = settings.get("audio_input_device")
        if saved_dev is not None:
            for i in range(self.mic_combo.count()):
                if self.mic_combo.itemData(i) == saved_dev:
                    self.mic_combo.setCurrentIndex(i)
                    break

    def _save_settings(self):
        anim_text = self.anim_combo.currentText().split(" ")[0]
        pos_text = "top"
        if "Bottom" in self.pos_combo.currentText():
            pos_text = "bottom"
        elif "Last" in self.pos_combo.currentText():
            pos_text = "last"

        user_name = self.owner_name_input.text().strip() or get_default_owner_name()
        user_title = self.title_combo.currentText()
        model_name = self.model_combo.currentText()
        ollama_host = self.ollama_host_input.text().strip() or "http://localhost:11434"

        data = {
            "user_name": user_name,
            "user_title": user_title,
            "model": model_name,
            "ollama_host": ollama_host,
            "voice": self.voice_combo.currentText().split(" ")[0],
            "audio_input_device": self.mic_combo.currentData(),
            "mic_sensitivity": self.sens_combo.currentData() or "high",
            "theme_mode": self.theme_combo.currentData() or "warm_light",
            "chimes_enabled": self.chimes_switch.isChecked(),
            "auto_start_voice_loop": self.auto_voice_switch.isChecked(),
            "seamless_speech": self.seamless_switch.isChecked(),
            "continuous_conversation": self.conv_switch.isChecked(),
            "speak_full_response": self.full_speech_switch.isChecked(),
            "semantic_routing": self.semantic_router_switch.isChecked(),
            "decision_engine": self.decision_engine_combo.currentData() or "ollama",
            "animation_level": anim_text,

            "command_bar_position": pos_text
        }
        settings.update(data)
        self.settings_saved.emit(data)
        InfoBar.success(
            "Settings Synchronized",
            f"F.R.I.D.A.Y. tactical parameters updated. Identity: {user_title} ({user_name}), Model: {model_name}",
            parent=self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000
        )
