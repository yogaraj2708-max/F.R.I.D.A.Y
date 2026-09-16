"""
F.R.I.D.A.Y. 2.0 - Tactical Security Confirmation Dialog
Presents dry-run action preview with a 10-second cancellable countdown for Tier 2 actions.
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame
)
from qfluentwidgets import (
    PrimaryPushButton, PushButton, FluentIcon
)

class SecurityConfirmationDialog(QDialog):
    """Modal verification dialog for Tier 2 sensitive operations."""
    confirmed = Signal()
    cancelled = Signal()

    def __init__(self, dry_run_text: str, action_name: str = "Sensitive Operation", parent=None):
        super().__init__(parent)
        self.dry_run_text = dry_run_text
        self.action_name = action_name
        self.countdown_remaining = 10
        self.user_confirmed = False

        self._init_ui()
        self._init_timer()

    def _init_ui(self):
        self.setWindowTitle("F.R.I.D.A.Y. Security Clearance")
        self.setFixedSize(520, 260)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        container = QFrame(self)
        container.setGeometry(0, 0, 520, 260)
        container.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(18, 22, 34, 0.98), stop:1 rgba(10, 14, 24, 0.98));
                border: 2px solid #FFB900;
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        # Header
        header_row = QHBoxLayout()
        shield_icon = QLabel("🛡️")
        shield_icon.setFont(QFont("Segoe UI Emoji", 18))
        shield_icon.setStyleSheet("border: none; background: transparent;")

        title = QLabel(f"TIER 2 SECURITY CLEARANCE REQUIRED")
        title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        title.setStyleSheet("color: #FFB900; letter-spacing: 1px; border: none; background: transparent;")

        header_row.addWidget(shield_icon)
        header_row.addWidget(title)
        header_row.addStretch(1)
        layout.addLayout(header_row)

        # Dry-run text
        self.preview_label = QLabel(self.dry_run_text)
        self.preview_label.setFont(QFont("Segoe UI", 10))
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet("color: #FFFFFF; border: none; background: transparent; padding: 4px 0;")
        layout.addWidget(self.preview_label)

        # Countdown label
        self.countdown_label = QLabel(f"Auto-cancelling in {self.countdown_remaining} seconds...")
        self.countdown_label.setFont(QFont("Segoe UI", 9))
        self.countdown_label.setStyleSheet("color: #9CA3AF; border: none; background: transparent;")
        layout.addWidget(self.countdown_label)

        layout.addStretch(1)

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch(1)

        self.cancel_btn = PushButton("Cancel (Esc)", container)
        self.cancel_btn.setFixedWidth(130)
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self.cancel_btn)

        self.confirm_btn = PrimaryPushButton(FluentIcon.ACCEPT, "Confirm Action", container)
        self.confirm_btn.setFixedWidth(160)
        self.confirm_btn.setStyleSheet("""
            PrimaryPushButton {
                background-color: #D83B01;
                border: 1px solid #EA4300;
                font-weight: bold;
            }
        """)
        self.confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(self.confirm_btn)

        layout.addLayout(btn_row)

    def _init_timer(self):
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    def _tick(self):
        self.countdown_remaining -= 1
        if self.countdown_remaining <= 0:
            self.timer.stop()
            self._on_cancel()
        else:
            self.countdown_label.setText(f"Auto-cancelling in {self.countdown_remaining} seconds...")

    def _on_confirm(self):
        self.timer.stop()
        self.user_confirmed = True
        self.confirmed.emit()
        self.accept()

    def _on_cancel(self):
        self.timer.stop()
        self.user_confirmed = False
        self.cancelled.emit()
        self.reject()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._on_cancel()
        else:
            super().keyPressEvent(event)
