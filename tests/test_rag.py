"""
Tests for friday_ui.rag.store (Deterministic Vector Store & Embedder)
Verifies hash determinism across calls, document chunking, ingestion, and query retrieval.
"""

import os
import tempfile
import unittest
import numpy as np

from friday_ui.rag.store import FastLocalEmbedder, FridayVectorStore

class TestRAGStore(unittest.TestCase):
    def test_embedder_determinism(self):
        embedder1 = FastLocalEmbedder(dim=384)
        embedder2 = FastLocalEmbedder(dim=384)

        sample = "Iron Man Arc Reactor Mark 85 Nanotech Armor"
        vec1 = embedder1.embed_text(sample)
        vec2 = embedder2.embed_text(sample)

        # Must be 100% numerically identical
        np.testing.assert_array_almost_equal(vec1, vec2)
        # Vector must be normalized (norm close to 1.0)
        self.assertAlmostEqual(np.linalg.norm(vec1), 1.0, places=5)

    def test_embedder_different_text(self):
        embedder = FastLocalEmbedder(dim=384)
        v1 = embedder.embed_text("quantum computing encryption")
        v2 = embedder.embed_text("cooking pasta recipe")

        cosine_sim = np.dot(v1, v2)
        # Dissimilar texts should have lower cosine similarity
        self.assertLess(cosine_sim, 0.5)

    def test_vector_store_ingest_and_query(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            temp_db = f.name

        try:
            store = FridayVectorStore(db_path=temp_db)
            doc_text = (
                "Project Mark 85 is Tony Stark's advanced nanotech suit featuring an integrated "
                "Arc Reactor with energy shields, repulsors, and lightning re-channeling capabilities. "
                "It is designed to withstand extreme cosmic power."
            )
            count = store.ingest_document("Mark 85 Blueprint", doc_text)
            self.assertGreater(count, 0)

            # Query matching topic
            results = store.query("nanotech suit and energy shields", top_k=1)
            self.assertEqual(len(results), 1)
            self.assertIn("Mark 85", results[0]["title"])
            self.assertGreater(results[0]["score"], 0.2)

        finally:
            if os.path.exists(temp_db):
                os.remove(temp_db)

if __name__ == "__main__":
    unittest.main()
