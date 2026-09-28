"""
Tests for F.R.I.D.A.Y. 3.0 — Memory Leaks & Steady-State Memory Audit
Verifies bounded memory growth over repeated cycles (10, 25, 50, 100 iterations)
across conversation history, memory insertion/retrieval, and tool executions.
"""

import gc
import sys
import psutil
import unittest
from pathlib import Path

root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from friday_core.memory.manager import PersistentMemoryManager
from friday_core.memory.tiers import MemoryItem, MemoryTier
from friday_core.rag.hybrid_retriever import FastLocalEmbedder, BM25Index
from friday_core.calc import safe_calculate


class TestMemoryLeaks(unittest.TestCase):
    def setUp(self):
        self.process = psutil.Process()
        gc.collect()

    def test_repeated_tool_execution_memory_stability(self):
        """Verifies 100 repeated tool executions have flat memory footprint with zero leak."""
        gc.collect()
        mem_start = self.process.memory_info().rss / (1024 * 1024)

        checkpoints = {}
        for i in range(1, 101):
            safe_calculate(f"{i} * 10 + {i * 2}")
            if i in [1, 10, 25, 50, 75, 100]:
                gc.collect()
                checkpoints[i] = round(self.process.memory_info().rss / (1024 * 1024), 2)

        mem_end = self.process.memory_info().rss / (1024 * 1024)
        growth_mb = mem_end - mem_start
        print(f"\n[MEMORY AUDIT] Tool Execution 100 turns: Start={mem_start:.2f}MB, End={mem_end:.2f}MB, Delta={growth_mb:.2f}MB")
        print(f"[MEMORY AUDIT] Checkpoints (MB): {checkpoints}")

        # Over 100 simple evaluations, memory growth must be strictly bounded (< 5MB)
        self.assertLess(growth_mb, 5.0, f"Uncontrolled tool memory growth: {growth_mb:.2f}MB")

    def test_repeated_memory_retrieval_stability(self):
        """Verifies repeated memory lookups and semantic indexing do not leak memory."""
        mgr = PersistentMemoryManager()
        embedder = FastLocalEmbedder()

        gc.collect()
        mem_start = self.process.memory_info().rss / (1024 * 1024)

        for i in range(1, 101):
            embedder.embed_text(f"Query check number {i} for memory stability verification")
            mgr.append_working_turn("user", f"Turn check {i}")
            mgr.get_preference(f"pref_key_{i % 5}", default="nominal")
            mgr.get_episodes(max_items=5)


        gc.collect()
        mem_end = self.process.memory_info().rss / (1024 * 1024)
        growth_mb = mem_end - mem_start
        print(f"[MEMORY AUDIT] Retrieval 100 cycles: Start={mem_start:.2f}MB, End={mem_end:.2f}MB, Delta={growth_mb:.2f}MB")
        self.assertLess(growth_mb, 15.0, f"Unbounded retrieval memory growth: {growth_mb:.2f}MB")

    def test_repeated_bm25_reindexing_bounded(self):
        """Verifies repeated BM25 indexing operations cleanly release previous index structures."""
        gc.collect()
        mem_start = self.process.memory_info().rss / (1024 * 1024)

        for i in range(50):
            bm25 = BM25Index()
            docs = [f"Transient document chunk {j} iteration {i}" for j in range(200)]
            bm25.index_documents(docs)
            del docs
            del bm25

        gc.collect()
        mem_end = self.process.memory_info().rss / (1024 * 1024)
        growth_mb = mem_end - mem_start
        print(f"[MEMORY AUDIT] BM25 50 Re-indexes: Delta={growth_mb:.2f}MB")
        self.assertLess(growth_mb, 10.0, f"BM25 index memory accumulation: {growth_mb:.2f}MB")


if __name__ == "__main__":
    unittest.main()
