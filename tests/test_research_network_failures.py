"""
Tests for F.R.I.D.A.Y. 3.0 — Section 9 & 10: Research Network and Quality Failures
Validates:
1. HTTP 404, 403, 500 responses return clean failure records without crashing.
2. DNS resolution failure and socket timeouts transition gracefully to TIMEOUT/FAILED.
3. Empty responses, JavaScript-only shells (<50 chars), and binary content are marked EMPTY/BLOCKED.
4. Total network outage fails closed with honest inconclusive status and zero fabricated claims.
"""

import unittest
from unittest.mock import MagicMock, patch
import socket
import urllib.error

from friday_ui.core.engine import fetch_page_content_detailed
from friday_core.research.engine import DeepResearchEngine
from friday_core.research.models import ResearchSource


class TestResearchNetworkFailures(unittest.TestCase):

    def setUp(self):
        self.dns_patcher = patch("socket.gethostbyname", return_value="93.184.216.34")
        self.dns_patcher.start()

    def tearDown(self):
        self.dns_patcher.stop()

    def test_01_http_404_not_found(self):
        """Verify HTTP 404 returns parser_status FAILED with status 404."""
        err = urllib.error.HTTPError("https://example.com/404", 404, "Not Found", {}, None)
        with patch("friday_core.web.fetcher._NO_REDIRECT_OPENER.open", side_effect=err):
            res = fetch_page_content_detailed("https://example.com/404")
            self.assertEqual(res["http_status"], 404)
            self.assertEqual(res["parser_status"], "FAILED")
            self.assertIsNone(res["extracted_text"])

    def test_02_http_403_forbidden(self):
        """Verify HTTP 403 returns parser_status FAILED with status 403."""
        err = urllib.error.HTTPError("https://example.com/403", 403, "Forbidden", {}, None)
        with patch("friday_core.web.fetcher._NO_REDIRECT_OPENER.open", side_effect=err):
            res = fetch_page_content_detailed("https://example.com/403")
            self.assertEqual(res["http_status"], 403)
            self.assertEqual(res["parser_status"], "FAILED")
            self.assertIsNone(res["extracted_text"])

    def test_03_http_500_server_error(self):
        """Verify HTTP 500 returns parser_status FAILED with status 500."""
        err = urllib.error.HTTPError("https://example.com/500", 500, "Internal Server Error", {}, None)
        with patch("friday_core.web.fetcher._NO_REDIRECT_OPENER.open", side_effect=err):
            res = fetch_page_content_detailed("https://example.com/500")
            self.assertEqual(res["http_status"], 500)
            self.assertEqual(res["parser_status"], "FAILED")
            self.assertIsNone(res["extracted_text"])

    def test_04_socket_timeout(self):
        """Verify socket timeout returns timeout_status True and parser_status TIMEOUT."""
        with patch("friday_core.web.fetcher._NO_REDIRECT_OPENER.open", side_effect=socket.timeout("Connection timed out")):
            res = fetch_page_content_detailed("https://example.com/timeout")
            self.assertTrue(res["timeout_status"])
            self.assertEqual(res["parser_status"], "TIMEOUT")
            self.assertEqual(res["http_status"], 408)

    def test_05_dns_resolution_failure(self):
        """Verify DNS lookup failure fails safely."""
        self.dns_patcher.stop()
        try:
            with patch("socket.gethostbyname", side_effect=socket.gaierror("Name or service not known")):
                res = fetch_page_content_detailed("https://nonexistent-domain-xyz-12345.org")
                self.assertEqual(res["parser_status"], "BLOCKED")
                self.assertIn("DNS resolution", res["error"])
        finally:
            self.dns_patcher.start()

    def test_06_empty_response_and_js_shell(self):
        """Verify empty HTML or JS-only client shell (<50 chars) returns parser_status EMPTY."""
        mock_resp = MagicMock()
        mock_resp.headers = {'Content-Type': 'text/html; charset=utf-8'}
        mock_resp.read.return_value = b"<html><head><script src='bundle.js'></script></head><body><div id='app'></div></body></html>"
        mock_resp.__enter__.return_value = mock_resp

        with patch("friday_core.web.fetcher._NO_REDIRECT_OPENER.open", return_value=mock_resp):
            res = fetch_page_content_detailed("https://spa.example.com")
            self.assertEqual(res["parser_status"], "EMPTY")
            self.assertIsNone(res["extracted_text"])

    def test_07_binary_or_pdf_content_blocked(self):
        """Verify non-HTML content type is marked BLOCKED."""
        mock_resp = MagicMock()
        mock_resp.headers = {'Content-Type': 'application/octet-stream'}
        mock_resp.__enter__.return_value = mock_resp

        with patch("friday_core.web.fetcher._NO_REDIRECT_OPENER.open", return_value=mock_resp):
            res = fetch_page_content_detailed("https://example.com/binary.bin")
            self.assertEqual(res["parser_status"], "BLOCKED")
            self.assertIn("Unsupported Content-Type", res["error"])

    def test_08_total_network_outage_fails_closed_without_hallucination(self):
        """Verify complete network unavailability produces honest inconclusive briefing."""
        mock_search_fn = MagicMock(side_effect=OSError("Network is completely unreachable"))
        engine = DeepResearchEngine(search_fetcher=mock_search_fn)

        briefing = engine.conduct_research("latest semiconductor advances")
        self.assertFalse(briefing.is_verified)
        self.assertEqual(briefing.total_sources_verified, 0)
        self.assertEqual(len(briefing.findings), 0)
        self.assertIn("Research Inconclusive", briefing.executive_summary)
        self.assertIn("refuses to synthesize ungrounded claims", briefing.executive_summary)


if __name__ == "__main__":
    unittest.main()
