"""
F.R.I.D.A.Y. 3.0 - Deep Research Workspace
Autonomous Multi-Source Web Investigation & Synthesis.

Features:
- Research command bar with depth selector
- Live task status stepper (Searching -> Fetching -> Analyzing -> Synthesizing)
- Dynamic compact source cards stream
- Executive synthesized briefing reader
- Centralized ThemeTokens consumption & accessible identifiers
"""

import os
from typing import List, Dict, Optional
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser,
    QProgressBar, QScrollArea, QFrame
)
from qfluentwidgets import (
    PrimaryPushButton, PushButton, LineEdit, ComboBox, FluentIcon,
    CardWidget, InfoBar, InfoBarPosition, TransparentToolButton
)

from friday_ui.styles.themes import get_current_palette, get_theme_palette, TOKENS, fade_in


class SourceCard(QFrame):
    """Compact source card for retrieved research evidence."""
    def __init__(self, domain: str, title: str, status: str = "Verified", relevance: str = "High", parent=None):
        super().__init__(parent)
        self.setObjectName("sourceCard")
        p = get_current_palette()
        self.setStyleSheet(f"""
            QFrame#sourceCard {{
                background-color: {p['bg_surface']};
                border: 1px solid {p['border_card']};
                border-radius: 8px;
                padding: 6px 10px;
            }}
            QFrame#sourceCard:hover {{
                border: 1px solid {p['border_hover']};
                background-color: {p['bg_card_hover']};
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        domain_label = QLabel(domain.upper())
        domain_label.setFont(QFont("Consolas", 8, QFont.Bold))
        domain_label.setStyleSheet(f"""
            color: {p['accent']};
            background-color: {p['accent_bg']};
            border: 1px solid {p['accent_border']};
            border-radius: 4px;
            padding: 1px 6px;
        """)
        top_row.addWidget(domain_label)

        status_label = QLabel(f"✓ {status}")
        status_label.setFont(QFont("Inter", 8))
        status_label.setStyleSheet(f"color: {p['live_green']};")
        top_row.addWidget(status_label)

        top_row.addStretch(1)

        rel_label = QLabel(f"Rel: {relevance}")
        rel_label.setFont(QFont("Consolas", 7))
        rel_label.setStyleSheet(f"color: {p['text_muted']};")
        top_row.addWidget(rel_label)

        layout.addLayout(top_row)

        title_lbl = QLabel(title[:65] + ("..." if len(title) > 65 else ""))
        title_lbl.setFont(QFont("Inter", 8, QFont.Medium))
        title_lbl.setStyleSheet(f"color: {p['text_primary']};")
        layout.addWidget(title_lbl)


class ResearchView(QWidget):
    """
    Autonomous Deep Research Workspace.
    Executes multi-step internet searches, extracts evidence sources, and
    compiles a verified intelligence briefing.
    """
    research_requested = Signal(str, str)  # topic, depth
    research_stopped = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("research_view")
        self.setAccessibleName("Autonomous Deep Research Workspace")
        self._is_active = False
        self._init_ui()

    def _init_ui(self):
        p = get_current_palette()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # ── Header ──────────────────────────────────────────
        header_box = QVBoxLayout()
        header_box.setSpacing(2)

        self.title_label = QLabel("AUTONOMOUS DEEP RESEARCH")
        self.title_label.setFont(QFont("Inter", 12, QFont.Bold))
        self.title_label.setStyleSheet(f"color: {p['text_primary']}; letter-spacing: 0.5px;")

        self.subtitle_label = QLabel("Recursive multi-agent investigation, evidence verification & synthesis")
        self.subtitle_label.setFont(QFont("Inter", 8))
        self.subtitle_label.setStyleSheet(f"color: {p['text_muted']};")

        header_box.addWidget(self.title_label)
        header_box.addWidget(self.subtitle_label)
        layout.addLayout(header_box)

        # ── Command Bar Card ────────────────────────────────
        cmd_card = CardWidget(self)
        cmd_card.setObjectName("researchCmdCard")
        cmd_layout = QVBoxLayout(cmd_card)
        cmd_layout.setContentsMargins(14, 12, 14, 12)
        cmd_layout.setSpacing(10)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.query_input = LineEdit(cmd_card)
        self.query_input.setObjectName("research_input")
        self.query_input.setAccessibleName("Research topic query input")
        self.query_input.setPlaceholderText("Ask anything about a topic (e.g. 'Latest frontier AI architectures', 'RTX 5090 compute benchmarks')...")
        self.query_input.setClearButtonEnabled(True)
        self.query_input.returnPressed.connect(self._start_research)
        input_row.addWidget(self.query_input, 1)

        self.depth_combo = ComboBox(cmd_card)
        self.depth_combo.setObjectName("research_depth_combo")
        self.depth_combo.setAccessibleName("Investigation depth selector")
        self.depth_combo.addItems([
            "Standard (4 Sources)",
            "Deep Comprehensive (8 Sources)",
            "Exhaustive Audit (12 Sources)"
        ])
        self.depth_combo.setFixedWidth(200)
        input_row.addWidget(self.depth_combo)

        self.start_btn = PrimaryPushButton(FluentIcon.SEARCH, "Conduct Research", cmd_card)
        self.start_btn.setObjectName("research_start_btn")
        self.start_btn.setAccessibleName("Start deep research investigation")
        self.start_btn.clicked.connect(self._start_research)
        input_row.addWidget(self.start_btn)

        self.stop_btn = PushButton("■ Stop", cmd_card)
        self.stop_btn.setObjectName("research_stop_btn")
        self.stop_btn.setAccessibleName("Stop research execution")
        self.stop_btn.setStyleSheet(f"""
            PushButton {{
                background-color: {p['danger_red_bg']};
                border: 1px solid {p['danger_red_border']};
                color: {p['danger_red']};
                font-weight: bold;
                border-radius: 8px;
                padding: 6px 14px;
            }}
            PushButton:hover {{
                background-color: {p['danger_red']};
                color: #FFFFFF;
            }}
        """)
        self.stop_btn.clicked.connect(self._stop_research)
        self.stop_btn.hide()
        input_row.addWidget(self.stop_btn)

        cmd_layout.addLayout(input_row)

        # ── Task Status Stepper Row ──────────────────────────
        self.stepper_frame = QFrame(cmd_card)
        self.stepper_frame.setObjectName("stepperFrame")
        st_layout = QHBoxLayout(self.stepper_frame)
        st_layout.setContentsMargins(0, 4, 0, 0)
        st_layout.setSpacing(12)

        self.step_labels = []
        step_names = ["1. Searching", "2. Fetching", "3. Analyzing", "4. Synthesizing"]
        for idx, name in enumerate(step_names):
            lbl = QLabel(name)
            lbl.setFont(QFont("Consolas", 8, QFont.Bold))
            lbl.setStyleSheet(f"color: {p['text_dim']};")
            self.step_labels.append(lbl)
            st_layout.addWidget(lbl)
            if idx < len(step_names) - 1:
                arrow = QLabel("→")
                arrow.setStyleSheet(f"color: {p['text_dim']}; font-size: 8px;")
                st_layout.addWidget(arrow)

        st_layout.addStretch(1)

        self.live_status_lbl = QLabel("Standing By")
        self.live_status_lbl.setFont(QFont("Inter", 8))
        self.live_status_lbl.setStyleSheet(f"color: {p['text_muted']};")
        st_layout.addWidget(self.live_status_lbl)

        cmd_layout.addWidget(self.stepper_frame)

        # Thin Progress Bar
        self.progress_bar = QProgressBar(cmd_card)
        self.progress_bar.setObjectName("research_progress_bar")
        self.progress_bar.setAccessibleName("Research progress bar")
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {p['bg_surface']};
                border: none;
                border-radius: 1.5px;
            }}
            QProgressBar::chunk {{
                background-color: {p['accent']};
                border-radius: 1.5px;
            }}
        """)
        cmd_layout.addWidget(self.progress_bar)

        layout.addWidget(cmd_card)

        # ── Live Sources Stream (Horizontal cards) ──────────
        self.sources_container = QFrame(self)
        self.sources_container.setObjectName("sourcesContainer")
        self.sources_container.setStyleSheet("background: transparent;")
        sources_vbox = QVBoxLayout(self.sources_container)
        sources_vbox.setContentsMargins(0, 0, 0, 0)
        sources_vbox.setSpacing(6)

        sources_header_row = QHBoxLayout()
        self.sources_title = QLabel("Verified Evidence Sources")
        self.sources_title.setFont(QFont("Inter", 9, QFont.Bold))
        self.sources_title.setStyleSheet(f"color: {p['text_secondary']};")
        sources_header_row.addWidget(self.sources_title)

        self.sources_count_lbl = QLabel("0 sources")
        self.sources_count_lbl.setFont(QFont("Consolas", 8))
        self.sources_count_lbl.setStyleSheet(f"color: {p['text_muted']};")
        sources_header_row.addWidget(self.sources_count_lbl)
        sources_header_row.addStretch(1)
        sources_vbox.addLayout(sources_header_row)

        self.sources_scroll = QScrollArea(self.sources_container)
        self.sources_scroll.setFixedHeight(64)
        self.sources_scroll.setWidgetResizable(True)
        self.sources_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.sources_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sources_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.sources_cards_widget = QWidget()
        self.sources_cards_widget.setStyleSheet("background: transparent;")
        self.sources_layout = QHBoxLayout(self.sources_cards_widget)
        self.sources_layout.setContentsMargins(0, 0, 0, 0)
        self.sources_layout.setSpacing(8)
        self.sources_layout.addStretch(1)

        self.sources_scroll.setWidget(self.sources_cards_widget)
        sources_vbox.addWidget(self.sources_scroll)
        self.sources_container.hide()
        layout.addWidget(self.sources_container)

        # ── Synthesized Report Viewer ────────────────────────
        report_card = CardWidget(self)
        report_card.setObjectName("researchReportCard")
        report_layout = QVBoxLayout(report_card)
        report_layout.setContentsMargins(14, 14, 14, 14)
        report_layout.setSpacing(8)

        rep_header_row = QHBoxLayout()
        rep_title = QLabel("Intelligence Dossier & Briefing")
        rep_title.setFont(QFont("Inter", 10, QFont.Bold))
        rep_title.setStyleSheet(f"color: {p['text_primary']};")
        rep_header_row.addWidget(rep_title)
        rep_header_row.addStretch(1)

        self.report_status_pill = QLabel("● IDLE")
        self.report_status_pill.setFont(QFont("Consolas", 8, QFont.Bold))
        self.report_status_pill.setStyleSheet(f"""
            color: {p['text_muted']};
            background-color: {p['bg_surface']};
            border: 1px solid {p['border_subtle']};
            border-radius: 4px;
            padding: 2px 8px;
        """)
        rep_header_row.addWidget(self.report_status_pill)
        report_layout.addLayout(rep_header_row)

        self.report_browser = QTextBrowser(report_card)
        self.report_browser.setObjectName("research_report_browser")
        self.report_browser.setAccessibleName("Synthesized research report")
        self.report_browser.setOpenExternalLinks(True)
        self.report_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {p['bg_input']};
                border: 1px solid {p['border_card']};
                color: {p['text_primary']};
                border-radius: 8px;
                padding: 12px;
                font-size: 13px;
                line-height: 1.6;
            }}
        """)
        self.report_browser.setMarkdown(
            "### Research Any Topic\n\n"
            "Enter a research target above to dispatch autonomous web crawlers, verify real external citations, "
            "and synthesize an executive intelligence briefing.\n\n"
            "**Example Directives**:\n"
            "- *State-of-the-art multimodal agent benchmarks*\n"
            "- *Local LLM quant comparative performance on consumer GPUs*\n"
            "- *Autonomous tool calling protocols with function signatures*"
        )
        report_layout.addWidget(self.report_browser, 1)

        layout.addWidget(report_card, 1)

    def set_stage(self, stage_idx: int, description: str = ""):
        """Updates active stepper phase (0=Search, 1=Fetch, 2=Analyze, 3=Synthesize)."""
        p = get_current_palette()
        for idx, lbl in enumerate(self.step_labels):
            if idx == stage_idx:
                lbl.setStyleSheet(f"color: {p['accent']}; font-weight: bold;")
            elif idx < stage_idx:
                lbl.setStyleSheet(f"color: {p['live_green']};")
            else:
                lbl.setStyleSheet(f"color: {p['text_dim']};")

        if description:
            self.live_status_lbl.setText(description)

    def add_source(self, domain: str, title: str, status: str = "Verified", relevance: str = "High"):
        """Appends a new compact source card into the live source stream."""
        self.sources_container.show()
        card = SourceCard(domain, title, status, relevance, self.sources_cards_widget)
        # Insert before stretch
        self.sources_layout.insertWidget(self.sources_layout.count() - 1, card)
        count = self.sources_layout.count() - 1
        self.sources_count_lbl.setText(f"{count} sources")

    def clear_sources(self):
        while self.sources_layout.count() > 1:
            item = self.sources_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.sources_count_lbl.setText("0 sources")
        self.sources_container.hide()

    def _start_research(self):
        topic = self.query_input.text().strip()
        if not topic:
            InfoBar.warning("Input Needed", "Please specify a research target.", parent=self, position=InfoBarPosition.TOP_RIGHT)
            return

        self._is_active = True
        self.start_btn.setEnabled(False)
        self.stop_btn.show()
        self.progress_bar.setValue(15)
        self.clear_sources()
        self.set_stage(0, "Querying search providers...")

        p = get_current_palette()
        self.report_status_pill.setText("● INVESTIGATING")
        self.report_status_pill.setStyleSheet(f"""
            color: {p['accent']};
            background-color: {p['accent_bg']};
            border: 1px solid {p['accent_border']};
            border-radius: 4px;
            padding: 2px 8px;
        """)

        self.report_browser.setMarkdown(
            f"### Investigating: *{topic}*\n\n"
            f"> Dispatching background search crawlers and validating source domains..."
        )

        self.research_requested.emit(topic, self.depth_combo.currentText())

    def _stop_research(self):
        self._is_active = False
        self.start_btn.setEnabled(True)
        self.stop_btn.hide()
        self.progress_bar.setValue(0)
        p = get_current_palette()
        self.report_status_pill.setText("● CANCELLED")
        self.report_status_pill.setStyleSheet(f"""
            color: {p['danger_red']};
            background-color: {p['danger_red_bg']};
            border: 1px solid {p['danger_red_border']};
            border-radius: 4px;
            padding: 2px 8px;
        """)
        self.live_status_lbl.setText("Research cancelled by operator")
        self.research_stopped.emit()

    def update_report(self, topic: str, markdown_content: str):
        """Called when research worker synthesizes final briefing."""
        self._is_active = False
        self.progress_bar.setValue(100)
        self.start_btn.setEnabled(True)
        self.stop_btn.hide()
        self.set_stage(3, "Investigation complete")

        p = get_current_palette()
        self.report_status_pill.setText("✓ COMPLETED")
        self.report_status_pill.setStyleSheet(f"""
            color: {p['live_green']};
            background-color: {p['live_green_bg']};
            border: 1px solid {p['live_green_border']};
            border-radius: 4px;
            padding: 2px 8px;
        """)
        self.report_browser.setMarkdown(markdown_content)
        fade_in(self.report_browser, duration=200)

    def apply_theme(self, theme_mode: str = None):
        """Updates palette dynamically across research controls."""
        p = get_theme_palette(theme_mode)
        if hasattr(self, 'title_label'):
            self.title_label.setStyleSheet(f"color: {p['text_primary']}; letter-spacing: 0.5px;")
        if hasattr(self, 'subtitle_label'):
            self.subtitle_label.setStyleSheet(f"color: {p['text_muted']};")
