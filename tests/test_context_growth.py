"""
Tests for F.R.I.D.A.Y. 3.0 — Context Growth & Retention Correctness
Verifies ContextBudgetManager token bounds under long conversations, large attachments,
and proves that history pruning never breaks assistant tool_call + tool_result pairings.
"""

import sys
import unittest
from pathlib import Path

root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from friday_core.context.budget import ContextBudgetManager, ContextBudgetResult


class TestContextGrowth(unittest.TestCase):
    def setUp(self):
        # 4096 token limit test scenario
        self.mgr = ContextBudgetManager(model_context_limit=4096)

    def test_long_conversation_bounded_by_budget_manager(self):
        """Verifies a 50-turn conversation is bounded by ContextBudgetManager without exceeding limit."""
        messages = [{"role": "system", "content": "You are F.R.I.D.A.Y., a tactical assistant."}]

        for i in range(1, 51):
            messages.append({"role": "user", "content": f"Turn {i}: Detailed user inquiry about system state {i * 10}"})
            messages.append({"role": "assistant", "content": f"Turn {i}: Tactical response and status analysis {i * 10}"})

        # Preflight validate with tight 1000 token limit
        bounded_msgs, result = self.mgr.validate_and_bound_prompt(messages, context_limit=1000)

        print(f"\n[CONTEXT AUDIT] Initial Tokens: {result.estimated_tokens}, Bounded Tokens: {result.final_prompt_tokens}")
        print(f"[CONTEXT AUDIT] Initial Messages: {len(messages)}, Bounded Messages: {len(bounded_msgs)}")

        self.assertTrue(result.is_valid)
        self.assertLess(result.final_prompt_tokens, 1000)
        self.assertTrue(result.truncation_occurred)

        # System prompt preserved as first message
        self.assertEqual(bounded_msgs[0]["role"], "system")
        # Most recent user directive preserved as last message
        self.assertEqual(bounded_msgs[-1]["content"], messages[-1]["content"])

    def test_massive_attachment_compaction(self):
        """Verifies that large document attachments inside prompt are compacted to prevent context overflow."""
        huge_doc_content = "def calculate_orbit():\n    pass\n" * 1500  # ~30k characters
        user_prompt = f"[Attached Document: orbit_calc.py]\n```{huge_doc_content}```\n\nBoss Directive:\nAnalyze orbit calculation."

        messages = [
            {"role": "system", "content": "Tactical AI."},
            {"role": "user", "content": user_prompt}
        ]

        bounded_msgs, result = self.mgr.validate_and_bound_prompt(messages, context_limit=4096)

        print(f"[CONTEXT AUDIT] Huge Attachment: Initial={result.estimated_tokens}, Final={result.final_prompt_tokens}")
        self.assertTrue(result.is_valid)
        self.assertLess(result.final_prompt_tokens, 4096)
        self.assertTrue(result.truncation_occurred)
        self.assertIn("Boss Directive:\nAnalyze orbit calculation.", bounded_msgs[-1]["content"])

    def test_tool_call_and_result_pairing_integrity(self):
        """Verifies context trimming does not isolate a tool result from its corresponding tool call."""
        # Pair structure in messages
        messages = [
            {"role": "system", "content": "Assistant prompt."},
            {"role": "user", "content": "Old request"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "call_123", "function": {"name": "calculate"}}]},
            {"role": "tool", "tool_call_id": "call_123", "content": "42"},
            {"role": "user", "content": "Recent question"}
        ]

        # Prune with a small budget
        bounded_msgs, result = self.mgr.validate_and_bound_prompt(messages, context_limit=500)

        # Check pairing
        tool_call_ids = set()
        tool_result_ids = set()
        for m in bounded_msgs:
            if m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    tool_call_ids.add(tc["id"])
            if m.get("role") == "tool":
                tool_result_ids.add(m.get("tool_call_id"))

        print(f"[CONTEXT AUDIT] Tool call IDs: {tool_call_ids}, Tool result IDs: {tool_result_ids}")
        # Every tool result present must have its tool call present
        self.assertTrue(tool_result_ids.issubset(tool_call_ids))


if __name__ == "__main__":
    unittest.main()
