"""
Tests for F.R.I.D.A.Y. 3.0 — Long Session Longevity & Multi-Turn Stability
Simulates a multi-turn conversation (100 turns), tracking memory, working context limits,
thread stability, and tool history persistence without cumulative degradation.
"""

import gc
import sys
import time
import unittest
import psutil
from pathlib import Path

root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from friday_core.memory.manager import PersistentMemoryManager
from friday_core.context.budget import ContextBudgetManager
from friday_core.calc import safe_calculate


class TestLongSession(unittest.TestCase):
    def setUp(self):
        self.process = psutil.Process()
        gc.collect()

    def test_100_turn_session_stability(self):
        """Verifies 100 sequential interaction turns maintain bounded memory, threads, and context."""
        mem_start = self.process.memory_info().rss / (1024 * 1024)
        threads_start = len(self.process.threads())

        memory_mgr = PersistentMemoryManager()
        budget_mgr = ContextBudgetManager(model_context_limit=4096)
        history = [{"role": "system", "content": "You are F.R.I.D.A.Y., a tactical assistant."}]

        checkpoints = {}
        for turn in range(1, 101):
            user_msg = f"Turn {turn}: calculate {turn} * 5"
            history.append({"role": "user", "content": user_msg})

            # Simulate tool execution
            ans = safe_calculate(f"{turn} * 5")
            history.append({"role": "assistant", "content": f"The answer is {ans}."})

            # Track in working memory
            memory_mgr.append_working_turn("user", user_msg)
            memory_mgr.append_working_turn("assistant", f"The answer is {ans}.")

            # Validate and bound context
            bounded, res = budget_mgr.validate_and_bound_prompt(history, context_limit=4096)
            self.assertTrue(res.is_valid)
            self.assertLess(res.final_prompt_tokens, 4096)

            if turn in [1, 5, 10, 25, 50, 75, 100]:
                gc.collect()
                checkpoints[turn] = {
                    "rss_mb": round(self.process.memory_info().rss / (1024 * 1024), 2),
                    "prompt_tokens": res.final_prompt_tokens,
                    "bounded_msg_count": len(bounded),
                    "working_memory_count": len(memory_mgr.get_working_memory())
                }

        mem_end = self.process.memory_info().rss / (1024 * 1024)
        threads_end = len(self.process.threads())
        growth_mb = mem_end - mem_start

        print(f"\n[LONG SESSION AUDIT] 100 Turns Finished:")
        for t, data in checkpoints.items():
            print(f"  Turn {t:3d}: RSS={data['rss_mb']}MB, Tokens={data['prompt_tokens']}, Msgs={data['bounded_msg_count']}, WorkingMem={data['working_memory_count']}")

        # Assertions
        self.assertLess(growth_mb, 10.0, f"Uncontrolled memory growth over 100 turns: {growth_mb:.2f}MB")
        self.assertEqual(threads_start, threads_end, "Lingering threads created across long session")
        # Working memory must remain strictly capped at 20 turns
        self.assertLessEqual(len(memory_mgr.get_working_memory()), 20)


if __name__ == "__main__":
    unittest.main()
