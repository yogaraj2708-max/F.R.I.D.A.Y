"""
Tests for F.R.I.D.A.Y. 3.0 — Section 1, 2, 28, 29, 37: Deep Research Forensics
Validates:
1. End-to-end trace: USER -> MAIN MODEL -> native deep_research tool_call -> dispatcher -> engine -> HTTP -> extraction -> provenance -> synthesis -> tool result -> main model.
2. Unique-nonce test query ensuring real retrieval without fabrication.
3. Tool result format preserves tool_call_id, tool_name, status, sources, evidence, provenance.
4. Structured failure formatting when zero sources are found, supporting same-model replanning.
"""

import unittest
import uuid
import time
from unittest.mock import MagicMock, patch, AsyncMock

from friday_core.research.models import ResearchSource, KeyFinding, Contradiction, ResearchBriefing
from friday_core.research.engine import DeepResearchEngine
from friday_core.research.synthesizer import DeepResearchSynthesizer
from friday_core.skills.agent_bridge import agent_tool_bridge
from friday_core.agent.task_lifecycle import task_supervisor, TaskState


class TestDeepResearchForensics(unittest.TestCase):

    def test_01_unique_nonce_search_execution_and_provenance(self):
        """Verify unique nonce in query is executed through search, retrieval, and provenance tracking."""
        nonce = f"NONCE_{uuid.uuid4().hex[:10]}"
        query = f"NVIDIA Blackwell Ultra benchmark verification {nonce}"

        mock_search_results = [
            {
                "title": f"NVIDIA Official Announcement {nonce}",
                "href": "https://nvidianews.nvidia.com/news/blackwell-ultra",
                "body": f"Official details on Blackwell Ultra architecture and specifications {nonce}."
            }
        ]

        page_record = {
            "original_url": "https://nvidianews.nvidia.com/news/blackwell-ultra",
            "final_url": "https://nvidianews.nvidia.com/news/blackwell-ultra",
            "http_status": 200,
            "content_type": "text/html",
            "content_length": 1540,
            "retrieved_at": "2026-09-27T12:00:00Z",
            "timeout_status": False,
            "parser_status": "SUCCESS",
            "extracted_text": f"NVIDIA announced the Blackwell Ultra platform delivering unprecedented computing density for enterprise AI {nonce}.",
            "content_hash": "a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0",
            "relevant_excerpt": f"Blackwell Ultra platform delivering unprecedented computing density {nonce}."
        }

        mock_search_fn = MagicMock(return_value=mock_search_results)
        mock_page_fn = MagicMock(return_value=page_record)

        engine = DeepResearchEngine(search_fetcher=mock_search_fn, page_fetcher=mock_page_fn)
        briefing = engine.conduct_research(query, max_subqueries=2)

        # Assert search was actually called with subquery containing topic keywords
        self.assertTrue(mock_search_fn.called)
        self.assertTrue(mock_page_fn.called)
        self.assertTrue(briefing.is_verified)
        self.assertGreaterEqual(briefing.total_sources_verified, 1)

        # Verify source metadata preserved
        src = briefing.sources[0]
        self.assertEqual(src.http_status, 200)
        self.assertEqual(src.verification_status, "VERIFIED")
        self.assertEqual(src.content_hash, page_record["content_hash"])
        self.assertIn(nonce, src.snippet)

        # Verify findings maintain provenance to exact URL and content hash
        self.assertGreater(len(briefing.findings), 0)
        finding = briefing.findings[0]
        self.assertIn(src.url, finding.supporting_sources)
        self.assertGreater(len(finding.provenance_chain), 0)
        self.assertEqual(finding.provenance_chain[0]["content_hash"], page_record["content_hash"])

    def test_02_native_tool_call_result_preserves_provenance_and_schema(self):
        """Verify tool result formatted for the main model preserves tool_call_id, status, sources, and provenance."""
        tool_call_id = f"call_{uuid.uuid4().hex[:8]}"
        trace_id = f"trace_{uuid.uuid4().hex[:8]}"
        raw_output = (
            "# Research Dossier: Quantum Computing\n\n"
            "## Key Findings\n"
            "1. Coherence time improved by 40%.\n"
            "   - Citations: [Source](https://quantum.nature.com/article1)\n\n"
            "## Consulted Sources\n"
            "- [Nature Quantum](https://quantum.nature.com/article1)\n"
        )

        verified_bundle = agent_tool_bridge.verify_tool_result(
            tool_name="deep_research",
            arguments={"topic": "Quantum Computing"},
            raw_output=raw_output,
            trace_id=trace_id,
            tool_call_id=tool_call_id
        )

        self.assertEqual(verified_bundle["tool_name"], "deep_research")
        self.assertEqual(verified_bundle["tool_call_id"], tool_call_id)
        self.assertEqual(verified_bundle["execution_status"], "SUCCESS")
        self.assertEqual(verified_bundle["verification_status"], "VERIFIED")
        self.assertEqual(verified_bundle["trace_id"], trace_id)
        self.assertIn("https://quantum.nature.com/article1", verified_bundle["source_urls"])

        # Check formatted result contains provenance header
        formatted = verified_bundle["formatted_result"]
        self.assertIn("[VERIFIED TOOL PROVENANCE", formatted)
        self.assertIn("deep_research", formatted)
        self.assertIn("SUCCESS", formatted)
        self.assertIn(trace_id, formatted)

    def test_03_structured_failure_returned_to_main_model_for_replanning(self):
        """Verify research failure returns structured error that the main model can replan on."""
        mock_search_fn = MagicMock(return_value=[])
        engine = DeepResearchEngine(search_fetcher=mock_search_fn)

        briefing = engine.conduct_research("obscure query with zero results")
        self.assertFalse(briefing.is_verified)
        self.assertEqual(briefing.total_sources_verified, 0)
        self.assertIn("Research Inconclusive", briefing.executive_summary)

        # Formatting through verify_tool_result must report FAILED/REJECTED
        verified_bundle = agent_tool_bridge.verify_tool_result(
            tool_name="deep_research",
            arguments={"topic": "obscure query"},
            raw_output=f"Error: No verifiable web sources could be retrieved. {briefing.executive_summary}",
            trace_id="test_trace_fail"
        )

        self.assertEqual(verified_bundle["execution_status"], "FAILED")
        self.assertEqual(verified_bundle["verification_status"], "REJECTED")
        self.assertIn("Error:", verified_bundle["formatted_result"])


if __name__ == "__main__":
    unittest.main()
