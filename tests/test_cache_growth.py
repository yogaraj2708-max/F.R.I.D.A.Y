"""
Tests for F.R.I.D.A.Y. 3.0 — Cache Growth & Eviction Policy Audit
Audits model capability cache, image context cache, memory sliding window,
and ensures strict bounds, eviction on overflow, and invalidation on model change.
"""

import sys
import unittest
from pathlib import Path

root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from friday_core.vision.image_context import ImageContext, ImageContextManager
from friday_core.memory.manager import PersistentMemoryManager
from friday_core.settings import settings


class TestCacheGrowth(unittest.TestCase):
    def test_image_context_cache_bounded_fifo_eviction(self):
        """Verifies ImageContextManager strictly bounds contexts per session (max 20) with FIFO eviction."""
        mgr = ImageContextManager()
        session_id = "cache_test_session"

        # Insert 30 contexts into a 20-max cache
        for i in range(1, 31):
            ctx = ImageContext(
                image_id=f"img_{i:03d}",
                session_id=session_id,
                description=f"Test image frame {i}"
            )
            mgr.store_context(ctx)

        contexts = mgr.get_all_contexts(session_id)
        print(f"\n[CACHE AUDIT] Image Contexts in session: {len(contexts)} (Max allowed={mgr.MAX_CONTEXTS_PER_SESSION})")
        self.assertEqual(len(contexts), mgr.MAX_CONTEXTS_PER_SESSION)
        # Verify oldest contexts (1-10) were evicted, newest remain
        self.assertEqual(contexts[0].image_id, "img_011")
        self.assertEqual(contexts[-1].image_id, "img_030")

    def test_working_memory_sliding_window_bound(self):
        """Verifies PersistentMemoryManager working memory strictly caps dialogue turns to 20."""
        mgr = PersistentMemoryManager()
        mgr.clear_working_memory()

        for i in range(50):
            mgr.append_working_turn("user" if i % 2 == 0 else "assistant", f"Turn message {i}")

        turns = mgr.get_working_memory()
        print(f"[CACHE AUDIT] Working Memory Turns: {len(turns)} (Max allowed=20)")
        self.assertEqual(len(turns), 20)
        self.assertEqual(turns[-1]["content"], "Turn message 49")

    def test_model_capability_cache_invalidation_on_model_switch(self):
        """Verifies that switching models cleanly purges the cached capability results."""
        from friday_ui.core.engine import FridayBrain, FridaySignals
        signals = FridaySignals()
        brain = FridayBrain(signals, tts_engine=None)

        brain._tool_capability_cache.clear()
        # Seed cache
        brain._tool_capability_cache["model_a"] = "VERIFIED"
        brain._tool_capability_cache["model_b"] = "UNAVAILABLE"
        self.assertEqual(len(brain._tool_capability_cache), 2)


        # Trigger model change event
        brain._on_settings_change("model", "qwen2.5:0.5b")
        print(f"[CACHE AUDIT] Brain Capability Cache after switch: {brain._tool_capability_cache}")
        self.assertEqual(len(brain._tool_capability_cache), 0, "Capability cache failed to invalidate on model change")


if __name__ == "__main__":
    unittest.main()
