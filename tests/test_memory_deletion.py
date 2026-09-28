"""
Tests for F.R.I.D.A.Y. 3.0 — Memory Deletion Verification
Validates:
1. Exact deletion: delete key -> commit -> readback verify absent.
2. No zombie memory: deleted item cannot be retrieved by ID, key, or search.
3. Multiple memory items deletion.
4. Clear tier wiping.
5. Deletion persistence across store instances (app restart simulation).
"""

import os
import tempfile
import unittest
from friday_core.memory.tiers import MemoryTier, MemoryItem
from friday_core.memory.store import MemoryStore
from friday_core.memory.manager import PersistentMemoryManager


class TestMemoryDeletion(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_file.close()
        self.db_path = self.temp_file.name
        self.store = MemoryStore(db_path=self.db_path)
        self.manager = PersistentMemoryManager(store=self.store)

    def tearDown(self):
        self.store.close()
        try:
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except Exception:
            pass

    def test_exact_deletion_and_absence_verification(self):
        mem_id = self.manager.set_preference("favorite_drink", "green tea", confirmed=True)
        self.assertIsNotNone(mem_id)
        self.assertEqual(self.manager.get_preference("favorite_drink"), "green tea")

        # Delete and verify
        deleted = self.manager.delete_preference("favorite_drink")
        self.assertTrue(deleted)

        # Verify absent: by key, by ID, by search
        self.assertIsNone(self.manager.get_preference("favorite_drink"))
        self.assertIsNone(self.store.get(mem_id))
        search_res = self.store.search("green tea")
        self.assertEqual(len(search_res), 0)

    def test_deletion_persists_across_restart(self):
        # 1. Store
        self.manager.set_preference("project_code", "JARVIS_4060", confirmed=True)
        self.assertEqual(self.manager.get_preference("project_code"), "JARVIS_4060")

        # 2. Delete
        deleted = self.manager.delete_preference("project_code")
        self.assertTrue(deleted)

        # 3. Simulate App Restart (fresh connection to the same SQLite file)
        self.store.close()
        new_store = MemoryStore(db_path=self.db_path)
        new_manager = PersistentMemoryManager(store=new_store)

        # 4. Verify Still Absent (No zombie memory revived)
        self.assertIsNone(new_manager.get_preference("project_code"))
        self.assertEqual(len(new_store.search("JARVIS_4060")), 0)
        new_store.close()

    def test_multiple_memory_deletions(self):
        keys = ["k1", "k2", "k3", "k4"]
        for k in keys:
            self.manager.set_preference(k, f"val_{k}", confirmed=True)

        for k in keys:
            self.assertEqual(self.manager.get_preference(k), f"val_{k}")

        # Delete two keys
        self.assertTrue(self.manager.delete_preference("k1"))
        self.assertTrue(self.manager.delete_preference("k3"))

        self.assertIsNone(self.manager.get_preference("k1"))
        self.assertIsNotNone(self.manager.get_preference("k2"))
        self.assertIsNone(self.manager.get_preference("k3"))
        self.assertIsNotNone(self.manager.get_preference("k4"))

    def test_clear_tier(self):
        self.manager.set_preference("pref_a", 1)
        self.manager.set_preference("pref_b", 2)
        self.manager.index_semantic_fact("entity_a", "fact_a")

        # Clear Tier 4 Preferences only
        cleared = self.manager.clear_tier(MemoryTier.TIER_4_PREFERENCE)
        self.assertGreaterEqual(cleared, 2)

        self.assertIsNone(self.manager.get_preference("pref_a"))
        self.assertIsNone(self.manager.get_preference("pref_b"))
        # Semantic fact in Tier 5 should remain untouched
        self.assertIsNotNone(self.manager.get_semantic_fact("entity_a"))


if __name__ == "__main__":
    unittest.main()
