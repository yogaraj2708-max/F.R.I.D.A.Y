"""
F.R.I.D.A.Y. 2.0 - Left Navigation & History Sidebar
Modern 3-column desktop sidebar matching reference design:
- Top '+ New chat' action button
- 'RECENT' scrollable conversation session history list
- 'Usage this month' token progress indicator card
- Bottom User Profile card with initials and organization
"""

import datetime
from typing import Optional, List, Dict, Any
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QColor, QPainter, QBrush, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QProgressBar, QSizePolicy
)

from friday_ui.core.session_store import SessionStore
from friday_core.settings import settings


class SidebarSessionButton(QPushButton):
    """Clean chat session row button with document icon and timestamp."""
    def __init__(self, session_id: str, title: str, timestamp_str: str = "", is_active: bool = False, parent=None):
        super().__init__(parent)
        self.session_id = session_id
        self.setObjectName("chatSessionItem")
        self.setProperty("active", "true" if is_active else "false")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(38)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        # Icon
        self.icon_label = QLabel("💬")
        self.icon_label.setStyleSheet("font-size: 13px; color: #94A3B8; background: transparent;")
        layout.addWidget(self.icon_label)

        # Title
        display_title = title if len(title) <= 24 else title[:22] + "..."
        self.title_label = QLabel(display_title)
        self.title_label.setStyleSheet("background: transparent; font-size: 13px; font-weight: 500;")
        layout.addWidget(self.title_label, 1)

        # Timestamp / Pin
        if timestamp_str:
            self.time_label = QLabel(timestamp_str)
            self.time_label.setStyleSheet("font-size: 10px; color: #64748B; background: transparent;")
            layout.addWidget(self.time_label)

    def set_active(self, active: bool):
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class SidebarView(QWidget):
    """
    3-Column Layout: Left Sidebar
    Houses '+ New chat', 'RECENT' history list, monthly usage telemetry, and profile footer.
    """
    new_chat_requested = Signal()
    session_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebarView")
        self.setFixedWidth(260)
        self.active_session_id = None
        self.session_store = SessionStore()

        self._init_ui()
        self.refresh_sessions()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 16, 14, 14)
        main_layout.setSpacing(10)

        # 1. '+ New chat' Button
        self.new_chat_btn = QPushButton("＋  New chat", self)
        self.new_chat_btn.setObjectName("newChatBtn")
        self.new_chat_btn.setFixedHeight(40)
        self.new_chat_btn.setCursor(Qt.PointingHandCursor)
        self.new_chat_btn.clicked.connect(self._on_new_chat_clicked)
        main_layout.addWidget(self.new_chat_btn)

        # 2. 'RECENT' Section Label
        self.recent_header = QLabel("RECENT", self)
        self.recent_header.setObjectName("sidebarSectionLabel")
        main_layout.addWidget(self.recent_header)

        # 3. Scroll Area for Recent Chats
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.session_list_container = QWidget()
        self.session_list_container.setStyleSheet("background: transparent;")
        self.session_list_layout = QVBoxLayout(self.session_list_container)
        self.session_list_layout.setContentsMargins(0, 0, 0, 0)
        self.session_list_layout.setSpacing(4)
        self.session_list_layout.addStretch(1)

        self.scroll_area.setWidget(self.session_list_container)
        main_layout.addWidget(self.scroll_area, 1)

        # 4. Usage This Month Card
        self.usage_card = QFrame(self)
        self.usage_card.setObjectName("usageCard")
        usage_layout = QVBoxLayout(self.usage_card)
        usage_layout.setContentsMargins(12, 10, 12, 10)
        usage_layout.setSpacing(6)

        usage_title = QLabel("Usage this month", self.usage_card)
        usage_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #64748B;")
        usage_layout.addWidget(usage_title)

        usage_numbers_layout = QHBoxLayout()
        self.usage_tokens = QLabel("24.6K / 100K tokens", self.usage_card)
        self.usage_tokens.setStyleSheet("font-size: 12px; font-weight: 600;")
        self.usage_percent = QLabel("24%", self.usage_card)
        self.usage_percent.setStyleSheet("font-size: 11px; color: #64748B; font-weight: 500;")
        usage_numbers_layout.addWidget(self.usage_tokens)
        usage_numbers_layout.addStretch(1)
        usage_numbers_layout.addWidget(self.usage_percent)
        usage_layout.addLayout(usage_numbers_layout)

        # Custom Styled Progress Bar
        self.progress_bar = QProgressBar(self.usage_card)
        self.progress_bar.setFixedHeight(5)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(24)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(148, 163, 184, 0.20);
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #2563EB;
                border-radius: 2px;
            }
        """)
        usage_layout.addWidget(self.progress_bar)

        reset_label = QLabel("Resets in 12 days", self.usage_card)
        reset_label.setStyleSheet("font-size: 10px; color: #64748B;")
        usage_layout.addWidget(reset_label)

        main_layout.addWidget(self.usage_card)

        # 5. User Profile Footer Card
        self.profile_footer = QFrame(self)
        self.profile_footer.setObjectName("profileFooterCard")
        profile_layout = QHBoxLayout(self.profile_footer)
        profile_layout.setContentsMargins(6, 8, 6, 8)
        profile_layout.setSpacing(10)

        # Avatar Initial Badge
        self.avatar_badge = QLabel("JD", self.profile_footer)
        self.avatar_badge.setFixedSize(32, 32)
        self.avatar_badge.setAlignment(Qt.AlignCenter)
        self.avatar_badge.setStyleSheet("""
            background-color: #2563EB;
            color: #FFFFFF;
            font-weight: 700;
            font-size: 12px;
            border-radius: 16px;
        """)
        profile_layout.addWidget(self.avatar_badge)

        # Name and Org
        info_layout = QVBoxLayout()
        info_layout.setSpacing(1)
        user_name = settings.get("user_name", "Jane Doe")
        self.name_label = QLabel(user_name, self.profile_footer)
        self.name_label.setStyleSheet("font-size: 12px; font-weight: 600;")
        self.org_label = QLabel("Acme Corporation", self.profile_footer)
        self.org_label.setStyleSheet("font-size: 10px; color: #64748B;")
        info_layout.addWidget(self.name_label)
        info_layout.addWidget(self.org_label)
        profile_layout.addLayout(info_layout, 1)

        # Caret icon
        caret = QLabel("⌄", self.profile_footer)
        caret.setStyleSheet("font-size: 14px; color: #64748B;")
        profile_layout.addWidget(caret)

        main_layout.addWidget(self.profile_footer)

    def refresh_sessions(self):
        """Loads sessions from SQLite store, populating starter items if new."""
        # Clear existing items
        while self.session_list_layout.count() > 1:
            item = self.session_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        sessions = []
        try:
            sessions = self.session_store.list_sessions()
        except Exception:
            pass

        # If store has no sessions yet, provide clean initial items matching reference
        if not sessions:
            starter_sessions = [
                {"id": "market-entry", "title": "Market entry strategy", "time": "10:42 AM"},
                {"id": "q2-financial", "title": "Q2 financial summary", "time": "Yesterday"},
                {"id": "user-research", "title": "User research synthesis", "time": "Yesterday"},
                {"id": "comp-landscape", "title": "Competitive landscape", "time": "May 18"},
                {"id": "prod-roadmap", "title": "Product roadmap ideas", "time": "May 17"},
                {"id": "exec-briefing", "title": "Executive briefing", "time": "May 16"},
                {"id": "hiring-plan", "title": "Hiring plan outline", "time": "May 15"},
            ]
            for s in starter_sessions:
                btn = SidebarSessionButton(
                    session_id=s["id"],
                    title=s["title"],
                    timestamp_str=s["time"],
                    is_active=(s["id"] == self.active_session_id),
                    parent=self.session_list_container
                )
                btn.clicked.connect(lambda checked=False, sid=s["id"]: self._on_session_clicked(sid))
                self.session_list_layout.insertWidget(self.session_list_layout.count() - 1, btn)
            return

        for s in sessions:
            title = s.get("title", "Conversation")
            sid = s.get("id", "")
            time_str = ""
            updated = s.get("updated_at")
            if updated:
                try:
                    dt = datetime.datetime.fromisoformat(updated)
                    time_str = dt.strftime("%b %d")
                except Exception:
                    pass

            btn = SidebarSessionButton(
                session_id=sid,
                title=title,
                timestamp_str=time_str,
                is_active=(sid == self.active_session_id),
                parent=self.session_list_container
            )
            btn.clicked.connect(lambda checked=False, s_id=sid: self._on_session_clicked(s_id))
            self.session_list_layout.insertWidget(self.session_list_layout.count() - 1, btn)

    def set_active_session(self, session_id: str):
        self.active_session_id = session_id
        for i in range(self.session_list_layout.count() - 1):
            w = self.session_list_layout.itemAt(i).widget()
            if isinstance(w, SidebarSessionButton):
                w.set_active(w.session_id == session_id)

    def _on_session_clicked(self, session_id: str):
        self.set_active_session(session_id)
        self.session_selected.emit(session_id)

    def _on_new_chat_clicked(self):
        self.set_active_session(None)
        self.new_chat_requested.emit()
