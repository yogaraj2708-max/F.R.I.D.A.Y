"""
Tests for F.R.I.D.A.Y. 3.0 — Section 25: SSRF & URL Security
Validates:
1. is_safe_url blocks localhost, 127.0.0.1, and ::1.
2. is_safe_url blocks private network ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16).
3. is_safe_url blocks cloud metadata IP (169.254.169.254).
4. Non-HTTP schemes (file://, gopher://, javascript://) are rejected.
5. Dangerous redirects from public URLs to private destinations are refused by _NO_REDIRECT_OPENER.
"""

import unittest
import urllib.error
import urllib.request
from unittest.mock import patch, MagicMock

from friday_core.web.fetcher import is_safe_url, _NO_REDIRECT_OPENER, _NoRedirect
from friday_ui.core.engine import fetch_page_content_detailed


class TestResearchSSRF(unittest.TestCase):

    def test_01_block_localhost_and_loopback(self):
        """Verify access to localhost and 127.0.0.1 is blocked."""
        safe, reason = is_safe_url("http://localhost:8080/secret")
        self.assertFalse(safe)
        self.assertIn("localhost", reason.lower())

        safe, reason = is_safe_url("http://127.0.0.1:11434/api/tags")
        self.assertFalse(safe)
        self.assertIn("loopback", reason.lower())

    def test_02_block_cloud_metadata_endpoint(self):
        """Verify access to 169.254.169.254 is rejected."""
        safe, reason = is_safe_url("http://169.254.169.254/latest/meta-data/")
        self.assertFalse(safe)
        self.assertIn("cloud metadata", reason.lower())

    def test_03_block_private_subnets(self):
        """Verify RFC 1918 private subnets are blocked."""
        private_urls = [
            "http://10.0.0.1/admin",
            "http://192.168.1.1/setup",
            "http://172.16.0.1/status",
        ]
        for url in private_urls:
            safe, reason = is_safe_url(url)
            self.assertFalse(safe, f"Expected {url} to be blocked")
            self.assertIn("private network", reason.lower())

    def test_04_block_dangerous_schemes(self):
        """Verify file://, javascript://, and other non-http schemes are blocked."""
        dangerous_urls = [
            "file:///C:/Windows/System32/drivers/etc/hosts",
            "file:///etc/passwd",
            "javascript:alert(1)",
            "ftp://ftp.corp.local",
            "gopher://gopher.floodgap.com"
        ]
        for url in dangerous_urls:
            safe, reason = is_safe_url(url)
            self.assertFalse(safe, f"Expected {url} to be blocked")
            self.assertIn("scheme", reason.lower())

    def test_05_no_redirect_opener_refuses_redirect_to_private(self):
        """Verify HTTP 302 redirects are refused so that public-to-private pivot is blocked."""
        handler = _NoRedirect()
        req = urllib.request.Request("http://public-site.com/track")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            handler.redirect_request(req, None, 302, "Found", {}, "http://127.0.0.1:8080/admin")
        self.assertIn("Redirect to 'http://127.0.0.1:8080/admin' refused", str(ctx.exception))

    def test_06_fetch_page_content_detailed_blocks_ssrf(self):
        """Verify fetch_page_content_detailed returns BLOCKED for SSRF target."""
        res = fetch_page_content_detailed("http://127.0.0.1:8000/internal")
        self.assertEqual(res["parser_status"], "BLOCKED")
        self.assertEqual(res["http_status"], 403)
        self.assertIn("SSRF Guard", res["error"])


if __name__ == "__main__":
    unittest.main()
