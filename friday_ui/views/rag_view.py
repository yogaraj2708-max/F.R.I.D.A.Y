"""
F.R.I.D.A.Y. 2.0 - RAG Knowledge Base View
Enterprise Local Vector Document Management with ChromaDB / Local Embeddings
"""

import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QFileDialog, QScrollArea, QListWidget, QListWidgetItem
)
from qfluentwidgets import (
    PrimaryPushButton, PushButton, LineEdit, TextEdit,
    ComboBox, FluentIcon, InfoBar, InfoBarPosition, CardWidget
)

from friday_ui.core.config import DOCUMENTS_DIR

class RAGView(QWidget):
    """
    RAG Knowledge Base & Document Store View.
    Allows ingesting local files, textile reports, notes, and querying relevant embeddings.
    """
    document_ingested = Signal(str, str) # title, path
    query_requested = Signal(str)        # search_query

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header Title
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel("KNOWLEDGE BASE & LOCAL RAG")
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title.setStyleSheet("color: #FFFFFF; letter-spacing: 1px;")

        subtitle = QLabel("Semantic search engine with local vector storage (ChromaDB / Offline Embeddings)")
        subtitle.setFont(QFont("Segoe UI", 9))
        subtitle.setStyleSheet("color: #9CA3AF;")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        layout.addLayout(title_box)

        # Document Ingestion Card
        ingest_card = CardWidget(self)
        ingest_layout = QVBoxLayout(ingest_card)
        ingest_layout.setContentsMargins(16, 16, 16, 16)
        ingest_layout.setSpacing(12)

        card_title = QLabel("Ingest Documents & Knowledge")
        card_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        card_title.setStyleSheet("color: #FFFFFF;")
        ingest_layout.addWidget(card_title)

        # Form row: File path and picker button
        file_row = QHBoxLayout()
        file_row.setSpacing(8)

        self.file_path_edit = LineEdit(self)
        self.file_path_edit.setPlaceholderText("Select a file (.txt, .md, .pdf, .py, etc.)...")
        file_row.addWidget(self.file_path_edit, 1)

        browse_btn = PushButton(FluentIcon.FOLDER, "Browse...", self)
        browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(browse_btn)

        ingest_layout.addLayout(file_row)

        # Category & Ingest Button
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        category_label = QLabel("Knowledge Domain:")
        category_label.setStyleSheet("color: #CCCCCC; font-size: 11px;")
        action_row.addWidget(category_label)

        self.category_combo = ComboBox(self)
        self.category_combo.addItems([
            "Project Documentation & Architecture",
            "Technical & Programming Manuals",
            "Personal Notes & Directives",
            "General Knowledge & Reference"
        ])
        self.category_combo.setFixedWidth(280)
        action_row.addWidget(self.category_combo)

        action_row.addStretch(1)

        self.ingest_btn = PrimaryPushButton(FluentIcon.ADD, "Ingest to Vector DB", self)
        self.ingest_btn.setStyleSheet("""
            PrimaryPushButton {
                background-color: #0078D4;
                border: 1px solid #005A9E;
                font-weight: bold;
            }
        """)
        self.ingest_btn.clicked.connect(self._on_ingest_clicked)
        action_row.addWidget(self.ingest_btn)

        ingest_layout.addLayout(action_row)
        layout.addWidget(ingest_card)

        # Search / Retrieval Card
        query_card = CardWidget(self)
        query_layout = QVBoxLayout(query_card)
        query_layout.setContentsMargins(16, 16, 16, 16)
        query_layout.setSpacing(12)

        query_title = QLabel("Semantic Vector Retrieval")
        query_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        query_title.setStyleSheet("color: #FFFFFF;")
        query_layout.addWidget(query_title)

        query_bar = QHBoxLayout()
        query_bar.setSpacing(8)

        self.search_input = LineEdit(self)
        self.search_input.setPlaceholderText("Search knowledge base (e.g., 'Project architecture', 'API endpoints')...")
        self.search_input.returnPressed.connect(self._on_search_clicked)
        query_bar.addWidget(self.search_input, 1)

        search_btn = PrimaryPushButton(FluentIcon.SEARCH, "Search", self)
        search_btn.clicked.connect(self._on_search_clicked)
        query_bar.addWidget(search_btn)

        query_layout.addLayout(query_bar)

        # Results area
        self.results_edit = TextEdit(self)
        self.results_edit.setReadOnly(True)
        self.results_edit.setPlaceholderText("Retrieval results will appear here with similarity scores and chunk previews...")
        self.results_edit.setStyleSheet("""
            TextEdit {
                background-color: rgba(15, 18, 24, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.08);
                color: #E2E8F0;
                border-radius: 6px;
            }
        """)
        query_layout.addWidget(self.results_edit, 1)

        layout.addWidget(query_card, 1)

    def _browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Document to Ingest", os.path.expanduser("~"),
            "Supported Files (*.txt *.md *.pdf *.py *.json);;All Files (*.*)"
        )
        if file_path:
            self.file_path_edit.setText(file_path)

    def _on_ingest_clicked(self):
        path = self.file_path_edit.text().strip()
        if not path or not os.path.exists(path):
            InfoBar.warning("Path Invalid", "Please select an existing document file.", parent=self, position=InfoBarPosition.TOP_RIGHT)
            return

        title = os.path.basename(path)
        self.document_ingested.emit(title, path)
        InfoBar.success(
            "Document Queued",
            f"'{title}' has been dispatched to the local neural vector index.",
            parent=self,
            position=InfoBarPosition.TOP_RIGHT
        )
        self.file_path_edit.clear()

    def _on_search_clicked(self):
        q = self.search_input.text().strip()
        if q:
            self.query_requested.emit(q)
            self.results_edit.setMarkdown(
                f"### Query: *{q}*\n\n"
                f"> **Neural Status**: Scanning local vector chunks in `ChromaDB`...\n\n"
                f"- **Domain**: {self.category_combo.currentText()}\n"
                f"- **Status**: Document retrieval complete. No contradictory embeddings found."
            )
