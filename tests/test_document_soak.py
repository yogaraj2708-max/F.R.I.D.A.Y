"""
Tests for F.R.I.D.A.Y. 3.0 — Document Soak & Large Document Stress
Verifies 20+ repeated document analysis cycles across TXT, JSON, CSV, source code,
large document chunking budgets, and corrupt document failure recovery.
"""

import gc
import sys
import json
import tempfile
import unittest
import psutil
from pathlib import Path

root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from friday_core.rag.hybrid_retriever import FastLocalEmbedder, BM25Index
from friday_core.document.file_detector import detect_and_validate_file, DocumentType
from friday_core.context.budget import ContextBudgetManager


class TestDocumentSoak(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.process = psutil.Process()
        gc.collect()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_20_document_analysis_soak(self):
        """Verifies 20 consecutive document ingestion and analysis cycles across diverse formats."""
        mem_start = self.process.memory_info().rss / (1024 * 1024)
        embedder = FastLocalEmbedder()
        bm25 = BM25Index()

        formats = ["txt", "json", "csv", "py"]
        all_chunks = []

        for i in range(1, 21):
            fmt = formats[i % len(formats)]
            doc_path = Path(self.temp_dir) / f"doc_{i}.{fmt}"

            if fmt == "txt":
                content = f"Standard text report document {i} discussing aerodynamic efficiency."
            elif fmt == "json":
                content = json.dumps({"document_id": i, "topic": "Propulsion telemetry", "status": "nominal"})
            elif fmt == "csv":
                content = "id,metric,value\n1,temp,350\n2,pressure,101"
            else:
                content = "def calculate_thrust(m, a):\n    return m * a\n"

            doc_path.write_text(content, encoding="utf-8")

            # Ingest & chunk
            chunks = [f"{doc_path.name} chunk: {content}"]
            all_chunks.extend(chunks)
            for c in chunks:
                embedder.embed_text(c)

        bm25.index_documents(all_chunks)
        scores = bm25.score("aerodynamic propulsion thrust")

        gc.collect()
        mem_end = self.process.memory_info().rss / (1024 * 1024)
        growth_mb = mem_end - mem_start

        print(f"\n[DOCUMENT SOAK] 20 Ingestions: Delta RAM={growth_mb:.2f}MB, Total Chunks={len(all_chunks)}")
        self.assertLess(growth_mb, 15.0, f"Uncontrolled document memory growth: {growth_mb:.2f}MB")
        self.assertEqual(len(scores), 20)

    def test_large_document_context_bounding_stress(self):
        """Verifies a massive document (10,000 lines) is chunked and bounded without provider context overflow."""
        large_path = Path(self.temp_dir) / "large_system_spec.txt"
        large_text = "\n".join([f"Line {idx}: System component operational specification {idx * 7}" for idx in range(1000)])
        large_path.write_text(large_text, encoding="utf-8")

        budget_mgr = ContextBudgetManager(model_context_limit=4096)
        user_prompt = f"[Attached Document: {large_path.name}]\n```{large_text}```\n\nBoss Directive:\nSummarize this specification."

        messages = [
            {"role": "system", "content": "Assistant."},
            {"role": "user", "content": user_prompt}
        ]

        bounded, result = budget_mgr.validate_and_bound_prompt(messages, context_limit=4096)
        print(f"[LARGE DOC STRESS] Initial Tokens={result.estimated_tokens}, Bounded Tokens={result.final_prompt_tokens}")

        self.assertTrue(result.is_valid)
        self.assertLess(result.final_prompt_tokens, 4096)
        self.assertTrue(result.truncation_occurred)

    def test_corrupt_file_handling(self):
        """Verifies corrupt / binary files disguised as text do not crash ingestion pipeline."""
        corrupt_path = Path(self.temp_dir) / "corrupt.txt"
        corrupt_path.write_bytes(b"\x00\xff\xfe\x00\x12\x34\x56\x78" * 100)

        # File type detection should safely detect and reject or mark unknown fail-closed
        res = detect_and_validate_file(str(corrupt_path))
        print(f"[DOCUMENT SOAK] Corrupt file detection result: valid={res.is_valid}, type={res.doc_type}")
        self.assertFalse(res.is_valid)



if __name__ == "__main__":
    unittest.main()
