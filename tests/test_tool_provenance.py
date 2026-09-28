"""
Tests for Tool Provenance and Security Layer (Section 19, 20).
Verifies:
1. Tool executions produce complete provenance:
   - tool_name
   - tool_call_id
   - trace_id
   - execution_status (SUCCESS | FAILED | BLOCKED)
   - verification_status (VERIFIED | UNVERIFIED | REJECTED)
   - executed_at
2. Domain-specific provenance:
   - Web tools: source_urls
   - UI tools: target_app, action, verified_state
   - Document tools: source_file, extracted_chars
3. Security risk gate blocks dangerous actions before execution and returns BLOCKED.
"""

import unittest
from friday_core.skills.agent_bridge import agent_tool_bridge


class TestToolProvenance(unittest.TestCase):
    def test_complete_provenance_structure(self):
        bundle = agent_tool_bridge.verify_tool_result(
            tool_name="calculate",
            arguments={"expression": "10 + 10"},
            raw_output="20",
            trace_id="trace-test-101",
            tool_call_id="call-test-101"
        )

        self.assertIn("tool_name", bundle)
        self.assertEqual(bundle["tool_name"], "calculate")
        self.assertEqual(bundle["tool_call_id"], "call-test-101")
        self.assertEqual(bundle["trace_id"], "trace-test-101")
        self.assertEqual(bundle["status"], "SUCCESS")
        self.assertEqual(bundle["verification_status"], "VERIFIED")
        self.assertIn("executed_at", bundle)

    def test_web_tool_provenance(self):
        sample_output = "Results from https://example.com/news and https://test.org/article"
        bundle = agent_tool_bridge.verify_tool_result(
            tool_name="web_search",
            arguments={"query": "quantum computing"},
            raw_output=sample_output,
            trace_id="trace-web-1",
            tool_call_id="call-web-1"
        )
        self.assertIn("source_urls", bundle)
        self.assertIn("https://example.com/news", bundle["source_urls"])
        self.assertIn("https://test.org/article", bundle["source_urls"])

    def test_ui_tool_provenance(self):
        bundle = agent_tool_bridge.verify_tool_result(
            tool_name="launch_app",
            arguments={"app_name": "notepad"},
            raw_output="Launched notepad successfully.",
            trace_id="trace-ui-1",
            tool_call_id="call-ui-1"
        )
        self.assertEqual(bundle["target_app"], "notepad")
        self.assertEqual(bundle["action"], "launch_app")
        self.assertEqual(bundle["verified_state"], "CONFIRMED_ON_DESKTOP")

    def test_document_tool_provenance(self):
        bundle = agent_tool_bridge.verify_tool_result(
            tool_name="read_document",
            arguments={"file_path": "C:\\docs\\manual.pdf"},
            raw_output="Extracted text from page 1.",
            trace_id="trace-doc-1",
            tool_call_id="call-doc-1"
        )
        self.assertEqual(bundle["source_file"], "C:\\docs\\manual.pdf")
        self.assertGreater(bundle["extracted_chars"], 0)

    def test_security_gate_blocks_dangerous_actions(self):
        # Format hard drive or destructive commands
        allowed, reason = agent_tool_bridge.risk_gate("launch_app", {"app_name": "cmd.exe /c format C:"})
        self.assertFalse(allowed)
        self.assertIn("destructive", reason.lower())

        # Path traversal or system directory tampering
        allowed_doc, doc_reason = agent_tool_bridge.risk_gate("read_document", {"file_path": "C:\\Windows\\System32\\config\\SAM"})
        self.assertFalse(allowed_doc)
        self.assertIn("sensitive", doc_reason.lower())

        # Relative path traversal
        allowed_trav, trav_reason = agent_tool_bridge.risk_gate("read_document", {"file_path": "../../secret.env"})
        self.assertFalse(allowed_trav)
        self.assertIn("traversal", trav_reason.lower())

        # UNC network share abuse
        allowed_unc, unc_reason = agent_tool_bridge.risk_gate("read_document", {"file_path": "\\\\attacker-ip\\share\\payload.pdf"})
        self.assertFalse(allowed_unc)
        self.assertIn("unc", unc_reason.lower())

        # SSRF: localhost and private IPs
        allowed_lh, lh_reason = agent_tool_bridge.risk_gate("web_fetch", {"url": "http://localhost:8080/metrics"})
        self.assertFalse(allowed_lh)
        self.assertIn("ssrf", lh_reason.lower())

        allowed_meta, meta_reason = agent_tool_bridge.risk_gate("deep_research", {"topic": "http://169.254.169.254/latest/meta-data"})
        self.assertFalse(allowed_meta)
        self.assertIn("ssrf", meta_reason.lower())

        allowed_priv, priv_reason = agent_tool_bridge.risk_gate("web_fetch", {"url": "http://192.168.1.1/admin"})
        self.assertFalse(allowed_priv)
        self.assertIn("ssrf", priv_reason.lower())

        # Non-HTTP schemes
        allowed_file, file_reason = agent_tool_bridge.risk_gate("web_fetch", {"url": "file:///c:/windows/win.ini"})
        self.assertFalse(allowed_file)
        self.assertIn("unsupported scheme", file_reason.lower())

        # Script interpreter injection
        allowed_ps, ps_reason = agent_tool_bridge.risk_gate("launch_app", {"app_name": "powershell.exe -enc JABhID0A..."})
        self.assertFalse(allowed_ps)
        self.assertIn("injection", ps_reason.lower())

    def test_tool_failure_status_unverified(self):
        bundle = agent_tool_bridge.verify_tool_result(
            tool_name="web_search",
            arguments={"query": "error query"},
            raw_output="Error: Connection refused by remote host",
            trace_id="trace-err-1",
            tool_call_id="call-err-1"
        )
        self.assertEqual(bundle["status"], "FAILED")
        self.assertEqual(bundle["verification_status"], "REJECTED")


if __name__ == "__main__":
    unittest.main()
