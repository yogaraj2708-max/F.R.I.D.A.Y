"""
Tests for F.R.I.D.A.Y. 3.0 — Memory Session Isolation
Validates:
1. Session A stores memory A (session-scoped).
2. Session B stores memory B (session-scoped).
3. Session B querying for memory A returns None (no cross-session leakage).
4. Session A querying for memory B returns None.
5. App restart simulation: Session A recovers A, Session B recovers B.
6. Global scope memories are accessible across sessions.
"""

import os
import tempfile
import unittest
from friday_core.memory.tiers import MemoryTier, MemoryItem
from friday_core.memory.store import MemoryStore
from friday_core.memory.manager import PersistentMemoryManager


class TestMemorySessionIsolation(unittest.TestCase):
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

    def test_session_isolation_and_no_leakage(self):
        session_a = "sess_alpha_101"
        session_b = "sess_bravo_202"

        # 1. Session A stores secret fact A
        id_a = self.manager.set_preference(
            key="secret_token",
            value="TOKEN_ALPHA_SECRET",
            session_id=session_a,
            scope="session"
        )
        self.assertIsNotNone(id_a)

        # 2. Session B stores secret fact B
        id_b = self.manager.set_preference(
            key="secret_token",
            value="TOKEN_BRAVO_SECRET",
            session_id=session_b,
            scope="session"
        )
        self.assertIsNotNone(id_b)

        # 3. Session A queries for secret_token -> gets TOKEN_ALPHA_SECRET
        val_a = self.manager.get_preference("secret_token", session_id=session_a)
        self.assertEqual(val_a, "TOKEN_ALPHA_SECRET")

        # 4. Session B queries for secret_token -> gets TOKEN_BRAVO_SECRET
        val_b = self.manager.get_preference("secret_token", session_id=session_b)
        self.assertEqual(val_b, "TOKEN_BRAVO_SECRET")

        # 5. Session C (unrelated session) queries for secret_token -> gets None!
        val_c = self.manager.get_preference("secret_token", session_id="sess_charlie_303")
        self.assertIsNone(val_c)

    def test_session_isolation_across_restart(self):
        session_a = "sess_a"
        session_b = "sess_b"

        self.manager.set_preference("project_focus", "Focus Alpha", session_id=session_a, scope="session")
        self.manager.set_preference("project_focus", "Focus Beta", session_id=session_b, scope="session")

        # Simulate restart
        self.store.close()
        reopened_store = MemoryStore(db_path=self.db_path)
        reopened_manager = PersistentMemoryManager(store=reopened_store)

        # Re-check isolation after restart
        self.assertEqual(reopened_manager.get_preference("project_focus", session_id=session_a), "Focus Alpha")
        self.assertEqual(reopened_manager.get_preference("project_focus", session_id=session_b), "Focus Beta")
        self.assertIsNone(reopened_manager.get_preference("project_focus", session_id="sess_unknown"))

        reopened_store.close()

    def test_global_scope_sharing(self):
        # Global memory without session restriction
        self.manager.set_preference("system_name", "FRIDAY_MAIN", scope="global")

        # Accessible to any session
        self.assertEqual(self.manager.get_preference("system_name", session_id="sess_x"), "FRIDAY_MAIN")
        self.assertEqual(self.manager.get_preference("system_name", session_id="sess_y"), "FRIDAY_MAIN")


if __name__ == "__main__":
    unittest.main()
