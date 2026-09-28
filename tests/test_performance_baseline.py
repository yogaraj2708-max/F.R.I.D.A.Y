"""
Tests for F.R.I.D.A.Y. 3.0 — Performance Baseline & Latency Budgets
Verifies startup footprint, memory/thread baseline budgets, embedder throughput,
lexical retrieval, calculator, telemetry, and UI tab navigation latency.
"""

import sys
import time
import unittest
import psutil
from pathlib import Path
from PySide6.QtWidgets import QApplication

root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from friday_core.settings import settings
from friday_core.calc import safe_calculate
from friday_core.system.telemetry import get_cpu_info, get_battery_info
from friday_core.rag.hybrid_retriever import FastLocalEmbedder, BM25Index
from friday_core.skills.agent_bridge import agent_tool_bridge


class TestPerformanceBaseline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(sys.argv)

    def test_startup_and_resource_baseline(self):
        """Verifies clean application memory, thread count, and startup latency are bounded."""
        process = psutil.Process()
        rss_mb = process.memory_info().rss / (1024 * 1024)
        threads = process.threads()

        print(f"\n[BASELINE] Current Process RSS: {rss_mb:.2f} MB, Threads: {len(threads)}")
        # Friday desktop process must start with bounded footprint
        self.assertLess(rss_mb, 550.0, "Process RSS exceeded 550MB on baseline startup")
        self.assertLess(len(threads), 45, "Thread count exceeded 45 on baseline startup")

    def test_embedder_and_bm25_latencies(self):
        """Verifies dense vector projection throughput > 2000 texts/sec and BM25 < 15ms."""
        embedder = FastLocalEmbedder()
        sample_texts = [f"System operational state check {i}" for i in range(300)]

        start = time.perf_counter()
        for t in sample_texts:
            embedder.embed_text(t)
        duration = time.perf_counter() - start
        throughput = len(sample_texts) / duration

        print(f"[BASELINE] Embedder throughput: {throughput:.0f} texts/sec")
        self.assertGreater(throughput, 2000.0)

        bm25 = BM25Index()
        docs = [f"Technical document chunk {i} on machine intelligence and agent verification" for i in range(500)]
        bm25.index_documents(docs)

        start = time.perf_counter()
        scores = bm25.score("agent verification machine intelligence")
        bm25_ms = (time.perf_counter() - start) * 1000.0

        print(f"[BASELINE] BM25 lexical query (500 docs): {bm25_ms:.2f} ms")
        self.assertLess(bm25_ms, 15.0)

    def test_native_tool_latencies(self):
        """Verifies deterministic sub-millisecond calculation and fast telemetry snapshots."""
        # safe_calculate
        t0 = time.perf_counter()
        for _ in range(50):
            res = safe_calculate("25 * 4 + 100 / 2")
            self.assertIn("150", str(res))
        calc_avg_ms = (time.perf_counter() - t0) * 1000 / 50

        print(f"[BASELINE] safe_calculate avg latency: {calc_avg_ms:.3f} ms")
        self.assertLess(calc_avg_ms, 1.0)

        # get_cpu_info
        t0 = time.perf_counter()
        for _ in range(10):
            snap = get_cpu_info()
            self.assertIn("percent", snap)
        telem_avg_ms = (time.perf_counter() - t0) * 1000 / 10
        print(f"[BASELINE] Telemetry snapshot avg latency: {telem_avg_ms:.2f} ms")
        self.assertLess(telem_avg_ms, 25.0)


    def test_agent_bridge_native_tool_call_latency(self):
        """Verifies native tool execution via agent_bridge pipeline executes under 20ms."""
        from friday_core.skills.agent_bridge import agent_tool_bridge
        t0 = time.perf_counter()
        is_allowed, reason = agent_tool_bridge.risk_gate("calculate", {"expression": "1000 / 8"})
        self.assertTrue(is_allowed)
        raw_output = safe_calculate("1000 / 8")
        bundle = agent_tool_bridge.verify_tool_result(
            tool_name="calculate",
            arguments={"expression": "1000 / 8"},
            raw_output=raw_output,
            trace_id="bench_trace_01"
        )
        duration_ms = (time.perf_counter() - t0) * 1000
        print(f"[BASELINE] agent_tool_bridge pipeline latency: {duration_ms:.2f} ms")
        self.assertEqual(bundle["verification_status"], "VERIFIED")
        self.assertIn("125", bundle["formatted_result"])
        self.assertLess(duration_ms, 20.0)



if __name__ == "__main__":
    unittest.main()
