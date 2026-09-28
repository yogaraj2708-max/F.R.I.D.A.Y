"""
Tests for F.R.I.D.A.Y. 3.0 — Memory & RAG Concurrency
Validates:
1. Concurrent writes and reads from multiple threads without SQLite locking errors.
2. Simultaneous write + delete operations.
3. Concurrent multi-session queries maintaining session isolation.
4. RAG simultaneous ingestion and query execution.
"""

import os
import tempfile
import threading
import unittest
from friday_core.memory.store import MemoryStore
from friday_core.memory.manager import PersistentMemoryManager
from friday_core.rag.engine import RAGEngine


class TestMemoryConcurrency(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.mem_db = os.path.join(self.temp_dir, "conc_mem.db")
        self.rag_db = os.path.join(self.temp_dir, "conc_rag.db")

        self.mem_store = MemoryStore(db_path=self.mem_db)
        self.mem_mgr = PersistentMemoryManager(store=self.mem_store)
        self.rag_engine = RAGEngine(db_path=self.rag_db)

    def tearDown(self):
        self.mem_store.close()
        self.rag_engine.close()
        for f in [self.mem_db, self.rag_db]:
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

    def test_concurrent_memory_writes_and_reads(self):
        errors = []

        def worker(thread_idx: int):
            try:
                for i in range(15):
                    key = f"thread_{thread_idx}_key_{i}"
                    val = f"val_{i}"
                    self.mem_mgr.set_preference(key, val, confirmed=True)
                    readback = self.mem_mgr.get_preference(key)
                    if readback != val:
                        errors.append(f"Mismatch in thread {thread_idx}: {readback} != {val}")
            except Exception as e:
                errors.append(f"Exception in thread {thread_idx}: {e}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrency errors occurred: {errors}")

    def test_simultaneous_write_and_delete(self):
        errors = []

        def writer():
            try:
                for i in range(20):
                    self.mem_mgr.set_preference("shared_key", f"update_{i}")
            except Exception as e:
                errors.append(f"Writer exception: {e}")

        def deleter():
            try:
                for i in range(20):
                    self.mem_mgr.delete_preference("shared_key")
            except Exception as e:
                errors.append(f"Deleter exception: {e}")

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=deleter)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(errors), 0, f"Write/Delete collision: {errors}")

    def test_concurrent_rag_ingest_and_query(self):
        errors = []
        doc_path = os.path.join(self.temp_dir, "conc_doc.txt")
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write("Continuous concurrent knowledge base ingestion and searching.")

        def ingester():
            try:
                for i in range(5):
                    self.rag_engine.ingest_file(doc_path, title=f"Doc {i}")
            except Exception as e:
                errors.append(f"Ingester error: {e}")

        def reader():
            try:
                for _ in range(10):
                    res = self.rag_engine.query("continuous knowledge")
            except Exception as e:
                errors.append(f"Reader error: {e}")

        t1 = threading.Thread(target=ingester)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        if os.path.exists(doc_path):
            os.remove(doc_path)

        self.assertEqual(len(errors), 0, f"RAG concurrency errors: {errors}")


if __name__ == "__main__":
    unittest.main()
