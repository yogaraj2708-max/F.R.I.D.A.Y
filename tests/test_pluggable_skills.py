"""
Tests for F.R.I.D.A.Y. 3.0 Pluggable Skill / Tool Framework
Verifies:
1. 9-Stage execution lifecycle (validate, authorize, precondition, execute, observe, verify, rollback, cancel).
2. Input argument validation and pre-execution rejection.
3. False-success detection (command returns success but postcondition fails).
4. Idempotency protection (duplicate operation_id does not re-run side effects).
5. Transactional rollback for reversible filesystem changes.
6. Clean emergency stop cancellation handling.
7. Built-in skills (Telemetry, Volume, Apps, Organizer, Word).
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from pydantic import BaseModel, Field

from friday_core.skills.base import (
    BaseSkill,
    RiskLevel,
    ObservationResult,
    VerificationResult,
    RollbackResult
)
from friday_core.skills.registry import SkillRegistry, skill_registry
from friday_core.skills.builtins.telemetry import SystemTelemetrySkill
from friday_core.skills.builtins.volume import VolumeControlSkill
from friday_core.skills.builtins.apps import AppLauncherSkill
from friday_core.skills.builtins.organizer import FileOrganizerSkill
from friday_core.skills.builtins.word import WordDrafterSkill


# Mock Skill for Testing False-Success and Idempotency
class MockCreateFileInput(BaseModel):
    filename: str = Field(..., min_length=1)
    content: str = ""


class MockCreateFileSkill(BaseSkill):
    tool_id = "test_create_file"
    tool_version = "1.0.0"
    input_schema = MockCreateFileInput
    risk_level = RiskLevel.LOW_RISK

    def __init__(self, target_dir: str):
        super().__init__()
        self.target_dir = target_dir
        self.execution_count = 0
        self.simulate_false_success = False

    def execute(self, params, operation_id):
        self.execution_count += 1
        filepath = os.path.join(self.target_dir, params["filename"])
        if not self.simulate_false_success:
            with open(filepath, "w") as f:
                f.write(params.get("content", ""))
        return {"created": True, "path": filepath}

    def observe(self, operation_id, params=None):
        filename = params.get("filename", "") if params else ""
        filepath = os.path.join(self.target_dir, filename)
        file_exists = os.path.isfile(filepath)
        return ObservationResult(observed_state={"file_exists": file_exists, "path": filepath})

    def verify(self, observation, params=None):
        exists = observation.observed_state.get("file_exists", False)
        if not exists:
            return VerificationResult(
                verified=False,
                postcondition_met=False,
                message="Target file does not exist on disk."
            )
        return VerificationResult(
            verified=True,
            postcondition_met=True,
            message="File creation verified."
        )

    def rollback(self, operation_id, params=None):
        filename = params.get("filename", "") if params else ""
        filepath = os.path.join(self.target_dir, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            return RollbackResult(success=True, message="Deleted created file.")
        return RollbackResult(success=True, message="File was already absent.")


class TestPluggableSkills(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="friday_skill_test_")

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_pre_execution_validation_rejection(self):
        """Invalid arguments must be rejected prior to execution."""
        skill = MockCreateFileSkill(self.temp_dir)
        # Missing required parameter 'filename'
        res = skill.run_lifecycle({})
        self.assertFalse(res.success)
        self.assertIn("Validation failed", res.error)
        self.assertEqual(skill.execution_count, 0)

    def test_successful_lifecycle_and_verification(self):
        """Valid arguments execute, observe, and verify postconditions."""
        skill = MockCreateFileSkill(self.temp_dir)
        res = skill.run_lifecycle({"filename": "test.txt", "content": "hello world"})
        self.assertTrue(res.success)
        self.assertIsNotNone(res.verification)
        self.assertTrue(res.verification.verified)
        self.assertEqual(skill.execution_count, 1)
        self.assertTrue(os.path.isfile(os.path.join(self.temp_dir, "test.txt")))

    def test_false_success_detection(self):
        """If tool returns success but postcondition fails, report NOT SUCCESS."""
        skill = MockCreateFileSkill(self.temp_dir)
        skill.simulate_false_success = True  # Simulates file not actually being written
        res = skill.run_lifecycle({"filename": "phantom.txt", "content": "ghost"})

        self.assertFalse(res.success)
        self.assertIn("Postcondition verification failed", res.error)
        self.assertEqual(skill.execution_count, 1)
        self.assertFalse(os.path.isfile(os.path.join(self.temp_dir, "phantom.txt")))

    def test_idempotency_prevents_duplicate_side_effects(self):
        """Calling with the same operation_id must not repeat side effects."""
        skill = MockCreateFileSkill(self.temp_dir)
        op_id = "op-file-create-001"

        res1 = skill.run_lifecycle({"filename": "idempotent.txt", "content": "v1"}, operation_id=op_id)
        self.assertTrue(res1.success)
        self.assertFalse(res1.idempotent_replay)
        self.assertEqual(skill.execution_count, 1)

        # Re-run with identical operation_id
        res2 = skill.run_lifecycle({"filename": "idempotent.txt", "content": "v1"}, operation_id=op_id)
        self.assertTrue(res2.success)
        self.assertTrue(res2.idempotent_replay)
        self.assertEqual(skill.execution_count, 1)  # Execution count did NOT increase

    def test_cancellation_handling(self):
        """Operations cancelled prior to execution must abort cleanly."""
        skill = MockCreateFileSkill(self.temp_dir)
        op_id = "op-cancel-001"
        skill.cancel(op_id)

        res = skill.run_lifecycle({"filename": "cancelled.txt"}, operation_id=op_id)
        self.assertFalse(res.success)
        self.assertIn("cancelled", res.error.lower())
        self.assertEqual(skill.execution_count, 0)

    def test_skill_registry_dispatch(self):
        """Registry manages registration and lifecycle dispatch."""
        reg = SkillRegistry()
        skill = MockCreateFileSkill(self.temp_dir)
        reg.register(skill)

        # Verify discovery manifest
        manifest = reg.list_skills()
        self.assertEqual(len(manifest), 1)
        self.assertEqual(manifest[0]["tool_id"], "test_create_file")

        # Execute through registry
        res = reg.execute_skill("test_create_file", {"filename": "registry_test.txt"})
        self.assertTrue(res.success)
        self.assertTrue(os.path.isfile(os.path.join(self.temp_dir, "registry_test.txt")))

        # Unregistered skill handling
        res_unknown = reg.execute_skill("unknown_tool", {})
        self.assertFalse(res_unknown.success)
        self.assertIn("not registered", res_unknown.error)

    def test_system_telemetry_skill(self):
        """Verify built-in SystemTelemetrySkill returns verified metrics."""
        skill = SystemTelemetrySkill()
        res = skill.run_lifecycle({"metrics": ["cpu", "memory", "disk"]})
        self.assertTrue(res.success)
        self.assertIn("memory_percent", res.data)
        self.assertIn("disk_free_gb", res.data)
        self.assertTrue(res.verification.verified)

    def test_volume_control_skill(self):
        """Verify built-in VolumeControlSkill validates input and executes."""
        skill = VolumeControlSkill()
        # Invalid action should fail validation
        res_inv = skill.run_lifecycle({"action": "explode"})
        self.assertFalse(res_inv.success)

        # Valid action
        with patch("friday_core.skills.builtins.volume.adjust_volume") as mock_adj:
            res_val = skill.run_lifecycle({"action": "up", "steps": 5})
            self.assertTrue(res_val.success)
            mock_adj.assert_called_with("up")

    def test_file_organizer_skill_with_rollback(self):
        """Verify FileOrganizerSkill organizes files and provides atomic rollback."""
        skill = FileOrganizerSkill()

        # Create dummy files
        doc_file = os.path.join(self.temp_dir, "report.pdf")
        img_file = os.path.join(self.temp_dir, "photo.png")
        with open(doc_file, "w") as f:
            f.write("dummy pdf")
        with open(img_file, "w") as f:
            f.write("dummy png")

        op_id = "op-organize-test-01"
        res = skill.run_lifecycle({"directory_path": self.temp_dir}, operation_id=op_id)
        self.assertTrue(res.success)
        self.assertTrue(res.verification.verified)
        self.assertEqual(res.data["files_moved"], 2)

        # Verify files moved to categories
        self.assertTrue(os.path.isfile(os.path.join(self.temp_dir, "Documents", "report.pdf")))
        self.assertTrue(os.path.isfile(os.path.join(self.temp_dir, "Images", "photo.png")))
        self.assertFalse(os.path.isfile(doc_file))
        self.assertFalse(os.path.isfile(img_file))

        # Rollback execution
        rb = skill.rollback(op_id, {"directory_path": self.temp_dir})
        self.assertTrue(rb.success)

        # Verify files restored to original locations
        self.assertTrue(os.path.isfile(doc_file))
        self.assertTrue(os.path.isfile(img_file))

    @patch("friday_core.skills.builtins.apps.gatekeeper.execute_action")
    def test_app_launcher_skill(self, mock_gk):
        mock_gk.return_value = MagicMock(success=True, message="Launched")
        skill = AppLauncherSkill()

        res = skill.run_lifecycle({"app_name": "notepad"})
        self.assertTrue(res.success)
        self.assertTrue(res.verification.verified)
        mock_gk.assert_called()

    @patch("friday_core.skills.builtins.word.open_word_with_content")
    def test_word_drafter_skill(self, mock_word):
        mock_word.return_value = (True, "Document created.")
        skill = WordDrafterSkill()

        res = skill.run_lifecycle({"title": "Meeting Notes", "content": "Summary text"})
        self.assertTrue(res.success)
        self.assertTrue(res.verification.verified)
        mock_word.assert_called_with("Summary text", title="Meeting Notes")


if __name__ == "__main__":
    unittest.main()
