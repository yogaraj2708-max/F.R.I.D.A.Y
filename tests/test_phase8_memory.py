"""
Tests for F.R.I.D.A.Y. 3.0 — Phase 8: 5-Tier Persistent Memory Architecture
Validates:
1. Tier 1: Working Memory dialogue turns and window bounding.
2. Tier 2: Task Memory retrieval from MissionStore.
3. Tier 3: Episodic Memory recording, success/failure outcomes.
4. Tier 4: Preference Memory user-confirmed settings and retrieval.
5. Tier 5: Semantic Memory fact indexing and full-text keyword search.
6. Sovereignty & UI: Inspection manifest, item deletion, tier wiping.
7. Permission Gates: 'permission_memory' toggle blocks all persistence and queries when disabled.
"""

import unittest
from friday_core.memory.tiers import MemoryTier, MemoryItem
from friday_core.memory.store import MemoryStore
from friday_core.memory.manager import PersistentMemoryManager
from friday_core.context.models import ContextPermission, ContextPermissionError
from friday_core.agent.mission_store import MissionStore, MissionState, MissionStatus, MissionStep


class MockSettings:
    def __init__(self, memory_permitted: bool = True):
        self._values = {ContextPermission.MEMORY.value: memory_permitted}

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        self._values[key] = value


class TestPersistentMemory(unittest.TestCase):
    def setUp(self):
        self.settings = MockSettings(memory_permitted=True)
        self.store = MemoryStore(db_path=":memory:", config=self.settings)
        self.mission_store = MissionStore(db_path=":memory:")
        self.manager = PersistentMemoryManager(store=self.store, mission_mgr=self.mission_store)

    def tearDown(self):
        self.store.close()
        self.mission_store.close()

    def test_tier1_working_memory_and_bounding(self):
        """Validates Tier 1 conversational turns and the 20-turn sliding window."""
        self.assertEqual(len(self.manager.get_working_memory()), 0)
        
        # Add 25 turns
        for i in range(25):
            self.manager.append_working_turn("user" if i % 2 == 0 else "assistant", f"Turn message {i}")
            
        turns = self.manager.get_working_memory()
        self.assertEqual(len(turns), 20)
        self.assertEqual(turns[0]["content"], "Turn message 5")
        self.assertEqual(turns[-1]["content"], "Turn message 24")
        
        self.manager.clear_working_memory()
        self.assertEqual(len(self.manager.get_working_memory()), 0)

    def test_tier2_task_memory_integration(self):
        """Validates Tier 2 reading active mission DAG and checkpoints from MissionStore."""
        mission = MissionState(
            mission_id="m-test-801",
            goal="Refactor memory subsystem",
            status=MissionStatus.RUNNING,
            current_step=1,
            steps=[
                MissionStep(step_id="step-1", tool_id="memory_organizer", params={"tier": 5})
            ]
        )
        self.mission_store.save_mission(mission)

        task_mem = self.manager.get_task_memory("m-test-801")
        self.assertIsNotNone(task_mem)
        self.assertEqual(task_mem["mission_id"], "m-test-801")
        self.assertEqual(task_mem["status"], "RUNNING")
        self.assertEqual(len(task_mem["steps"]), 1)

    def test_tier3_episodic_memory(self):
        """Validates Tier 3 recording workflows, diagnostic details, and outcomes."""
        mem_id = self.manager.record_episode(
            workflow_name="AutoEmailDrafting",
            outcome="Sent email to accounting with invoice attached",
            details={"invoice_id": "INV-2026-09", "recipient": "finance@corp.com"},
            success=True
        )
        self.assertIsNotNone(mem_id)
        
        episodes = self.manager.get_episodes()
        self.assertEqual(len(episodes), 1)
        ep = episodes[0]
        self.assertEqual(ep.key, "AutoEmailDrafting")
        self.assertEqual(ep.tier, MemoryTier.TIER_3_EPISODIC)
        self.assertTrue(ep.value["success"])
        self.assertEqual(ep.value["details"]["invoice_id"], "INV-2026-09")

    def test_tier4_preference_memory(self):
        """Validates Tier 4 user preferences and user confirmation tracking."""
        mem_id = self.manager.set_preference("editor_theme", "dracula", confirmed=True)
        self.assertIsNotNone(mem_id)

        pref_val = self.manager.get_preference("editor_theme")
        self.assertEqual(pref_val, "dracula")

        # Overwrite preference
        self.manager.set_preference("editor_theme", "monokai", confirmed=True)
        self.assertEqual(self.manager.get_preference("editor_theme"), "monokai")

        # Non-existent preference fallback
        self.assertEqual(self.manager.get_preference("non_existent", default="light"), "light")

    def test_tier5_semantic_fact_indexing_and_search(self):
        """Validates Tier 5 entity fact storage and keyword search."""
        f1 = self.manager.index_semantic_fact("Project Friday", "Architecture uses 5-tier cognitive memory.")
        f2 = self.manager.index_semantic_fact("Database", "SQLite with WAL mode is used for local persistence.")
        self.assertIsNotNone(f1)
        self.assertIsNotNone(f2)

        # Search for cognitive memory
        results = self.store.search("cognitive")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].key, "Project Friday")

        # Search for persistence
        results_db = self.store.search("persistence")
        self.assertEqual(len(results_db), 1)
        self.assertEqual(results_db[0].key, "Database")

    def test_user_sovereignty_ui_manifest_and_deletion(self):
        """Validates user inspection manifest, deleting specific memories, and clearing a tier."""
        self.manager.set_preference("font_size", 14)
        self.manager.record_episode("BatchCompress", "Files compressed", success=True)
        self.manager.index_semantic_fact("User", "Name is Alex")

        ui_manifest = self.manager.get_all_for_ui()
        self.assertEqual(len(ui_manifest["preferences"]), 1)
        self.assertEqual(len(ui_manifest["episodes"]), 1)
        self.assertEqual(len(ui_manifest["semantic_facts"]), 1)

        # Delete single item
        pref_id = ui_manifest["preferences"][0]["id"]
        deleted = self.manager.delete_memory_item(pref_id)
        self.assertTrue(deleted)
        self.assertIsNone(self.manager.get_preference("font_size"))

        # Clear entire tier
        cleared_count = self.manager.clear_tier(MemoryTier.TIER_5_SEMANTIC)
        self.assertEqual(cleared_count, 1)
        self.assertEqual(len(self.store.list_by_tier(MemoryTier.TIER_5_SEMANTIC)), 0)

    def test_permission_memory_enforcement(self):
        """Validates that disabling permission_memory strictly blocks storage and retrieval."""
        self.manager.set_preference("key1", "val1")
        self.assertEqual(self.manager.get_preference("key1"), "val1")

        # Disable memory permission
        self.settings.set(ContextPermission.MEMORY.value, False)
        self.assertFalse(self.store.is_permitted())

        # Read should return None
        self.assertIsNone(self.manager.get_preference("key1"))
        self.assertEqual(self.manager.get_episodes(), [])
        self.assertEqual(self.store.search("key1"), [])

        # Write should be blocked
        add_result = self.manager.set_preference("key2", "val2")
        self.assertIsNone(add_result)

        # Strict write should raise ContextPermissionError
        item = MemoryItem(
            id="strict-1",
            tier=MemoryTier.TIER_4_PREFERENCE,
            key="strict_key",
            value="strict_val"
        )
        with self.assertRaises(ContextPermissionError):
            self.store.add(item, strict=True)


if __name__ == "__main__":
    unittest.main()
