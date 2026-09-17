"""
F.R.I.D.A.Y. 2.0 - Deep Research View
Autonomous multi-step internet research & synthesis with DuckDuckGo
"""

import asyncio
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser,
    QProgressBar
)
from qfluentwidgets import (
    PrimaryPushButton, LineEdit, ComboBox, FluentIcon,
    CardWidget, InfoBar, InfoBarPosition
)

from duckduckgo_search import DDGS

class ResearchView(QWidget):
    """
    Autonomous deep research workspace.
    Executes live search queries, aggregates multi-source summaries, and produces comprehensive reports.
    """
    research_requested = Signal(str, str) # topic, depth

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
        title = QLabel("AUTONOMOUS DEEP RESEARCH")
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title.setStyleSheet("color: #FFFFFF; letter-spacing: 1px;")

        subtitle = QLabel("Multi-agent recursive search, citation synthesis, and intelligence gathering")
        subtitle.setFont(QFont("Segoe UI", 9))
        subtitle.setStyleSheet("color: #9CA3AF;")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        layout.addLayout(title_box)

        # Query Config Card
        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.query_input = LineEdit(self)
        self.query_input.setPlaceholderText("Enter research target (e.g. 'Latest AI benchmark results', 'RTX 3050 Ollama speed')...")
        self.query_input.returnPressed.connect(self._start_research)
        input_row.addWidget(self.query_input, 1)

        self.depth_combo = ComboBox(self)
        self.depth_combo.addItems(["Quick Intelligence (3 Sources)", "Deep Investigation (8 Sources)"])
        self.depth_combo.setFixedWidth(240)
        input_row.addWidget(self.depth_combo)

        self.start_btn = PrimaryPushButton(FluentIcon.SEARCH, "Conduct Research", self)
        self.start_btn.setStyleSheet("""
            PrimaryPushButton {
                background-color: #06B6D4;
                border: none;
                color: #000000;
                font-weight: bold;
                border-radius: 8px;
                padding: 6px 18px 6px 36px;
            }
            PrimaryPushButton:hover {
                background-color: #22D3EE;
            }
            PrimaryPushButton:pressed {
                background-color: #0891B2;
            }
        """)
        self.start_btn.clicked.connect(self._start_research)
        input_row.addWidget(self.start_btn)

        card_layout.addLayout(input_row)

        # Progress bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #18181B;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #06B6D4;
                border-radius: 2px;
            }
        """)
        card_layout.addWidget(self.progress_bar)

        layout.addWidget(card)

        # Report Viewer Card
        report_card = CardWidget(self)
        report_layout = QVBoxLayout(report_card)
        report_layout.setContentsMargins(16, 16, 16, 16)
        report_layout.setSpacing(8)

        report_header = QLabel("Intelligence Dossier / Synthesized Report")
        report_header.setFont(QFont("Segoe UI", 11, QFont.Bold))
        report_header.setStyleSheet("color: #FFFFFF;")
        report_layout.addWidget(report_header)

        self.report_browser = QTextBrowser(self)
        self.report_browser.setOpenExternalLinks(True)
        self.report_browser.setStyleSheet("""
            QTextBrowser {
                background-color: rgba(14, 17, 24, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.08);
                color: #E2E8F0;
                border-radius: 6px;
                padding: 12px;
                font-size: 13px;
            }
        """)
        self.report_browser.setMarkdown(
            "### Standing By for Intelligence Directives\n\n"
            "Autonomous Deep Research agent is ready to query DuckDuckGo, extract structured summaries, "
            "and format an executive briefing for you, Boss."
        )
        report_layout.addWidget(self.report_browser, 1)

        layout.addWidget(report_card, 1)

    def _start_research(self):
        topic = self.query_input.text().strip()
        if not topic:
            InfoBar.warning("Input Needed", "Please specify a research target.", parent=self, position=InfoBarPosition.TOP_RIGHT)
            return

        self.start_btn.setEnabled(False)
        self.progress_bar.setValue(30)
        self.report_browser.setMarkdown(f"### Investigating: *{topic}*\n\n> Dispatching background crawlers across search engines...")

        self.research_requested.emit(topic, self.depth_combo.currentText())

    def update_report(self, topic: str, markdown_content: str):
        self.progress_bar.setValue(100)
        self.start_btn.setEnabled(True)
        self.report_browser.setMarkdown(markdown_content)
