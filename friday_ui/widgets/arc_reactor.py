"""
F.R.I.D.A.Y. 2.0 - Stark Arc Reactor / Holographic Core Widget
60 FPS Ultra-Smooth Procedural HUD Animation with Concentric Rotating Rings,
Breathing Idle Pulse, Wake Energy Bursts, Smooth Color LERP, and Laptop Power Throttling.
"""

import math
import random
from typing import List
from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QRadialGradient, QPolygonF
)
from PySide6.QtWidgets import QWidget
from friday_core.settings import settings

class Particle:
    def __init__(self, x: float, y: float, vx: float, vy: float, color: QColor, life: float = 1.0):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.life = life
        self.max_life = life

class ArcReactorWidget(QWidget):
    """
    Stark Industries Holographic Arc Reactor.
    Features:
    - 60 FPS / 30 FPS / Off power-managed rendering
    - Concentric rotating segmented rings & tick rings
    - Standby breathing pulse (0.98 <-> 1.02 scale over ~3s)
    - Particle & shockwave bursts on wake-word detection
    - Smooth color LERP between idle/thinking/listening/speaking
    """
    def __init__(self, size: int = 110, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

        # Animation states
        self.angle_outer = 0.0
        self.angle_inner = 0.0
        self.angle_orbiters = 0.0
        self.pulse_phase = 0.0
        self.current_energy = 0.15
        self.target_energy = 0.15

        # Assistant state: "idle", "listening", "thinking", "speaking"
        self.state = "idle"

        # Color LERP states (RGB floats) - Warm Editorial Palette
        self.current_color = [217.0, 116.0, 91.0]  # Soft Terracotta (#D9745B)
        self.target_color = [217.0, 116.0, 91.0]

        # Burst particles
        self.particles: List[Particle] = []
        self.shockwave_radius = 0.0
        self.shockwave_alpha = 0.0

        # Animation Timer with power adaptation
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animation_tick)
        self._apply_power_budget()

    def _apply_power_budget(self):
        anim_level = settings.get("animation_level", "Full")
        if anim_level == "Off":
            self.timer.stop()
        elif anim_level == "Reduced":
            self.timer.setInterval(33)  # ~30 FPS
            if not self.timer.isActive():
                self.timer.start()
        else:
            # Dynamic power budget: 30 FPS in standby/idle, 60 FPS during active interaction
            interval = 16 if getattr(self, "state", "idle") in ["listening", "thinking", "speaking"] else 33
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
        if self.state == "listening":
            self.target_color = [107.0, 142.0, 120.0]   # Muted Sage (#6B8E78)
        elif self.state == "thinking":
            self.target_color = [217.0, 119.0, 6.0]     # Warm Amber (#D97706)
        elif self.state == "speaking":
            self.target_color = [217.0, 116.0, 91.0]    # Soft Terracotta (#D9745B)
        else:  # idle / standby
            self.target_color = [160.0, 150.0, 145.0]  # Warm Muted Slate
        self._apply_power_budget()
        self.update()

    def trigger_burst(self):
        """Triggers radial particle and shockwave ring burst upon wake-word detection."""
        w = self.width() / 2.0
        h = self.height() / 2.0
        self.shockwave_radius = 6.0
        self.shockwave_alpha = 250.0

        self.particles.clear()
        for _ in range(20):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(2.5, 5.0)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            col = QColor(int(self.current_color[0]), int(self.current_color[1]), int(self.current_color[2]), 230)
            self.particles.append(Particle(w, h, vx, vy, col, life=random.uniform(0.40, 0.70)))

    def set_energy(self, level: float):
        """Sets target energy level (0.0 to 1.0) based on microphone or TTS amplitude."""
        self.target_energy = max(0.12, min(1.0, float(level)))

    def _animation_tick(self):
        # Color LERP interpolation
        for i in range(3):
            self.current_color[i] += (self.target_color[i] - self.current_color[i]) * 0.12

        # Smooth energy interpolation
        self.current_energy += (self.target_energy - self.current_energy) * 0.20
        self.target_energy *= 0.94

        # Speeds based on state
        if self.state == "thinking":
            spd_outer = 2.8
            spd_inner = -4.0
            spd_orb = 3.5
            pulse_spd = 0.14
        elif self.state == "listening":
            spd_outer = 1.6
            spd_inner = -2.2
            spd_orb = 2.4
            pulse_spd = 0.10
        elif self.state == "speaking":
            spd_outer = 2.0
            spd_inner = -3.0
            spd_orb = 2.8
            pulse_spd = 0.12
        else:  # idle breathing
            spd_outer = 0.6
            spd_inner = -0.8
            spd_orb = 1.0
            pulse_spd = 0.035  # ~3 second full breathing cycle

        self.angle_outer = (self.angle_outer + spd_outer) % 360.0
        self.angle_inner = (self.angle_inner + spd_inner) % 360.0
        self.angle_orbiters = (self.angle_orbiters + spd_orb) % 360.0
        self.pulse_phase = (self.pulse_phase + pulse_spd) % (2 * math.pi)

        # Eased burst shockwave expansion & particles
        if self.shockwave_alpha > 1.0:
            self.shockwave_radius += (55.0 - self.shockwave_radius) * 0.22
            self.shockwave_alpha *= 0.91
        else:
            self.shockwave_alpha = 0.0

        for p in list(self.particles):
            p.x += p.vx
            p.y += p.vy
            p.vx *= 0.94
            p.vy *= 0.94
            p.life -= 0.02
            if p.life <= 0:
                self.particles.remove(p)

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        center = QPointF(w / 2.0, h / 2.0)
        base_radius = min(w, h) / 2.0 - 4

        # Breathing scale factor (0.98 to 1.02)
        breath_scale = 1.0 + 0.02 * math.sin(self.pulse_phase)
        radius = base_radius * breath_scale

        r_int = int(max(0, min(255, self.current_color[0])))
        g_int = int(max(0, min(255, self.current_color[1])))
        b_int = int(max(0, min(255, self.current_color[2])))

        c_core = QColor(r_int, g_int, b_int)
        c_ring = QColor(r_int, g_int, b_int, 180)
        c_glow = QColor(r_int, g_int, b_int, 60)

        # 1. Outer Glow Aura (breathing with pulse)
        pulse_val = 0.5 + 0.5 * math.sin(self.pulse_phase)
        glow_radius = radius * (0.85 + 0.25 * (self.current_energy + pulse_val * 0.15))
        radial = QRadialGradient(center, glow_radius)
        radial.setColorAt(0.0, c_glow)
        radial.setColorAt(0.8, QColor(r_int, g_int, b_int, 12))
        radial.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(radial)
        painter.drawEllipse(center, glow_radius, glow_radius)

        # 2. Outer Segmented Housing Ring
        painter.save()
        painter.translate(center)
        painter.rotate(self.angle_outer)

        pen_outer = QPen(c_ring, 2.0)
        painter.setPen(pen_outer)
        painter.setBrush(Qt.NoBrush)

        num_outer_segments = 6
        seg_span = 360.0 / num_outer_segments
        arc_len = seg_span * 0.72
        r_outer = radius * 0.88

        for i in range(num_outer_segments):
            start_deg = i * seg_span
            painter.drawArc(int(-r_outer), int(-r_outer), int(r_outer * 2), int(r_outer * 2), int(start_deg * 16), int(arc_len * 16))

        # Fine telemetry tick marks
        pen_tick = QPen(QColor(r_int, g_int, b_int, 90), 1.0)
        painter.setPen(pen_tick)
        for i in range(24):
            deg = i * (360.0 / 24)
            rad = math.radians(deg)
            x1 = (r_outer - 4) * math.cos(rad)
            y1 = (r_outer - 4) * math.sin(rad)
            x2 = (r_outer + 2) * math.cos(rad)
            y2 = (r_outer + 2) * math.sin(rad)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        painter.restore()

        # 3. Counter-Rotating Inner Reactor Lattice
        painter.save()
        painter.translate(center)
        painter.rotate(self.angle_inner)

        pen_inner = QPen(c_ring, 1.8)
        painter.setPen(pen_inner)
        r_inner = radius * 0.62

        num_inner_segments = 8
        seg_span_in = 360.0 / num_inner_segments
        arc_len_in = seg_span_in * 0.60

        for i in range(num_inner_segments):
            start_deg = i * seg_span_in
            painter.drawArc(int(-r_inner), int(-r_inner), int(r_inner * 2), int(r_inner * 2), int(start_deg * 16), int(arc_len_in * 16))

        # Triangular power spokes
        painter.setPen(QPen(QColor(r_int, g_int, b_int, 130), 1.2))
        for i in range(3):
            deg = i * 120.0
            rad = math.radians(deg)
            x = r_inner * math.cos(rad)
            y = r_inner * math.sin(rad)
            painter.drawLine(QPointF(0, 0), QPointF(x, y))
        painter.restore()

        # 4. Orbiting Quantum Photons
        painter.save()
        painter.translate(center)
        painter.rotate(self.angle_orbiters)

        r_orbit = radius * 0.74
        for i in range(3):
            deg = i * 120.0
            rad = math.radians(deg)
            ox = r_orbit * math.cos(rad)
            oy = r_orbit * math.sin(rad)

            orb_rad = QRadialGradient(QPointF(ox, oy), 7.0)
            orb_rad.setColorAt(0.0, QColor(255, 255, 255, 240))
            orb_rad.setColorAt(0.5, c_ring)
            orb_rad.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(orb_rad)
            painter.drawEllipse(QPointF(ox, oy), 7.0, 7.0)
        painter.restore()

        # 5. Core High-Intensity Node
        core_r = radius * (0.28 + self.current_energy * 0.15)
        core_grad = QRadialGradient(center, core_r)
        core_grad.setColorAt(0.0, QColor(255, 255, 255, 255))
        core_grad.setColorAt(0.4, c_core)
        core_grad.setColorAt(0.85, QColor(r_int, g_int, b_int, 180))
        core_grad.setColorAt(1.0, QColor(r_int, g_int, b_int, 0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(core_grad)
        painter.drawEllipse(center, core_r, core_r)

        # 6. Particle & Shockwave Bursts
        if self.shockwave_alpha > 0:
            sw_pen = QPen(QColor(r_int, g_int, b_int, int(self.shockwave_alpha)), 2.0)
            painter.setPen(sw_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, self.shockwave_radius, self.shockwave_radius)

        for p in self.particles:
            alpha = int(220 * (p.life / p.max_life))
            col = QColor(p.color.red(), p.color.green(), p.color.blue(), alpha)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(col))
            painter.drawEllipse(QPointF(p.x, p.y), 2.5, 2.5)
        painter.end()
