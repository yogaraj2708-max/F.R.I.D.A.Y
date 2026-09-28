"""
Tests for F.R.I.D.A.Y. 3.0 — False Memory Success Prevention
Validates:
1. Never claim "I remember that" unless record was verified in database.
2. Never claim "I deleted that memory" unless deletion was confirmed absent.
3. Querying non-existent memory honestly returns failure (success=False).
4. Deleting non-existent memory honestly returns failure (success=False).
5. Verification logic catches failed state discrepancies.
"""

import unittest
from friday_core.skills.builtins.memory import MemorySkill
from friday_core.memory.store import MemoryStore
from friday_core.memory.manager import PersistentMemoryManager


class TestFalseMemorySuccess(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore(db_path=":memory:")
        self.manager = PersistentMemoryManager(store=self.store)
        self.skill = MemorySkill(manager=self.manager)

    def tearDown(self):
        self.store.close()

    def test_query_non_existent_memory_fails_honestly(self):
        # Retrieve key that was never stored
        res = self.skill.execute({"action": "get", "key": "phantom_preference"}, "op-1")
        self.assertFalse(res["success"])
        self.assertIsNone(res["value"])
        self.assertFalse(res["persisted_to_db"])
        self.assertIn("No record found", res["message"])

    def test_delete_non_existent_memory_fails_honestly(self):
        # Attempting to delete non-existent key returns success=False
        res = self.skill.execute({"action": "delete", "key": "non_existent_key"}, "op-2")
        self.assertFalse(res["success"])
        self.assertIn("Could not find or delete", res["message"])

    def test_verified_store_readback(self):
        # Store preference and ensure persistence flag and readback match
        res = self.skill.execute({"action": "set", "key": "language", "value": "Python"}, "op-3")
        self.assertTrue(res["success"])
        self.assertTrue(res["persisted_to_db"])
        self.assertEqual(res["value"], "Python")

        # Independent observation and verification
        obs = self.skill.observe("op-3", {"key": "language"})
        self.assertEqual(obs.observed_state["current_value"], "Python")
        ver = self.skill.verify(obs, {"action": "set", "key": "language", "value": "Python"})
        self.assertTrue(ver.verified)
        self.assertTrue(ver.postcondition_met)

    def test_verified_deletion_readback(self):
        # Store then delete
        self.skill.execute({"action": "set", "key": "temp_pref", "value": "123"}, "op-4")
        del_res = self.skill.execute({"action": "delete", "key": "temp_pref"}, "op-5")
        self.assertTrue(del_res["success"])

        # Independent observation must see None
        obs = self.skill.observe("op-5", {"key": "temp_pref"})
        self.assertIsNone(obs.observed_state["current_value"])
        ver = self.skill.verify(obs, {"action": "delete", "key": "temp_pref"})
        self.assertTrue(ver.verified)
        self.assertTrue(ver.postcondition_met)


if __name__ == "__main__":
    unittest.main()
