"""
F.R.I.D.A.Y. 2.0 - Universal AI Model Manager Dialog
Allows users to easily add any custom model (Ollama or local) and pull it live.
"""

import threading
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QWidget,
    QProgressBar, QSizePolicy
)
from qfluentwidgets import (
    LineEdit, PrimaryPushButton, PushButton, CardWidget,
    InfoBar, InfoBarPosition
)
from friday_core.settings import settings

class AddModelDialog(QDialog):
    """Stark-themed dialog to enter and optionally pull any AI model."""
    model_added = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_model = None
        self._is_pulling = False
        self.setWindowTitle("F.R.I.D.A.Y. 2.0 - Add AI Model")
        try:
            from friday_ui.app import get_app_icon
            self.setWindowIcon(get_app_icon())
        except Exception:
            pass
        self.setFixedSize(500, 380)
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
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Header
        header = QWidget(self)
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(2)

        title = QLabel("UNIVERSAL AI MODEL MANAGER")
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title.setStyleSheet("color: #00F0FF; letter-spacing: 1px;")
        h_layout.addWidget(title)

        desc = QLabel("Add any Ollama model name, tag, or fine-tuned checkpoint to F.R.I.D.A.Y.")
        desc.setFont(QFont("Segoe UI", 9))
        desc.setStyleSheet("color: #A1A1AA;")
        h_layout.addWidget(desc)
        layout.addWidget(header)

        # Main Card
        card = CardWidget(self)
        card.setStyleSheet("""
            CardWidget {
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(0, 240, 255, 0.25);
                border-radius: 8px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)

        input_label = QLabel("MODEL TAG / IDENTIFIER:")
        input_label.setFont(QFont("Segoe UI", 8, QFont.Bold))
        input_label.setStyleSheet("color: #00F0FF; font-family: monospace;")
        card_layout.addWidget(input_label)

        self.model_input = LineEdit(card)
        self.model_input.setPlaceholderText("e.g. llama3.2:1b, mistral:7b, deepseek-r1:8b, phi3:mini...")
        card_layout.addWidget(self.model_input)

        chips_label = QLabel("QUICK PRESETS:")
        chips_label.setFont(QFont("Segoe UI", 8, QFont.Bold))
        chips_label.setStyleSheet("color: #71717A; font-family: monospace;")
        card_layout.addWidget(chips_label)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)
        presets = ["llama3.2:1b", "mistral:7b", "deepseek-r1:8b", "phi3:mini", "qwen2.5:3b"]
        for p in presets:
            btn = PushButton(p, card)
            btn.setFixedHeight(24)
            btn.setFont(QFont("Segoe UI", 8))
            btn.setStyleSheet("""
                PushButton {
                    background-color: rgba(255, 255, 255, 0.06);
                    border: 1px solid rgba(255, 255, 255, 0.12);
                    color: #D4D4D8;
                    border-radius: 4px;
                    padding: 0 8px;
                }
                PushButton:hover {
                    background-color: rgba(0, 240, 255, 0.15);
                    border-color: #00F0FF;
                    color: #FFFFFF;
                }
            """)
            btn.clicked.connect(lambda checked=False, tag=p: self.model_input.setText(tag))
            chips_row.addWidget(btn)
        card_layout.addLayout(chips_row)

        layout.addWidget(card)

        # Status & Progress
        self.status_label = QLabel("")
        self.status_label.setFont(QFont("Segoe UI", 9))
        self.status_label.setStyleSheet("color: #10B981;")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(255, 255, 255, 0.08);
                border-radius: 3px;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #00F0FF;
                border-radius: 3px;
            }
        """)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.add_btn = PrimaryPushButton("Add to Active Models", self)
        self.add_btn.setFixedHeight(34)
        self.add_btn.clicked.connect(self._on_add_direct)
        btn_layout.addWidget(self.add_btn)

        self.pull_btn = PushButton("Download / Pull via Ollama", self)
        self.pull_btn.setFixedHeight(34)
        self.pull_btn.clicked.connect(self._on_pull)
        btn_layout.addWidget(self.pull_btn)

        layout.addLayout(btn_layout)

    def _on_add_direct(self):
        tag = self.model_input.text().strip()
        if not tag:
            InfoBar.warning("Input Error", "Please enter a model name or tag.", parent=self)
            return
        settings.add_custom_model(tag)
        self.selected_model = tag
        self.model_added.emit(tag)
        self.accept()

    def _on_pull(self):
        tag = self.model_input.text().strip()
        if not tag:
            InfoBar.warning("Input Error", "Please enter a model name to pull.", parent=self)
            return
        if self._is_pulling:
            return

        self._is_pulling = True
        self.add_btn.setEnabled(False)
        self.pull_btn.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setRange(0, 0) # Indeterminate
        self.status_label.setStyleSheet("color: #00F0FF;")
        self.status_label.setText(f"Contacting Ollama to pull '{tag}'... Please wait.")

        def run_pull():
            try:
                import ollama
                client = ollama.Client(host=settings.get("ollama_host", "http://localhost:11434"))
                client.pull(tag)
                success = True
                msg = f"Model '{tag}' successfully downloaded!"
            except Exception as e:
                success = False
                msg = f"Download error: {e}"

            from PySide6.QtCore import QMetaObject, Q_ARG
            # Update UI on main thread
            from friday_ui.core.engine import run_on_main_thread
            run_on_main_thread(self._finish_pull, success, tag, msg)

        threading.Thread(target=run_pull, daemon=True).start()

    def _finish_pull(self, success: bool, tag: str, msg: str):
        self._is_pulling = False
        self.add_btn.setEnabled(True)
        self.pull_btn.setEnabled(True)
        self.progress_bar.hide()
        if success:
            settings.add_custom_model(tag)
            self.selected_model = tag
            self.status_label.setStyleSheet("color: #10B981;")
            self.status_label.setText(msg)
            self.model_added.emit(tag)
            self.accept()
        else:
            self.status_label.setStyleSheet("color: #EF4444;")
            self.status_label.setText(msg)
