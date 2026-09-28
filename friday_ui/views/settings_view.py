"""
F.R.I.D.A.Y. 3.0 - Professional Settings Architecture
Clean Category Sub-Navigation with Structured Settings Panes:
GENERAL | AI MODELS | VOICE | APPEARANCE | AUTOMATION | SECURITY | ADVANCED

Consumes centralized ThemeTokens and preserves all settings persistence hooks.
"""

import logging
import ollama
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QStackedWidget, QListWidget, QListWidgetItem,
    QSlider, QSizePolicy
)
from qfluentwidgets import (
    ComboBox, SwitchButton, PrimaryPushButton, PushButton, LineEdit,
    CardWidget, InfoBar, InfoBarPosition, Slider, SpinBox, FluentIcon
)

from friday_core.settings import settings, get_default_owner_name
from friday_ui.styles.themes import get_current_palette, get_theme_palette, TOKENS, fade_in

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
    Modular Settings View with Category Sub-Navigation.
    Exposes General, AI Models, Voice, Appearance, Automation, Security, and Advanced settings.
    """
    settings_saved = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settings_view")
        self.setAccessibleName("Application Settings View")
        self._pull_worker = None
        self._init_ui()

    def _init_ui(self):
        p = get_current_palette()
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 16, 20, 16)
        root_layout.setSpacing(12)

        # ── Header ──────────────────────────────────────────
        header_row = QHBoxLayout()
        header_box = QVBoxLayout()
        header_box.setSpacing(2)

        self.title_label = QLabel("SETTINGS & PREFERENCES")
        self.title_label.setFont(QFont("Inter", 12, QFont.Bold))
        self.title_label.setStyleSheet(f"color: {p['text_primary']}; letter-spacing: 0.5px;")

        self.subtitle_label = QLabel("Configure identity, neural models, voice acoustics, automation guardrails, and security")
        self.subtitle_label.setFont(QFont("Inter", 8))
        self.subtitle_label.setStyleSheet(f"color: {p['text_muted']};")

        header_box.addWidget(self.title_label)
        header_box.addWidget(self.subtitle_label)
        header_row.addLayout(header_box)
        header_row.addStretch(1)

        # Action Buttons in Header
        self.restore_btn = PushButton("Restore Defaults", self)
        self.restore_btn.setObjectName("restore_defaults_btn")
        self.restore_btn.setAccessibleName("Restore default settings")
        self.restore_btn.clicked.connect(self._on_restore_defaults)
        header_row.addWidget(self.restore_btn)

        self.save_btn = PrimaryPushButton(FluentIcon.SAVE, "Save Settings", self)
        self.save_btn.setObjectName("save_settings_btn")
        self.save_btn.setAccessibleName("Save settings to disk")
        self.save_btn.clicked.connect(self._on_save_settings)
        header_row.addWidget(self.save_btn)

        root_layout.addLayout(header_row)

        # ── Main Body: Left Category Nav + Right Stacked Panes ──
        body_layout = QHBoxLayout()
        body_layout.setSpacing(14)

        # Category Nav List
        self.category_list = QListWidget(self)
        self.category_list.setObjectName("settings_category_list")
        self.category_list.setAccessibleName("Settings categories")
        self.category_list.setFixedWidth(190)
        self.category_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {p['bg_surface']};
                border: 1px solid {p['border_card']};
                border-radius: 10px;
                color: {p['text_secondary']};
                padding: 6px;
            }}
            QListWidget::item {{
                padding: 10px 12px;
                border-radius: 6px;
                font-size: 11.5px;
                font-weight: 500;
                margin-bottom: 2px;
            }}
            QListWidget::item:hover {{
                background-color: {p['bg_card_hover']};
                color: {p['text_primary']};
            }}
            QListWidget::item:selected {{
                background-color: {p['selection_bg']};
                color: {p['text_primary']};
                font-weight: 600;
            }}
        """)

        categories = [
            ("👤  General",      "general"),
            ("🧠  AI Models",    "models"),
            ("🎙️  Voice & Audio", "voice"),
            ("🎨  Appearance",   "appearance"),
            ("⚡  Automation",   "automation"),
            ("🛡️  Security",     "security"),
            ("⚙️  Advanced",     "advanced")
        ]
        for name, key in categories:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, key)
            self.category_list.addItem(item)

        body_layout.addWidget(self.category_list)

        # Right Stacked Panes Container
        self.stacked_panes = QStackedWidget(self)
        self.stacked_panes.setObjectName("settings_stacked_panes")

        # 1. GENERAL PANE
        self.stacked_panes.addWidget(self._create_general_pane())
        # 2. AI MODELS PANE
        self.stacked_panes.addWidget(self._create_models_pane())
        # 3. VOICE PANE
        self.stacked_panes.addWidget(self._create_voice_pane())
        # 4. APPEARANCE PANE
        self.stacked_panes.addWidget(self._create_appearance_pane())
        # 5. AUTOMATION PANE
        self.stacked_panes.addWidget(self._create_automation_pane())
        # 6. SECURITY PANE
        self.stacked_panes.addWidget(self._create_security_pane())
        # 7. ADVANCED PANE
        self.stacked_panes.addWidget(self._create_advanced_pane())

        self.category_list.currentRowChanged.connect(self._on_category_changed)
        self.category_list.setCurrentRow(0)

        body_layout.addWidget(self.stacked_panes, 1)
        root_layout.addLayout(body_layout, 1)

    def _on_category_changed(self, row: int):
        if row >= 0:
            self.stacked_panes.setCurrentIndex(row)
            fade_in(self.stacked_panes.currentWidget(), duration=160)

    # ── 1. General Pane ────────────────────────────────────────────────
    def _create_general_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = CardWidget(pane)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 16, 16, 16)
        c_layout.setSpacing(12)

        head = QLabel("Owner Profile & Identity")
        head.setFont(QFont("Inter", 10, QFont.Bold))
        c_layout.addWidget(head)

        name_row = QHBoxLayout()
        name_lbl = QLabel("Owner Name:")
        name_lbl.setFixedWidth(130)
        self.owner_name_input = LineEdit(card)
        self.owner_name_input.setObjectName("owner_name_input")
        self.owner_name_input.setAccessibleName("Owner name")
        self.owner_name_input.setText(settings.get("user_name", get_default_owner_name()))
        name_row.addWidget(name_lbl)
        name_row.addWidget(self.owner_name_input)
        c_layout.addLayout(name_row)

        title_row = QHBoxLayout()
        title_lbl = QLabel("Call-Sign / Title:")
        title_lbl.setFixedWidth(130)
        self.title_combo = ComboBox(card)
        self.title_combo.setObjectName("title_combo")
        self.title_combo.setAccessibleName("Owner title or call sign")
        self.title_combo.addItems(["Boss", "Sir", "Ma'am", "Commander", "Doctor", "Friend", "None"])
        saved_title = settings.get("user_title", "Boss")
        idx = self.title_combo.findText(saved_title)
        if idx >= 0:
            self.title_combo.setCurrentIndex(idx)
        title_row.addWidget(title_lbl)
        title_row.addWidget(self.title_combo)
        title_row.addStretch(1)
        c_layout.addLayout(title_row)

        c_layout.addSpacing(6)
        hk_lbl = QLabel("Global Shortcut: Ctrl + Space opens floating command bar from anywhere in Windows.")
        hk_lbl.setFont(QFont("Inter", 8))
        hk_lbl.setStyleSheet("color: #9CA3AF;")
        c_layout.addWidget(hk_lbl)

        layout.addWidget(card)
        layout.addStretch(1)
        return pane

    # ── 2. AI Models Pane ──────────────────────────────────────────────
    def _create_models_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = CardWidget(pane)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 16, 16, 16)
        c_layout.setSpacing(12)

        head = QLabel("Main Agent Model")
        head.setFont(QFont("Inter", 10, QFont.Bold))
        c_layout.addWidget(head)

        m_row = QHBoxLayout()
        m_lbl = QLabel("Active LLM Core:")
        m_lbl.setFixedWidth(130)
        self.model_combo = ComboBox(card)
        self.model_combo.setObjectName("model_selector_settings")
        self.model_combo.setAccessibleName("Select active LLM core model")
        self.model_combo.setMinimumWidth(260)
        self._populate_models()
        self.refresh_models_btn = PushButton("Refresh Models", card)
        self.refresh_models_btn.setObjectName("refresh_models_btn")
        self.refresh_models_btn.setAccessibleName("Refresh available Ollama models")
        self.refresh_models_btn.clicked.connect(self._on_refresh_models_clicked)
        m_row.addWidget(m_lbl)
        m_row.addWidget(self.model_combo)
        m_row.addWidget(self.refresh_models_btn)
        m_row.addStretch(1)
        c_layout.addLayout(m_row)

        # Model Capabilities & Runtime State Badges
        p = get_current_palette()
        status_box = QHBoxLayout()
        status_box.setSpacing(8)

        conn_badge = QLabel("● Provider: Ollama Local (Connected)")
        conn_badge.setFont(QFont("Consolas", 8, QFont.Bold))
        conn_badge.setStyleSheet(f"""
            color: {p['live_green']};
            background-color: {p['live_green_bg']};
            border: 1px solid {p['live_green_border']};
            border-radius: 4px;
            padding: 3px 8px;
        """)
        status_box.addWidget(conn_badge)

        tools_badge = QLabel("● Native Tool Calling: Supported (JSON Schema)")
        tools_badge.setFont(QFont("Consolas", 8, QFont.Bold))
        tools_badge.setStyleSheet(f"""
            color: {p['accent']};
            background-color: {p['accent_bg']};
            border: 1px solid {p['accent_border']};
            border-radius: 4px;
            padding: 3px 8px;
        """)
        status_box.addWidget(tools_badge)
        status_box.addStretch(1)
        c_layout.addLayout(status_box)

        c_layout.addSpacing(4)

        # Vision Model Row
        v_row = QHBoxLayout()
        v_lbl = QLabel("Vision Specialist:")
        v_lbl.setFixedWidth(130)
        self.vision_combo = ComboBox(card)
        self.vision_combo.setObjectName("vision_model_combo")
        self.vision_combo.setAccessibleName("Select vision specialist model")
        self.vision_combo.addItems(["qwen2.5-vl:7b", "llama3.2-vision", "llava:7b", "Automatic Routing"])
        saved_v = settings.get("vision_model", "qwen2.5-vl:7b")
        idx_v = self.vision_combo.findText(saved_v)
        if idx_v >= 0:
            self.vision_combo.setCurrentIndex(idx_v)
        v_row.addWidget(v_lbl)
        v_row.addWidget(self.vision_combo)
        v_row.addStretch(1)
        c_layout.addLayout(v_row)

        c_layout.addSpacing(6)

        # Pull New Model Row
        pull_head = QLabel("Download / Install New Model")
        pull_head.setFont(QFont("Inter", 9, QFont.Bold))
        c_layout.addWidget(pull_head)

        pull_row = QHBoxLayout()
        self.new_model_input = LineEdit(card)
        self.new_model_input.setObjectName("new_model_input")
        self.new_model_input.setAccessibleName("Model name or tag to pull")
        self.new_model_input.setPlaceholderText("e.g. qwen2.5:7b, mistral:7b, llama3.2:3b...")
        pull_row.addWidget(self.new_model_input, 1)

        self.pull_model_btn = PrimaryPushButton(FluentIcon.DOWNLOAD, "Pull Model", card)
        self.pull_model_btn.setObjectName("pull_model_btn")
        self.pull_model_btn.setAccessibleName("Start model download")
        self.pull_model_btn.clicked.connect(self._on_pull_model_clicked)
        pull_row.addWidget(self.pull_model_btn)
        c_layout.addLayout(pull_row)

        self.pull_status_label = QLabel("")
        self.pull_status_label.setFont(QFont("Inter", 8))
        self.pull_status_label.setStyleSheet("color: #9CA3AF;")
        c_layout.addWidget(self.pull_status_label)

        layout.addWidget(card)
        layout.addStretch(1)
        return pane

    # ── 3. Voice Pane ──────────────────────────────────────────────────
    def _create_voice_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = CardWidget(pane)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 16, 16, 16)
        c_layout.setSpacing(12)

        head = QLabel("Voice Engine & Acoustics")
        head.setFont(QFont("Inter", 10, QFont.Bold))
        c_layout.addWidget(head)

        # STT Row
        stt_row = QHBoxLayout()
        stt_lbl = QLabel("Speech Recognition (STT):")
        stt_lbl.setFixedWidth(160)
        self.stt_combo = ComboBox(card)
        self.stt_combo.setObjectName("stt_combo")
        self.stt_combo.setAccessibleName("Select speech-to-text engine")
        self.stt_combo.addItems(["Faster-Whisper (Local GPU/CPU)", "Google Speech API", "Whisper Small"])
        saved_stt = settings.get("stt_engine", "Faster-Whisper")
        idx_s = self.stt_combo.findText(saved_stt)
        if idx_s >= 0:
            self.stt_combo.setCurrentIndex(idx_s)
        stt_row.addWidget(stt_lbl)
        stt_row.addWidget(self.stt_combo)
        stt_row.addStretch(1)
        c_layout.addLayout(stt_row)

        # TTS Voice Row
        tts_row = QHBoxLayout()
        tts_lbl = QLabel("Vocal Voice Profile (TTS):")
        tts_lbl.setFixedWidth(160)
        self.tts_combo = ComboBox(card)
        self.tts_combo.setObjectName("tts_combo")
        self.tts_combo.setAccessibleName("Select vocal profile")
        self.tts_combo.addItems([
            "bf_emma (Local FRIDAY)",
            "af_sarah (Local Sarah)",
            "af_bella (Local Bella)",
            "en-US-AriaNeural (Cloud)",
            "en-IE-EmilyNeural (Cloud)",
            "en-GB-SoniaNeural (Cloud)",
            "en-US-JennyNeural (Cloud)"
        ])
        saved_voice = settings.get("voice", "bf_emma")
        for i in range(self.tts_combo.count()):
            if saved_voice in self.tts_combo.itemText(i):
                self.tts_combo.setCurrentIndex(i)
                break
        tts_row.addWidget(tts_lbl)
        tts_row.addWidget(self.tts_combo)
        tts_row.addStretch(1)
        c_layout.addLayout(tts_row)

        # Local Kokoro Switch
        kokoro_row = QHBoxLayout()
        kokoro_lbl = QLabel("Offline Kokoro Engine:")
        kokoro_lbl.setFixedWidth(160)
        self.local_kokoro_switch = SwitchButton(card)
        self.local_kokoro_switch.setObjectName("local_kokoro_switch")
        self.local_kokoro_switch.setAccessibleName("Toggle offline Kokoro TTS engine")
        self.local_kokoro_switch.setChecked(settings.get("use_local_tts", True))
        kokoro_row.addWidget(kokoro_lbl)
        kokoro_row.addWidget(self.local_kokoro_switch)
        kokoro_row.addStretch(1)
        c_layout.addLayout(kokoro_row)

        # Speed Slider
        speed_row = QHBoxLayout()
        speed_title = QLabel("Speech Rate / Speed:")
        speed_title.setFixedWidth(160)
        self.speed_slider = Slider(Qt.Horizontal, card)
        self.speed_slider.setObjectName("speed_slider")
        self.speed_slider.setAccessibleName("Speech rate slider")
        self.speed_slider.setRange(70, 150)
        saved_speed = int(settings.get("speech_speed", 1.0) * 100)
        self.speed_slider.setValue(saved_speed)
        self.speed_label = QLabel(f"{saved_speed / 100.0:.2f}x")
        self.speed_slider.valueChanged.connect(lambda v: self.speed_label.setText(f"{v / 100.0:.2f}x"))
        speed_row.addWidget(speed_title)
        speed_row.addWidget(self.speed_slider, 1)
        speed_row.addWidget(self.speed_label)
        c_layout.addLayout(speed_row)

        # Pitch Slider
        pitch_row = QHBoxLayout()
        pitch_title = QLabel("Speech Pitch:")
        pitch_title.setFixedWidth(160)
        self.pitch_slider = Slider(Qt.Horizontal, card)
        self.pitch_slider.setObjectName("pitch_slider")
        self.pitch_slider.setAccessibleName("Speech pitch slider")
        self.pitch_slider.setRange(70, 130)
        saved_pitch = int(settings.get("speech_pitch", 1.0) * 100)
        self.pitch_slider.setValue(saved_pitch)
        self.pitch_label = QLabel(f"{saved_pitch / 100.0:.2f}x")
        self.pitch_slider.valueChanged.connect(lambda v: self.pitch_label.setText(f"{v / 100.0:.2f}x"))
        pitch_row.addWidget(pitch_title)
        pitch_row.addWidget(self.pitch_slider, 1)
        pitch_row.addWidget(self.pitch_label)
        c_layout.addLayout(pitch_row)

        layout.addWidget(card)
        layout.addStretch(1)
        return pane

    # ── 4. Appearance Pane ─────────────────────────────────────────────
    def _create_appearance_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = CardWidget(pane)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 16, 16, 16)
        c_layout.setSpacing(12)

        head = QLabel("Visual Theme & Animation Scaling")
        head.setFont(QFont("Inter", 10, QFont.Bold))
        c_layout.addWidget(head)

        th_row = QHBoxLayout()
        th_lbl = QLabel("Color Theme:")
        th_lbl.setFixedWidth(160)
        self.theme_combo = ComboBox(card)
        self.theme_combo.setObjectName("theme_combo")
        self.theme_combo.setAccessibleName("Select visual color theme")
        self.theme_combo.addItems(["Dark Neutral (Charcoal)", "Slate Light (Clean)"])
        saved_th = settings.get("theme_mode", "dark")
        self.theme_combo.setCurrentIndex(1 if "light" in saved_th.lower() else 0)
        th_row.addWidget(th_lbl)
        th_row.addWidget(self.theme_combo)
        th_row.addStretch(1)
        c_layout.addLayout(th_row)

        anim_row = QHBoxLayout()
        anim_lbl = QLabel("Microinteraction Animations:")
        anim_lbl.setFixedWidth(160)
        self.anim_combo = ComboBox(card)
        self.anim_combo.setObjectName("anim_combo")
        self.anim_combo.setAccessibleName("Select animation fidelity level")
        self.anim_combo.addItems(["Full (Fluid 60 FPS)", "Reduced (Power Saving)", "Off (Instant)"])
        saved_anim = settings.get("animation_level", "Full")
        for i in range(self.anim_combo.count()):
            if saved_anim in self.anim_combo.itemText(i):
                self.anim_combo.setCurrentIndex(i)
                break
        anim_row.addWidget(anim_lbl)
        anim_row.addWidget(self.anim_combo)
        anim_row.addStretch(1)
        c_layout.addLayout(anim_row)

        layout.addWidget(card)
        layout.addStretch(1)
        return pane

    # ── 5. Automation Pane ─────────────────────────────────────────────
    def _create_automation_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = CardWidget(pane)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 16, 16, 16)
        c_layout.setSpacing(12)

        head = QLabel("Task Supervisor & Desktop Automation")
        head.setFont(QFont("Inter", 10, QFont.Bold))
        c_layout.addWidget(head)

        wd_row = QHBoxLayout()
        wd_lbl = QLabel("Task Watchdog Monitoring:")
        wd_lbl.setFixedWidth(180)
        self.watchdog_switch = SwitchButton(card)
        self.watchdog_switch.setObjectName("watchdog_switch")
        self.watchdog_switch.setAccessibleName("Toggle task watchdog stall monitor")
        self.watchdog_switch.setChecked(settings.get("watchdog_enabled", True))
        wd_row.addWidget(wd_lbl)
        wd_row.addWidget(self.watchdog_switch)
        wd_row.addStretch(1)
        c_layout.addLayout(wd_row)

        to_row = QHBoxLayout()
        to_lbl = QLabel("Watchdog Idle Timeout (s):")
        to_lbl.setFixedWidth(180)
        self.idle_timeout_spin = SpinBox(card)
        self.idle_timeout_spin.setObjectName("idle_timeout_spin")
        self.idle_timeout_spin.setAccessibleName("Watchdog idle timeout in seconds")
        self.idle_timeout_spin.setRange(15, 300)
        self.idle_timeout_spin.setValue(int(settings.get("idle_timeout", 45)))
        to_row.addWidget(to_lbl)
        to_row.addWidget(self.idle_timeout_spin)
        to_row.addStretch(1)
        c_layout.addLayout(to_row)

        perm_row = QHBoxLayout()
        perm_lbl = QLabel("Desktop Control Tools:")
        perm_lbl.setFixedWidth(180)
        self.tools_switch = SwitchButton(card)
        self.tools_switch.setObjectName("tools_switch")
        self.tools_switch.setAccessibleName("Toggle desktop tool execution")
        self.tools_switch.setChecked(settings.get("desktop_tools_enabled", True))
        perm_row.addWidget(perm_lbl)
        perm_row.addWidget(self.tools_switch)
        perm_row.addStretch(1)
        c_layout.addLayout(perm_row)

        layout.addWidget(card)
        layout.addStretch(1)
        return pane

    # ── 6. Security Pane ───────────────────────────────────────────────
    def _create_security_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = CardWidget(pane)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 16, 16, 16)
        c_layout.setSpacing(12)

        head = QLabel("Zero-Trust Security Gatekeeper")
        head.setFont(QFont("Inter", 10, QFont.Bold))
        c_layout.addWidget(head)

        p = get_current_palette()
        status_lbl = QLabel("● Protection Status: Active (Tiered Clearance Enforced)")
        status_lbl.setFont(QFont("Consolas", 8, QFont.Bold))
        status_lbl.setStyleSheet(f"""
            color: {p['live_green']};
            background-color: {p['live_green_bg']};
            border: 1px solid {p['live_green_border']};
            border-radius: 4px;
            padding: 4px 8px;
        """)
        c_layout.addWidget(status_lbl)

        # Policy overview
        policies = [
            ("Safe Actions (Tier 1 Autonomous):", "Read files, inspect UI, compute, search web, capture preview"),
            ("Guarded Actions (Tier 2 Confirmation):", "Write files, execute shell processes, delete items, run code"),
            ("Blocked Actions (Strictly Prohibited):", "Arbitrary root operations, SSRF against internal IP metadata, unvetted downloads")
        ]
        for title, desc in policies:
            sec_box = QVBoxLayout()
            sec_box.setSpacing(2)
            t_lbl = QLabel(title)
            t_lbl.setFont(QFont("Inter", 8, QFont.Bold))
            t_lbl.setStyleSheet(f"color: {p['text_primary']};")
            d_lbl = QLabel(f"• {desc}")
            d_lbl.setFont(QFont("Inter", 8))
            d_lbl.setStyleSheet(f"color: {p['text_secondary']};")
            sec_box.addWidget(t_lbl)
            sec_box.addWidget(d_lbl)
            c_layout.addLayout(sec_box)

        layout.addWidget(card)
        layout.addStretch(1)
        return pane

    # ── 7. Advanced Pane ───────────────────────────────────────────────
    def _create_advanced_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = CardWidget(pane)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 16, 16, 16)
        c_layout.setSpacing(12)

        head = QLabel("Advanced System & Context Tuning")
        head.setFont(QFont("Inter", 10, QFont.Bold))
        c_layout.addWidget(head)

        ctx_row = QHBoxLayout()
        ctx_lbl = QLabel("Context Token Budget:")
        ctx_lbl.setFixedWidth(180)
        self.context_budget_spin = SpinBox(card)
        self.context_budget_spin.setObjectName("context_budget_spin")
        self.context_budget_spin.setAccessibleName("Context token budget spinbox")
        self.context_budget_spin.setRange(2048, 65536)
        self.context_budget_spin.setValue(int(settings.get("context_budget", 8192)))
        ctx_row.addWidget(ctx_lbl)
        ctx_row.addWidget(self.context_budget_spin)
        ctx_row.addStretch(1)
        c_layout.addLayout(ctx_row)

        tel_row = QHBoxLayout()
        tel_lbl = QLabel("Telemetry Poll Interval (s):")
        tel_lbl.setFixedWidth(180)
        self.telemetry_poll_spin = SpinBox(card)
        self.telemetry_poll_spin.setObjectName("telemetry_poll_spin")
        self.telemetry_poll_spin.setAccessibleName("Telemetry polling interval spinbox")
        self.telemetry_poll_spin.setRange(5, 120)
        self.telemetry_poll_spin.setValue(int(settings.get("telemetry_poll_interval", 20)))
        tel_row.addWidget(tel_lbl)
        tel_row.addWidget(self.telemetry_poll_spin)
        tel_row.addStretch(1)
        c_layout.addLayout(tel_row)

        layout.addWidget(card)
        layout.addStretch(1)
        return pane

    # ── Helpers & Action Handlers ──────────────────────────────────────
    def _populate_models(self):
        self.model_combo.clear()
        models = settings.get_available_models()
        self.model_combo.addItems(models)
        current = settings.get("model", models[0] if models else "llama3.2:3b")
        idx = self.model_combo.findText(current)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        elif current:
            self.model_combo.addItem(current)
            self.model_combo.setCurrentText(current)

    def _on_refresh_models_clicked(self):
        settings.refresh_models()
        self._populate_models()
        InfoBar.success("Models Refreshed", "Discovered latest local Ollama models.", parent=self, position=InfoBarPosition.TOP_RIGHT, duration=2000)

    def _on_pull_model_clicked(self):
        target = self.new_model_input.text().strip()
        if not target:
            InfoBar.warning("Input Required", "Enter model name (e.g. qwen2.5:7b)", parent=self, position=InfoBarPosition.TOP_RIGHT)
            return

        self.pull_model_btn.setEnabled(False)
        self.pull_status_label.setText(f"Initiating pull for '{target}'...")
        host = settings.get("ollama_host", "http://localhost:11434")

        self._pull_worker = ModelPullWorker(target, host)
        self._pull_worker.progress_signal.connect(self.pull_status_label.setText)

        def _done(success, msg):
            self.pull_model_btn.setEnabled(True)
            self.pull_status_label.setText(msg)
            if success:
                self._populate_models()
                InfoBar.success("Model Installed", msg, parent=self, position=InfoBarPosition.TOP_RIGHT, duration=4000)
            else:
                InfoBar.error("Pull Failed", msg, parent=self, position=InfoBarPosition.TOP_RIGHT, duration=4000)

        self._pull_worker.completed_signal.connect(_done)
        self._pull_worker.start()

    def _on_save_settings(self):
        new_theme = "warm_dark" if self.theme_combo.currentIndex() == 0 else "warm_light"
        updates = {
            "user_name": self.owner_name_input.text().strip(),
            "user_title": self.title_combo.currentText(),
            "model": self.model_combo.currentText(),
            "vision_model": getattr(self, 'vision_combo', None) and self.vision_combo.currentText(),
            "stt_engine": self.stt_combo.currentText(),
            "voice": self.tts_combo.currentText(),
            "use_local_tts": self.local_kokoro_switch.isChecked(),
            "speech_speed": self.speed_slider.value() / 100.0,
            "speech_pitch": self.pitch_slider.value() / 100.0,
            "theme_mode": new_theme,
            "animation_level": self.anim_combo.currentText().split()[0],
            "watchdog_enabled": getattr(self, 'watchdog_switch', None) and self.watchdog_switch.isChecked(),
            "idle_timeout": getattr(self, 'idle_timeout_spin', None) and self.idle_timeout_spin.value(),
            "context_budget": getattr(self, 'context_budget_spin', None) and self.context_budget_spin.value(),
            "telemetry_poll_interval": getattr(self, 'telemetry_poll_spin', None) and self.telemetry_poll_spin.value()
        }
        for k, v in updates.items():
            if v is not None:
                settings.set(k, v)

        self.settings_saved.emit(updates)
        InfoBar.success("Settings Saved", "Preferences persisted cleanly to configuration store.", parent=self, position=InfoBarPosition.TOP_RIGHT, duration=2500)

        main_win = self.window()
        if hasattr(main_win, '_apply_global_style'):
            main_win._apply_global_style()

    def _on_restore_defaults(self):
        self.owner_name_input.setText(get_default_owner_name())
        self.title_combo.setCurrentText("Boss")
        self.speed_slider.setValue(100)
        self.pitch_slider.setValue(100)
        self.local_kokoro_switch.setChecked(True)
        self.theme_combo.setCurrentIndex(0)
        self.anim_combo.setCurrentIndex(0)
        InfoBar.info("Defaults Restored", "Form values reset to default profiles.", parent=self, position=InfoBarPosition.TOP_RIGHT, duration=2000)

    def apply_theme(self, theme_mode: str = None):
        """Dynamically applies theme palette across settings controls."""
        p = get_theme_palette(theme_mode)
        if hasattr(self, 'title_label'):
            self.title_label.setStyleSheet(f"color: {p['text_primary']}; letter-spacing: 0.5px;")
        if hasattr(self, 'subtitle_label'):
            self.subtitle_label.setStyleSheet(f"color: {p['text_muted']};")
