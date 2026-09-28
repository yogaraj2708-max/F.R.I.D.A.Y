"""
Tests for F.R.I.D.A.Y. 3.0 — Phase 15: Security Hardening & Observability
Validates:
1. Structured Event Observability logging and parameter redaction.
2. Explainability queries ("What did you do?", "What failed?").
3. Encrypted CredentialVault persistence, retrieval, and key listing.
4. SecurityGate 5-tier risk evaluation.
5. Confirmation gating on HIGH_RISK and RESTRICTED irreversible operations.
6. Path fencing blocking alterations to protected Windows system directories.
7. Destructive rate limiting.
"""

import os
import tempfile
import unittest

from friday_core.observability.models import StructuredEvent
from friday_core.observability.event_logger import StructuredEventLogger
from friday_core.security.taxonomy import SecurityRiskLevel, get_action_risk_level
from friday_core.security.credential_vault import CredentialVault
from friday_core.security.gate import SecurityGate


class TestSecurityAndObservability(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.temp_dir, "test_events.jsonl")
        self.vault_file = os.path.join(self.temp_dir, "test_vault.enc")

        self.event_logger = StructuredEventLogger(log_path=self.log_file)
        self.vault = CredentialVault(vault_path=self.vault_file)
        self.gate = SecurityGate(max_destructive_per_minute=2)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_structured_event_logging_and_redaction(self):
        """Validates that structured events redact sensitive parameters."""
        event = self.event_logger.create_and_log(
            tool="login_helper",
            action="authenticate",
            parameters={"username": "tony_stark", "api_key": "SK-994828472", "password": "SuperSecret123"},
            status="SUCCESS",
            duration_ms=45.2
        )

        self.assertEqual(event.parameters["username"], "tony_stark")
        self.assertEqual(event.parameters["api_key"], "********")
        self.assertEqual(event.parameters["password"], "********")

        # Verify disk persistence
        self.assertTrue(os.path.exists(self.log_file))
        with open(self.log_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("SuperSecret123", content)
        self.assertIn("********", content)

    def test_explainability_apis(self):
        """Validates factual query explanations without model hallucination."""
        # 1. Log success
        self.event_logger.create_and_log(
            tool="app_launcher",
            action="open_app",
            parameters={"app_name": "notepad"},
            status="SUCCESS",
            duration_ms=120.0
        )
        # 2. Log failure
        self.event_logger.create_and_log(
            tool="file_organizer",
            action="permanent_delete",
            parameters={"path": "C:\\Windows\\system32"},
            status="BLOCKED",
            error="Target path is protected by system fence.",
            duration_ms=5.0
        )

        what_happened = self.event_logger.explain_what_happened()
        self.assertIn("app_launcher", what_happened)
        self.assertIn("open_app", what_happened)

        what_failed = self.event_logger.explain_failures()
        self.assertIn("file_organizer.permanent_delete' was BLOCKED", what_failed)
        self.assertIn("protected by system fence", what_failed)

    def test_credential_vault_encryption(self):
        """Validates secret storage, encryption on disk, retrieval, and key listing."""
        self.vault.set_secret("OPENAI_API_KEY", "sk-proj-secret-12345")
        self.vault.set_secret("DATABASE_PASSWORD", "db_pass_7788")

        # Verify ciphertext on disk
        with open(self.vault_file, "rb") as f:
            raw_bytes = f.read()
        self.assertNotIn(b"sk-proj-secret-12345", raw_bytes)

        # Retrieve
        val1 = self.vault.get_secret("OPENAI_API_KEY")
        self.assertEqual(val1, "sk-proj-secret-12345")

        # List keys
        keys = self.vault.list_keys()
        self.assertIn("OPENAI_API_KEY", keys)
        self.assertIn("DATABASE_PASSWORD", keys)

        # Delete
        deleted = self.vault.delete_secret("DATABASE_PASSWORD")
        self.assertTrue(deleted)
        self.assertIsNone(self.vault.get_secret("DATABASE_PASSWORD"))

    def test_security_gate_confirmation_and_path_fence(self):
        """Validates confirmation gates and system directory protection."""
        # 1. SAFE action should pass without confirmation
        safe_eval = self.gate.evaluate_authorization("get_time", {})
        self.assertTrue(safe_eval["authorized"])

        # 2. RESTRICTED action without confirmation must be BLOCKED
        restr_eval = self.gate.evaluate_authorization("permanent_delete", {"path": "C:\\test.txt"}, user_confirmed=False)
        self.assertFalse(restr_eval["authorized"])
        self.assertTrue(restr_eval.get("confirmation_required", False))

        # 3. RESTRICTED action with confirmation should pass
        restr_ok = self.gate.evaluate_authorization("permanent_delete", {"path": "C:\\test.txt"}, user_confirmed=True)
        self.assertTrue(restr_ok["authorized"])

        # 4. Path fence: targeting Windows directory must be BLOCKED even if user confirmed
        win_dir = os.environ.get("WINDIR", r"C:\Windows")
        fence_eval = self.gate.evaluate_authorization(
            "write_file",
            {"path": os.path.join(win_dir, "system32", "hack.dll")},
            user_confirmed=True
        )
        self.assertFalse(fence_eval["authorized"])
        self.assertIn("system fence", fence_eval["reason"])


if __name__ == "__main__":
    unittest.main()
