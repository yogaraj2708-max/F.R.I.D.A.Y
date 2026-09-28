"""
Tests for F.R.I.D.A.Y. 3.0 — Embedding Compatibility & Dimension Safety
Validates:
1. Dynamic embedder initialization (custom dimensions and model names).
2. Deterministic embedding output for identical texts.
3. Dimension mismatch detection between query vector and stored chunk vectors.
4. Graceful handling of incompatible vectors (incompatible chunk excluded without crashing).
"""

import unittest
import numpy as np
from friday_ui.rag.store import FastLocalEmbedder
from friday_core.rag.hybrid_retriever import HybridRetriever
from friday_core.rag.models import DocumentChunk


class TestEmbeddingCompatibility(unittest.TestCase):
    def test_dynamic_embedder_dimensions(self):
        emb_384 = FastLocalEmbedder(dim=384, model_name="fast_blake2b_384")
        vec_384 = emb_384.embed_text("Test embedding string")
        self.assertEqual(vec_384.shape[0], 384)

        emb_512 = FastLocalEmbedder(dim=512, model_name="fast_blake2b_512")
        vec_512 = emb_512.embed_text("Test embedding string")
        self.assertEqual(vec_512.shape[0], 512)

    def test_embedding_determinism(self):
        emb = FastLocalEmbedder(dim=384)
        v1 = emb.embed_text("Consistent deterministic vector generation")
        v2 = emb.embed_text("Consistent deterministic vector generation")
        np.testing.assert_array_almost_equal(v1, v2)

    def test_dimension_mismatch_safety(self):
        # Create retriever with 384-dim embedder
        embedder_384 = FastLocalEmbedder(dim=384)
        retriever = HybridRetriever(alpha=1.0, embedder=embedder_384)

        chunk1 = DocumentChunk(
            chunk_id="chk1",
            doc_id="d1",
            title="Doc 1",
            source_path="d1.txt",
            source_filename="d1.txt",
            chunk_index=0,
            content="This is chunk 1"
        )
        chunk2 = DocumentChunk(
            chunk_id="chk2",
            doc_id="d2",
            title="Doc 2",
            source_path="d2.txt",
            source_filename="d2.txt",
            chunk_index=0,
            content="This is chunk 2 with mismatched dimensions"
        )

        # Chunk 1 has correct 384-dim embedding, Chunk 2 has 512-dim embedding (simulating vector DB written by different model)
        vec_valid = embedder_384.embed_text(chunk1.content)
        vec_mismatch = np.zeros(512, dtype=np.float32)

        chunks = [chunk1, chunk2]
        embeddings = [vec_valid, vec_mismatch]

        # HybridRetriever should safely rank without crashing on np.dot
        results = retriever.rank("chunk 1", chunks, embeddings, top_k=2)
        self.assertEqual(len(results), 2)
        # Valid chunk should have non-zero score, mismatched chunk should have 0.0 vector score
        self.assertEqual(results[0].chunk.chunk_id, "chk1")
        self.assertGreater(results[0].vector_score, 0.0)
        self.assertEqual(results[1].chunk.chunk_id, "chk2")
        self.assertEqual(results[1].vector_score, 0.0)


if __name__ == "__main__":
    unittest.main()
