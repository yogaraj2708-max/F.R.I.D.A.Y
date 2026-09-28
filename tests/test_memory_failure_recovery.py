"""
Tests for F.R.I.D.A.Y. 3.0 — Memory & RAG Failure Recovery
Validates:
1. Honest failure reporting when database is corrupted or unavailable.
2. Safe database rebuild via rebuild_database().
3. Querying empty database returns empty results without crashing.
4. Permission disabled handles requests cleanly without fabricating data.
"""

import os
import tempfile
import unittest
from friday_core.rag.engine import RAGEngine
from friday_core.memory.store import MemoryStore
from friday_core.memory.manager import PersistentMemoryManager
from friday_core.context.models import ContextPermission


class TestMemoryFailureRecovery(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "corrupt_test.db")
        self.engine = RAGEngine(db_path=self.db_path)

    def tearDown(self):
        self.engine.close()
        for f in os.listdir(self.temp_dir):
            try:
                os.remove(os.path.join(self.temp_dir, f))
            except Exception:
                pass
        try:
            os.rmdir(self.temp_dir)
        except Exception:
            pass

    def test_empty_database_query_handling(self):
        # Querying an empty database should return [] without exception
        results = self.engine.query("non_existent_topic", top_k=5)
        self.assertEqual(len(results), 0)

        ctx = self.engine.build_citation_context(results)
        self.assertEqual(ctx, "No relevant context found in repository.")

    def test_database_corruption_detection_and_rebuild(self):
        # 1. Close clean engine
        self.engine.close()

        # 2. Corrupt the database file by writing garbage
        with open(self.db_path, "wb") as f:
            f.write(b"CORRUPTED_SQLITE_GARBAGE_HEADER_DATA_1234567890")

        # 3. Create engine pointing to corrupt DB
        corrupt_engine = RAGEngine(db_path=self.db_path)

        # Integrity check should detect failure
        is_intact = corrupt_engine.check_integrity()
        self.assertFalse(is_intact)

        # 4. Trigger safe rebuild
        rebuilt = corrupt_engine.rebuild_database()
        self.assertTrue(rebuilt)
        self.assertTrue(corrupt_engine.check_integrity())

        # 5. Queries and ingestion now work normally
        test_file = os.path.join(self.temp_dir, "post_recovery.txt")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("System recovered successfully after database rebuild.")
        chunks = corrupt_engine.ingest_file(test_file)
        self.assertGreater(len(chunks), 0)
        corrupt_engine.close()

    def test_permission_failure_handling(self):
        class MockSettings:
            def get(self, key, default=None):
                if key == ContextPermission.FILE_INDEXING.value:
                    return False
                return True

        blocked_engine = RAGEngine(db_path=":memory:", config=MockSettings())
        test_file = os.path.join(self.temp_dir, "blocked.txt")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("Blocked file content.")

        # Ingestion blocked returns empty list without crashing
        chunks = blocked_engine.ingest_file(test_file, strict=False)
        self.assertEqual(len(chunks), 0)
        blocked_engine.close()


if __name__ == "__main__":
    unittest.main()
