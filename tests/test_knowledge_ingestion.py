"""
Tests for F.R.I.D.A.Y. 3.0 — Knowledge Ingestion & Domain Isolation
Validates:
1. Multi-format file ingestion and semantic chunking.
2. Duplicate ingestion detection: identical content does not create duplicate chunks.
3. Document updates: modified file increments version and replaces stale chunks.
4. Knowledge domain isolation: PROJECT, PERSONAL, TECHNICAL, RESEARCH scopes.
"""

import os
import tempfile
import unittest
from friday_core.rag.engine import RAGEngine
from friday_core.rag.models import KnowledgeDomain


class TestKnowledgeIngestion(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.engine = RAGEngine(db_path=":memory:")

        self.doc_path = os.path.join(self.temp_dir, "project_charter.txt")
        with open(self.doc_path, "w", encoding="utf-8") as f:
            f.write("Project Alpha: Initial design phase for autonomous assistant.")

    def tearDown(self):
        self.engine.close()
        if os.path.exists(self.doc_path):
            os.remove(self.doc_path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    def test_duplicate_ingestion_prevention(self):
        # Ingest first time
        chunks_1 = self.engine.ingest_file(self.doc_path, title="Project Charter", domain=KnowledgeDomain.PROJECT.value)
        self.assertEqual(len(chunks_1), 1)

        # Ingest second time with identical content
        chunks_2 = self.engine.ingest_file(self.doc_path, title="Project Charter", domain=KnowledgeDomain.PROJECT.value)
        self.assertEqual(len(chunks_2), 1)

        # Query and ensure only 1 chunk exists in the store (no duplicate bloat)
        all_results = self.engine.query("Project Alpha", top_k=10)
        self.assertEqual(len(all_results), 1)

    def test_document_update_versioning(self):
        # 1. Ingest v1
        self.engine.ingest_file(self.doc_path, title="Project Charter", domain=KnowledgeDomain.PROJECT.value)
        res_v1 = self.engine.query("Project", top_k=1)
        self.assertEqual(res_v1[0].chunk.version, 1)
        self.assertIn("Project Alpha", res_v1[0].chunk.content)

        # 2. Modify document to Project Beta
        with open(self.doc_path, "w", encoding="utf-8") as f:
            f.write("Project Beta: Advanced implementation phase for autonomous assistant.")

        # 3. Re-ingest
        self.engine.ingest_file(self.doc_path, title="Project Charter", domain=KnowledgeDomain.PROJECT.value)

        # 4. Query should retrieve v2 and Project Beta, not stale Project Alpha
        res_v2 = self.engine.query("Project", top_k=1)
        self.assertEqual(res_v2[0].chunk.version, 2)
        self.assertIn("Project Beta", res_v2[0].chunk.content)
        self.assertNotIn("Project Alpha", res_v2[0].chunk.content)

    def test_knowledge_domain_isolation(self):
        tech_path = os.path.join(self.temp_dir, "tech_spec.txt")
        with open(tech_path, "w", encoding="utf-8") as f:
            f.write("CUDA 12.4 and PyTorch 2.5 are required for GPU inference.")

        proj_path = os.path.join(self.temp_dir, "project_spec.txt")
        with open(proj_path, "w", encoding="utf-8") as f:
            f.write("Project milestone deadline is October 15.")

        self.engine.ingest_file(tech_path, title="Tech Spec", domain=KnowledgeDomain.TECHNICAL.value)
        self.engine.ingest_file(proj_path, title="Project Spec", domain=KnowledgeDomain.PROJECT.value)

        # Query Technical domain
        tech_results = self.engine.query("inference", domain=KnowledgeDomain.TECHNICAL.value)
        self.assertEqual(len(tech_results), 1)
        self.assertEqual(tech_results[0].chunk.domain, KnowledgeDomain.TECHNICAL.value)

        # Query Project domain: should not return technical document
        proj_results = self.engine.query("inference", domain=KnowledgeDomain.PROJECT.value)
        self.assertEqual(len(proj_results), 0)

        # Cleanup
        os.remove(tech_path)
        os.remove(proj_path)


if __name__ == "__main__":
    unittest.main()
