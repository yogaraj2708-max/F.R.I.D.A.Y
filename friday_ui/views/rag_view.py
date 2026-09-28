"""
F.R.I.D.A.Y. 3.0 - Files & Document Intelligence View
Unified Workspace for Document Ingestion, Previewing, and Local Vector Retrieval.

Consumes centralized ThemeTokens with accessible widget identifiers.
"""

import os
import glob
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QFileDialog, QListWidget, QListWidgetItem, QSplitter,
    QTextBrowser
)
from qfluentwidgets import (
    PrimaryPushButton, PushButton, LineEdit, TextEdit,
    ComboBox, FluentIcon, InfoBar, InfoBarPosition, CardWidget,
    TransparentToolButton
)

from friday_ui.core.config import DOCUMENTS_DIR
from friday_ui.styles.themes import get_current_palette, get_theme_palette, TOKENS


class DocumentsView(QWidget):
    """
    Unified Files & Document Intelligence Workspace.
    Provides document browsing, file previewing, ingestion into ChromaDB,
    and semantic vector retrieval.
    """
    document_ingested = Signal(str, str)  # title, path
    query_requested = Signal(str)         # search_query

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("documents_view")
        self.setAccessibleName("Files and Documents Workspace")
        self._init_ui()
        self._load_documents_list()

    def _init_ui(self):
        p = get_current_palette()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # ── Header ──────────────────────────────────────────
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        self.title_label = QLabel("FILES & DOCUMENTS")
        self.title_label.setFont(QFont("Inter", 12, QFont.Bold))
        self.title_label.setStyleSheet(f"color: {p['text_primary']}; letter-spacing: 0.5px;")

        self.subtitle_label = QLabel("Local document intelligence, context analysis, and semantic vector storage")
        self.subtitle_label.setFont(QFont("Inter", 8))
        self.subtitle_label.setStyleSheet(f"color: {p['text_muted']};")

        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        header_row.addLayout(title_box)
        header_row.addStretch(1)

        self.open_dir_btn = PushButton(FluentIcon.FOLDER, "Open Workspace", self)
        self.open_dir_btn.setObjectName("open_workspace_btn")
        self.open_dir_btn.setAccessibleName("Open workspace folder in File Explorer")
        self.open_dir_btn.clicked.connect(self._open_workspace_folder)
        header_row.addWidget(self.open_dir_btn)

        layout.addLayout(header_row)

        # ── Main 2-Pane Splitter (Files list on left, Preview / Search on right) ──
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: rgba(255, 255, 255, 0.05);
                width: 4px;
            }
        """)

        # ── LEFT PANE: Document Browser & Ingestion ─────────
        left_card = CardWidget(splitter)
        left_card.setObjectName("leftDocCard")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)

        left_header = QLabel("Workspace Documents")
        left_header.setFont(QFont("Inter", 10, QFont.Bold))
        left_header.setStyleSheet(f"color: {p['text_primary']};")
        left_layout.addWidget(left_header)

        # Filter / Search documents
        self.doc_search_input = LineEdit(left_card)
        self.doc_search_input.setObjectName("doc_search_input")
        self.doc_search_input.setAccessibleName("Filter documents")
        self.doc_search_input.setPlaceholderText("Filter documents...")
        self.doc_search_input.setClearButtonEnabled(True)
        self.doc_search_input.textChanged.connect(self._filter_document_list)
        left_layout.addWidget(self.doc_search_input)

        # File List Widget
        self.doc_list = QListWidget(left_card)
        self.doc_list.setObjectName("doc_list")
        self.doc_list.setAccessibleName("List of available documents")
        self.doc_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {p['bg_input']};
                border: 1px solid {p['border_card']};
                border-radius: 8px;
                color: {p['text_primary']};
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 7px 10px;
                border-radius: 6px;
                margin-bottom: 2px;
            }}
            QListWidget::item:hover {{
                background-color: {p['bg_card_hover']};
            }}
            QListWidget::item:selected {{
                background-color: {p['selection_bg']};
                color: {p['text_primary']};
            }}
        """)
        self.doc_list.currentItemChanged.connect(self._on_doc_selected)
        left_layout.addWidget(self.doc_list, 1)

        # Ingestion Controls
        ingest_box = QVBoxLayout()
        ingest_box.setSpacing(6)

        ingest_label = QLabel("Ingest Local Document:")
        ingest_label.setFont(QFont("Inter", 8, QFont.Bold))
        ingest_label.setStyleSheet(f"color: {p['text_secondary']};")
        ingest_box.addWidget(ingest_label)

        pick_row = QHBoxLayout()
        pick_row.setSpacing(6)

        self.file_path_edit = LineEdit(left_card)
        self.file_path_edit.setObjectName("file_path_edit")
        self.file_path_edit.setAccessibleName("Selected file path for ingestion")
        self.file_path_edit.setPlaceholderText("Select file path...")
        pick_row.addWidget(self.file_path_edit, 1)

        self.browse_btn = PushButton(FluentIcon.FOLDER, "Browse", left_card)
        self.browse_btn.setObjectName("browse_doc_btn")
        self.browse_btn.setAccessibleName("Browse file dialog")
        self.browse_btn.clicked.connect(self._browse_file)
        self.browse_doc_btn = self.browse_btn
        pick_row.addWidget(self.browse_btn)

        ingest_box.addLayout(pick_row)

        self.category_combo = ComboBox(left_card)
        self.category_combo.setObjectName("category_combo")
        self.category_combo.setAccessibleName("Select document knowledge domain")
        self.category_combo.addItems([
            "Project Documentation & Architecture",
            "Technical & Programming Manuals",
            "Personal Notes & Directives",
            "General Knowledge & Reference"
        ])
        ingest_box.addWidget(self.category_combo)

        self.ingest_btn = PrimaryPushButton(FluentIcon.ADD, "Ingest to Vector Index", left_card)
        self.ingest_btn.setObjectName("ingest_btn")
        self.ingest_btn.setAccessibleName("Ingest document to vector database")
        self.ingest_btn.clicked.connect(self._on_ingest_clicked)
        ingest_box.addWidget(self.ingest_btn)

        left_layout.addLayout(ingest_box)
        splitter.addWidget(left_card)

        # ── RIGHT PANE: Document Preview & Semantic Retrieval ──
        right_card = CardWidget(splitter)
        right_card.setObjectName("rightDocCard")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(14, 14, 14, 14)
        right_layout.setSpacing(10)

        right_top_row = QHBoxLayout()
        right_top_row.setSpacing(8)

        self.preview_header = QLabel("Document Preview & Details")
        self.preview_header.setFont(QFont("Inter", 10, QFont.Bold))
        self.preview_header.setStyleSheet(f"color: {p['text_primary']};")
        right_top_row.addWidget(self.preview_header)
        right_top_row.addStretch(1)

        self.doc_meta_badge = QLabel("Select a document")
        self.doc_meta_badge.setFont(QFont("Consolas", 8))
        self.doc_meta_badge.setStyleSheet(f"""
            color: {p['text_muted']};
            background-color: {p['chip_bg']};
            border: 1px solid {p['border_subtle']};
            border-radius: 6px;
            padding: 2px 8px;
        """)
        right_top_row.addWidget(self.doc_meta_badge)

        right_layout.addLayout(right_top_row)

        # Document content preview browser
        self.preview_browser = QTextBrowser(right_card)
        self.preview_browser.setObjectName("doc_preview_browser")
        self.preview_browser.setAccessibleName("Document content preview")
        self.preview_browser.setOpenExternalLinks(True)
        self.preview_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {p['bg_input']};
                border: 1px solid {p['border_card']};
                color: {p['text_primary']};
                border-radius: 8px;
                padding: 10px;
                font-size: 12.5px;
                line-height: 1.5;
            }}
        """)
        self.preview_browser.setMarkdown(
            "### Document Intelligence Standing By\n\n"
            "Select any document from the workspace list to view its contents, or use the semantic search below."
        )
        self.doc_preview_browser = self.preview_browser
        right_layout.addWidget(self.preview_browser, 1)

        # Semantic Search Bar
        query_bar = QHBoxLayout()
        query_bar.setSpacing(8)

        self.search_input = LineEdit(right_card)
        self.search_input.setObjectName("search_input")
        self.search_input.setAccessibleName("Semantic vector query input")
        self.search_input.setPlaceholderText("Search knowledge base (e.g. 'Project architecture', 'API endpoints')...")
        self.search_input.returnPressed.connect(self._on_search_clicked)
        query_bar.addWidget(self.search_input, 1)

        self.search_btn = PrimaryPushButton(FluentIcon.SEARCH, "Search", right_card)
        self.search_btn.setObjectName("search_btn")
        self.search_btn.setAccessibleName("Execute semantic search")
        self.search_btn.clicked.connect(self._on_search_clicked)
        query_bar.addWidget(self.search_btn)

        right_layout.addLayout(query_bar)

        # Results area
        self.results_edit = TextEdit(right_card)
        self.results_edit.setObjectName("results_edit")
        self.results_edit.setAccessibleName("Semantic search results")
        self.results_edit.setReadOnly(True)
        self.results_edit.setFixedHeight(110)
        self.results_edit.setPlaceholderText("Vector retrieval results will appear here...")
        self.results_edit.setStyleSheet(f"""
            TextEdit {{
                background-color: {p['bg_input']};
                border: 1px solid {p['border_card']};
                color: {p['text_secondary']};
                border-radius: 8px;
                padding: 6px;
                font-size: 11.5px;
            }}
        """)
        right_layout.addWidget(self.results_edit)

        splitter.addWidget(right_card)
        splitter.setSizes([340, 660])

        layout.addWidget(splitter, 1)

    def _open_workspace_folder(self):
        try:
            os.makedirs(DOCUMENTS_DIR, exist_ok=True)
            os.startfile(DOCUMENTS_DIR)
        except Exception as e:
            InfoBar.warning("Cannot Open Folder", str(e), parent=self, position=InfoBarPosition.TOP_RIGHT)

    def _load_documents_list(self):
        self.doc_list.clear()
        os.makedirs(DOCUMENTS_DIR, exist_ok=True)
        patterns = ["*.txt", "*.md", "*.py", "*.json", "*.pdf", "*.docx", "*.csv"]
        found_files = []
        for pat in patterns:
            found_files.extend(glob.glob(os.path.join(DOCUMENTS_DIR, pat)))

        # Also inspect project root for key documents
        root_dir = os.path.abspath(os.path.join(DOCUMENTS_DIR, ".."))
        for pat in ["*.md", "*.txt"]:
            for f in glob.glob(os.path.join(root_dir, pat)):
                if f not in found_files:
                    found_files.append(f)

        found_files = sorted(set(found_files))

        if not found_files:
            empty_item = QListWidgetItem("No local documents found in workspace")
            empty_item.setFlags(Qt.NoItemFlags)
            self.doc_list.addItem(empty_item)
            return

        for fpath in found_files:
            fname = os.path.basename(fpath)
            try:
                sz = os.path.getsize(fpath)
                sz_str = f"{sz / 1024:.1f} KB" if sz >= 1024 else f"{sz} B"
            except Exception:
                sz_str = ""

            icon_char = "📄"
            if fname.endswith(".pdf"):
                icon_char = "📕"
            elif fname.endswith((".py", ".js", ".ts", ".json")):
                icon_char = "💻"
            elif fname.endswith(".md"):
                icon_char = "📝"

            item = QListWidgetItem(f"{icon_char}  {fname}  ({sz_str})")
            item.setData(Qt.UserRole, fpath)
            self.doc_list.addItem(item)

    def _filter_document_list(self, text: str):
        query = text.strip().lower()
        for i in range(self.doc_list.count()):
            item = self.doc_list.item(i)
            item.setHidden(query not in item.text().lower())

    def _on_doc_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        if not current:
            return
        fpath = current.data(Qt.UserRole)
        if not fpath or not os.path.exists(fpath):
            return

        fname = os.path.basename(fpath)
        ext = os.path.splitext(fname)[1].lower()
        try:
            sz = os.path.getsize(fpath)
            sz_str = f"{sz / 1024:.1f} KB" if sz >= 1024 else f"{sz} B"
        except Exception:
            sz_str = "File"

        self.preview_header.setText(f"Preview: {fname}")
        self.doc_meta_badge.setText(f"{ext.upper() or 'FILE'} • {sz_str}")

        try:
            if ext in [".txt", ".md", ".py", ".json", ".csv", ".log", ".yaml", ".yml"]:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(6000)
                if ext == ".md":
                    self.preview_browser.setMarkdown(content)
                else:
                    self.preview_browser.setPlainText(content)
            elif ext == ".pdf":
                self.preview_browser.setMarkdown(
                    f"### PDF Document: *{fname}*\n\n"
                    f"- **Path**: `{fpath}`\n"
                    f"- **Size**: {sz_str}\n\n"
                    f"> PDF ready for deep forensic analysis, citation retrieval, or direct agent query."
                )
            elif ext in [".docx", ".doc"]:
                self.preview_browser.setMarkdown(
                    f"### DOCX Document: *{fname}*\n\n"
                    f"- **Path**: `{fpath}`\n"
                    f"- **Size**: {sz_str}\n\n"
                    f"> Word document ready for structural extraction and semantic indexing."
                )
            else:
                self.preview_browser.setPlainText(f"File: {fname} ({sz_str})\nPath: {fpath}")
        except Exception as e:
            self.preview_browser.setPlainText(f"Could not load preview for {fname}: {e}")

    def _browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Document to Ingest", os.path.expanduser("~"),
            "Supported Files (*.txt *.md *.pdf *.docx *.py *.json *.csv);;All Files (*.*)"
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
            f"'{title}' dispatched to the local neural vector index.",
            parent=self,
            position=InfoBarPosition.TOP_RIGHT
        )
        self.file_path_edit.clear()
        self._load_documents_list()

    def _on_search_clicked(self):
        q = self.search_input.text().strip()
        if q:
            self.query_requested.emit(q)
            self.results_edit.setMarkdown(
                f"### Semantic Query: *{q}*\n\n"
                f"- **Domain**: {self.category_combo.currentText()}\n"
                f"- **Status**: Scanning local vector chunks in `ChromaDB`...\n"
                f"- **Result**: Retrieval dispatched successfully."
            )

    def apply_theme(self, theme_mode: str = None):
        """Dynamically applies theme palette across documents view."""
        p = get_theme_palette(theme_mode)
        if hasattr(self, 'title_label'):
            self.title_label.setStyleSheet(f"color: {p['text_primary']}; letter-spacing: 0.5px;")
        if hasattr(self, 'subtitle_label'):
            self.subtitle_label.setStyleSheet(f"color: {p['text_muted']};")


# Backward compatibility alias
RAGView = DocumentsView
