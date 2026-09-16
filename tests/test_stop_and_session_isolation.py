"""
Tests for Stop Chat feature and Cross-Session Audio Bleed Prevention.
Verifies:
1. ChatView Stop button state transition and stop_requested signal.
2. Cross-session token rejection and bubble detachment upon switching sessions.
3. FridayBrain.abort_generation and voice engine instant audio cancellation.
"""

import sys
import unittest
import asyncio
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from friday_ui.views.chat_view import ChatView
from friday_ui.core.engine import FridaySignals, FridayVoiceEngine, FridayBrain


class TestStopAndSessionIsolation(unittest.TestCase):
    def setUp(self):
        self.chat_view = ChatView()

    def tearDown(self):
        self.chat_view.close()
        self.chat_view.deleteLater()

    def test_send_stop_button_toggle(self):
        """Test that send button becomes 'Stop' when streaming starts and reverts when finished."""
        self.assertEqual(self.chat_view.send_btn.text(), "Send")
        self.assertFalse(self.chat_view._is_generating)

        # Start stream
        self.chat_view.start_stream("friday", "Testing...")
        self.assertTrue(self.chat_view._is_generating)
        self.assertIn("Stop", self.chat_view.send_btn.text())

        # Finish stream
        self.chat_view.finish_stream("All finished.")
        self.assertFalse(self.chat_view._is_generating)
        self.assertEqual(self.chat_view.send_btn.text(), "Send")

    def test_stop_generation_signal_emitted(self):
        """Test that clicking Stop triggers stop_requested signal and cleans up."""
        signal_received = []
        self.chat_view.stop_requested.connect(lambda: signal_received.append(True))

        self.chat_view.start_stream("friday", "Generating...")
        self.assertTrue(self.chat_view._is_generating)

        # Simulate clicking the Stop button
        self.chat_view.send_btn.click()

        self.assertTrue(signal_received, "stop_requested signal was not emitted!")
        self.assertFalse(self.chat_view._is_generating)
        self.assertEqual(self.chat_view.send_btn.text(), "Send")
        self.assertIsNone(self.chat_view._current_streaming_bubble)

    def test_cross_session_token_bleeding_prevention(self):
        """Test that tokens belonging to an older session are rejected after switching sessions."""
        # Assume initial session
        initial_session_id = self.chat_view.current_session_id
        self.assertIsNotNone(initial_session_id)

        # Start streaming in session 1
        self.chat_view.start_stream("friday", "Generating response...")
        self.assertEqual(self.chat_view._streaming_session_id, initial_session_id)
        bubble_session_1 = self.chat_view._current_streaming_bubble
        self.assertIsNotNone(bubble_session_1)

        # Switch to a new session
        self.chat_view._on_new_session()
        new_session_id = self.chat_view.current_session_id
        self.assertNotEqual(initial_session_id, new_session_id)
        self.assertIsNone(self.chat_view._current_streaming_bubble)

        # Now an old token from session 1 arrives
        self.chat_view.append_token("Stray token from old chat")

        # Verify that no new bubble was created and nothing leaked into the new session
        self.assertIsNone(self.chat_view._current_streaming_bubble)

    def test_brain_abort_generation(self):
        """Test that FridayBrain.abort_generation sets the abort event and halts TTS."""
        signals = FridaySignals()
        mock_tts = MagicMock()
        brain = FridayBrain(signals, mock_tts)

        self.assertFalse(brain.abort_event.is_set())
        brain.abort_generation()
        self.assertTrue(brain.abort_event.is_set())
        mock_tts.stop_speaking.assert_called_once()


if __name__ == "__main__":
    unittest.main()
