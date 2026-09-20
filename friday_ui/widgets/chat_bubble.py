"""
F.R.I.D.A.Y. 2.0 - Chat Bubble Component
Premium Glassmorphic Message Card with Markdown, Hover Effects & 60FPS Animations
"""

import math
from datetime import datetime
from PySide6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, Property,
    QParallelAnimationGroup, QTimer, QRectF, QPointF
)
from PySide6.QtGui import (
    QFont, QColor, QPainter, QPen
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser,
    QFrame, QApplication, QGraphicsOpacityEffect
)
from qfluentwidgets import TransparentToolButton, FluentIcon
from friday_core.settings import settings
from friday_ui.styles.themes import (
    MONO_DARK, fade_in, install_hover_reveal, install_button_micro_interaction,
    get_current_palette
)


class ChatBubble(QFrame):
    """
    Modern desktop chat message card (ChatGPT / Claude / Cursor aesthetic).
    Features:
    - Strict monochrome palette (black / white / zinc)
    - Asymmetric corner radius (user top-right 4px, assistant top-left 4px)
    - Hover-reveal copy utility
    - Code blocks with dark styling
    - Metadata pills (latency, AST verification)
    - Dynamic auto-expanding height (zero clipping)
    """
    def __init__(self, role: str, text: str = "", is_streaming: bool = False, status_text: str = "", parent=None):
        super().__init__(parent)
        import time
        self.role = role.lower()
        self.raw_text = text
        self.is_streaming = is_streaming
        self.status_text = status_text
        self.start_time = time.time()
        self.timestamp = datetime.now().strftime("%I:%M %p")
        self._slide_offset = 12.0
        self._init_ui()

        # 60 FPS Fade-in + slide entrance
        anim_level = settings.get("animation_level", "Full")
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        if anim_level == "Off":
            self.opacity_effect.setOpacity(1.0)
            self._slide_offset = 0.0
        else:
            duration = 200 if anim_level == "Full" else 100
            self.anim_group = QParallelAnimationGroup(self)

            self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
            self.fade_anim.setDuration(duration)
            self.fade_anim.setStartValue(0.0)
            self.fade_anim.setEndValue(1.0)
            self.fade_anim.setEasingCurve(QEasingCurve.OutCubic)
            self.anim_group.addAnimation(self.fade_anim)

            self.slide_anim = QPropertyAnimation(self, b"slide_offset")
            self.slide_anim.setDuration(duration)
            self.slide_anim.setStartValue(12.0)
            self.slide_anim.setEndValue(0.0)
            self.slide_anim.setEasingCurve(QEasingCurve.OutCubic)
            self.anim_group.addAnimation(self.slide_anim)

            self.anim_group.start()

    def get_slide_offset(self) -> float:
        return self._slide_offset

    def set_slide_offset(self, val: float):
        self._slide_offset = val
        top = int(10 + val)
        bottom = max(0, int(10 - val))
        if hasattr(self, 'main_layout'):
            self.main_layout.setContentsMargins(14, top, 14, bottom)

    slide_offset = Property(float, get_slide_offset, set_slide_offset)

    def _init_ui(self):
        p = get_current_palette()
        self.setFrameShape(QFrame.NoFrame)
        self.setCursor(Qt.ArrowCursor)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, int(10 + self._slide_offset), 16, max(0, int(10 - self._slide_offset)))
        self.main_layout.setSpacing(6)

        # ── Header Row ────────────────────────
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        # Role indicator dot & label
        self.badge = QLabel()
        badge_font = QFont("Segoe UI", 9, QFont.Bold)
        self.badge.setFont(badge_font)

        if self.role == "friday":
            self.badge.setText("● F.R.I.D.A.Y. 2.0")
            self.badge.setStyleSheet(f"color: {p['text_primary']}; font-weight: bold; background: transparent; border: none;")
        elif self.role == "user":
            name = str(settings.get("user_name", "Boss")).strip()
            title = str(settings.get("user_title", "Boss")).strip()
            if title and title.lower() not in ("none", ""):
                if name.lower() != title.lower():
                    badge_str = f"{title.upper()} ({name.upper()})"
                else:
                    badge_str = title.upper()
            else:
                badge_str = name.upper() if name else "OPERATOR"
            self.badge.setText(badge_str)
            self.badge.setStyleSheet(f"color: {p['text_primary']}; font-weight: bold; background: transparent; border: none;")
        else:
            self.badge.setText("SYSTEM")
            self.badge.setStyleSheet(f"color: {p['text_secondary']}; font-weight: bold; background: transparent; border: none;")

        header_layout.addWidget(self.badge)

        # Separator bullet
        bullet = QLabel("•")
        bullet.setStyleSheet(f"color: {p['text_dim']}; font-size: 10px;")
        header_layout.addWidget(bullet)

        # Timestamp
        time_label = QLabel(self.timestamp)
        time_label.setStyleSheet(f"color: {p['text_muted']}; font-size: 10px; font-family: monospace; background: transparent; border: none;")
        header_layout.addWidget(time_label)

        # Optional metadata pills for Friday responses
        if self.role == "friday":
            self.latency_pill = QLabel("···" if self.is_streaming else "0.12s latency")
            self.latency_pill.setStyleSheet(f"""
                color: {p['text_secondary']};
                background-color: {p['bg_surface']};
                border: 1px solid {p['border_card']};
                border-radius: 4px;
                font-family: monospace;
                font-size: 9px;
                padding: 1px 6px;
            """)
            header_layout.addWidget(self.latency_pill)

            self.ast_pill = QLabel("STREAMING" if self.is_streaming else "VERIFIED")
            if self.is_streaming:
                self.ast_pill.setStyleSheet(f"""
                    color: {p['accent']};
                    background-color: {p['accent_bg']};
                    border: 1px solid {p['accent_border']};
                    border-radius: 4px;
                    font-family: monospace;
                    font-size: 9px;
                    font-weight: bold;
                    padding: 1px 6px;
                """)
            else:
                self.ast_pill.setStyleSheet(f"""
                    color: {p['live_green']};
                    background-color: {p['live_green_bg']};
                    border: 1px solid {p['live_green_border']};
                    border-radius: 4px;
                    font-family: monospace;
                    font-size: 9px;
                    font-weight: bold;
                    padding: 1px 6px;
                """)
            header_layout.addWidget(self.ast_pill)

        header_layout.addStretch(1)

        # Hover-reveal Copy Button
        self.copy_btn = TransparentToolButton(FluentIcon.COPY, self)
        self.copy_btn.setFixedSize(24, 24)
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setToolTip("Copy response")
        self.copy_btn.clicked.connect(self._copy_content)
        install_button_micro_interaction(self.copy_btn)
        header_layout.addWidget(self.copy_btn)

        self.main_layout.addLayout(header_layout)

        # ── Content Card (Dynamic Auto-Expanding Markdown) ──
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.setReadOnly(True)
        self.text_browser.setLineWrapMode(QTextBrowser.WidgetWidth)
        self.text_browser.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.text_browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_browser.document().setDefaultFont(QFont("Inter", 10))

        # Theme-aware rich markdown stylesheet
        self.text_browser.document().setDefaultStyleSheet(f"""
            code {{
                background-color: {p['code_bg']};
                color: {p['code_text']};
                font-family: 'Consolas', 'Cascadia Code', monospace;
                padding: 2px 4px;
                border-radius: 4px;
                font-size: 12px;
            }}
            pre {{
                background-color: {p['code_block_bg']};
                color: {p['text_primary']};
                font-family: 'Consolas', 'Cascadia Code', monospace;
                border: 1px solid {p['code_border']};
                padding: 10px;
                border-radius: 6px;
                margin: 6px 0;
            }}
            h1 {{ color: {p['text_primary']}; font-size: 15px; margin: 8px 0; }}
            h2 {{ color: {p['text_primary']}; font-size: 14px; margin: 6px 0; }}
            h3 {{ color: {p['text_secondary']}; font-size: 13px; margin: 4px 0; }}
            a {{ color: {p['accent']}; text-decoration: none; }}
            blockquote {{
                border-left: 2px solid {p['text_dim']};
                margin: 4px 0;
                padding-left: 8px;
                color: {p['text_secondary']};
            }}
            ul, ol {{ margin: 4px 0; padding-left: 18px; }}
            li {{ margin-bottom: 2px; }}
        """)

        # Set raw markdown text or initial thinking placeholder
        if self.raw_text:
            self.text_browser.setMarkdown(self.raw_text)
        elif self.is_streaming:
            placeholder = self.status_text if self.status_text else "Neural core synthesizing response..."
            self.text_browser.setHtml(f"<div style='color: {p['text_muted']}; font-family: monospace; font-size: 12px; padding: 4px 0;'>⚡ {placeholder}</div>")

        # Connect document layout to dynamic height auto-expansion
        self.text_browser.document().documentLayout().documentSizeChanged.connect(self._adjust_height)

        # ── Role-specific Modern Card Geometry & Palette ──
        if self.role == "user":
            bubble_bg = p['bubble_user']
            margin_style = "margin: 3px 0px 3px 60px;"
        elif self.role == "friday":
            bubble_bg = p['bubble_assistant']
            margin_style = "margin: 3px 60px 3px 0px;"
        else:
            bubble_bg = p['bubble_system']
            margin_style = "margin: 3px 30px;"

        self.setStyleSheet(f"""
            ChatBubble {{
                background-color: {bubble_bg};
                border: 1px solid {p['border_card']};
                border-radius: 14px;
                {margin_style}
            }}
            ChatBubble:hover {{
                border: 1px solid {p['border_hover']};
            }}
            QTextBrowser {{
                background-color: transparent;
                border: none;
                color: {p['text_primary']};
                selection-background-color: {p['selection_bg']};
                selection-color: {p['text_primary']};
                padding: 0px 2px;
                font-size: 13px;
                line-height: 1.55;
            }}
        """)

        self.main_layout.addWidget(self.text_browser)

        # Install hover-reveal on copy button
        install_hover_reveal(self, [self.copy_btn])

        # Schedule initial height calculations as layout finishes rendering
        QTimer.singleShot(20, self._adjust_height)
        QTimer.singleShot(150, self._adjust_height)

    def _adjust_height(self, *args):
        """Dynamically computes the exact height required for full multi-paragraph/code text."""
        try:
            viewport_w = self.text_browser.viewport().width()
            if viewport_w > 10:
                self.text_browser.document().setTextWidth(viewport_w)
            doc_h = int(self.text_browser.document().size().height())
            target_h = max(doc_h + 18, 44)
            self.text_browser.setFixedHeight(target_h)
            self.updateGeometry()
        except Exception as ex:
            import logging
            logging.getLogger("FRIDAY.ChatBubble").debug("Height adjustment error: %s", ex)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_height()

    def append_token(self, token: str):
        """Appends a streamed token chunk in real time and smoothly expands height."""
        if not self.raw_text:
            self.raw_text = token
        else:
            self.raw_text += token
        self.text_browser.setMarkdown(self.raw_text)
        self._adjust_height()

    def set_status(self, status_text: str):
        """Updates the thinking or search status description before tokens stream."""
        self.status_text = status_text
        if not self.raw_text and self.is_streaming:
            p = get_current_palette()
            self.text_browser.setHtml(f"<div style='color: {p['text_muted']}; font-family: monospace; font-size: 12px; padding: 4px 0;'>⚡ {status_text}</div>")
            self._adjust_height()

    def finish_stream(self, final_text: str = None):
        """Finalizes the streaming session, updates latency pill, and marks verified."""
        import time
        self.is_streaming = False
        if final_text is not None:
            self.raw_text = final_text
        self.text_browser.setMarkdown(self.raw_text)

        elapsed = max(0.1, time.time() - self.start_time)
        if hasattr(self, 'latency_pill'):
            self.latency_pill.setText(f"{elapsed:.2f}s latency")
        if hasattr(self, 'ast_pill'):
            self.ast_pill.setText("VERIFIED")
            p = get_current_palette()
            self.ast_pill.setStyleSheet(f"""
                color: {p['live_green']};
                background-color: {p['live_green_bg']};
                border: 1px solid {p['live_green_border']};
                border-radius: 4px;
                font-family: monospace;
                font-size: 9px;
                font-weight: bold;
                padding: 1px 6px;
            """)
        self._adjust_height()

    def _copy_content(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.raw_text)
        self.copy_btn.setIcon(FluentIcon.ACCEPT)
        self.copy_btn.setToolTip("Copied!")
        QTimer.singleShot(1500, lambda: (self.copy_btn.setIcon(FluentIcon.COPY), self.copy_btn.setToolTip("Copy response")))
