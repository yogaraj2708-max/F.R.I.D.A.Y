"""
Tests for F.R.I.D.A.Y. 3.0 — Stale Memory Defense & Conflict Detection
Validates:
1. Changed facts: GPU = RTX 2050 -> GPU = RTX 4060.
2. Retrieval prioritizes latest valid memory (no stale dominance).
3. Conflict detection: identify contradictory records for the same attribute.
4. No silent merging of contradictory facts.
"""

import time
import unittest
from friday_core.memory.tiers import MemoryTier, MemoryItem
from friday_core.memory.store import MemoryStore
from friday_core.memory.manager import PersistentMemoryManager


class TestMemoryStaleData(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore(db_path=":memory:")
        self.manager = PersistentMemoryManager(store=self.store)

    def tearDown(self):
        self.store.close()

    def test_stale_memory_defense_gpu_update(self):
        # Initial saved memory: GPU = RTX 2050
        id1 = self.manager.set_preference("gpu_model", "RTX 2050", confirmed=True)
        self.assertIsNotNone(id1)
        self.assertEqual(self.manager.get_preference("gpu_model"), "RTX 2050")

        # Time passes, user updates: GPU = RTX 4060
        time.sleep(0.01)
        id2 = self.manager.set_preference("gpu_model", "RTX 4060", confirmed=True)
        self.assertIsNotNone(id2)

        # Retrieval must return RTX 4060, NOT the stale RTX 2050
        current_gpu = self.manager.get_preference("gpu_model")
        self.assertEqual(current_gpu, "RTX 4060")

        item = self.manager.get_preference_item("gpu_model")
        self.assertEqual(item.value, "RTX 4060")
        self.assertGreaterEqual(item.version, 2)

    def test_conflict_detection(self):
        # Save a fact
        self.manager.set_preference("meeting_time", "10:00 AM", confirmed=True)

        # Detect conflicts when trying to store contradictory fact "02:00 PM"
        conflicts = self.manager.detect_conflicts("meeting_time", "02:00 PM")
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].value, "10:00 AM")

        # If values match, no conflict detected
        no_conflicts = self.manager.detect_conflicts("meeting_time", "10:00 AM")
        self.assertEqual(len(no_conflicts), 0)


if __name__ == "__main__":
    unittest.main()
