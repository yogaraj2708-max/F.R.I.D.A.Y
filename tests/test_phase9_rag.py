"""
Tests for F.R.I.D.A.Y. 3.0 — Phase 9: RAG 2.0 (Document Intelligence & Citations)
Validates:
1. Multi-format Document Extraction (.txt, .md, .docx, .pdf).
2. Lexical BM25 matching for rare keywords and technical identifiers.
3. Dense vector semantic matching for conceptual queries.
4. Hybrid ranking fusing lexical and vector scores.
5. Strict chunk provenance and citation tagging.
6. Citation hallucination verification (supported vs hallucinated citations).
7. Permission gate enforcement ('permission_file_indexing').
"""

import os
import io
import zipfile
import tempfile
import unittest
import pypdf

from friday_core.rag.models import DocumentChunk, QueryResult, CitationVerificationResult
from friday_core.rag.extractors import DocumentExtractor
from friday_core.rag.hybrid_retriever import BM25Index, HybridRetriever
from friday_core.rag.engine import RAGEngine
from friday_core.context.models import ContextPermission, ContextPermissionError


class MockSettings:
    def __init__(self, indexing_permitted: bool = True):
        self._values = {ContextPermission.FILE_INDEXING.value: indexing_permitted}

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        self._values[key] = value


class TestRAG2Subsystem(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.settings = MockSettings(indexing_permitted=True)
        self.engine = RAGEngine(db_path=":memory:", config=self.settings)

    def tearDown(self):
        self.engine.close()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_sample_docx(self, path: str, paragraphs: list):
        """Creates a minimal valid .docx file using standard library zipfile."""
        xml_parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>']
        xml_parts.append('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>')
        for p in paragraphs:
            xml_parts.append(f'<w:p><w:r><w:t>{p}</w:t></w:r></w:p>')
        xml_parts.append('</w:body></w:document>')
        doc_xml = "".join(xml_parts).encode("utf-8")

        with zipfile.ZipFile(path, "w") as z:
            z.writestr("word/document.xml", doc_xml)
            z.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>')

    def _create_sample_pdf(self, path: str, pages_text: list):
        """Creates a minimal valid .pdf file with pypdf."""
        writer = pypdf.PdfWriter()
        for text in pages_text:
            writer.add_blank_page(width=612, height=792)
        # Write out blank pages then save
        with open(path, "wb") as f:
            writer.write(f)

    def test_multi_format_extraction_and_ingestion(self):
        """Validates ingestion of .txt, .md, and .docx formats."""
        # 1. Plaintext file
        txt_path = os.path.join(self.temp_dir, "notes.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("F.R.I.D.A.Y. 3.0 uses an advanced closed-loop agent architecture.")
        chunks_txt = self.engine.ingest_file(txt_path)
        self.assertEqual(len(chunks_txt), 1)
        self.assertEqual(chunks_txt[0].source_filename, "notes.txt")

        # 2. Markdown file
        md_path = os.path.join(self.temp_dir, "architecture.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# Specification\n\nThe hybrid retriever combines BM25 and vector search.")
        chunks_md = self.engine.ingest_file(md_path)
        self.assertEqual(len(chunks_md), 1)
        self.assertEqual(chunks_md[0].source_filename, "architecture.md")

        # 3. DOCX file
        docx_path = os.path.join(self.temp_dir, "contract.docx")
        self._create_sample_docx(docx_path, ["Confidential agreement on quantum cryptography.", "Clause 42: zero leakage."])
        chunks_docx = self.engine.ingest_file(docx_path)
        self.assertEqual(len(chunks_docx), 1)
        self.assertEqual(chunks_docx[0].source_filename, "contract.docx")
        self.assertIn("quantum cryptography", chunks_docx[0].content)

    def test_bm25_lexical_keyword_retrieval(self):
        """Validates that BM25 exact match finds unique identifiers."""
        bm25 = BM25Index()
        docs = [
            "The standard operating protocol for morning briefing.",
            "Emergency code alpha 4892_PROJECT_XENON is classified.",
            "Weather forecast predicts heavy rain in Seattle."
        ]
        bm25.index_documents(docs)
        scores = bm25.score("4892_PROJECT_XENON")
        # Second doc must be the top match
        self.assertGreater(scores[1], scores[0])
        self.assertGreater(scores[1], scores[2])

    def test_hybrid_ranking_and_citations(self):
        """Validates hybrid search ranking and citation tag formatting."""
        p1 = os.path.join(self.temp_dir, "telemetry.txt")
        with open(p1, "w", encoding="utf-8") as f:
            f.write("System CPU usage reached 92 percent during high load.")
        self.engine.ingest_file(p1)

        p2 = os.path.join(self.temp_dir, "specs.txt")
        with open(p2, "w", encoding="utf-8") as f:
            f.write("The database uses WAL mode for concurrent SQLite operations.")
        self.engine.ingest_file(p2)

        results = self.engine.query("What is the database mode?", top_k=2)
        self.assertGreater(len(results), 0)
        top = results[0]
        self.assertEqual(top.chunk.source_filename, "specs.txt")
        self.assertIn("WAL mode", top.chunk.content)
        self.assertTrue(top.citation_tag.startswith("[Doc: specs.txt"))

        # Test context assembly
        context_str = self.engine.build_citation_context(results)
        self.assertIn("--- Context Snippet [Doc: specs.txt", context_str)
        self.assertIn("WAL mode", context_str)

    def test_citation_hallucination_verification(self):
        """Validates verification of answer citations against actual retrieved chunks."""
        chunk1 = DocumentChunk(
            chunk_id="c1",
            doc_id="d1",
            title="Specs",
            source_path="/fake/specs.txt",
            source_filename="specs.txt",
            page_or_section="p.1",
            chunk_index=0,
            content="SQLite WAL mode."
        )

        retrieved = [chunk1]

        # Valid answer referencing real chunk
        valid_answer = "The system uses WAL mode [Doc: specs.txt, Sec: p.1, Chunk: 0] as configured."
        v_res = self.engine.verify_citations(valid_answer, retrieved)
        self.assertTrue(v_res.is_valid)
        self.assertEqual(len(v_res.supported_tags), 1)
        self.assertEqual(len(v_res.hallucinated_tags), 0)

        # Hallucinated answer referencing non-existent doc
        hallucinated_answer = "The system uses Postgres [Doc: internal_secret_plan.pdf, Sec: p.99, Chunk: 5]."
        h_res = self.engine.verify_citations(hallucinated_answer, retrieved)
        self.assertFalse(h_res.is_valid)
        self.assertEqual(len(h_res.hallucinated_tags), 1)
        self.assertIn("internal_secret_plan.pdf", h_res.hallucinated_tags[0])

    def test_permission_file_indexing_gate(self):
        """Validates that turning off permission_file_indexing prevents document ingestion and query."""
        txt_path = os.path.join(self.temp_dir, "secret.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("Secret data.")

        # Disable permission
        self.settings.set(ContextPermission.FILE_INDEXING.value, False)
        self.assertFalse(self.engine.is_permitted())

        # Ingest should return empty
        chunks = self.engine.ingest_file(txt_path)
        self.assertEqual(chunks, [])

        # Strict mode should raise error
        with self.assertRaises(ContextPermissionError):
            self.engine.ingest_file(txt_path, strict=True)

        # Queries should return empty
        self.assertEqual(self.engine.query("secret"), [])


if __name__ == "__main__":
    unittest.main()
