"""
Unit tests for Deep Research in-chat synthesis and Image Vision handling.
"""

import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio
import os
import tempfile
import re

from friday_ui.core.engine import FridayBrain, FridaySignals
from friday_ui.views.main_window import FridayMainWindow


class TestDeepResearchAndVision(unittest.TestCase):

    def setUp(self):
        self.signals = FridaySignals()
        self.tts = MagicMock()
        self.brain = FridayBrain(self.signals, self.tts)

    def test_topic_cleaning_regex(self):
        test_inputs = [
            ("deep research web and tell about company named continental", "company named continental"),
            ("do a deep research on quantum computing", "quantum computing"),
            ("deep research about neural networks", "neural networks"),
            ("tell about company named continental", "continental"),
            ("deep search on space exploration", "space exploration"),
        ]

        pattern = r"^(?:(?:do\s+(?:a\s+)?)?deep\s+(?:web\s+)?research\s+(?:web\s+and\s+tell\s+about|web\s+about|on|about)?|research\s+(?:web\s+and\s+tell\s+about|on|about)?|tell\s+(?:me\s+)?about\s+(?:company\s+named\s+)?|deep\s+search\s+(?:on|about)?)\s*"
        for raw_input, expected_topic in test_inputs:
            cleaned = re.sub(pattern, "", raw_input, flags=re.IGNORECASE).strip()
            self.assertEqual(cleaned, expected_topic)

    @patch("friday_ui.core.engine.fetch_web_results")
    def test_run_research_synthesizes_in_chat(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "title": "Continental AG - Automotive Manufacturing",
                "href": "https://www.continental.com",
                "body": "Continental AG develops pioneering technologies and services for sustainable and connected mobility."
            },
            {
                "title": "Continental History and Overview",
                "href": "https://en.wikipedia.org/wiki/Continental_AG",
                "body": "Founded in Hanover in 1871, Continental is one of the world's leading automotive suppliers."
            }
        ]

        # Create mock main window
        mock_win = MagicMock()
        mock_win.signals = FridaySignals()
        mock_win.chat_view = MagicMock()
        mock_win.research_view = MagicMock()
        mock_win.tts = MagicMock()
        mock_win.tts.extract_spoken_summary = MagicMock(return_value="Continental AG is a leading automotive supplier.")
        mock_win.tts.speak = AsyncMock()
        mock_win.brain = MagicMock()
        mock_win.brain.query_llm = AsyncMock(return_value="Executive Overview: Continental AG is a global leader in mobility technology.")

        # Bind the actual _run_research method to our mock window
        asyncio.run(FridayMainWindow._run_research(mock_win, "deep research web and tell about company named continental", "Deep Comprehensive"))

        # 1. Verify Research View was updated with cleaned topic
        mock_win.research_view.update_report.assert_called_once()
        topic_passed = mock_win.research_view.update_report.call_args[0][0]
        self.assertEqual(topic_passed, "company named continental")

        # 2. Verify Chat View received the rich Executive Dossier message
        mock_win.chat_view.add_message.assert_called()
        chat_args = mock_win.chat_view.add_message.call_args[0]
        self.assertEqual(chat_args[0], "friday")
        chat_body = chat_args[1]
        self.assertIn("Executive Intelligence Dossier", chat_body)
        self.assertIn("Continental AG", chat_body)
        self.assertIn("https://www.continental.com", chat_body)
        self.assertIn("Verified Sources", chat_body)

        # 3. Verify spoken brief was triggered
        mock_win.tts.speak.assert_called_once()
        spoken_text = mock_win.tts.speak.call_args[0][0]
        self.assertIn("Continental", spoken_text)

    def test_image_attachment_does_not_corrupt_binary(self):
        from friday_ui.views.chat_view import ChatView
        with patch.object(ChatView, "__init__", lambda self, parent=None: None):
            chat = ChatView()
            chat._is_generating = False
            chat.attached_files = []
            chat.deep_research_active = False
            chat.prompt_input = MagicMock()
            chat.prompt_input.text.return_value = "What is in this image?"
            chat.prompt_input.clear = MagicMock()
            chat._refresh_attachments_ui = MagicMock()
            chat.command_submitted = MagicMock()

            # Create a dummy image file
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_img:
                tmp_img.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01")
                tmp_img_path = tmp_img.name

            try:
                chat.attached_files = [tmp_img_path]
                chat._submit_prompt()

                chat.command_submitted.emit.assert_called_once()
                full_prompt, display_msg = chat.command_submitted.emit.call_args[0]

                # Ensure binary content was NOT opened as UTF-8 text
                self.assertNotIn("\x89PNG", full_prompt)
                # Ensure it was formatted as [Attached Image: ... | Path: ...]
                self.assertIn("[Attached Image:", full_prompt)
                self.assertIn(f"Path: {tmp_img_path}", full_prompt)
                self.assertIn("What is in this image?", full_prompt)
            finally:
                if os.path.exists(tmp_img_path):
                    os.remove(tmp_img_path)

    @patch("friday_ui.core.engine.FridayBrain._get_available_vision_model")
    @patch("friday_ui.core.engine.FridayBrain._stream_vision_chat")
    def test_analyze_image_file_routes_to_vision(self, mock_stream, mock_get_model):
        mock_get_model.return_value = "qwen2-vl:2b"
        mock_stream.return_value = AsyncMock()

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_img:
            tmp_img.write(b"\xff\xd8\xff\xe0\x00\x10JFIF")
            tmp_img_path = tmp_img.name

        try:
            asyncio.run(self.brain.analyze_image_file(tmp_img_path, "Analyze this architecture diagram", "arch.jpg"))
            mock_stream.assert_called_once()
            called_model, called_prompt, called_b64 = mock_stream.call_args[0]
            self.assertEqual(called_model, "qwen2-vl:2b")
            self.assertIn("Analyze this architecture diagram", called_prompt)
            self.assertTrue(len(called_b64) > 0)
        finally:
            if os.path.exists(tmp_img_path):
                os.remove(tmp_img_path)


if __name__ == "__main__":
    unittest.main()
