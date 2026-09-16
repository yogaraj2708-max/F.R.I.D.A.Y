"""
F.R.I.D.A.Y. 2.0 - Right Contextual Operations Panel (Inspector)
Implements the 3-tab inspector from the modern desktop layout:
- Stats: Hardware telemetry bars, model state, quick command buttons
- Audit Log: Real-time scrolling event feed with category tags
- Security: 4-tier Gatekeeper summary
"""

from datetime import datetime
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QProgressBar, QGridLayout, QSizePolicy
)
from qfluentwidgets import PushButton, TransparentToolButton, FluentIcon
from friday_ui.styles.themes import (
    MONO_DARK, STARK_CYAN, LIVE_GREEN, DANGER_RED, AMBER_WARN,
    install_button_micro_interaction, fade_in
)
from friday_ui.widgets.glass_panel import GlassPanel


class OperationsPanel(GlassPanel):
    """Right-side operations and inspection panel matching reference desktop client."""
    quick_command_triggered = Signal(str)

    def __init__(self, parent=None):
        super().__init__(
            parent=parent,
            bg_color="rgba(14, 16, 22, 0.70)",
            border_color="rgba(255, 255, 255, 0.08)",
            radius=0,
            enable_shadow=False
        )
        self.setObjectName("operationsPanel")
        self.setFixedWidth(280)
        self._active_tab = "audit"
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # ── 1. Tab Selector Bar ──────────────────────────────
        tab_container = QFrame(self)
        tab_container.setStyleSheet("""
            QFrame {
                background-color: rgba(9, 9, 11, 0.75);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 2px;
            }
        """)
        tab_layout = QHBoxLayout(tab_container)
        tab_layout.setContentsMargins(2, 2, 2, 2)
        tab_layout.setSpacing(4)

        self.tab_audit_btn = PushButton("Audit Log", tab_container)
        self.tab_stats_btn = PushButton("Actions", tab_container)
        self.tab_sec_btn = PushButton("Security", tab_container)

        for btn in (self.tab_audit_btn, self.tab_stats_btn, self.tab_sec_btn):
            btn.setFixedHeight(26)
            btn.setFont(QFont("Segoe UI", 9))
            btn.setCursor(Qt.PointingHandCursor)
            install_button_micro_interaction(btn)

        self.tab_audit_btn.clicked.connect(lambda: self.switch_tab("audit"))
        self.tab_stats_btn.clicked.connect(lambda: self.switch_tab("stats"))
        self.tab_sec_btn.clicked.connect(lambda: self.switch_tab("sec"))

        tab_layout.addWidget(self.tab_audit_btn)
        tab_layout.addWidget(self.tab_stats_btn)
        tab_layout.addWidget(self.tab_sec_btn)
        layout.addWidget(tab_container)

        # ── 2. Content Stack ────────────────────────────────
        self.content_container = QWidget(self)
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

        # Tab 1: Audit (Primary)
        self.audit_widget = self._build_audit_widget()
        # Tab 2: Actions & State (Decluttered - No duplicate battery/RAM bars)
        self.stats_widget = self._build_stats_widget()
        # Tab 3: Security
        self.sec_widget = self._build_sec_widget()

        self.content_layout.addWidget(self.audit_widget)
        self.content_layout.addWidget(self.stats_widget)
        self.content_layout.addWidget(self.sec_widget)

        layout.addWidget(self.content_container, 1)

        self.switch_tab("audit")

    def _build_stats_widget(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(10)

        # Card 1: Neural Model State
        model_card = QFrame()
        model_card.setStyleSheet("""
            QFrame {
                background-color: rgba(18, 18, 24, 0.60);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 8px;
            }
        """)
        mc_layout = QVBoxLayout(model_card)
        mc_layout.setSpacing(6)

        m_head = QLabel("Neural Model State")
        m_head.setFont(QFont("Segoe UI", 9, QFont.Bold))
        m_head.setStyleSheet("color: #FFFFFF;")
        mc_layout.addWidget(m_head)

        grid = QGridLayout()
        grid.setSpacing(6)

        cell1 = self._make_stat_box("Architecture", "Llama 3.2 3B")
        cell2 = self._make_stat_box("Inference", "48 tok/s")
        grid.addWidget(cell1, 0, 0)
        grid.addWidget(cell2, 0, 1)
        mc_layout.addLayout(grid)
        l.addWidget(model_card)

        # Card 3: Quick Commands
        cmd_card = QFrame()
        cmd_card.setStyleSheet("""
            QFrame {
                background-color: #09090B;
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 10px;
                padding: 8px;
            }
        """)
        cc_layout = QVBoxLayout(cmd_card)
        cc_layout.setSpacing(6)

        c_head = QLabel("Quick Commands")
        c_head.setFont(QFont("Segoe UI", 9, QFont.Bold))
        c_head.setStyleSheet("color: #FFFFFF;")
        cc_layout.addWidget(c_head)

        cmd_grid = QGridLayout()
        cmd_grid.setSpacing(6)

        cmds = [
            ("wt.exe", "open terminal"),
            ("code .", "open vs code"),
            ("Status", "system status telemetry"),
            ("Edge", "open edge")
        ]
        for idx, (label, cmd_text) in enumerate(cmds):
            b = PushButton(label)
            b.setFixedHeight(26)
            b.setFont(QFont("Consolas", 9))
            b.setStyleSheet("""
                PushButton {
                    background-color: #141416;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    color: #D4D4D8;
                    border-radius: 6px;
                }
                PushButton:hover {
                    background-color: #FFFFFF;
                    color: #000000;
                }
            """)
            b.clicked.connect(lambda checked=False, q=cmd_text: self.quick_command_triggered.emit(q))
            install_button_micro_interaction(b)
            cmd_grid.addWidget(b, idx // 2, idx % 2)

        cc_layout.addLayout(cmd_grid)
        l.addWidget(cmd_card)

        l.addStretch(1)
        return w

    def _make_stat_box(self, title: str, val: str) -> QFrame:
        f = QFrame()
        f.setStyleSheet("""
            QFrame {
                background-color: #141416;
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 6px;
                padding: 4px;
            }
        """)
        fl = QVBoxLayout(f)
        fl.setContentsMargins(4, 4, 4, 4)
        fl.setSpacing(1)
        t = QLabel(title)
        t.setStyleSheet("color: #71717A; font-size: 8px; font-family: monospace;")
        v = QLabel(val)
        v.setStyleSheet("color: #FFFFFF; font-size: 10px; font-weight: bold; font-family: monospace;")
        fl.addWidget(t)
        fl.addWidget(v)
        return f

    def _build_audit_widget(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(6)

        head = QLabel("AUDIT.JSONL // LIVE FEED")
        head.setFont(QFont("Segoe UI", 9, QFont.Bold))
        head.setStyleSheet("color: #FFFFFF; letter-spacing: 0.5px;")
        l.addWidget(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.audit_container = QWidget()
        self.audit_layout = QVBoxLayout(self.audit_container)
        self.audit_layout.setContentsMargins(0, 0, 0, 0)
        self.audit_layout.setSpacing(6)
        self.audit_layout.addStretch(1)

        scroll.setWidget(self.audit_container)
        l.addWidget(scroll, 1)

        # Seed initial entries
        self.add_audit("INIT", "Neural core synchronized", "#10B981")
        self.add_audit("GATE", "Tier-0 pass: Read telemetry", "#06B6D4")
        return w

    def _build_sec_widget(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(8)

        head = QLabel("4-Tier Security Gatekeeper")
        head.setFont(QFont("Segoe UI", 9, QFont.Bold))
        head.setStyleSheet("color: #FFFFFF;")
        l.addWidget(head)

        tiers = [
            ("Tier 0: Read Only", "PASS", "#10B981", "Telemetry, date/time, non-destructive reads"),
            ("Tier 1: Safe Launch", "AUTO", "#06B6D4", "Known binaries: wt.exe, code.exe, browser"),
            ("Tier 2: Mod / Trash", "10s WARN", "#F59E0B", "File deletions route to Recycle Bin"),
            ("Tier 3: Windows Root", "BLOCKED", "#EF4444", "Registry wipe, format, system32 blocked")
        ]
        for name, badge, color, desc in tiers:
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: #09090B;
                    border: 1px solid rgba(255, 255, 255, 0.10);
                    border-radius: 8px;
                    padding: 8px;
                }}
            """)
            cl = QVBoxLayout(card)
            cl.setSpacing(3)
            r = QHBoxLayout()
            n = QLabel(name)
            n.setStyleSheet("color: #FFFFFF; font-size: 10px; font-weight: bold;")
            b = QLabel(badge)
            b.setStyleSheet(f"color: {color}; font-size: 9px; font-family: monospace; font-weight: bold;")
            r.addWidget(n)
            r.addWidget(b, 0, Qt.AlignRight)
            cl.addLayout(r)

            d = QLabel(desc)
            d.setStyleSheet("color: #71717A; font-size: 9px;")
            d.setWordWrap(True)
            cl.addWidget(d)
            l.addWidget(card)

        l.addStretch(1)
        return w

    def switch_tab(self, tab_id: str):
        self._active_tab = tab_id
        active_style = """
            background-color: #FFFFFF;
            color: #000000;
            border-radius: 6px;
            font-weight: bold;
        """
        inactive_style = """
            background-color: transparent;
            color: #A1A1AA;
            border: none;
        """

        self.tab_stats_btn.setStyleSheet(active_style if tab_id == "stats" else inactive_style)
        self.tab_audit_btn.setStyleSheet(active_style if tab_id == "audit" else inactive_style)
        self.tab_sec_btn.setStyleSheet(active_style if tab_id == "sec" else inactive_style)

        target = self.stats_widget if tab_id == "stats" else (self.audit_widget if tab_id == "audit" else self.sec_widget)
        self.stats_widget.setVisible(tab_id == "stats")
        self.audit_widget.setVisible(tab_id == "audit")
        self.sec_widget.setVisible(tab_id == "sec")
        if target:
            fade_in(target, duration=180)

    def update_telemetry(self, bat, mem):
        """Hardware telemetry is handled glanceably by the bottom HUD dock."""
        pass

    def add_audit(self, tag: str, message: str, color: str = "#10B981"):
        time_str = datetime.now().strftime("%H:%M:%S")
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #09090B;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-left: 3px solid {color};
                border-radius: 6px;
                padding: 4px;
            }}
        """)
        l = QVBoxLayout(card)
        l.setContentsMargins(4, 2, 4, 2)
        l.setSpacing(1)

        hdr = QLabel(f"{time_str} [{tag}]")
        hdr.setStyleSheet("color: #71717A; font-size: 8px; font-family: monospace;")
        msg = QLabel(message)
        msg.setStyleSheet("color: #D4D4D8; font-size: 9px; font-family: monospace;")
        msg.setWordWrap(True)

        l.addWidget(hdr)
        l.addWidget(msg)

        # Insert before stretch
        self.audit_layout.insertWidget(self.audit_layout.count() - 1, card)
        fade_in(card, duration=150)
