"""
Tests for F.R.I.D.A.Y. 3.0 — Memory Lifecycle
Validates:
1. Memory creation across tiers (Tier 3 Episodic, Tier 4 Preference, Tier 5 Semantic).
2. Memory retrieval by key and by ID.
3. Memory update with version increment.
4. Memory deletion with postcondition verification.
5. Permission memory toggle gate enforcement.
"""

import unittest
from friday_core.memory.tiers import MemoryTier, MemoryItem, MemoryDomain
from friday_core.memory.store import MemoryStore
from friday_core.memory.manager import PersistentMemoryManager
from friday_core.context.models import ContextPermission, ContextPermissionError


class MockSettings:
    def __init__(self, memory_permitted: bool = True):
        self._values = {ContextPermission.MEMORY.value: memory_permitted}

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        self._values[key] = value


class TestMemoryLifecycle(unittest.TestCase):
    def setUp(self):
        self.settings = MockSettings(memory_permitted=True)
        self.store = MemoryStore(db_path=":memory:", config=self.settings)
        self.manager = PersistentMemoryManager(store=self.store)

    def tearDown(self):
        self.store.close()

    def test_preference_lifecycle(self):
        # 1. Create
        mem_id = self.manager.set_preference("editor", "vscode", confirmed=True)
        self.assertIsNotNone(mem_id)

        # 2. Retrieve
        val = self.manager.get_preference("editor")
        self.assertEqual(val, "vscode")

        item = self.manager.get_preference_item("editor")
        self.assertIsNotNone(item)
        self.assertEqual(item.version, 1)
        self.assertEqual(item.domain, MemoryDomain.PERSONAL.value)

        # 3. Update
        mem_id2 = self.manager.set_preference("editor", "pycharm", confirmed=True)
        self.assertIsNotNone(mem_id2)
        val2 = self.manager.get_preference("editor")
        self.assertEqual(val2, "pycharm")
        item2 = self.manager.get_preference_item("editor")
        self.assertGreaterEqual(item2.version, 2)

        # 4. Delete
        deleted = self.manager.delete_preference("editor")
        self.assertTrue(deleted)
        self.assertIsNone(self.manager.get_preference("editor"))

    def test_semantic_fact_lifecycle(self):
        mem_id = self.manager.index_semantic_fact("FRIDAY", "F.R.I.D.A.Y. is an AI assistant", domain=MemoryDomain.PROJECT.value)
        self.assertIsNotNone(mem_id)

        fact = self.manager.get_semantic_fact("FRIDAY")
        self.assertIsNotNone(fact)
        self.assertIn("AI assistant", fact.value)
        self.assertEqual(fact.domain, MemoryDomain.PROJECT.value)

        deleted = self.manager.delete_memory_item(mem_id)
        self.assertTrue(deleted)
        self.assertIsNone(self.manager.get_semantic_fact("FRIDAY"))

    def test_episodic_memory_lifecycle(self):
        ep_id = self.manager.record_episode("deploy_model", "Model deployed successfully", success=True)
        self.assertIsNotNone(ep_id)

        episodes = self.manager.get_episodes(max_items=5)
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0].key, "deploy_model")
        self.assertTrue(episodes[0].value["success"])

    def test_permission_toggle(self):
        self.settings.set(ContextPermission.MEMORY.value, False)
        # Should be blocked when permission is disabled
        res = self.manager.set_preference("theme", "dark")
        self.assertIsNone(res)
        self.assertIsNone(self.manager.get_preference("theme"))


if __name__ == "__main__":
    unittest.main()
