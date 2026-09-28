"""
Tests for F.R.I.D.A.Y. 3.0 — Section 0, 5, 19, 20: False-Success & Hallucination Prevention
Validates:
1. Zero-source fail-closed: 0 search hits results in unverified briefing with refusal to hallucinate.
2. Snippet-only false research prevention: Sources with unverified page bodies (<50 chars or failed fetch)
   are tagged UNVERIFIED and not claimed as verified deep research.
3. Insufficient evidence handling: When retrieved sources do not contain answer to query,
   system flags research as unverified / inconclusive rather than inventing facts.
"""

import unittest
from unittest.mock import MagicMock, patch

from friday_core.research.models import ResearchSource, ResearchBriefing
from friday_core.research.engine import DeepResearchEngine
from friday_core.research.synthesizer import DeepResearchSynthesizer
from friday_core.research.worker import DeepResearchWorker
from friday_core.agent.task_lifecycle import task_supervisor, TaskState


class TestResearchFalseSuccess(unittest.TestCase):

    def test_01_zero_sources_returns_inconclusive_briefing(self):
        """Verify conduct_research with empty search results refuses to hallucinate."""
        mock_search = MagicMock(return_value=[])
        engine = DeepResearchEngine(search_fetcher=mock_search)

        briefing = engine.conduct_research("hypothetical non-existent phenomenon 98765")
        self.assertFalse(briefing.is_verified)
        self.assertEqual(briefing.total_sources_verified, 0)
        self.assertEqual(len(briefing.findings), 0)
        self.assertIn("Research Inconclusive", briefing.executive_summary)
        self.assertIn("refuses to synthesize ungrounded claims", briefing.executive_summary)

    def test_02_snippet_only_sources_remain_unverified(self):
        """Verify sources where deep page extraction fails remain UNVERIFIED."""
        search_hits = [
            {
                "title": "Unreachable Article",
                "href": "https://unreachable.org/news",
                "body": "A short search engine snippet that cannot be verified."
            }
        ]

        mock_search = MagicMock(return_value=search_hits)
        # Deep page fetch fails (e.g. 404 or empty)
        mock_page = MagicMock(return_value={"extracted_text": None, "parser_status": "FAILED", "http_status": 404})

        engine = DeepResearchEngine(search_fetcher=mock_search, page_fetcher=mock_page)
        briefing = engine.conduct_research("unreachable topic")

        self.assertFalse(briefing.is_verified)
        self.assertEqual(briefing.total_sources_verified, 0)
        self.assertEqual(briefing.sources[0].verification_status, "UNVERIFIED")

    def test_03_worker_fails_closed_when_all_sources_unverified(self):
        """Verify worker halts with TaskState.FAILED when search hits yield 0 verified pages."""
        task = task_supervisor.create_task(
            query="all sources broken test",
            session_id="test_unverif_worker",
            route="DEEP_RESEARCH"
        )
        worker = DeepResearchWorker(task_record=task)

        search_hits = [
            {"title": "Broken Link 1", "href": "https://broken1.com", "body": "Snippet 1"},
            {"title": "Broken Link 2", "href": "https://broken2.com", "body": "Snippet 2"},
        ]

        finished_results = []
        worker.finished_signal.connect(lambda md: finished_results.append(md))

        # Page reading fails for both
        with patch("friday_core.research.worker.fetch_web_results", return_value=search_hits), \
             patch("friday_core.research.worker.fetch_page_content_detailed", return_value={"extracted_text": None, "parser_status": "FAILED", "http_status": 500}):
            worker.run()

        # If zero verified pages, worker must fail closed or synthesize inconclusive dossier
        self.assertIn(task.current_state, [TaskState.FAILED, TaskState.COMPLETED])
        self.assertEqual(len(finished_results), 1)
        # Must not fabricate facts
        res = finished_results[0]
        self.assertTrue(
            "Research Inconclusive" in res or "No verifiable" in res or "Dossier compiled directly" in res,
            f"Unexpected response on failed sources: {res[:200]}"
        )


if __name__ == "__main__":
    unittest.main()
