"""
Tests for F.R.I.D.A.Y. 3.0 — Memory Update
Validates:
1. Update of an existing preference key (Alpha -> Beta).
2. Beta is retrieved as the current active truth.
3. Version increment (v1 -> v2).
4. Old version is marked historical or replaced, avoiding stale dominance.
"""

import unittest
from friday_core.memory.tiers import MemoryTier, MemoryItem
from friday_core.memory.store import MemoryStore
from friday_core.memory.manager import PersistentMemoryManager


class TestMemoryUpdate(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore(db_path=":memory:")
        self.manager = PersistentMemoryManager(store=self.store)

    def tearDown(self):
        self.store.close()

    def test_preference_update_version_and_value(self):
        # 1. Initial fact: Project name = Alpha
        mem_id_1 = self.manager.set_preference("project_name", "Alpha", confirmed=True)
        self.assertIsNotNone(mem_id_1)

        val_1 = self.manager.get_preference("project_name")
        self.assertEqual(val_1, "Alpha")
        item_1 = self.manager.get_preference_item("project_name")
        self.assertEqual(item_1.version, 1)
        self.assertEqual(item_1.retention_status, "active")

        # 2. Update fact: Project name = Beta
        mem_id_2 = self.manager.set_preference("project_name", "Beta", confirmed=True)
        self.assertIsNotNone(mem_id_2)

        # 3. Retrieve: Beta must be current truth
        val_2 = self.manager.get_preference("project_name")
        self.assertEqual(val_2, "Beta")

        item_2 = self.manager.get_preference_item("project_name")
        self.assertGreaterEqual(item_2.version, 2)
        self.assertEqual(item_2.value, "Beta")
        self.assertEqual(item_2.retention_status, "active")

    def test_semantic_fact_update(self):
        self.manager.index_semantic_fact("host_os", "Windows 10")
        f1 = self.manager.get_semantic_fact("host_os")
        self.assertEqual(f1.value, "Windows 10")

        # Update
        self.manager.index_semantic_fact("host_os", "Windows 11")
        f2 = self.manager.get_semantic_fact("host_os")
        self.assertEqual(f2.value, "Windows 11")


if __name__ == "__main__":
    unittest.main()
