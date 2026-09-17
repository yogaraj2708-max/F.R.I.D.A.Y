"""
Tests for friday_core.web (Safe Web Access Engine)
Verifies SSRF filtering, prompt-injection delimiter shielding, and HTML stripping.
"""

import unittest
from friday_core.web.fetcher import is_safe_url, clean_html_to_text, PROMPT_DELIMITER_START, PROMPT_DELIMITER_END

class TestSafeWeb(unittest.TestCase):
    def test_ssrf_rejects_localhost(self):
        safe, msg = is_safe_url("http://localhost/admin")
        self.assertFalse(safe)
        self.assertIn("localhost", msg.lower())

    def test_ssrf_rejects_loopback_ip(self):
        safe, msg = is_safe_url("http://127.0.0.1:8080/secret")
        self.assertFalse(safe)
        self.assertIn("loopback", msg.lower())

    def test_ssrf_rejects_private_class_c(self):
        safe, msg = is_safe_url("http://192.168.1.1/router")
        self.assertFalse(safe)
        self.assertIn("private", msg.lower())

    def test_ssrf_rejects_private_class_a(self):
        safe, msg = is_safe_url("http://10.0.0.1/intranet")
        self.assertFalse(safe)
        self.assertIn("private", msg.lower())

    def test_ssrf_rejects_cloud_metadata(self):
        safe, msg = is_safe_url("http://169.254.169.254/latest/meta-data/")
        self.assertFalse(safe)
        self.assertIn("metadata", msg.lower())

    def test_ssrf_rejects_non_http_schemes(self):
        safe, _ = is_safe_url("file:///C:/Windows/win.ini")
        self.assertFalse(safe)
        safe, _ = is_safe_url("gopher://example.com")
        self.assertFalse(safe)
        safe, _ = is_safe_url("ftp://ftp.example.com")
        self.assertFalse(safe)

    def test_html_cleaning_strips_scripts(self):
        dirty = "<html><head><script>alert('xss')</script><style>body{color:red;}</style></head><body><h1>Hello World</h1><p>Test paragraph.</p></body></html>"
        cleaned = clean_html_to_text(dirty)
        self.assertNotIn("alert", cleaned)
        self.assertNotIn("color:red", cleaned)
        self.assertIn("Hello World", cleaned)
        self.assertIn("Test paragraph.", cleaned)

    def test_prompt_delimiter_shielding_constants(self):
        self.assertEqual(PROMPT_DELIMITER_START, "<<<EXTERNAL_WEB_REFERENCE_DATA_NOT_SYSTEM_INSTRUCTIONS>>>")
        self.assertEqual(PROMPT_DELIMITER_END, "<<<END_EXTERNAL_WEB_REFERENCE_DATA>>>")

    def test_inline_web_search_temporal_and_contextual_triggers(self):
        import asyncio
        from unittest.mock import MagicMock, patch
        from PySide6.QtWidgets import QApplication
        import sys
        from friday_ui.core.engine import FridayBrain, FridaySignals

        if not QApplication.instance():
            _ = QApplication(sys.argv)

        signals = FridaySignals()
        tts = MagicMock()
        brain = FridayBrain(signals, tts)

        # Simulate prior conversation history about AI models
        brain.conversation_history.append({"role": "user", "content": "what are the latest ai models"})

        with patch("friday_ui.core.engine.fetch_web_results", return_value=[{"title": "Test AI 2026", "body": "Latest 2026 model info", "href": "https://example.com"}]), \
             patch.object(brain, "query_llm", return_value="Here is 2026 intel") as mock_query:
            res = asyncio.run(brain.execute_smart_skill("no tell as of 2026"))
            self.assertEqual(res, "__STREAMED__")
            self.assertTrue(mock_query.called)
            called_prompt = mock_query.call_args[0][0]
            self.assertIn("LIVE DUCKDUCKGO WEB SEARCH INTELLIGENCE", called_prompt)
            self.assertIn("Test AI 2026", called_prompt)


if __name__ == "__main__":
    unittest.main()

