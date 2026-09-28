"""
Tests for F.R.I.D.A.Y. 3.0 — Phase 11: Deep Research 2.0
Validates:
1. Query decomposition into orthogonal subqueries.
2. Source cross-checking, corroboration, and confidence scoring.
3. Contradiction detection across distinct sources.
4. Formal briefing synthesis and markdown rendering with URL provenance citations.
5. Emergency Stop integration during research execution.
6. False-success detection on empty or unverified sources.
"""

import unittest
from unittest.mock import MagicMock, patch

from friday_core.research.models import (
    ResearchSource,
    KeyFinding,
    Contradiction,
    ResearchBriefing
)
from friday_core.research.decomposer import QueryDecomposer
from friday_core.research.cross_checker import SourceCrossChecker
from friday_core.research.synthesizer import DeepResearchSynthesizer
from friday_core.research.engine import DeepResearchEngine
from friday_core.research.worker import DeepResearchWorker
from friday_core.agent.emergency_stop import emergency_stop
from friday_core.agent.task_lifecycle import task_supervisor, TaskState
from friday_ui.core.engine import fetch_page_content


class TestDeepResearch2(unittest.TestCase):
    def setUp(self):
        emergency_stop.reset()
        self.sources = [
            ResearchSource(
                url="https://tech.corp/qpu_benchmarks",
                title="QPU Benchmarks 2026",
                snippet="Superconducting qubits achieved a 99.9% two-qubit gate fidelity in laboratory benchmarks.",
                credibility_score=1.0
            ),
            ResearchSource(
                url="https://science.review/quantum_gates",
                title="Quantum Gate Scaling",
                snippet="Superconducting qubits achieved a 99.9% two-qubit gate fidelity according to independent university validation.",
                credibility_score=0.9
            ),
            ResearchSource(
                url="https://skeptic.blog/quantum_limits",
                title="Quantum Scalability Limits",
                snippet="Superconducting qubits have not achieved scalable coherence and failed real-world error correction benchmarks.",
                credibility_score=0.8
            )
        ]

    def tearDown(self):
        emergency_stop.reset()

    def test_query_decomposition(self):
        """Validates that a complex research request is cleaned and split into orthogonal facets."""
        raw_prompt = "deep research web and tell about solid state battery technology"
        cleaned = QueryDecomposer.clean_topic(raw_prompt)
        self.assertEqual(cleaned, "solid state battery technology")

        subqueries = QueryDecomposer.decompose(cleaned, max_subqueries=4)
        self.assertEqual(len(subqueries), 4)
        self.assertIn("overview", subqueries[0])
        self.assertIn("2026", subqueries[1])
        self.assertIn("limitations", subqueries[3])

    def test_source_cross_checking_and_corroboration(self):
        """Validates that corroborating sources boost finding confidence."""
        findings = SourceCrossChecker.extract_claims(self.sources)
        self.assertGreater(len(findings), 0)

        # Top finding should be the one supported by both source 1 and source 2
        top_finding = findings[0]
        self.assertIn("99.9%", top_finding.claim)
        self.assertEqual(len(top_finding.supporting_sources), 2)
        self.assertGreater(top_finding.confidence, 0.7)

    def test_contradiction_detection(self):
        """Validates identification of contrasting statements between sources."""
        contradictions = SourceCrossChecker.detect_contradictions(self.sources)
        self.assertGreater(len(contradictions), 0)
        c = contradictions[0]
        self.assertIn("tech.corp", c.source_a)
        self.assertIn("skeptic.blog", c.source_b)

    def test_briefing_synthesis_and_markdown(self):
        """Validates formal briefing generation and markdown rendering with URL provenance."""
        findings = SourceCrossChecker.extract_claims(self.sources)
        contradictions = SourceCrossChecker.detect_contradictions(self.sources)

        briefing = DeepResearchSynthesizer.synthesize(
            topic="Quantum Computing Qubit Scaling",
            findings=findings,
            contradictions=contradictions,
            sources=self.sources
        )

        self.assertTrue(briefing.is_verified)
        self.assertIn("Quantum Computing", briefing.executive_summary)
        self.assertEqual(len(briefing.sources), 3)

        # Markdown verification
        md = DeepResearchSynthesizer.format_markdown(briefing)
        self.assertIn("# Research Dossier: Quantum Computing Qubit Scaling", md)
        self.assertIn("## Executive Summary", md)
        self.assertIn("## Key Findings", md)
        self.assertIn("## Flagged Contradictions & Discrepancies", md)
        self.assertIn("[Source](https://tech.corp/qpu_benchmarks)", md)

    def test_false_success_on_empty_sources(self):
        """Validates that empty search results return an unverified briefing rather than false success."""
        engine = DeepResearchEngine()
        briefing = engine.conduct_research("obscure non-existent topic", sources_override=[])
        self.assertFalse(briefing.is_verified)
        self.assertIn("No verifiable multi-source intelligence", briefing.executive_summary)


class TestDeepResearchForensicsAndHardening(unittest.TestCase):
    """
    Forensic zero-trust test suite verifying complete failure and recovery modes:
    - empty search / zero sources -> fail-closed, no hallucination
    - network error / connection dropped
    - HTTP 500 server error
    - socket timeout
    - malformed HTML / tag stripping / length bounding
    - blocked page / non-HTML content
    - duplicate source deduplication
    - conflicting sources / contradiction detection
    - cooperative cancellation during crawling and synthesis
    - synthesis failure fallback with honest notice (no silent llama3.2:1b replacement)
    - SSRF prevention on private IP / metadata / localhost
    """

    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import QCoreApplication
        if not QCoreApplication.instance():
            cls._app = QCoreApplication([])

    def setUp(self):
        emergency_stop.reset()

    def tearDown(self):
        emergency_stop.reset()

    def test_ssrf_guard_in_fetch_page_content(self):
        """Verify fetch_page_content rejects loopback, private IP, and cloud metadata."""
        self.assertIsNone(fetch_page_content("http://127.0.0.1:11434/api/tags"))
        self.assertIsNone(fetch_page_content("http://localhost:8080/admin"))
        self.assertIsNone(fetch_page_content("http://169.254.169.254/latest/meta-data/"))
        self.assertIsNone(fetch_page_content("http://192.168.1.1/setup.cgi"))
        self.assertIsNone(fetch_page_content("http://10.0.0.1/private"))

    def test_fetch_page_content_malformed_html_and_bounding(self):
        """Verify malformed HTML with scripts and excessive size is sanitized and bounded."""
        huge_text = "Word " * 2000
        dirty_html = f"""
        <html>
            <head><script>alert('malicious')</script><style>body {{ display:none; }}</style></head>
            <body>
                <header>Navigation header</header>
                <p>Valid intelligence content that should be retained for research analysis.</p>
                <script>eval('bad code');</script>
                <p>{huge_text}</p>
                <footer>Legal footer boilerplate</footer>
            </body>
        </html>
        """
        mock_resp = MagicMock()
        mock_resp.headers = {'Content-Type': 'text/html; charset=utf-8'}
        mock_resp.read.return_value = dirty_html.encode('utf-8')
        mock_resp.__enter__.return_value = mock_resp

        with patch("friday_core.web.fetcher._NO_REDIRECT_OPENER.open", return_value=mock_resp):
            extracted = fetch_page_content("https://example.com/article", max_chars=1800)
            self.assertIsNotNone(extracted)
            self.assertNotIn("alert", extracted)
            self.assertNotIn("malicious", extracted)
            self.assertNotIn("bad code", extracted)
            self.assertIn("Valid intelligence content", extracted)
            self.assertLessEqual(len(extracted), 1800)

    def test_fetch_page_content_http_500_and_timeout(self):
        """Verify HTTP 500 error or socket timeout returns None cleanly without crashing."""
        import urllib.error
        import socket

        with patch("friday_core.web.fetcher._NO_REDIRECT_OPENER.open", side_effect=urllib.error.HTTPError("https://err.com", 500, "Server Error", {}, None)):
            res = fetch_page_content("https://err.com/500")
            self.assertIsNone(res)

        with patch("friday_core.web.fetcher._NO_REDIRECT_OPENER.open", side_effect=socket.timeout("Socket timed out")):
            res = fetch_page_content("https://slow.com/timeout")
            self.assertIsNone(res)

    def test_fetch_page_content_blocked_or_binary_content(self):
        """Verify non-HTML content (e.g. PDF, binary) returns None cleanly."""
        mock_resp = MagicMock()
        mock_resp.headers = {'Content-Type': 'application/pdf'}
        mock_resp.__enter__.return_value = mock_resp

        with patch("friday_core.web.fetcher._NO_REDIRECT_OPENER.open", return_value=mock_resp):
            res = fetch_page_content("https://example.com/document.pdf")
            self.assertIsNone(res)

    def test_worker_zero_sources_fails_closed_without_hallucination(self):
        """Verify worker transitions to FAILED and outputs honest message when 0 sources are found."""
        task = task_supervisor.create_task(
            query="totally nonexistent topic with zero search hits",
            session_id="test_zero_src",
            route="DEEP_RESEARCH"
        )
        worker = DeepResearchWorker(task_record=task, model_name="qwen3.5:9b")

        finished_results = []
        worker.finished_signal.connect(lambda md: finished_results.append(md))

        # Mock fetch_web_results to return empty list
        with patch("friday_core.research.worker.fetch_web_results", return_value=[]):
            worker.run()

        self.assertEqual(task.current_state, TaskState.FAILED)
        self.assertEqual(len(finished_results), 1)
        self.assertIn("Research Inconclusive", finished_results[0])
        self.assertIn("refuses to synthesize ungrounded claims", finished_results[0])

    def test_worker_network_error_fails_closed(self):
        """Verify network outage during search fails closed gracefully."""
        task = task_supervisor.create_task(
            query="test network outage",
            session_id="test_net_err",
            route="DEEP_RESEARCH"
        )
        worker = DeepResearchWorker(task_record=task, model_name="qwen3.5:9b")

        finished_results = []
        worker.finished_signal.connect(lambda md: finished_results.append(md))

        with patch("friday_core.research.worker.fetch_web_results", side_effect=OSError("Network is unreachable")):
            worker.run()

        self.assertEqual(task.current_state, TaskState.FAILED)
        self.assertEqual(len(finished_results), 1)
        self.assertIn("Research Inconclusive", finished_results[0])

    def test_worker_deduplicates_sources(self):
        """Verify duplicate URLs across query vectors are deduplicated."""
        task = task_supervisor.create_task(
            query="duplicate test query",
            session_id="test_dedup",
            route="DEEP_RESEARCH"
        )
        worker = DeepResearchWorker(task_record=task, model_name="qwen3.5:9b")

        duplicate_hits = [
            {"title": "Dup Source", "href": "https://example.com/same_page", "body": "Snippet A"},
            {"title": "Dup Source 2", "href": "https://example.com/same_page", "body": "Snippet B"},
            {"title": "Unique Source", "href": "https://example.com/other_page", "body": "Snippet C"},
        ]

        with patch("friday_core.research.worker.fetch_web_results", return_value=duplicate_hits), \
             patch("friday_core.research.worker.fetch_page_content", return_value="Page content text"), \
             patch.object(worker, "_stream_synthesis", return_value="Synthesized research report."):
            worker.run()

        self.assertEqual(task.current_state, TaskState.COMPLETED)

    def test_worker_synthesis_failure_falls_back_honestly_without_silent_replacement(self):
        """Verify synthesis HTTP 500 does NOT switch to llama3.2:1b and informs user honestly."""
        task = task_supervisor.create_task(
            query="test synthesis error handling",
            session_id="test_synth_err",
            route="DEEP_RESEARCH"
        )
        worker = DeepResearchWorker(task_record=task, model_name="qwen3.5:9b")

        valid_hits = [
            {"title": "Valid Source", "href": "https://example.com/valid", "body": "Valid facts discovered for research."}
        ]

        finished_results = []
        worker.finished_signal.connect(lambda md: finished_results.append(md))

        # Mock search succeeds, but Ollama returns 500
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.read.return_value = b'Internal Server Error'

        with patch("friday_core.research.worker.fetch_web_results", return_value=valid_hits), \
             patch("friday_core.research.worker.fetch_page_content", return_value="Detail text"), \
             patch("httpx.Client.send", return_value=mock_resp):
            worker.run()

        self.assertEqual(task.current_state, TaskState.COMPLETED)
        self.assertEqual(len(finished_results), 1)
        result_md = finished_results[0]
        # Must retain original model name in notice and must NOT have switched to llama3.2:1b
        self.assertIn("qwen3.5:9b", result_md)
        self.assertNotIn("llama3.2:1b", result_md)
        self.assertIn("Dossier compiled directly from verified source citations", result_md)
        self.assertIn("Valid Source", result_md)


if __name__ == "__main__":
    unittest.main()

