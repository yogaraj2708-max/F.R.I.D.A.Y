"""
Section H: MANDATORY UNIQUE-NONCE WEB TEST (Release Blocking)
Zero-Trust Web Grounding Verification:
1. Generates runtime cryptographic UUID nonce.
2. Serves unique nonce via live local HTTP server on ephemeral port.
3. Invokes FridayBrain.execute_smart_skill to retrieve and parse page.
4. Independent verification:
   - Live HTTP request was actually received by socket server.
   - Raw HTTP body contains nonce.
   - Response contains exact nonce in heading and paragraph.
   - Zero hallucination / no model memory fallback.
5. Failure-injection test:
   - Connection failure to dead port returns truthful failure, never fake success.
"""

import unittest
import asyncio
import uuid
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from unittest.mock import MagicMock

from friday_ui.core.engine import FridayBrain, FridaySignals


class NonceServerHandler(BaseHTTPRequestHandler):
    nonce = ""
    request_log = []

    def do_GET(self):
        NonceServerHandler.request_log.append({
            "path": self.path,
            "headers": dict(self.headers),
            "client": self.client_address
        })
        html = f"""<!DOCTYPE html>
<html>
<head><title>Title-{self.nonce}</title></head>
<body>
    <h1>FRIDAY-UNIQUE-{self.nonce}</h1>
    <p>GROUNDING-TEST-{self.nonce}</p>
</body>
</html>"""
        encoded = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        pass  # Suppress console logging during test


class TestMandatoryUniqueNonceWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Generate random cryptographic nonce
        cls.nonce = uuid.uuid4().hex[:16]
        NonceServerHandler.nonce = cls.nonce
        NonceServerHandler.request_log = []

        # Spin up HTTP server on ephemeral port (port 0 selects free port)
        cls.server = HTTPServer(("127.0.0.1", 0), NonceServerHandler)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

        # Initialize FridayBrain
        cls.signals = FridaySignals()
        cls.mock_tts = MagicMock()
        cls.mock_tts.is_available.return_value = False
        cls.mock_tts.cancel_event.is_set.return_value = False
        cls.mock_tts.stop_speaking = MagicMock()
        cls.brain = FridayBrain(cls.signals, cls.mock_tts)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_section_h_release_blocking_unique_nonce(self):
        """Release-blocking gate: Exact runtime nonce must appear in final parsed answer."""
        url = f"http://127.0.0.1:{self.port}"
        command = f"read the heading and paragraph of {url}"

        initial_requests = len(NonceServerHandler.request_log)
        res = asyncio.run(self.brain.execute_smart_skill(command))

        # 1. Physical verification: HTTP socket request actually occurred
        self.assertGreater(
            len(NonceServerHandler.request_log),
            initial_requests,
            "Independent Verifier: No live HTTP request was received by the server."
        )

        # 2. Output verification: Not None, no error prefix
        self.assertIsNotNone(res, "Web reading skill failed to execute.")
        self.assertFalse(res.startswith("⚠️"), f"Web reading returned an error: {res}")

        # 3. Grounding verification: Exact nonce must be present in heading and paragraph
        expected_heading_nonce = f"FRIDAY-UNIQUE-{self.nonce}"
        expected_para_nonce = f"GROUNDING-TEST-{self.nonce}"

        self.assertIn(
            expected_heading_nonce,
            res,
            f"Grounding failure: Heading nonce '{expected_heading_nonce}' not found in response:\n{res}"
        )
        self.assertIn(
            expected_para_nonce,
            res,
            f"Grounding failure: Paragraph nonce '{expected_para_nonce}' not found in response:\n{res}"
        )

    def test_semantic_variant_heading_only(self):
        """Verify semantic query for heading alone isolates the heading nonce."""
        url = f"http://127.0.0.1:{self.port}"
        command = f"what is the heading of {url}"
        res = asyncio.run(self.brain.execute_smart_skill(command))

        self.assertIsNotNone(res)
        expected_heading_nonce = f"FRIDAY-UNIQUE-{self.nonce}"
        self.assertIn(expected_heading_nonce, res)

    def test_failure_injection_dead_port_truthful_failure(self):
        """Failure Injection (Section M & BUG-016): Dead port must report error, never fabricate content."""
        dead_url = "http://127.0.0.1:59998"
        command = f"read the heading and paragraph of {dead_url}"

        res = asyncio.run(self.brain.execute_smart_skill(command))
        self.assertIsNotNone(res)
        self.assertTrue(
            res.startswith("⚠️ Webpage retrieval failed"),
            f"Expected truthful failure message, got: {res}"
        )
        # Ensure it didn't fabricate any nonce or mock text
        self.assertNotIn("FRIDAY-UNIQUE", res)


if __name__ == "__main__":
    unittest.main()
