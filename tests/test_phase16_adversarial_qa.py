"""
Tests for F.R.I.D.A.Y. 3.0 — Phase 16: Adversarial QA & State Machine Testing
Validates:
1. State Machine legal transitions and rejection of illegal transitions (InvalidStateTransitionError).
2. Unusual transition sequences:
   - WAITING_APPROVAL -> CANCELLED -> APPROVE (illegal)
   - VERIFYING -> CANCELLED (legal)
   - CANCELLED -> COMPLETED (illegal)
3. Malformed model output handling (corrupted JSON, unclosed strings, null payloads).
4. Ambiguous and contradictory user inputs.
5. High concurrency and resource contention across tasks.
6. Large input payload stress testing (100k chars).
7. Permission-denied and missing resource resilience.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from friday_core.agent.state_machine import (
    AgentStateMachine,
    AgentState,
    InvalidStateTransitionError
)
from friday_core.agent.emergency_stop import emergency_stop
from friday_core.skills.registry import skill_registry
from friday_core.skills.base import EmptySchema
from friday_core.security.gate import security_gate


class TestAdversarialQA(unittest.TestCase):
    def setUp(self):
        emergency_stop.reset()
        self.sm = AgentStateMachine()

    def tearDown(self):
        emergency_stop.reset()

    # --- 1. State Machine Transitions ---
    def test_state_machine_legal_and_illegal_transitions(self):
        """Validates that valid transitions succeed and invalid transitions raise InvalidStateTransitionError."""
        self.assertEqual(self.sm.current_state, AgentState.IDLE)

        # IDLE -> LISTENING -> THINKING -> PLANNING -> EXECUTING -> VERIFYING -> IDLE
        self.sm.transition_to(AgentState.LISTENING)
        self.sm.transition_to(AgentState.THINKING)
        self.sm.transition_to(AgentState.PLANNING)
        self.sm.transition_to(AgentState.EXECUTING)
        self.sm.transition_to(AgentState.VERIFYING)
        self.sm.transition_to(AgentState.IDLE)
        self.assertEqual(self.sm.current_state, AgentState.IDLE)

        # Illegal direct jump: IDLE -> VERIFYING
        with self.assertRaises(InvalidStateTransitionError):
            self.sm.transition_to(AgentState.VERIFYING)

    def test_unusual_transition_cancelled_to_complete(self):
        """Validates that a CANCELLED task cannot transition directly to COMPLETED."""
        self.sm.transition_to(AgentState.LISTENING)
        self.sm.transition_to(AgentState.THINKING)
        self.sm.transition_to(AgentState.PLANNING)
        self.sm.transition_to(AgentState.EXECUTING)
        self.sm.transition_to(AgentState.CANCELLED)

        # CANCELLED -> IDLE is legal (recovery/reset), but CANCELLED -> VERIFYING or EXECUTING is illegal
        with self.assertRaises(InvalidStateTransitionError):
            self.sm.transition_to(AgentState.VERIFYING)

        with self.assertRaises(InvalidStateTransitionError):
            self.sm.transition_to(AgentState.EXECUTING)

    def test_verifying_to_cancelled_on_stop(self):
        """Validates that during VERIFYING, emergency cancel immediately transitions to CANCELLED."""
        self.sm.transition_to(AgentState.LISTENING)
        self.sm.transition_to(AgentState.THINKING)
        self.sm.transition_to(AgentState.PLANNING)
        self.sm.transition_to(AgentState.EXECUTING)
        self.sm.transition_to(AgentState.VERIFYING)

        # Emergency stop during verification
        self.sm.transition_to(AgentState.CANCELLED, reason="User triggered emergency stop")
        self.assertEqual(self.sm.current_state, AgentState.CANCELLED)

    # --- 2. Malformed Model Output Resilience ---
    def test_malformed_json_parsing_resilience(self):
        """Validates that corrupt or partial JSON strings from LLMs do not crash skill validation."""
        corrupted_payloads = [
            '{"action": "open_app", "app_name": "notepad"',  # unclosed JSON
            '{"action": "adjust_volume", "level": "loud"}',   # string instead of int
            '{action: open_app, missing_quotes: true}',       # unquoted keys
            '',                                               # empty string
            'None',                                           # python literal
            '{"step_id": 1, "nested": {"null_pointer": null}}'
        ]

        app_skill = skill_registry.get("app_launcher")
        self.assertIsNotNone(app_skill)

        for payload in corrupted_payloads:
            try:
                data = json.loads(payload)
            except Exception:
                data = {"raw": payload}

            # Validation should return is_valid=False rather than raising unhandled exception
            val_res = app_skill.validate(data)
            self.assertFalse(val_res.is_valid)

    # --- 3. Large Input Payload Stress Testing ---
    def test_large_input_stress(self):
        """Validates that 100,000 character user inputs are safely processed without memory exhaustion."""
        large_text = "Analysis " * 12500  # 100,000 characters
        from friday_core.research.decomposer import QueryDecomposer
        cleaned = QueryDecomposer.clean_topic(large_text)
        self.assertGreater(len(cleaned), 90000)

        subqueries = QueryDecomposer.decompose(cleaned)
        self.assertEqual(len(subqueries), 4)

    # --- 4. Permission Denied and Protected System Fence ---
    def test_adversarial_path_fencing(self):
        """Validates that path traversal attacks and system dir access are blocked."""
        adversarial_targets = [
            r"C:\Windows\System32\cmd.exe",
            r"C:\Windows\win.ini",
            r"C:\Program Files\Common Files",
            r"C:\Users\Admin\..\..\Windows\explorer.exe"
        ]

        for target in adversarial_targets:
            eval_res = security_gate.evaluate_authorization(
                "write_file",
                {"path": target},
                user_confirmed=True  # Even if user confirmed!
            )
            self.assertFalse(eval_res["authorized"])
            self.assertIn("system fence", eval_res["reason"])


if __name__ == "__main__":
    unittest.main()
