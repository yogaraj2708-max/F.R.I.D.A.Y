"""
F.R.I.D.A.Y. 2.0 - Right Inspector & Context Panel
Matching reference design:
- Model specifications card with 'Default' badge and context/output metadata
- System status telemetry indicator ('● All systems operational')
- Pinned files (RAG knowledge base) quick access with file badges & 'View all files' button
"""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea
)
from friday_core.settings import settings


class PinnedFileRow(QFrame):
    """Clean pinned file item with color badge, filename, and size."""
    def __init__(self, badge_text: str, badge_bg: str, filename: str, filesize: str, parent=None):
        super().__init__(parent)
        self.setObjectName("pinnedFileRow")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(38)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(10)

        # File type badge
        badge = QLabel(badge_text, self)
        badge.setFixedSize(28, 20)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(f"""
            background-color: {badge_bg};
            color: #FFFFFF;
            font-size: 8px;
            font-weight: 800;
            border-radius: 4px;
            letter-spacing: 0.5px;
        """)
        layout.addWidget(badge)

        # Name and size
        info_layout = QVBoxLayout()
        info_layout.setSpacing(1)
        name_lbl = QLabel(filename, self)
        name_lbl.setStyleSheet("font-size: 12px; font-weight: 500;")
        size_lbl = QLabel(filesize, self)
        size_lbl.setStyleSheet("font-size: 10px; color: #64748B;")
        info_layout.addWidget(name_lbl)
        info_layout.addWidget(size_lbl)
        layout.addLayout(info_layout, 1)


class InspectorView(QWidget):
    """
    3-Column Layout: Right Inspector Panel
    Houses active model metadata, live system health status, and pinned RAG documents.
    """
    view_all_files_requested = Signal()
    model_details_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("inspectorView")
        self.setFixedWidth(280)

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 16, 14, 14)
        main_layout.setSpacing(14)

        # ── 1. Model Header & Card ──
        model_header_layout = QHBoxLayout()
        model_lbl = QLabel("Model", self)
        model_lbl.setStyleSheet("font-size: 12px; font-weight: 600;")
        more_btn = QLabel("•••", self)
        more_btn.setStyleSheet("font-size: 12px; color: #64748B; cursor: pointer;")
        model_header_layout.addWidget(model_lbl)
        model_header_layout.addStretch(1)
        model_header_layout.addWidget(more_btn)
        main_layout.addLayout(model_header_layout)

        self.model_card = QFrame(self)
        self.model_card.setObjectName("inspectorCard")
        card_layout = QVBoxLayout(self.model_card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(8)

        # Model title row with 'Default' badge and caret
        title_row = QHBoxLayout()
        current_model = settings.get("model", "F.R.I.D.A.Y. 4.0")
        if not current_model or "llama" in current_model:
            current_model = "F.R.I.D.A.Y. 4.0"
        self.model_title = QLabel(current_model, self.model_card)
        self.model_title.setStyleSheet("font-size: 13px; font-weight: 600;")
        default_badge = QLabel("Default", self.model_card)
        default_badge.setStyleSheet("""
            background-color: rgba(148, 163, 184, 0.20);
            color: #64748B;
            font-size: 9px;
            font-weight: 600;
            padding: 2px 6px;
            border-radius: 4px;
        """)
        caret = QLabel("⌄", self.model_card)
        caret.setStyleSheet("font-size: 13px; color: #64748B;")
        title_row.addWidget(self.model_title)
        title_row.addWidget(default_badge)
        title_row.addStretch(1)
        title_row.addWidget(caret)
        card_layout.addLayout(title_row)

        # Best for description
        best_for_lbl = QLabel("Best for", self.model_card)
        best_for_lbl.setStyleSheet("font-size: 10px; color: #64748B; font-weight: 600; margin-top: 4px;")
        desc_lbl = QLabel("Advanced reasoning, planning, and analysis", self.model_card)
        desc_lbl.setStyleSheet("font-size: 11px; color: #94A3B8; line-height: 1.3;")
        desc_lbl.setWordWrap(True)
        card_layout.addWidget(best_for_lbl)
        card_layout.addWidget(desc_lbl)

        # Specs grid
        specs_data = [
            ("Context window", "200K tokens"),
            ("Max output", "8K tokens"),
            ("Knowledge cutoff", "Apr 2024"),
        ]
        for k, v in specs_data:
            lbl_k = QLabel(k, self.model_card)
            lbl_k.setStyleSheet("font-size: 10px; color: #64748B; margin-top: 4px;")
            lbl_v = QLabel(v, self.model_card)
            lbl_v.setStyleSheet("font-size: 11px; font-weight: 500;")
            card_layout.addWidget(lbl_k)
            card_layout.addWidget(lbl_v)

        details_btn = QPushButton("Model details  ›", self.model_card)
        details_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                text-align: left;
                font-size: 11px;
                color: #64748B;
                padding-top: 6px;
                cursor: pointer;
            }
            QPushButton:hover {
                color: #2563EB;
            }
        """)
        details_btn.clicked.connect(self.model_details_requested.emit)
        card_layout.addWidget(details_btn)

        main_layout.addWidget(self.model_card)

        # ── 2. System Status ──
        status_box = QFrame(self)
        status_box.setStyleSheet("background: transparent;")
        status_layout = QVBoxLayout(status_box)
        status_layout.setContentsMargins(0, 4, 0, 4)
        status_layout.setSpacing(4)

        status_lbl = QLabel("System status", self)
        status_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #64748B;")
        status_layout.addWidget(status_lbl)

        live_row = QHBoxLayout()
        live_dot = QLabel("●", self)
        live_dot.setStyleSheet("color: #10B981; font-size: 10px; margin-right: 4px;")
        self.live_text = QLabel("All systems operational", self)
        self.live_text.setStyleSheet("font-size: 11px; font-weight: 500;")
        live_row.addWidget(live_dot)
        live_row.addWidget(self.live_text)
        live_row.addStretch(1)
        status_layout.addLayout(live_row)
        main_layout.addWidget(status_box)

        # ── 3. Pinned Files (RAG Memory) ──
        files_header = QHBoxLayout()
        pinned_lbl = QLabel("Pinned files", self)
        pinned_lbl.setStyleSheet("font-size: 12px; font-weight: 600;")
        edit_btn = QLabel("Edit", self)
        edit_btn.setStyleSheet("font-size: 11px; color: #2563EB; cursor: pointer;")
        files_header.addWidget(pinned_lbl)
        files_header.addStretch(1)
        files_header.addWidget(edit_btn)
        main_layout.addLayout(files_header)

        # Pinned files list
        files_container = QFrame(self)
        files_container.setStyleSheet("background: transparent;")
        files_layout = QVBoxLayout(files_container)
        files_layout.setContentsMargins(0, 0, 0, 0)
        files_layout.setSpacing(4)

        files_layout.addWidget(PinnedFileRow("PDF", "#EF4444", "Q2 Investor Deck.pdf", "12.4 MB", self))
        files_layout.addWidget(PinnedFileRow("XLS", "#10B981", "Product Roadmap.xlsx", "8.7 MB", self))
        files_layout.addWidget(PinnedFileRow("MD", "#3B82F6", "Market Research.md", "6.1 MB", self))
        main_layout.addWidget(files_container)

        # 'View all files' button
        self.view_files_btn = QPushButton("View all files", self)
        self.view_files_btn.setFixedHeight(34)
        self.view_files_btn.setCursor(Qt.PointingHandCursor)
        self.view_files_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid rgba(148, 163, 184, 0.25);
                border-radius: 8px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: rgba(148, 163, 184, 0.10);
            }
        """)
        self.view_files_btn.clicked.connect(self.view_all_files_requested.emit)
        main_layout.addWidget(self.view_files_btn)

        main_layout.addStretch(1)

    def update_model(self, model_name: str):
        self.model_title.setText(model_name)
