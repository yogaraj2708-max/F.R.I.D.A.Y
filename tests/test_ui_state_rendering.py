"""
Tests for F.R.I.D.A.Y. 3.0 State-Driven UI Rendering.
Verifies operational state rendering across HUD, research stepper, and chat bubble reasoning containers.
"""

import sys
import unittest
from PySide6.QtWidgets import QApplication

from friday_ui.views.main_window import FridayMainWindow
from friday_ui.widgets.chat_bubble import ChatBubble


class TestUIStateRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(sys.argv)

    def setUp(self):
        self.window = FridayMainWindow()
        self.window.resize(1100, 750)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def test_hud_listening_state_rendering(self):
        """Verifies HUD transitions to Listening state."""
        self.window._on_engine_state_changed("listening")
        self.app.processEvents()
        self.assertEqual(self.window.hud_dock.hud_state_label.text(), "● Listening")
        self.assertTrue(self.window.hud_dock.visualizer.is_active)
        self.assertTrue(self.window.hud_dock.stop_voice_btn.isHidden())

    def test_hud_thinking_state_rendering(self):
        """Verifies HUD transitions to Thinking state."""
        self.window._on_engine_state_changed("thinking")
        self.app.processEvents()
        self.assertEqual(self.window.hud_dock.hud_state_label.text(), "● Thinking")
        self.assertTrue(self.window.hud_dock.visualizer.is_active)

    def test_hud_speaking_state_rendering(self):
        """Verifies HUD transitions to Speaking state and exposes Stop Voice button."""
        self.window._on_engine_state_changed("speaking")
        self.app.processEvents()
        self.assertEqual(self.window.hud_dock.hud_state_label.text(), "● Speaking")
        self.assertTrue(self.window.hud_dock.stop_voice_btn.isVisible())

    def test_hud_researching_state_rendering(self):
        """Verifies HUD transitions to Researching state."""
        self.window._on_engine_state_changed("researching")
        self.app.processEvents()
        self.assertEqual(self.window.hud_dock.hud_state_label.text(), "● Researching")

    def test_hud_error_state_rendering(self):
        """Verifies HUD transitions to Error state."""
        self.window._on_engine_state_changed("error")
        self.app.processEvents()
        self.assertEqual(self.window.hud_dock.hud_state_label.text(), "● Error")
        self.assertFalse(self.window.hud_dock.visualizer.is_active)

    def test_hud_telemetry_rendering(self):
        """Verifies telemetry label renders battery and memory statistics."""
        data = {"battery": 88, "memory": 45}
        self.window._on_telemetry_updated(data)
        self.app.processEvents()
        self.assertIn("88%", self.window.hud_dock.telemetry_label.text())
        self.assertIn("45%", self.window.hud_dock.telemetry_label.text())

    def test_research_stepper_stage_updates(self):
        """Verifies research stepper highlights active phase."""
        rv = self.window.research_view
        rv.set_stage(0, "Crawling sources")
        self.assertEqual(rv.live_status_lbl.text(), "Crawling sources")

        rv.set_stage(2, "Analyzing evidence")
        self.assertEqual(rv.live_status_lbl.text(), "Analyzing evidence")

    def test_chat_bubble_operational_thinking_state(self):
        """Verifies chat bubble exhibits concise operational thinking without raw <think> dump."""
        bubble = ChatBubble("friday", "", is_streaming=True)
        self.assertTrue(bubble.thinking_container.isHidden())

        # Stream thinking
        bubble.append_thinking("Evaluating search results...")
        self.assertFalse(bubble.thinking_container.isHidden())
        self.assertEqual(bubble.thinking_title_label.text(), "Thinking...")

        # Transition to content tokens
        bubble.append_token("Found optimal trajectory.")
        self.assertIn("Thought for", bubble.thinking_title_label.text())
        self.assertNotIn("<think>", bubble.raw_text)


if __name__ == "__main__":
    unittest.main()
