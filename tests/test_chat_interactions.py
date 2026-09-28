"""
Tests for F.R.I.D.A.Y. 3.0 Chat Interactions.
Verifies prompt submission, token streaming, tool activity chips, attachments, and session switching.
"""

import sys
import unittest
from PySide6.QtWidgets import QApplication

from friday_ui.views.chat_view import ChatView
from friday_ui.widgets.chat_bubble import ChatBubble


class TestChatInteractions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(sys.argv)

    def setUp(self):
        self.chat_view = ChatView()
        self.chat_view.resize(900, 650)
        self.chat_view.show()
        self.app.processEvents()

    def tearDown(self):
        self.chat_view.close()
        self.app.processEvents()

    def test_prompt_submission_signal(self):
        """Verifies submitting text in prompt input emits command_submitted."""
        emitted = []
        self.chat_view.command_submitted.connect(lambda full, disp: emitted.append((full, disp)))

        self.chat_view.prompt_input.setText("Compute optimal burn time")
        self.chat_view._submit_prompt()
        self.app.processEvents()

        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0][0], "Compute optimal burn time")
        self.assertEqual(self.chat_view.prompt_input.text(), "")

    def test_streaming_lifecycle_and_tool_activity(self):
        """Verifies complete streaming lifecycle with tool status chips."""
        cv = self.chat_view

        # Start stream
        cv.start_stream(role="friday", initial_status="Analyzing intent...")
        self.assertTrue(cv._is_generating)
        self.assertIsNotNone(cv._current_streaming_bubble)
        self.assertTrue(cv.stop_btn.isVisible())

        # Update tool activity
        cv.update_status("Searching web for verified facts...")
        self.assertEqual(cv._current_streaming_bubble.status_text, "Searching web for verified facts...")

        # Append tokens
        cv.append_token("Evidence retrieved ")
        cv.append_token("and validated.")
        self.assertIn("Evidence retrieved and validated.", cv._current_streaming_bubble.raw_text)

        # Finish stream
        cv.finish_stream()
        self.assertFalse(cv._is_generating)
        self.assertTrue(cv.stop_btn.isHidden())

    def test_attachment_chips_staged(self):
        """Verifies attached files appear as compact staged chips."""
        cv = self.chat_view
        self.assertTrue(cv.attachments_container.isHidden())

        cv.attached_files.append("test_document.pdf")
        cv._refresh_attachments_ui()
        self.app.processEvents()

        self.assertTrue(cv.attachments_container.isVisible())
        self.assertGreaterEqual(cv.attachments_layout.count(), 1)

        # Remove attachment
        cv._remove_attachment("test_document.pdf")
        self.app.processEvents()
        self.assertTrue(cv.attachments_container.isHidden())

    def test_stop_generation_resets_controls(self):
        """Verifies clicking Stop resets buttons and halts generation."""
        cv = self.chat_view
        cv.start_stream(role="friday")
        self.assertTrue(cv._is_generating)

        cv.stop_generation()
        self.assertFalse(cv._is_generating)
        self.assertTrue(cv.stop_btn.isHidden())
        self.assertEqual(cv.send_btn.text(), "Send")


if __name__ == "__main__":
    unittest.main()
