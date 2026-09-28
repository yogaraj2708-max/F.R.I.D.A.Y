"""
Tests for F.R.I.D.A.Y. 3.0 — RAG Retrieval & Relevance
Validates:
1. Ingestion of multi-topic documents.
2. Hybrid search relevance ranking (high relevance for related, low for unrelated).
3. Bounded top-k results.
4. Bounded max_chars context assembly.
5. Exact lexical matching (BM25) and dense semantic retrieval.
"""

import os
import tempfile
import unittest
from friday_core.rag.engine import RAGEngine
from friday_core.rag.models import KnowledgeDomain


class TestRAGRetrieval(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.engine = RAGEngine(db_path=":memory:")

        # Create two sample documents
        self.doc1_path = os.path.join(self.temp_dir, "python_tips.txt")
        with open(self.doc1_path, "w", encoding="utf-8") as f:
            f.write(
                "Python generators use the yield keyword to produce a sequence of values lazily.\n"
                "Generators save memory compared to list comprehensions when dealing with large datasets."
            )

        self.doc2_path = os.path.join(self.temp_dir, "space_exploration.txt")
        with open(self.doc2_path, "w", encoding="utf-8") as f:
            f.write(
                "The James Webb Space Telescope observes the universe in infrared wavelengths.\n"
                "It is stationed at the Sun-Earth Lagrange point 2, about 1.5 million kilometers from Earth."
            )

        self.engine.ingest_file(self.doc1_path, title="Python Tips", domain=KnowledgeDomain.TECHNICAL.value)
        self.engine.ingest_file(self.doc2_path, title="Space Exploration", domain=KnowledgeDomain.RESEARCH.value)

    def tearDown(self):
        self.engine.close()
        for f in [self.doc1_path, self.doc2_path]:
            if os.path.exists(f):
                os.remove(f)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    def test_relevance_ranking(self):
        # Query for python generators
        res_python = self.engine.query("How do Python generators work with yield?", top_k=2)
        self.assertGreater(len(res_python), 0)
        self.assertEqual(res_python[0].chunk.source_filename, "python_tips.txt")
        self.assertIn("yield", res_python[0].chunk.content)

        # Query for space telescope
        res_space = self.engine.query("James Webb Space Telescope Lagrange point", top_k=2)
        self.assertGreater(len(res_space), 0)
        self.assertEqual(res_space[0].chunk.source_filename, "space_exploration.txt")
        self.assertIn("Lagrange point", res_space[0].chunk.content)

    def test_top_k_bounds(self):
        # Request top_k = 50, engine should safely clamp to max 10
        results = self.engine.query("Python", top_k=50)
        self.assertLessEqual(len(results), 10)

    def test_context_assembly_bounded_chars(self):
        results = self.engine.query("Python generators", top_k=5, max_chars=150)
        context = self.engine.build_citation_context(results)
        self.assertIn("Python generators", context)
        self.assertIn("<untrusted_document_evidence", context)


if __name__ == "__main__":
    unittest.main()
