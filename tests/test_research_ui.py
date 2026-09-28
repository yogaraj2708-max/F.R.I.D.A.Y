"""
Tests for F.R.I.D.A.Y. 3.0 Deep Research UI.
Verifies command bar inputs, stage transitions, live source card stream, and final report rendering.
"""

import sys
import unittest
from PySide6.QtWidgets import QApplication

from friday_ui.views.research_view import ResearchView, SourceCard


class TestResearchUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(sys.argv)

    def setUp(self):
        self.research_view = ResearchView()
        self.research_view.resize(950, 650)
        self.research_view.show()
        self.app.processEvents()

    def tearDown(self):
        self.research_view.close()
        self.app.processEvents()

    def test_start_research_emits_signal(self):
        """Verifies starting research triggers research_requested with topic and depth."""
        emitted = []
        self.research_view.research_requested.connect(lambda top, dep: emitted.append((top, dep)))

        self.research_view.query_input.setText("Autonomous tool calling protocols")
        self.research_view._start_research()
        self.app.processEvents()

        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0][0], "Autonomous tool calling protocols")
        self.assertTrue(self.research_view._is_active)
        self.assertTrue(self.research_view.stop_btn.isVisible())

    def test_live_source_cards_addition(self):
        """Verifies appending source cards displays compact card and updates count."""
        rv = self.research_view
        self.assertTrue(rv.sources_container.isHidden())

        rv.add_source(domain="arxiv.org", title="LLM Agent Reasoning Foundations", status="Verified", relevance="High")
        self.app.processEvents()

        self.assertTrue(rv.sources_container.isVisible())
        self.assertEqual(rv.sources_count_lbl.text(), "1 sources")

        rv.clear_sources()
        self.app.processEvents()
        self.assertTrue(rv.sources_container.isHidden())

    def test_stop_research_cancels_properly(self):
        """Verifies stopping research emits signal and marks UI as CANCELLED."""
        rv = self.research_view
        rv.query_input.setText("Testing cancel")
        rv._start_research()
        self.assertTrue(rv._is_active)

        cancelled = []
        rv.research_stopped.connect(lambda: cancelled.append(True))
        rv._stop_research()
        self.app.processEvents()

        self.assertEqual(len(cancelled), 1)
        self.assertFalse(rv._is_active)
        self.assertTrue(rv.stop_btn.isHidden())
        self.assertIn("CANCELLED", rv.report_status_pill.text())

    def test_update_report_renders_briefing(self):
        """Verifies update_report updates markdown and marks COMPLETED."""
        rv = self.research_view
        test_markdown = "### Executive Summary\n\nAll 8 citations were verified."
        rv.update_report("Test Topic", test_markdown)
        self.app.processEvents()

        self.assertIn("COMPLETED", rv.report_status_pill.text())
        self.assertIn("Executive Summary", rv.report_browser.toPlainText())
        self.assertEqual(rv.progress_bar.value(), 100)


if __name__ == "__main__":
    unittest.main()
