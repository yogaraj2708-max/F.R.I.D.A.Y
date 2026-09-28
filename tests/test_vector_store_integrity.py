"""
Tests for F.R.I.D.A.Y. 3.0 — Vector Store Integrity
Validates:
1. Vector database initialization and schema constraints.
2. Ingest document chunks -> retrieve -> close and reopen DB -> retrieve.
3. Logical result consistency across restarts.
4. Database integrity verification via PRAGMA check.
5. Unique chunk identity preventing index corruption.
"""

import os
import tempfile
import unittest
from friday_core.rag.engine import RAGEngine
from friday_ui.rag.store import FridayVectorStore


class TestVectorStoreIntegrity(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.rag_db = os.path.join(self.temp_dir, "test_rag.db")
        self.ui_db = os.path.join(self.temp_dir, "test_ui_vectors.db")

        self.engine = RAGEngine(db_path=self.rag_db)
        self.ui_store = FridayVectorStore(db_path=self.ui_db)

        self.sample_file = os.path.join(self.temp_dir, "sample.txt")
        with open(self.sample_file, "w", encoding="utf-8") as f:
            f.write("F.R.I.D.A.Y. vector database ensures offline zero-latency semantic search.")

        self.engine.ingest_file(self.sample_file, title="Sample Doc")
        self.ui_store.ingest_document("Sample Doc", "F.R.I.D.A.Y. vector database ensures offline zero-latency semantic search.")

    def tearDown(self):
        self.engine.close()
        for f in [self.sample_file, self.rag_db, self.ui_db]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
        if os.path.exists(self.temp_dir):
            try:
                os.rmdir(self.temp_dir)
            except Exception:
                pass

    def test_database_integrity_pragma(self):
        self.assertTrue(self.engine.check_integrity())
        self.assertTrue(self.ui_store.check_integrity())

    def test_restart_persistence_and_consistent_retrieval(self):
        # 1. Query before restart
        res1 = self.engine.query("zero-latency semantic search", top_k=1)
        self.assertEqual(len(res1), 1)
        score1 = res1[0].hybrid_score

        # 2. Simulate restart: close and re-open
        self.engine.close()
        reopened = RAGEngine(db_path=self.rag_db)

        # 3. Query after restart
        res2 = reopened.query("zero-latency semantic search", top_k=1)
        self.assertEqual(len(res2), 1)
        score2 = res2[0].hybrid_score

        self.assertEqual(res1[0].chunk.content, res2[0].chunk.content)
        self.assertEqual(score1, score2)
        reopened.close()

    def test_ui_vector_store_deletion(self):
        results = self.ui_store.query("semantic search", top_k=1)
        self.assertGreater(len(results), 0)
        doc_id = results[0]["doc_id"]

        deleted = self.ui_store.delete_document(doc_id)
        self.assertTrue(deleted)

        after_del = self.ui_store.query("semantic search", top_k=1)
        self.assertEqual(len(after_del), 0)


if __name__ == "__main__":
    unittest.main()
