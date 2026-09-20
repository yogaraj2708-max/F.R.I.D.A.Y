"""
Audio Waveform Visualizer Widget for F.R.I.D.A.Y. 2.0
Ultra-smooth 60 FPS acoustic wave rendering with glowing gradient arcs & spectrum bars.
"""

import math
import numpy as np
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QLinearGradient, QPainterPath,
    QRadialGradient
)
from PySide6.QtWidgets import QWidget


class AudioVisualizerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setMinimumWidth(180)

        self.num_points = 48
        self.amplitudes = np.zeros(self.num_points, dtype=np.float32)
        self.phase = 0.0
        self.is_active = False
        self.current_level = 0.0
        self.target_level = 0.0

        self.state = "idle"

        # Rendering timer with laptop power budgeting
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate_step)
        self._apply_power_budget()

    def _apply_power_budget(self):
        from friday_core.settings import settings
        anim_level = settings.get("animation_level", "Full")
        if anim_level == "Off":
            self.timer.stop()
        elif anim_level == "Reduced":
            self.timer.setInterval(33)
            if not self.timer.isActive():
                self.timer.start()
        else:
            # Dynamic power budget: 30 FPS in standby/idle, 60 FPS in active interaction
            interval = 16 if getattr(self, "state", "idle") in ["listening", "speaking"] else 33
            self.timer.setInterval(interval)
            if not self.timer.isActive():
                self.timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_power_budget()

    def hideEvent(self, event):
        super().hideEvent(event)
        if hasattr(self, 'timer') and self.timer.isActive():
            self.timer.stop()

    def set_state(self, state: str):
        self.state = state.lower()
        self._apply_power_budget()
        self.update()

    def update_level(self, rms_energy: float):
        norm = min(max((rms_energy - 150.0) / 2500.0, 0.0), 1.0)
        self.target_level = norm
        self.is_active = norm > 0.05

    def update_audio_level(self, norm_level: float):
        self.target_level = min(max(float(norm_level), 0.0), 1.0)
        self.is_active = self.target_level > 0.03

    def set_active(self, active: bool):
        self.is_active = active
        if not active:
            self.target_level = 0.0

    def _animate_step(self):
        self.current_level += (self.target_level - self.current_level) * 0.28
        self.target_level *= 0.90
        self.phase += 0.08
        if self.phase > 2 * math.pi:
            self.phase -= 2 * math.pi

        min_base = 0.06 if self.state in ["listening", "speaking"] else (0.03 if self.state in ["standby", "processing"] else 0.02)
        level = max(self.current_level, min_base)

        for i in range(self.num_points):
            x_norm = (i / self.num_points) * 2 * math.pi
            h1 = math.sin(x_norm * 2.0 + self.phase) * 0.5
            h2 = math.sin(x_norm * 4.0 - self.phase * 1.5) * 0.3
            h3 = math.cos(x_norm * 1.0 + self.phase * 0.7) * 0.2
            combined = (h1 + h2 + h3) * level
            self.amplitudes[i] = combined

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()
        mid_y = height / 2.0

        # Select color palette based on state
        from friday_ui.styles.themes import get_current_palette
        p = get_current_palette()
        c_accent = QColor(p.get('accent', '#D9745B'))
        c_green = QColor(p.get('live_green', '#6B8E78'))
        c_amber = QColor(p.get('amber_tag', '#D9745B'))
        c_muted = QColor(p.get('text_muted', '#8E8681'))

        if self.state == "listening":
            c_start = c_green
            c_end = QColor(c_green.red(), min(255, c_green.green() + 20), c_green.blue())
        elif self.state == "speaking":
            c_start = c_accent
            c_end = QColor(min(255, c_accent.red() + 20), c_accent.green(), c_accent.blue())
        elif self.state == "processing" or self.state == "thinking":
            c_start = c_amber
            c_end = c_accent
        else:
            c_start = QColor(c_muted.red(), c_muted.green(), c_muted.blue(), 90)
            c_end = QColor(c_muted.red(), c_muted.green(), c_muted.blue(), 50)

        gradient = QLinearGradient(0, 0, width, 0)
        gradient.setColorAt(0.0, c_start)
        gradient.setColorAt(1.0, c_end)

        max_amp = (height / 2.0) - 6

        # Slim spectrum bars
        num_bars = 32
        bar_w = (width - 16) / float(num_bars)
        for b in range(num_bars):
            bx = 8 + b * bar_w
            pt_idx = int((b / num_bars) * (self.num_points - 1))
            bar_h = max(2.0, abs(float(self.amplitudes[pt_idx])) * (max_amp * 1.8))
            bar_rect = QRectF(bx + 1, mid_y - bar_h / 2.0, bar_w - 2, bar_h)
            bar_alpha = 30 if self.state == "idle" else 70
            bar_color = QColor(c_start.red(), c_start.green(), c_start.blue(), bar_alpha)
            painter.setPen(Qt.NoPen)
            painter.setBrush(bar_color)
            painter.drawRoundedRect(bar_rect, 1.5, 1.5)

        # Primary dynamic wave path
        path = QPainterPath()
        dx = width / float(self.num_points - 1)
        path.moveTo(0, mid_y)

        for i in range(self.num_points):
            x = i * dx
            y = mid_y + self.amplitudes[i] * max_amp
            if i == 0:
                path.moveTo(x, y)
            else:
                prev_x = (i - 1) * dx
                prev_y = mid_y + self.amplitudes[i - 1] * max_amp
                cx = (prev_x + x) / 2.0
                path.quadTo(prev_x, prev_y, cx, (prev_y + y) / 2.0)

        pen = QPen(gradient, 2.0)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        # Mirrored secondary wave
        path_sec = QPainterPath()
        for i in range(self.num_points):
            x = i * dx
            y = mid_y - (self.amplitudes[i] * 0.55) * max_amp
            if i == 0:
                path_sec.moveTo(x, y)
            else:
                prev_x = (i - 1) * dx
                prev_y = mid_y - (self.amplitudes[i - 1] * 0.55) * max_amp
                cx = (prev_x + x) / 2.0
                path_sec.quadTo(prev_x, prev_y, cx, (prev_y + y) / 2.0)

        pen_sec = QPen(QColor(c_start.red(), c_start.green(), c_start.blue(), 50), 1.2)
        painter.setPen(pen_sec)
        painter.drawPath(path_sec)
        painter.end()
