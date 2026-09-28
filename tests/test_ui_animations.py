"""
Tests for F.R.I.D.A.Y. 3.0 UI Animation & Microinteraction Toolkit.
Verifies non-blocking property animations, slide entrances, spring button filters, and pulsing dots.
"""

import sys
import unittest
from PySide6.QtWidgets import QApplication, QWidget, QPushButton
from PySide6.QtCore import Qt, QPoint, QEvent
from PySide6.QtGui import QMouseEvent

from friday_ui.styles.themes import (
    fade_in, SlideFadeEntrance, ButtonMicroInteractionFilter,
    PulsingGlowWidget, PulseStatusDot, install_button_micro_interaction
)


class TestUIAnimations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(sys.argv)

    def test_fade_in_animation_lifecycle(self):
        """Verifies fade_in animates opacity and cleans up effect at 1.0."""
        widget = QWidget()
        widget.resize(100, 50)
        widget.show()
        self.app.processEvents()

        anim = fade_in(widget, duration=60, start_opacity=0.0, end_opacity=1.0)
        self.assertIsNotNone(anim)
        self.assertTrue(anim.state() == anim.State.Running)

        # Process events until finished
        import time
        t0 = time.time()
        while anim.state() == anim.State.Running and time.time() - t0 < 0.5:
            self.app.processEvents()
            time.sleep(0.01)

        self.assertIsNone(widget.graphicsEffect())
        widget.close()

    def test_slide_fade_entrance_group(self):
        """Verifies SlideFadeEntrance executes a parallel animation group."""
        widget = QWidget()
        widget.resize(120, 60)
        widget.show()
        self.app.processEvents()

        group = SlideFadeEntrance.play(widget, duration=60, offset_y=8)
        self.assertIsNotNone(group)
        self.assertTrue(group.state() == group.State.Running)

        import time
        t0 = time.time()
        while group.state() == group.State.Running and time.time() - t0 < 0.5:
            self.app.processEvents()
            time.sleep(0.01)

        widget.close()

    def test_button_micro_interaction_filter(self):
        """Verifies spring micro-press event filter handles mouse events cleanly."""
        btn = QPushButton("Test Button")
        btn.setGeometry(10, 10, 100, 30)
        btn.show()
        self.app.processEvents()

        filter_obj = install_button_micro_interaction(btn)
        self.assertIsNotNone(filter_obj)

        # Simulate press
        press_event = QMouseEvent(QEvent.MouseButtonPress, QPoint(10, 10), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        filter_obj.eventFilter(btn, press_event)

        # Simulate release
        release_event = QMouseEvent(QEvent.MouseButtonRelease, QPoint(10, 10), Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
        filter_obj.eventFilter(btn, release_event)

        btn.close()

    def test_pulse_status_dot_painting(self):
        """Verifies PulseStatusDot paints without exceptions."""
        dot = PulseStatusDot(size=10)
        dot.show()
        self.app.processEvents()
        dot.update()
        self.app.processEvents()
        dot.close()


if __name__ == "__main__":
    unittest.main()
