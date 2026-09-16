"""
F.R.I.D.A.Y. 2.0 - Tactical Onboarding & Owner Identity Initialization
First-run setup wizard allowing new owners to configure their name, title, and neural model.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QPainter, QBrush, QPen
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QGraphicsDropShadowEffect
)
from qfluentwidgets import LineEdit, ComboBox, PrimaryPushButton, PushButton, CardWidget
from friday_core.settings import settings, get_default_owner_name

class OnboardingDialog(QDialog):
    """Stark-themed First-Run Protocol Initialization Dialog."""
    initialized = Signal(str, str, str)  # user_name, user_title, model

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("F.R.I.D.A.Y. 2.0 - Tactical Protocol Setup")
        self.setFixedSize(540, 520)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint | Qt.MSWindowsFixedSizeDialogHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #0A0D14;
                color: #FFFFFF;
                font-family: 'Segoe UI', system-ui;
            }
            QLabel {
                color: #FFFFFF;
                background: transparent;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        # Header with Stark Cyan accents
        header_widget = QWidget(self)
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        title = QLabel("F.R.I.D.A.Y. 2.0")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setStyleSheet("color: #00F0FF; letter-spacing: 2px;")
        header_layout.addWidget(title)

        subtitle = QLabel("TACTICAL WORKSTATION INITIALIZATION")
        subtitle.setFont(QFont("Segoe UI", 10, QFont.Bold))
        subtitle.setStyleSheet("color: #71717A; letter-spacing: 1px;")
        header_layout.addWidget(subtitle)

        desc = QLabel("Configure your operator identity and intelligence core to calibrate Friday.")
        desc.setFont(QFont("Segoe UI", 9))
        desc.setStyleSheet("color: #A1A1AA;")
        header_layout.addWidget(desc)

        layout.addWidget(header_widget)

        # Main Identity Configuration Card
        card = CardWidget(self)
        card.setStyleSheet("""
            CardWidget {
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(0, 240, 255, 0.25);
                border-radius: 10px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(14)

        # 1. Owner Name
        name_label = QLabel("OPERATOR / OWNER NAME:")
        name_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        name_label.setStyleSheet("color: #00F0FF; font-family: monospace;")
        card_layout.addWidget(name_label)

        self.name_input = LineEdit(card)
        default_name = settings.get("user_name") or get_default_owner_name()
        self.name_input.setText(default_name)
        self.name_input.setPlaceholderText("Enter your name (e.g. Alphin, Renit, Yogi)...")
        card_layout.addWidget(self.name_input)

        # 2. Preferred Call-Sign / Title
        title_label = QLabel("PREFERRED CALL-SIGN / TITLE:")
        title_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        title_label.setStyleSheet("color: #00F0FF; font-family: monospace;")
        card_layout.addWidget(title_label)

        self.title_combo = ComboBox(card)
        titles = ["Boss", "Sir", "Ma'am", "Commander", "Doctor", "Friend", "None"]
        self.title_combo.addItems(titles)
        curr_title = settings.get("user_title", "Boss")
        idx_t = self.title_combo.findText(curr_title)
        if idx_t >= 0:
            self.title_combo.setCurrentIndex(idx_t)
        card_layout.addWidget(self.title_combo)

        # 3. Active Neural AI Model
        model_label = QLabel("ACTIVE NEURAL MODEL (OLLAMA):")
        model_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        model_label.setStyleSheet("color: #00F0FF; font-family: monospace;")
        card_layout.addWidget(model_label)

        self.model_combo = ComboBox(card)
        models = settings.get_available_models()
        self.model_combo.addItems(models)
        curr_model = settings.get("model", models[0] if models else "llama3.2:3b")
        idx_m = self.model_combo.findText(curr_model)
        if idx_m >= 0:
            self.model_combo.setCurrentIndex(idx_m)
        card_layout.addWidget(self.model_combo)

        layout.addWidget(card)

        # Action Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)

        self.init_btn = PrimaryPushButton("INITIALIZE PROTOCOLS", self)
        self.init_btn.setFixedHeight(38)
        self.init_btn.setStyleSheet("""
            PrimaryPushButton {
                background-color: #00F0FF;
                color: #000000;
                font-weight: bold;
                border-radius: 6px;
                letter-spacing: 1px;
            }
            PrimaryPushButton:hover {
                background-color: #38F8FF;
            }
        """)
        self.init_btn.clicked.connect(self._on_initialize)
        button_layout.addWidget(self.init_btn)

        layout.addLayout(button_layout)

    def _on_initialize(self):
        name = self.name_input.text().strip() or get_default_owner_name()
        title = self.title_combo.currentText()
        model = self.model_combo.currentText()

        settings.set("user_name", name)
        settings.set("user_title", title)
        settings.set("model", model)
        settings.set("onboarding_completed", True)

        self.initialized.emit(name, title, model)
        self.accept()
