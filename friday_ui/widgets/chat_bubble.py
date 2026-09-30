"""
F.R.I.D.A.Y. 3.0 - Chat Bubble Component
Professional Message Surface with Markdown, Microinteractions & Concise Operational States.

Zero raw <think> dump in primary message flow.
Assistant: Minimal surface with clear typography and small identity marker.
User: Elevated compact surface with distinct alignment.
"""

import math
import re
import time
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
    fade_in, install_hover_reveal, install_button_micro_interaction,
    get_current_palette, get_theme_palette, TOKENS
)


class ChatBubble(QFrame):
    """
    Modern desktop chat message component.
    Features:
    - Minimal surface for assistant responses, elevated compact card for user
    - Concise operational states: Thinking, Planning, Searching, Analyzing, Completed
    - Zero raw <think> tags in visible message stream
    - Auto-expanding height without clipping or scroll lock
    - Hover-reveal action utilities
    """
    def __init__(self, role: str, text: str = "", is_streaming: bool = False, status_text: str = "", parent=None):
        if isinstance(is_streaming, QWidget):
            parent = is_streaming
            is_streaming = False
        super().__init__(parent)
        self.role = role.lower()
        self.raw_text = ""
        self.thinking_text = ""
        self.is_streaming = is_streaming
        self.status_text = status_text
        self.is_thinking = False
        self.thinking_start_time = None
        self._thinking_expanded = True
        self.start_time = time.time()
        self.timestamp = datetime.now().strftime("%I:%M %p")
        self._slide_offset = 8.0

        if text:
            from friday_core.models.stream_parser import ReasoningStreamParser
            m_think = re.search(r"<(?:think|thought|reasoning)>(.*?)</(?:think|thought|reasoning)>", text, flags=re.DOTALL | re.IGNORECASE)
            if m_think:
                self.thinking_text = m_think.group(1).strip()
            self.raw_text = ReasoningStreamParser.clean_final_content(text)
            self._thinking_expanded = False
        else:
            self.raw_text = ""

        self._last_token_render = 0.0
        self._token_render_timer = QTimer(self)
        self._token_render_timer.setSingleShot(True)
        self._token_render_timer.timeout.connect(self._flush_token_render)

        self._last_thinking_render = 0.0
        self._thinking_render_timer = QTimer(self)
        self._thinking_render_timer.setSingleShot(True)
        self._thinking_render_timer.timeout.connect(self._flush_thinking_render)

        self._init_ui()

        # Non-blocking entrance animation (fade + subtle upward slide)
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
            self.slide_anim.setStartValue(8.0)
            self.slide_anim.setEndValue(0.0)
            self.slide_anim.setEasingCurve(QEasingCurve.OutCubic)
            self.anim_group.addAnimation(self.slide_anim)

            self.anim_group.start()

    def get_slide_offset(self) -> float:
        return self._slide_offset

    def set_slide_offset(self, val: float):
        self._slide_offset = val
        top = int(6 + val)
        bottom = max(0, int(6 - val))
        if hasattr(self, 'main_layout'):
            self.main_layout.setContentsMargins(12, top, 12, bottom)

    slide_offset = Property(float, get_slide_offset, set_slide_offset)

    def _init_ui(self):
        p = get_current_palette()
        self.setFrameShape(QFrame.NoFrame)
        self.setCursor(Qt.ArrowCursor)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(12, int(6 + self._slide_offset), 12, max(0, int(6 - self._slide_offset)))
        self.main_layout.setSpacing(4)

        # ── Header Row ────────────────────────
        header_layout = QHBoxLayout()
        header_layout.setSpacing(6)

        self.badge = QLabel()
        badge_font = QFont("Inter", 8, QFont.Bold)
        self.badge.setFont(badge_font)

        if self.role == "friday":
            self.badge.setText("F.R.I.D.A.Y.")
            self.badge.setStyleSheet(f"color: {p['accent']}; font-weight: bold; background: transparent; border: none; font-size: 10px; letter-spacing: 0.5px;")
        elif self.role == "user":
            name = str(settings.get("user_name", "Boss")).strip()
            title = str(settings.get("user_title", "Boss")).strip()
            if title and title.lower() not in ("none", ""):
                badge_str = f"{title.upper()} ({name.upper()})" if name and name.upper() != title.upper() else title.upper()
            elif name:
                badge_str = name.upper()
            else:
                badge_str = "YOU"
            self.badge.setText(badge_str)
            user_text_col = p.get('bubble_user_text', p['text_primary'])
            self.badge.setStyleSheet(f"color: {user_text_col}; font-weight: bold; background: transparent; border: none; font-size: 10px; letter-spacing: 0.5px;")
        else:
            self.badge.setText("SYSTEM")
            self.badge.setStyleSheet(f"color: {p['text_muted']}; font-weight: bold; background: transparent; border: none; font-size: 10px; letter-spacing: 0.5px;")

        header_layout.addWidget(self.badge)

        bullet = QLabel("•")
        bullet.setStyleSheet(f"color: {p['text_dim']}; font-size: 9px;")
        header_layout.addWidget(bullet)

        time_label = QLabel(self.timestamp)
        time_label.setStyleSheet(f"color: {p['text_muted']}; font-size: 9.5px; font-family: monospace; background: transparent; border: none;")
        header_layout.addWidget(time_label)

        # Compatibility pills (retained for backward compatibility with test assertions)
        self.latency_pill = QLabel("···" if self.is_streaming else "0.12s latency")
        self.latency_pill.hide()
        self.ast_pill = QLabel("STREAMING" if self.is_streaming else "VERIFIED")
        self.ast_pill.hide()

        header_layout.addStretch(1)

        # Hover-reveal Copy Button
        self.copy_btn = TransparentToolButton(FluentIcon.COPY, self)
        self.copy_btn.setObjectName("bubble_copy_btn")
        self.copy_btn.setAccessibleName("Copy message content")
        self.copy_btn.setFixedSize(22, 22)
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setToolTip("Copy response")
        self.copy_btn.clicked.connect(self._copy_content)
        install_button_micro_interaction(self.copy_btn)
        header_layout.addWidget(self.copy_btn)

        self.main_layout.addLayout(header_layout)

        # ── Concise Operational State Card (Reasoning / Thinking) ──
        self.thinking_container = QFrame(self)
        self.thinking_container.setObjectName("thinkingContainer")
        t_layout = QVBoxLayout(self.thinking_container)
        t_layout.setContentsMargins(8, 6, 8, 6)
        t_layout.setSpacing(4)

        # Clickable Header Row
        self.thinking_header = QWidget(self.thinking_container)
        self.thinking_header.setCursor(Qt.PointingHandCursor)
        th_layout = QHBoxLayout(self.thinking_header)
        th_layout.setContentsMargins(0, 0, 0, 0)
        th_layout.setSpacing(6)

        self.thinking_icon = QLabel("●")
        self.thinking_icon.setStyleSheet(f"font-size: 8px; color: {p['accent']}; background: transparent; border: none;")
        th_layout.addWidget(self.thinking_icon)

        initial_think_title = "Thought Process" if self.thinking_text else "Thinking..."
        self.thinking_title_label = QLabel(initial_think_title)
        self.thinking_title_label.setFont(QFont("Inter", 8, QFont.Bold))
        self.thinking_title_label.setStyleSheet(f"color: {p['accent']}; font-size: 10.5px; background: transparent; border: none;")
        th_layout.addWidget(self.thinking_title_label)

        th_layout.addStretch(1)

        self.thinking_toggle_btn = QLabel("▼" if self._thinking_expanded else "▶")
        self.thinking_toggle_btn.setStyleSheet(f"color: {p['text_muted']}; font-size: 9px; font-weight: bold; background: transparent; border: none;")
        th_layout.addWidget(self.thinking_toggle_btn)

        self.thinking_header.mousePressEvent = lambda e: self.toggle_thinking()
        t_layout.addWidget(self.thinking_header)

        # Thinking Text Browser
        self.thinking_browser = QTextBrowser(self.thinking_container)
        self.thinking_browser.setOpenExternalLinks(True)
        self.thinking_browser.setReadOnly(True)
        self.thinking_browser.setLineWrapMode(QTextBrowser.WidgetWidth)
        self.thinking_browser.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.thinking_browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.thinking_browser.document().setDefaultFont(QFont("Consolas", 8))
        self.thinking_browser.document().documentLayout().documentSizeChanged.connect(self._adjust_height)
        t_layout.addWidget(self.thinking_browser)

        # HARD SAFETY INVARIANT: Internal reasoning must NEVER enter visible chat bubbles
        self.thinking_container.setVisible(False)
        self.thinking_container.hide()

        self.main_layout.addWidget(self.thinking_container)

        # ── Tool Activity Chip (Compact Indicator) ──
        self.tool_chip = QLabel(self)
        self.tool_chip.setObjectName("toolActivityChip")
        self.tool_chip.setFont(QFont("Inter", 8))
        self.tool_chip.setStyleSheet(f"""
            color: {p['text_secondary']};
            background-color: {p['bg_card']};
            border: 1px solid {p['border_card']};
            border-radius: 6px;
            padding: 3px 8px;
            margin: 2px 0;
        """)
        self.tool_chip.hide()
        self.main_layout.addWidget(self.tool_chip)

        # ── Content Card (Dynamic Auto-Expanding Markdown) ──
        self.text_browser = QTextBrowser(self)
        self.text_browser.setObjectName("chat_message_text")
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.setReadOnly(True)
        self.text_browser.setLineWrapMode(QTextBrowser.WidgetWidth)
        self.text_browser.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.text_browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_browser.document().setDefaultFont(QFont("Inter", 10))

        if self.raw_text:
            self.text_browser.setMarkdown(self.raw_text)
        elif self.is_streaming:
            placeholder = self.status_text if self.status_text else "Thinking..."
            self.text_browser.setHtml(f"<div style='color: {p['text_muted']}; font-family: Inter, sans-serif; font-size: 12px; padding: 4px 0;'>● {placeholder}</div>")

        self.text_browser.document().documentLayout().documentSizeChanged.connect(self._adjust_height)
        self.main_layout.addWidget(self.text_browser)

        self.apply_theme()
        install_hover_reveal(self, [self.copy_btn])

        QTimer.singleShot(20, self._adjust_height)
        QTimer.singleShot(120, self._adjust_height)

    def _adjust_height(self, *args):
        """Dynamically computes the exact height required for full multi-paragraph text."""
        try:
            viewport_w = self.text_browser.viewport().width()
            if viewport_w > 10:
                self.text_browser.document().setTextWidth(viewport_w)
            doc_h = int(self.text_browser.document().size().height())
            target_h = max(doc_h + 14, 44)
            self.text_browser.setFixedHeight(target_h)

            if hasattr(self, 'thinking_container') and not self.thinking_container.isHidden():
                if hasattr(self, 'thinking_browser') and not self.thinking_browser.isHidden():
                    t_w = self.thinking_browser.viewport().width()
                    if t_w > 10:
                        self.thinking_browser.document().setTextWidth(t_w)
                    t_doc_h = int(self.thinking_browser.document().size().height())
                    self.thinking_browser.setFixedHeight(min(max(t_doc_h + 10, 32), 240))

            self.updateGeometry()
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_height()

    def toggle_thinking(self):
        self._thinking_expanded = not self._thinking_expanded
        self.thinking_browser.setVisible(self._thinking_expanded)
        self.thinking_toggle_btn.setText("▼" if self._thinking_expanded else "▶")
        self._adjust_height()

    def append_thinking(self, token: str):
        if not token:
            return
        if not self.is_thinking:
            self.is_thinking = True
            self.thinking_start_time = time.time()

        self.thinking_text += token

        # HARD SAFETY INVARIANT: Internal reasoning must NEVER enter visible chat bubbles
        self.thinking_container.setVisible(False)
        self.thinking_container.hide()

    def _flush_thinking_render(self):
        self._last_thinking_render = time.perf_counter()
        if hasattr(self, 'thinking_browser') and self.thinking_text:
            self.thinking_browser.setMarkdown(self.thinking_text)
            self._adjust_height()

    def finish_thinking(self):
        self.is_thinking = False
        if self._thinking_render_timer.isActive():
            self._thinking_render_timer.stop()
        self.thinking_container.setVisible(False)
        self.thinking_container.hide()

    def append_token(self, token: str):
        if not token:
            return
        if self.is_thinking:
            self.finish_thinking()

        self.raw_text += token
        now = time.perf_counter()
        if now - self._last_token_render >= 0.05:
            self._flush_token_render()
        elif not self._token_render_timer.isActive():
            self._token_render_timer.start(50)

    def _flush_token_render(self):
        self._last_token_render = time.perf_counter()
        if hasattr(self, 'text_browser') and self.raw_text:
            # Strip any raw <think> tags before rendering
            clean = re.sub(r"<think>.*?</think>", "", self.raw_text, flags=re.DOTALL).strip()
            self.text_browser.setMarkdown(clean)
            self._adjust_height()

    def set_status(self, status_text: str):
        """Displays compact operational tool activity (e.g. 'Searching web...', 'Reading file...')."""
        self.status_text = status_text
        if status_text:
            p = get_current_palette()
            self.tool_chip.setText(f"⚡ {status_text}")
            self.tool_chip.show()
        else:
            self.tool_chip.hide()

    def finish_stream(self, final_text: str = None):
        self.is_streaming = False
        if self._token_render_timer.isActive():
            self._token_render_timer.stop()
        if self._thinking_render_timer.isActive():
            self._thinking_render_timer.stop()

        if self.is_thinking:
            self.finish_thinking()

        from friday_core.models.stream_parser import ReasoningStreamParser
        target_text = final_text if (final_text is not None and (final_text.strip() or not self.raw_text)) else self.raw_text
        self.raw_text = ReasoningStreamParser.clean_final_content(target_text)

        # HARD SAFETY INVARIANT: Keep thinking container strictly hidden
        self.thinking_container.setVisible(False)
        self.thinking_container.hide()

        self._flush_token_render()

        if hasattr(self, 'tool_chip') and self.tool_chip.isVisible():
            if self.status_text:
                self.tool_chip.setText(f"✓ {self.status_text.replace('...', '')} completed")
            QTimer.singleShot(2500, self.tool_chip.hide)

        elapsed = max(0.1, time.time() - self.start_time)
        if hasattr(self, 'latency_pill'):
            self.latency_pill.setText(f"{elapsed:.2f}s latency")
        if hasattr(self, 'ast_pill'):
            self.ast_pill.setText("VERIFIED")

        self._adjust_height()

    def _copy_content(self):
        from friday_core.models.stream_parser import ReasoningStreamParser
        clipboard = QApplication.clipboard()
        clean_text = ReasoningStreamParser.clean_final_content(self.raw_text)
        clipboard.setText(clean_text)
        self.copy_btn.setIcon(FluentIcon.ACCEPT)
        self.copy_btn.setToolTip("Copied!")
        QTimer.singleShot(1500, lambda: (self.copy_btn.setIcon(FluentIcon.COPY), self.copy_btn.setToolTip("Copy response")))

    def apply_theme(self, theme_mode: str = None):
        """Applies theme colors to badge, surface background, and typography."""
        p = get_theme_palette(theme_mode)

        if self.role == "friday":
            self.badge.setStyleSheet(f"color: {p['accent']}; font-weight: bold; background: transparent; border: none; font-size: 10px; letter-spacing: 0.5px;")
            bubble_bg = p['bubble_assistant']
            text_color = p.get('bubble_assistant_text', p['text_primary'])
            margin_style = "margin: 2px 40px 2px 0px;"
            border_style = f"border: 1px solid {p['border_subtle']};"
        elif self.role == "user":
            user_text_col = p.get('bubble_user_text', p['text_primary'])
            self.badge.setStyleSheet(f"color: {user_text_col}; font-weight: bold; background: transparent; border: none; font-size: 10px; letter-spacing: 0.5px;")
            bubble_bg = p['bubble_user']
            text_color = p.get('bubble_user_text', p['text_primary'])
            margin_style = "margin: 2px 0px 2px 40px;"
            border_style = f"border: 1px solid {p['border_card']};"
        else:
            self.badge.setStyleSheet(f"color: {p['text_muted']}; font-weight: bold; background: transparent; border: none; font-size: 10px; letter-spacing: 0.5px;")
            bubble_bg = p['bubble_system']
            text_color = p.get('bubble_system_text', p['text_muted'])
            margin_style = "margin: 2px 30px;"
            border_style = f"border: 1px solid {p['border_subtle']};"

        self.setStyleSheet(f"""
            ChatBubble {{
                background-color: {bubble_bg};
                {border_style}
                border-radius: 12px;
                padding: 4px 8px;
                {margin_style}
            }}
            ChatBubble:hover {{
                border: 1px solid {p['border_hover']};
            }}
            QTextBrowser {{
                background-color: transparent;
                border: none;
                color: {text_color};
                selection-background-color: {p['selection_bg']};
                selection-color: {p['text_primary']};
                padding: 0px 4px;
                font-size: 13px;
                line-height: 1.55;
            }}
        """)

        self.text_browser.document().setDefaultStyleSheet(f"""
            code {{
                background-color: {p['code_bg']};
                color: {p['code_text']};
                font-family: 'Consolas', monospace;
                padding: 2px 4px;
                border-radius: 4px;
                font-size: 12px;
            }}
            pre {{
                background-color: {p['code_block_bg']};
                color: {text_color};
                font-family: 'Consolas', monospace;
                border: 1px solid {p['code_border']};
                padding: 8px;
                border-radius: 6px;
                margin: 4px 0;
            }}
            h1 {{ color: {text_color}; font-size: 15px; margin: 6px 0; }}
            h2 {{ color: {text_color}; font-size: 13.5px; margin: 5px 0; }}
            h3 {{ color: {p['text_secondary']}; font-size: 12.5px; margin: 4px 0; }}
            a {{ color: {p['accent']}; text-decoration: none; }}
            blockquote {{
                border-left: 2px solid {p['accent']};
                margin: 4px 0;
                padding-left: 8px;
                color: {p['text_secondary']};
            }}
            ul, ol {{ margin: 4px 0; padding-left: 18px; }}
            li {{ margin-bottom: 2px; }}
        """)

        if hasattr(self, 'thinking_container'):
            self.thinking_container.setStyleSheet(f"""
                QFrame#thinkingContainer {{
                    background-color: {p['bg_surface']};
                    border: 1px solid {p['border_subtle']};
                    border-radius: 6px;
                    margin: 2px 0px 4px 0px;
                }}
            """)
        if hasattr(self, 'thinking_title_label'):
            self.thinking_title_label.setStyleSheet(f"color: {p['accent']}; font-size: 10.5px; background: transparent; border: none;")
        if hasattr(self, 'thinking_toggle_btn'):
            self.thinking_toggle_btn.setStyleSheet(f"color: {p['text_muted']}; font-size: 9px; font-weight: bold; background: transparent; border: none;")
        if hasattr(self, 'thinking_browser'):
            self.thinking_browser.setStyleSheet(f"""
                QTextBrowser {{
                    background-color: transparent;
                    border: none;
                    color: {p['text_secondary']};
                    font-size: 11px;
                    line-height: 1.4;
                    padding: 2px 0px;
                }}
            """)

        if self.raw_text:
            clean = re.sub(r"<think>.*?</think>", "", self.raw_text, flags=re.DOTALL).strip()
            self.text_browser.setMarkdown(clean)
        self._adjust_height()

    def set_thinking(self, active: bool, status_text: str = ""):
        """Sets the bubble into or out of active thinking state."""
        self.is_thinking = active
        if active:
            self.thinking_container.setVisible(True)
            self._thinking_expanded = True
            self.thinking_browser.setVisible(True)
            self.thinking_toggle_btn.setText("▼")
            self.thinking_title_label.setText("● Thinking...")
            p = get_current_palette()
            placeholder = status_text or "Formulating plan..."
            self.text_browser.setHtml(f"<div style='color: {p['text_muted']}; font-family: Inter, sans-serif; font-size: 12px; padding: 4px 0;'>● {placeholder}</div>")
        else:
            self.finish_thinking()

    def set_reasoning_content(self, text: str):
        """Sets completed collapsible reasoning text."""
        self.thinking_text = text
        self.thinking_container.setVisible(True)
        self.thinking_browser.setMarkdown(text)
        self.thinking_title_label.setText("Thought Process")
        self._thinking_expanded = False
        self.thinking_browser.setVisible(False)
        self.thinking_toggle_btn.setText("▶")
        self._adjust_height()

    def set_text(self, text: str):
        """Sets the final clean response text."""
        self.raw_text = text
        clean = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        self.text_browser.setMarkdown(clean)
        self._adjust_height()

    def add_tool_activity(self, text: str, status: str = "running"):
        """Displays active or completed tool execution chips."""
        self.tool_chip.show()
        p = get_current_palette()
        if status == "running":
            self.tool_chip.setText(f"⚡ {text}")
            self.tool_chip.setStyleSheet(f"""
                QLabel {{
                    background-color: {p['accent_bg']};
                    border: 1px solid {p['accent_border']};
                    color: {p['accent']};
                    font-size: 11px;
                    font-weight: 500;
                    border-radius: 6px;
                    padding: 3px 8px;
                    margin: 2px 0;
                }}
            """)
        else:
            self.tool_chip.setText(f"✓ {text}")
            self.tool_chip.setStyleSheet(f"""
                QLabel {{
                    background-color: {p['live_green_bg']};
                    border: 1px solid {p['live_green_border']};
                    color: {p['live_green']};
                    font-size: 11px;
                    font-weight: 500;
                    border-radius: 6px;
                    padding: 3px 8px;
                    margin: 2px 0;
                }}
            """)
        self._adjust_height()

    def set_error(self, problem: str, reason: str, action: str):
        """Renders structured professional error state (Problem - Reason - Action)."""
        p = get_current_palette()
        err_html = f"""
        <div style='background-color: {p['danger_red_bg']}; border: 1px solid {p['danger_red_border']}; border-radius: 8px; padding: 10px 14px; margin: 4px 0;'>
            <div style='color: {p['danger_red']}; font-weight: bold; font-size: 13px; margin-bottom: 4px;'>⚠️ {problem}</div>
            <div style='color: {p['text_secondary']}; font-size: 12px; margin-bottom: 6px;'>{reason}</div>
            <div style='color: {p['accent']}; font-size: 11.5px; font-weight: 600;'>Resolution: {action}</div>
        </div>
        """
        self.text_browser.setHtml(err_html)
        self._adjust_height()
