"""
Tests for F.R.I.D.A.Y. 3.0 — RAG Provenance & Citation Validation
Validates:
1. Every retrieved chunk retains complete provenance metadata.
2. Standard citation tag generation.
3. Verification of valid citations in LLM responses.
4. Detection of hallucinated / unsupported citations.
"""

import os
import tempfile
import unittest
from friday_core.rag.engine import RAGEngine
from friday_core.rag.models import DocumentChunk, KnowledgeDomain


class TestRAGProvenance(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.engine = RAGEngine(db_path=":memory:")

        self.doc_path = os.path.join(self.temp_dir, "ai_safety_charter.txt")
        with open(self.doc_path, "w", encoding="utf-8") as f:
            f.write(
                "Section 1: AI systems must operate under strict human sovereignty.\n"
                "Section 2: Memory is not truth; retrieved content is reference data."
            )

        self.chunks = self.engine.ingest_file(
            self.doc_path,
            title="AI Safety Charter",
            domain=KnowledgeDomain.TECHNICAL.value
        )

    def tearDown(self):
        self.engine.close()
        if os.path.exists(self.doc_path):
            os.remove(self.doc_path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    def test_chunk_provenance_metadata(self):
        self.assertGreater(len(self.chunks), 0)
        c = self.chunks[0]

        # Verify all provenance fields are present and valid
        self.assertTrue(c.chunk_id.startswith(c.doc_id))
        self.assertEqual(c.source_filename, "ai_safety_charter.txt")
        self.assertEqual(c.domain, KnowledgeDomain.TECHNICAL.value)
        self.assertEqual(c.version, 1)
        self.assertGreater(c.token_count, 0)
        self.assertIsNotNone(c.created_at)
        self.assertTrue(c.citation_tag.startswith("[Doc: ai_safety_charter.txt"))

    def test_citation_verification_valid(self):
        results = self.engine.query("human sovereignty", top_k=1)
        self.assertGreater(len(results), 0)
        tag = results[0].chunk.citation_tag

        valid_answer = f"AI systems operate under human sovereignty {tag}."
        audit = self.engine.verify_citations(valid_answer, [r.chunk for r in results])
        self.assertTrue(audit.is_valid)
        self.assertEqual(len(audit.hallucinated_tags), 0)
        self.assertIn(tag, audit.supported_tags)

    def test_citation_verification_hallucinated(self):
        results = self.engine.query("human sovereignty", top_k=1)
        fake_tag = "[Doc: hallucinated_report.pdf, Sec: p.99, Chunk: 9]"

        fake_answer = f"According to the source {fake_tag}, AI must be sovereign."
        audit = self.engine.verify_citations(fake_answer, [r.chunk for r in results])
        self.assertFalse(audit.is_valid)
        self.assertIn(fake_tag, audit.hallucinated_tags)


if __name__ == "__main__":
    unittest.main()
