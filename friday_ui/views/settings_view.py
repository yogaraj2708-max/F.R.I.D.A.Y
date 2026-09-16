"""
F.R.I.D.A.Y. 2.0 - Tactical Settings & Hardware View
Controls active LLM, TTS voice parameters, animation levels, and system parameters.
"""

import logging
import ollama
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

logger = logging.getLogger("FRIDAY.SettingsView")
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea
)
from qfluentwidgets import (
    ComboBox, SwitchButton, PrimaryPushButton, FluentIcon,
    CardWidget, InfoBar, InfoBarPosition
)

from friday_core.settings import settings

class SettingsView(QWidget):
    """
    Hardware, Model Routing & Security Settings.
    Controls active LLM, TTS voice parameters, animation performance, and security posture.
    """
    settings_saved = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
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

        subtitle = QLabel("Configure local neural models, speech acoustics, power/animation scaling, and security controls")
        subtitle.setFont(QFont("Segoe UI", 9))
        subtitle.setStyleSheet("color: #9CA3AF;")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        layout.addLayout(title_box)

        # 1. Neural LLM Core Selection
        llm_card = CardWidget(content_widget)
        llm_layout = QVBoxLayout(llm_card)
        llm_layout.setContentsMargins(16, 16, 16, 16)
        llm_layout.setSpacing(10)

        llm_header = QLabel("Neural Intelligence Core (Ollama)")
        llm_header.setFont(QFont("Segoe UI", 11, QFont.Bold))
        llm_header.setStyleSheet("color: #FFFFFF;")
        llm_layout.addWidget(llm_header)

        llm_row = QHBoxLayout()
        llm_row.addWidget(QLabel("Active LLM Model:"))
        self.model_combo = ComboBox(self)
        self._populate_models()
        self.model_combo.setFixedWidth(280)
        # Select currently saved model
        saved_model = settings.get("model", "friday-model:latest")
        idx = self.model_combo.findText(saved_model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        llm_row.addWidget(self.model_combo)
        llm_row.addStretch(1)
        llm_layout.addLayout(llm_row)
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

        # Microphone Input Device
        mic_row = QHBoxLayout()
        mic_row.addWidget(QLabel("Microphone Input Device:"))
        self.mic_combo = ComboBox(self)
        self.mic_combo.setFixedWidth(360)
        self._populate_audio_devices()
        mic_row.addWidget(self.mic_combo)
        mic_row.addStretch(1)
        voice_layout.addLayout(mic_row)

        # Seamless Speech Mode Toggle
        seamless_row = QHBoxLayout()
        seamless_row.addWidget(QLabel("Seamless Unbroken Speech (Synthesize Complete Response Without Stuttering):"))
        seamless_row.addStretch(1)
        self.seamless_switch = SwitchButton(self)
        self.seamless_switch.setChecked(settings.get("seamless_speech", True))
        seamless_row.addWidget(self.seamless_switch)
        voice_layout.addLayout(seamless_row)

        # Continuous Conversation Follow-Up Toggle
        conv_row = QHBoxLayout()
        conv_row.addWidget(QLabel("Continuous Conversation (Auto-Listen for Second Question Without Button Press):"))
        conv_row.addStretch(1)
        self.conv_switch = SwitchButton(self)
        self.conv_switch.setChecked(settings.get("continuous_conversation", True))
        conv_row.addWidget(self.conv_switch)
        voice_layout.addLayout(conv_row)

        layout.addWidget(voice_card)

        # 3. Audio & Acoustic Earcons
        acoustics_card = CardWidget(content_widget)
        acoustics_layout = QVBoxLayout(acoustics_card)
        acoustics_layout.setContentsMargins(16, 16, 16, 16)
        acoustics_layout.setSpacing(10)

        acoustics_header = QLabel("Tactical HUD Acoustics")
        acoustics_header.setFont(QFont("Segoe UI", 11, QFont.Bold))
        acoustics_header.setStyleSheet("color: #FFFFFF;")
        acoustics_layout.addWidget(acoustics_header)

        switch_row = QHBoxLayout()
        switch_row.addWidget(QLabel("Enable Procedural Stark Audio Chimes (Wake, Confirm, Sleep):"))
        switch_row.addStretch(1)
        self.chimes_switch = SwitchButton(self)
        self.chimes_switch.setChecked(settings.get("chimes_enabled", True))
        switch_row.addWidget(self.chimes_switch)
        acoustics_layout.addLayout(switch_row)

        voice_loop_row = QHBoxLayout()
        voice_loop_row.addWidget(QLabel("Always Listen Hands-Free (Auto-Start Voice Loop on Launch):"))
        voice_loop_row.addStretch(1)
        self.auto_voice_switch = SwitchButton(self)
        self.auto_voice_switch.setChecked(settings.get("auto_start_voice_loop", True))
        voice_loop_row.addWidget(self.auto_voice_switch)
        acoustics_layout.addLayout(voice_loop_row)
        layout.addWidget(acoustics_card)

        # 4. Performance & Animation Scaling (Power Guard)
        perf_card = CardWidget(content_widget)
        perf_layout = QVBoxLayout(perf_card)
        perf_layout.setContentsMargins(16, 16, 16, 16)
        perf_layout.setSpacing(10)

        perf_header = QLabel("Laptop Protection & Animation Budget")
        perf_header.setFont(QFont("Segoe UI", 11, QFont.Bold))
        perf_header.setStyleSheet("color: #FFFFFF;")
        perf_layout.addWidget(perf_header)

        anim_row = QHBoxLayout()
        anim_row.addWidget(QLabel("Visual Animation Fidelity:"))
        self.anim_combo = ComboBox(self)
        self.anim_combo.addItems(["Full (60 FPS Holographic)", "Reduced (30 FPS Low Power)", "Off (Battery Saver)"])
        saved_anim = settings.get("animation_level", "Full")
        for i in range(self.anim_combo.count()):
            if saved_anim in self.anim_combo.itemText(i):
                self.anim_combo.setCurrentIndex(i)
                break
        anim_row.addWidget(self.anim_combo)
        anim_row.addStretch(1)
        perf_layout.addLayout(anim_row)

        cmd_pos_row = QHBoxLayout()
        cmd_pos_row.addWidget(QLabel("Floating Command Bar Screen Anchor:"))
        self.pos_combo = ComboBox(self)
        self.pos_combo.addItems(["Top of Screen", "Bottom of Screen", "Last Dragged Position"])
        saved_pos = (settings.get("command_bar_position") or "top").lower()
        if "bottom" in saved_pos:
            self.pos_combo.setCurrentIndex(1)
        elif "last" in saved_pos:
            self.pos_combo.setCurrentIndex(2)
        else:
            self.pos_combo.setCurrentIndex(0)
        cmd_pos_row.addWidget(self.pos_combo)
        cmd_pos_row.addStretch(1)
        perf_layout.addLayout(cmd_pos_row)
        layout.addWidget(perf_card)

        # 5. Visual Theme & Desktop Palette
        theme_card = CardWidget(content_widget)
        theme_layout = QVBoxLayout(theme_card)
        theme_layout.setContentsMargins(16, 16, 16, 16)
        theme_layout.setSpacing(10)

        theme_header = QLabel("Desktop Aesthetics & Backdrop Palette")
        theme_header.setFont(QFont("Segoe UI", 11, QFont.Bold))
        theme_header.setStyleSheet("color: #FFFFFF;")
        theme_layout.addWidget(theme_header)

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Visual Theme Palette:"))
        self.theme_combo = ComboBox(self)
        self.theme_combo.addItem("Tactical Dark (Cyan Accent)", userData="tactical")
        self.theme_combo.addItem("Monochrome Dark (Minimalist)", userData="dark")
        self.theme_combo.addItem("Light Mode (High Contrast)", userData="light")
        self.theme_combo.setFixedWidth(280)

        saved_theme = (settings.get("theme_mode") or "dark").lower()
        for i in range(self.theme_combo.count()):
            if self.theme_combo.itemData(i) == saved_theme:
                self.theme_combo.setCurrentIndex(i)
                break
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch(1)
        theme_layout.addLayout(theme_row)
        layout.addWidget(theme_card)

        # Save Button
        self.save_btn = PrimaryPushButton(FluentIcon.SAVE, "Apply Preferences", content_widget)
        self.save_btn.setFixedWidth(200)
        self.save_btn.setStyleSheet("""
            PrimaryPushButton {
                background-color: #0078D4;
                border: 1px solid #005A9E;
                font-weight: bold;
            }
        """)
        self.save_btn.clicked.connect(self._save_settings)
        layout.addWidget(self.save_btn)

        layout.addStretch(1)
        scroll.setWidget(content_widget)

        main_vbox = QVBoxLayout(self)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.addWidget(scroll)

    def _populate_audio_devices(self):
        self.mic_combo.addItem("Default System Microphone", userData=None)
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

    def _populate_models(self):
        try:
            installed = [m.model for m in ollama.list().models]
            if installed:
                self.model_combo.addItems(installed)
                return
        except Exception as e:
            logger.debug(f"Ollama local models query skipped: {e}")
        self.model_combo.addItems(["friday-model:latest", "qwen2.5-coder:latest", "llama3.1:latest"])

    def _save_settings(self):
        anim_text = self.anim_combo.currentText().split(" ")[0]
        pos_text = "top"
        if "Bottom" in self.pos_combo.currentText():
            pos_text = "bottom"
        elif "Last" in self.pos_combo.currentText():
            pos_text = "last"

        data = {
            "model": self.model_combo.currentText(),
            "voice": self.voice_combo.currentText().split(" ")[0],
            "audio_input_device": self.mic_combo.currentData(),
            "theme_mode": self.theme_combo.currentData() or "dark",
            "chimes_enabled": self.chimes_switch.isChecked(),
            "auto_start_voice_loop": self.auto_voice_switch.isChecked(),
            "seamless_speech": self.seamless_switch.isChecked(),
            "continuous_conversation": self.conv_switch.isChecked(),
            "animation_level": anim_text,
            "command_bar_position": pos_text
        }
        self.settings_saved.emit(data)
        InfoBar.success(
            "Settings Synchronized",
            "F.R.I.D.A.Y. tactical parameters updated and persisted to disk.",
            parent=self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000
        )
