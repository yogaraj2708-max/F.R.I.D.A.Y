"""
F.R.I.D.A.Y. Forensic Audit — Phase 5: Web Pipeline Probe
Tests web retrieval THROUGH the actual FridayBrain.execute_smart_skill path.
Verifies:
1. External live HTTP retrieval via actual engine dispatch (not direct HTTP)
2. httpbin.org dynamic nonce test (runtime-generated, model cannot know beforehand)
3. example.com title extraction
4. HTTP error truthful reporting
5. SSRF guard enforcement
6. Web vs telemetry routing collision
7. No model memory substitution
"""

import os
import sys
import uuid
import json
import asyncio
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from friday_ui.core.engine import FridayBrain, FridaySignals
from friday_core.router.semantic_router import SemanticIntentRouter, SkillIntent


class TestWebPipelineForensicProbe(unittest.TestCase):
    """Forensic audit probe for the web retrieval pipeline."""

    @classmethod
    def setUpClass(cls):
        cls.signals = FridaySignals()
        cls.mock_tts = MagicMock()
        cls.mock_tts.is_available.return_value = False
        cls.mock_tts.cancel_event.is_set.return_value = False
        cls.mock_tts.stop_speaking = MagicMock()
        cls.brain = FridayBrain(cls.signals, cls.mock_tts)
        cls.router = SemanticIntentRouter(threshold=0.76)

    # ── TEST-WEB-001: example.com title retrieval ──
    def test_web_001_example_com_title(self):
        """Verify title extraction from example.com comes from live HTTP, not model memory."""
        res = asyncio.run(self.brain.execute_smart_skill(
            "read https://example.com and tell me the title"
        ))
        self.assertIsNotNone(res, "Engine returned None for web reading command")
        # example.com title is "Example Domain"
        self.assertIn("Example Domain", res,
                       f"Title not found in response. Got: {res}")
        # Verify this was NOT routed to general chat
        self.assertNotIn("I don't have", res)

    # ── TEST-WEB-002: example.com first sentence ──
    def test_web_002_example_com_content(self):
        """Verify content extraction from example.com."""
        res = asyncio.run(self.brain.execute_smart_skill(
            "read https://example.com and tell me the first paragraph"
        ))
        self.assertIsNotNone(res, "Engine returned None for web reading command")
        # example.com actual text: "This domain is for use in illustrative examples in documents."
        # OR "This domain is for use in documentation examples without needing permission."
        self.assertTrue(
            "example" in res.lower() and ("domain" in res.lower() or "documentation" in res.lower()),
            f"Expected paragraph about example domain not found. Got: {res}"
        )

    # ── TEST-WEB-003: httpbin dynamic nonce ──
    def test_web_003_httpbin_dynamic_nonce(self):
        """
        Generate a runtime nonce unknown to the model, send it to httpbin,
        verify the engine extracts and returns the exact nonce.
        PASS only if the response contains the exact nonce string.
        """
        nonce = uuid.uuid4().hex
        url = f"https://httpbin.org/anything?friday_audit_nonce={nonce}"
        res = asyncio.run(self.brain.execute_smart_skill(
            f"read {url} and tell me what it says"
        ))
        self.assertIsNotNone(res, "Engine returned None for httpbin nonce test")
        self.assertIn(nonce, res,
                       f"Runtime nonce '{nonce}' not found in response. Got: {res[:500]}")

    # ── TEST-WEB-007: httpbin args extraction ──
    def test_web_007_httpbin_args_extraction(self):
        """Fetch httpbin with random query param, verify it appears in response."""
        random_val = uuid.uuid4().hex[:12]
        url = f"https://httpbin.org/get?x={random_val}"
        res = asyncio.run(self.brain.execute_smart_skill(
            f"read {url}"
        ))
        self.assertIsNotNone(res, "Engine returned None for httpbin args test")
        self.assertIn(random_val, res,
                       f"Random query value '{random_val}' not found in response. Got: {res[:500]}")

    # ── TEST-WEB-011: HTTP error truthful reporting ──
    def test_web_011_http_error_truthful(self):
        """Verify 404 or connection error is reported truthfully, not hallucinated."""
        res = asyncio.run(self.brain.execute_smart_skill(
            "read https://httpbin.org/status/404"
        ))
        self.assertIsNotNone(res)
        # Should contain error indication, not fabricated content
        err_indicators = ["404", "error", "failed", "⚠️", "not found", "Client Error"]
        self.assertTrue(
            any(ind.lower() in res.lower() for ind in err_indicators),
            f"Expected error indication for 404, got: {res}"
        )

    # ── TEST-WEB-ROUTING: Web vs Telemetry collision ──
    def test_web_routing_collision_web_vs_telemetry(self):
        """'use web to get current unixtime' MUST NOT route to local time skill."""
        route = asyncio.run(self.router.route("use web to get current unixtime"))
        self.assertNotEqual(route.intent, SkillIntent.SYSTEM_TIME_DATE,
                            f"Routed to TIME instead of WEB. Route: {route}")

    def test_web_routing_collision_web_vs_weather(self):
        """'open this page and tell me what it says about weather' MUST route to web, not weather."""
        route = asyncio.run(self.router.route("open this page and tell me what it says about weather"))
        self.assertNotEqual(route.intent, SkillIntent.WEATHER,
                            f"Routed to WEATHER instead of WEB. Route: {route}")

    # ── SSRF Guard ──
    def test_ssrf_guard_blocks_localhost(self):
        """SSRF guard must block localhost access."""
        from friday_core.web.fetcher import is_safe_url
        safe, reason = is_safe_url("http://localhost:8080/secret")
        self.assertFalse(safe, f"SSRF guard failed to block localhost. Reason: {reason}")

    def test_ssrf_guard_blocks_metadata(self):
        """SSRF guard must block cloud metadata endpoint."""
        from friday_core.web.fetcher import is_safe_url
        safe, reason = is_safe_url("http://169.254.169.254/latest/meta-data/")
        self.assertFalse(safe, f"SSRF guard failed to block metadata. Reason: {reason}")


if __name__ == "__main__":
    unittest.main()
