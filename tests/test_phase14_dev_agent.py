"""
Tests for F.R.I.D.A.Y. 3.0 — Phase 14: Developer / Coding Agent Subsystem
Validates:
1. Unified diff generation and Python AST syntax validation.
2. Rejection of invalid Python syntax prior to writing.
3. Human approval gating on code modification and git commit.
4. Atomic rollback restoring prior files when errors occur.
5. Automated test runner capturing execution results.
"""

import os
import tempfile
import unittest

from friday_core.dev_agent.diff_engine import DiffEngine
from friday_core.dev_agent.runner import TestRunner
from friday_core.dev_agent.git_manager import GitManager
from friday_core.dev_agent.agent import DeveloperAgent


class TestDeveloperAgent(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.agent = DeveloperAgent()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_diff_engine_and_syntax_validation(self):
        """Validates unified diff computation and syntax error detection."""
        orig = "def greet(name):\n    return f'Hello {name}'\n"
        proposed = "def greet(name):\n    return f'Greetings {name}'\n"
        diff = DiffEngine.compute_diff("greet.py", orig, proposed)
        self.assertIn("-    return f'Hello {name}'", diff)
        self.assertIn("+    return f'Greetings {name}'", diff)

        # Valid syntax
        valid, err = DiffEngine.validate_python_syntax(proposed)
        self.assertTrue(valid)
        self.assertIsNone(err)

        # Invalid syntax
        bad_code = "def broken(\n    return 42"
        invalid, err = DiffEngine.validate_python_syntax(bad_code)
        self.assertFalse(invalid)
        self.assertIsNotNone(err)

    def test_human_approval_gate_on_plan_application(self):
        """Validates that plans requiring human approval reject execution without confirmation."""
        target_file = os.path.join(self.temp_dir, "feature.py")
        with open(target_file, "w", encoding="utf-8") as f:
            f.write("VALUE = 10\n")

        plan = self.agent.formulate_plan(
            task_description="Upgrade feature constant",
            file_edits=[{"path": target_file, "content": "VALUE = 20\n"}],
            requires_approval=True
        )

        # 1. Attempt apply without human approval
        res_unapproved = self.agent.apply_plan(plan.plan_id, user_confirmed=False)
        self.assertFalse(res_unapproved["success"])
        self.assertEqual(res_unapproved["status"], "WAITING_APPROVAL")

        # Verify disk file is unchanged
        with open(target_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "VALUE = 10\n")

        # 2. Apply with explicit human approval
        res_approved = self.agent.apply_plan(plan.plan_id, user_confirmed=True)
        self.assertTrue(res_approved["success"])
        with open(target_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "VALUE = 20\n")

    def test_syntax_error_blocks_write_and_rolls_back(self):
        """Validates that a syntax error prevents file write and protects codebase."""
        target_file = os.path.join(self.temp_dir, "script.py")
        with open(target_file, "w", encoding="utf-8") as f:
            f.write("# Original valid script\n")

        plan = self.agent.formulate_plan(
            task_description="Introduce malformed syntax",
            file_edits=[{"path": target_file, "content": "def broken(\nreturn 123"}],
            requires_approval=False
        )

        res = self.agent.apply_plan(plan.plan_id)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "REVERTED")

        # File must remain original
        with open(target_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "# Original valid script\n")

    def test_git_manager_approval_gate(self):
        """Validates that GitManager enforces human approval before committing."""
        git_mgr = GitManager(repo_root=self.temp_dir)
        res_no_approval = git_mgr.commit("auto commit", approved_by_user=False)
        self.assertFalse(res_no_approval["success"])
        self.assertIn("Explicit human approval is required", res_no_approval["error"])

    def test_plan_rollback(self):
        """Validates atomic rollback restoring previous file state."""
        target_file = os.path.join(self.temp_dir, "config.py")
        with open(target_file, "w", encoding="utf-8") as f:
            f.write("DEBUG = False\n")

        plan = self.agent.formulate_plan(
            task_description="Enable debug mode",
            file_edits=[{"path": target_file, "content": "DEBUG = True\n"}],
            requires_approval=False
        )
        self.agent.apply_plan(plan.plan_id)

        with open(target_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "DEBUG = True\n")

        # Rollback
        rolled_back = self.agent.rollback_plan(plan.plan_id)
        self.assertTrue(rolled_back)

        with open(target_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "DEBUG = False\n")


if __name__ == "__main__":
    unittest.main()
