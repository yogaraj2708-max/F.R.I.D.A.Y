"""
Tests for Microsoft Word Automation, Drafting, and Direct YouTube Playback.
Verifies:
1. "open word" opens a blank document rather than arbitrary recent files.
2. "open word and paste this" / "paste this into word" extracts prior assistant response and inserts into Word.
3. "open word and help me write [topic]" triggers LLM drafting and Word insertion.
4. "open youtube and play [song]" and "open and play [video]" resolves direct watch?v= video playback URL.
"""

import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from friday_ui.core.engine import FridayBrain, FridaySignals
from friday_core.settings import settings
from friday_core.web.youtube import resolve_youtube_video


class TestWordAndYouTubeAutomation(unittest.TestCase):
    def setUp(self):
        self.signals = FridaySignals()
        self.tts = MagicMock()
        self.tts.speak = AsyncMock()
        self.brain = FridayBrain(self.signals, self.tts)
        settings.set("observe_only", False)

    @patch("friday_ui.core.engine.open_blank_word")
    def test_open_word_blank_document(self, mock_blank):
        mock_blank.return_value = (True, "Opened blank document.")

        # Test simple "open word"
        res = asyncio.run(self.brain.execute_smart_skill("open word"))
        self.assertIsNotNone(res)
        self.assertIn("blank document", res.lower())
        self.assertIn("word", res.lower())
        mock_blank.assert_called()

        # Test variants
        res_ms = asyncio.run(self.brain.execute_smart_skill("open ms word"))
        self.assertIn("blank document", res_ms.lower())

        res_full = asyncio.run(self.brain.execute_smart_skill("open microsoft word"))
        self.assertIn("blank document", res_full.lower())

    @patch("friday_ui.core.engine.open_word_with_content")
    def test_open_word_and_paste_previous_message(self, mock_content):
        mock_content.return_value = (True, "Inserted content.")

        # Add an assistant message to history
        sample_reply = "Dear Team, thank you for your outstanding dedication this quarter."
        self.brain.conversation_history.append({"role": "assistant", "content": sample_reply})

        res = asyncio.run(self.brain.execute_smart_skill("open word and paste this"))
        self.assertIsNotNone(res)
        self.assertIn("pasting the content", res.lower())
        mock_content.assert_called_with(sample_reply, title="Document")

        # Test alternate phrasing
        res2 = asyncio.run(self.brain.execute_smart_skill("paste this into word"))
        self.assertIsNotNone(res2)
        self.assertIn("pasting the content", res2.lower())

    @patch("friday_ui.core.engine.open_word_with_content")
    def test_open_word_and_help_write(self, mock_content):
        mock_content.return_value = (True, "Inserted draft.")

        # Mock query_llm
        draft_text = "Dear Grandma, thank you so much for the wonderful birthday gift!"
        self.brain.query_llm = AsyncMock(return_value=draft_text)

        cmd = "open word and help me write a thank you note"
        res = asyncio.run(self.brain.execute_smart_skill(cmd))
        self.assertEqual(res, "__STREAMED__")
        self.brain.query_llm.assert_called()
        mock_content.assert_called_with(draft_text, title="a thank you note")

    @patch("friday_core.web.youtube.urllib.request.urlopen")
    def test_youtube_video_direct_resolution(self, mock_urlopen):
        # Mock YouTube HTML containing a watch?v= link
        mock_html = """
        <html>
            <body>
                <a href="/watch?v=ji1TIBybjp4">Golden Brown</a>
                <script>{"title":{"runs":[{"text":"The Stranglers - Golden Brown"}]}}</script>
            </body>
        </html>
        """
        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_html.encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        url, title = resolve_youtube_video("golden brown")
        self.assertEqual(url, "https://www.youtube.com/watch?v=ji1TIBybjp4&autoplay=1")
        self.assertEqual(title, "The Stranglers - Golden Brown")

    @patch("friday_ui.core.engine.resolve_youtube_video_async")
    @patch("friday_ui.core.engine.gatekeeper.execute_action")
    def test_open_youtube_and_play(self, mock_gatekeeper, mock_resolve):
        mock_resolve.return_value = ("https://www.youtube.com/watch?v=ji1TIBybjp4&autoplay=1", "The Stranglers - Golden Brown")
        mock_gatekeeper.return_value = MagicMock(success=True)

        res = asyncio.run(self.brain.execute_smart_skill("open youtube and play golden brown"))
        self.assertIsNotNone(res)
        self.assertIn("golden brown", res)
        mock_gatekeeper.assert_called()
        # Verify gatekeeper was called with the direct video URL
        intent_passed = mock_gatekeeper.call_args[0][0]
        self.assertEqual(intent_passed.target, "https://www.youtube.com/watch?v=ji1TIBybjp4&autoplay=1")

    @patch("friday_ui.core.engine.resolve_youtube_video_async")
    @patch("friday_ui.core.engine.gatekeeper.execute_action")
    def test_open_you_tube_with_spaces(self, mock_gatekeeper, mock_resolve):
        mock_resolve.return_value = ("https://www.youtube.com/watch?v=qvhM5AzhGiU&autoplay=1", "Golden Solace")
        mock_gatekeeper.return_value = MagicMock(success=True)

        res = asyncio.run(self.brain.execute_smart_skill("open you tube and play golden solace"))
        self.assertIsNotNone(res)
        self.assertIn("golden solace", res)
        mock_gatekeeper.assert_called()
        intent_passed = mock_gatekeeper.call_args[0][0]
        self.assertEqual(intent_passed.target, "https://www.youtube.com/watch?v=qvhM5AzhGiU&autoplay=1")

    @patch("friday_ui.core.engine.resolve_youtube_video_async")
    @patch("friday_ui.core.engine.gatekeeper.execute_action")
    def test_open_and_play_latest_video(self, mock_gatekeeper, mock_resolve):
        mock_resolve.return_value = ("https://www.youtube.com/watch?v=X1aFkAkFASk&autoplay=1", "Marvel Studios Thunderbolts")
        mock_gatekeeper.return_value = MagicMock(success=True)

        res = asyncio.run(self.brain.execute_smart_skill("open and play latest vidio of marvel"))
        self.assertIsNotNone(res)
        self.assertIn("latest vidio of marvel", res)
        mock_gatekeeper.assert_called()
        intent_passed = mock_gatekeeper.call_args[0][0]
        self.assertEqual(intent_passed.target, "https://www.youtube.com/watch?v=X1aFkAkFASk&autoplay=1")

    @patch("friday_ui.core.engine.gatekeeper.execute_action")
    def test_a_open_vs_code(self, mock_gatekeeper):
        mock_gatekeeper.return_value = MagicMock(success=True)

        # Test speech recognition noise: "a open vs code"
        res = asyncio.run(self.brain.execute_smart_skill("a open vs code"))
        self.assertIsNotNone(res)
        self.assertIn("vs code", res.lower())
        mock_gatekeeper.assert_called()
        intent_passed = mock_gatekeeper.call_args[0][0]
        self.assertEqual(intent_passed.action, "open_app")
        self.assertEqual(intent_passed.target, "vs code")

        # Test speech recognition noise: "uh open vs code"
        mock_gatekeeper.reset_mock()
        res = asyncio.run(self.brain.execute_smart_skill("uh open vs code"))
        self.assertIsNotNone(res)
        self.assertIn("vs code", res.lower())
        intent_passed = mock_gatekeeper.call_args[0][0]
        self.assertEqual(intent_passed.action, "open_app")
        self.assertEqual(intent_passed.target, "vs code")


if __name__ == "__main__":
    unittest.main()
