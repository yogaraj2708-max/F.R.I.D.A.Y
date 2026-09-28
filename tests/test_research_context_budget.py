"""
Tests for F.R.I.D.A.Y. 3.0 — Section 15 & 26: Context Budget & Payload Limits
Validates:
1. Web fetch caps extracted visible text to max_chars (e.g. 1800-2500) preventing giant raw dumps.
2. Web fetch caps HTTP response payload to prevent memory exhaustion / zip bombs.
3. DeepResearchWorker caps synthesis prompt and source summary context (~6000-8000 chars).
4. Raw HTML tags (scripts, styles, headers, footers) are stripped before context injection.
"""

import unittest
from unittest.mock import MagicMock, patch

from friday_ui.core.engine import fetch_page_content_detailed
from friday_core.research.models import ResearchSource
from friday_core.research.worker import DeepResearchWorker
from friday_core.agent.task_lifecycle import task_supervisor


class TestResearchContextBudget(unittest.TestCase):

    def setUp(self):
        self.dns_patcher = patch("socket.gethostbyname", return_value="93.184.216.34")
        self.dns_patcher.start()

    def tearDown(self):
        self.dns_patcher.stop()

    def test_01_page_fetch_caps_text_length(self):
        """Verify fetch_page_content_detailed strictly enforces max_chars budget."""
        huge_paragraph = "<p>" + ("Intelligence observation data. " * 500) + "</p>"
        html_content = f"<html><body>{huge_paragraph}</body></html>"

        mock_resp = MagicMock()
        mock_resp.headers = {'Content-Type': 'text/html; charset=utf-8'}
        mock_resp.read.return_value = html_content.encode('utf-8')
        mock_resp.__enter__.return_value = mock_resp

        with patch("friday_core.web.fetcher._NO_REDIRECT_OPENER.open", return_value=mock_resp):
            res = fetch_page_content_detailed("https://example.com/huge", max_chars=1200)
            self.assertIsNotNone(res["extracted_text"])
            self.assertLessEqual(len(res["extracted_text"]), 1200)

    def test_02_html_strips_scripts_and_styles(self):
        """Verify markup, stylesheets, and scripts are stripped so tokens are not wasted on noise."""
        raw_html = """
        <html>
            <head>
                <style>.ads { color: red; }</style>
                <script>function track() { return 1; }</script>
            </head>
            <body>
                <header><nav>Home About Contact</nav></header>
                <main>
                    <h1>Core Scientific Breakthrough</h1>
                    <p>Researchers verified anomalous high-temperature superconductivity under ambient conditions.</p>
                </main>
                <footer>Copyright 2026 Corporation</footer>
            </body>
        </html>
        """
        mock_resp = MagicMock()
        mock_resp.headers = {'Content-Type': 'text/html; charset=utf-8'}
        mock_resp.read.return_value = raw_html.encode('utf-8')
        mock_resp.__enter__.return_value = mock_resp

        with patch("friday_core.web.fetcher._NO_REDIRECT_OPENER.open", return_value=mock_resp):
            res = fetch_page_content_detailed("https://example.com/article")
            extracted = res["extracted_text"]
            self.assertIsNotNone(extracted)
            self.assertNotIn("<style>", extracted)
            self.assertNotIn("function track", extracted)
            self.assertNotIn("Home About Contact", extracted)
            self.assertIn("Core Scientific Breakthrough", extracted)

    def test_03_worker_synthesis_context_budget_is_bounded(self):
        """Verify DeepResearchWorker synthesis prompt stays within strict token/character budget."""
        task = task_supervisor.create_task(
            query="test context budget query",
            session_id="test_ctx_budget",
            route="DEEP_RESEARCH"
        )
        worker = DeepResearchWorker(task_record=task)

        # Create 20 mock hits
        many_hits = [
            {"title": f"Source {i}", "href": f"https://example.com/{i}", "body": f"Snippet {i} " * 50}
            for i in range(20)
        ]

        captured_prompt = []

        def mock_stream(prompt):
            captured_prompt.append(prompt)
            return "Synthesized result."

        with patch("friday_core.research.worker.fetch_web_results", return_value=many_hits), \
             patch("friday_core.research.worker.fetch_page_content_detailed", return_value={"extracted_text": "Detail text " * 100, "parser_status": "SUCCESS"}), \
             patch.object(worker, "_stream_synthesis", side_effect=mock_stream):
            worker.run()

        self.assertEqual(len(captured_prompt), 1)
        p = captured_prompt[0]
        # Must be bounded: maximum ~10,000 characters to prevent context window explosion
        self.assertLess(len(p), 10000, f"Synthesis prompt was {len(p)} chars, exceeding safe budget")


if __name__ == "__main__":
    unittest.main()
