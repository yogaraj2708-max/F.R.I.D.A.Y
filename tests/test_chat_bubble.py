"""
Tests for friday_ui.widgets.chat_bubble (ChatBubble Dynamic Height & Content Expansion)
Verifies multi-paragraph rendering, code block expansion, and copy functionality.
"""

import sys
import unittest
from PySide6.QtWidgets import QApplication
from friday_ui.widgets.chat_bubble import ChatBubble

app = QApplication.instance() or QApplication(sys.argv)

class TestChatBubble(unittest.TestCase):
    def test_single_line_bubble(self):
        bubble = ChatBubble("friday", "Short status message.")
        bubble._adjust_height()
        self.assertGreaterEqual(bubble.text_browser.height(), 44)

    def test_multi_paragraph_bubble_expansion(self):
        long_text = (
            "# Architecture Analysis\n\n"
            "This is the first detailed paragraph explaining system components.\n\n"
            "Here is the code block:\n\n"
            "```python\n"
            "def calculate_trajectory(v, theta):\n"
            "    g = 9.81\n"
            "    return (v ** 2) * math.sin(2 * theta) / g\n"
            "```\n\n"
            "### Summary Findings\n\n"
            "1. High throughput pipeline\n"
            "2. Low latency voice loop\n"
            "3. Dynamic AMOLED rendering\n\n"
            "This final paragraph wraps up the architectural breakdown."
        )
        bubble = ChatBubble("friday", long_text)
        bubble.resize(800, 600)
        bubble.text_browser.resize(750, 400)
        bubble._adjust_height()

        # The height should expand to accommodate multiple paragraphs and code, significantly above 45px!
        self.assertGreater(bubble.text_browser.height(), 150)

    def test_user_bubble_styling(self):
        bubble = ChatBubble("user", "Analyse this file please")
        self.assertEqual(bubble.role, "user")
        self.assertIn("BOSS", bubble.badge.text())

    def test_system_bubble_styling(self):
        bubble = ChatBubble("system", "Acoustic sensors online")
        self.assertEqual(bubble.role, "system")
        self.assertIn("SYSTEM", bubble.badge.text())

    def test_streaming_bubble_lifecycle(self):
        bubble = ChatBubble("friday", "", is_streaming=True, status_text="Scanning web...")
        self.assertTrue(bubble.is_streaming)
        self.assertEqual(bubble.ast_pill.text(), "STREAMING")

        # Update status
        bubble.set_status("Synthesizing sources...")
        self.assertEqual(bubble.status_text, "Synthesizing sources...")

        # Append tokens
        bubble.append_token("Hello ")
        bubble.append_token("Boss, ")
        bubble.append_token("systems nominal.")
        self.assertEqual(bubble.raw_text, "Hello Boss, systems nominal.")

        # Finish stream
        bubble.finish_stream()
        self.assertFalse(bubble.is_streaming)
        self.assertEqual(bubble.ast_pill.text(), "VERIFIED")
        self.assertIn("latency", bubble.latency_pill.text())

    def test_thinking_stream_lifecycle(self):
        """Verifies real-time streaming of thinking tokens into thinking container."""
        bubble = ChatBubble("friday", "", is_streaming=True, status_text="Neural core synthesizing...")
        self.assertTrue(bubble.is_streaming)
        self.assertTrue(bubble.thinking_container.isHidden())

        # 1. Stream thinking tokens
        bubble.append_thinking("Analyzing ")
        self.assertFalse(bubble.thinking_container.isHidden())
        self.assertTrue(bubble.is_thinking)
        self.assertIn("Thinking", bubble.thinking_title_label.text())

        bubble.append_thinking("neural weights...")
        self.assertEqual(bubble.thinking_text, "Analyzing neural weights...")

        # 2. Transition to content tokens
        bubble.append_token("Directive complete.")
        self.assertFalse(bubble.is_thinking)
        self.assertIn("Thought for", bubble.thinking_title_label.text())
        self.assertEqual(bubble.raw_text, "Directive complete.")

        # 3. Finish stream
        bubble.finish_stream()
        self.assertFalse(bubble.is_streaming)
        self.assertEqual(bubble.thinking_text, "Analyzing neural weights...")
        self.assertEqual(bubble.raw_text, "Directive complete.")

    def test_thinking_history_parsing(self):
        """Verifies that <think> tags in loaded message text are parsed into thinking container."""
        content_with_think = "<think>\nConsidered multiple execution paths.\nSelected optimal path.\n</think>\n\nHere is the answer: 42."
        bubble = ChatBubble("friday", content_with_think)
        self.assertEqual(bubble.thinking_text, "Considered multiple execution paths.\nSelected optimal path.")
        self.assertEqual(bubble.raw_text, "Here is the answer: 42.")
        self.assertFalse(bubble.thinking_container.isHidden())
        self.assertFalse(bubble._thinking_expanded) # Collapsed by default for historical messages

    def test_toggle_thinking(self):
        """Verifies expand/collapse toggle functionality of thinking container."""
        bubble = ChatBubble("friday", "<think>Some reasoning</think>\n\nAnswer")
        self.assertFalse(bubble._thinking_expanded)
        self.assertEqual(bubble.thinking_toggle_btn.text(), "▶")

        # Toggle to expand
        bubble.toggle_thinking()
        self.assertTrue(bubble._thinking_expanded)
        self.assertFalse(bubble.thinking_browser.isHidden())
        self.assertEqual(bubble.thinking_toggle_btn.text(), "▼")

        # Toggle to collapse
        bubble.toggle_thinking()
        self.assertFalse(bubble._thinking_expanded)
        self.assertTrue(bubble.thinking_browser.isHidden())
        self.assertEqual(bubble.thinking_toggle_btn.text(), "▶")

    def test_empty_token_does_not_clear_placeholder(self):
        """Verifies that empty string tokens do not wipe out the placeholder or set raw_text to empty."""
        bubble = ChatBubble("friday", "", is_streaming=True, status_text="Synthesizing...")
        bubble.append_token("")
        self.assertEqual(bubble.raw_text, "")

if __name__ == "__main__":
    unittest.main()
