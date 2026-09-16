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

if __name__ == "__main__":
    unittest.main()
