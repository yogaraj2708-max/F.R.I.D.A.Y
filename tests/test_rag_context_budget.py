"""
Tests for F.R.I.D.A.Y. 3.0 — RAG & Memory Context Budget Integration
Validates:
1. Integration with ContextBudgetManager.
2. Token bounds for retrieved RAG chunks (max_tokens ceiling).
3. Estimation of prompt messages with memory and RAG content.
4. Validation that large multi-chunk context does not cause context overflow.
"""

import os
import tempfile
import unittest
from friday_core.rag.engine import RAGEngine
from friday_core.context.budget import ContextBudgetManager, context_budget_manager


class TestRAGContextBudget(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.engine = RAGEngine(db_path=":memory:")

        # Create a large document with 10 paragraphs
        self.large_doc_path = os.path.join(self.temp_dir, "large_doc.txt")
        with open(self.large_doc_path, "w", encoding="utf-8") as f:
            for i in range(15):
                f.write(f"Paragraph {i}: This is a detailed technical analysis regarding module {i} with extensive architecture notes and parameters.\n\n")

        self.engine.ingest_file(self.large_doc_path, title="Large Architecture Document", chunk_size=150, overlap=30)

    def tearDown(self):
        self.engine.close()
        if os.path.exists(self.large_doc_path):
            os.remove(self.large_doc_path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    def test_token_bounded_context_assembly(self):
        results = self.engine.query("technical analysis module", top_k=10)
        self.assertGreater(len(results), 1)

        # Build context with strict token ceiling of 200 tokens
        bounded_ctx = self.engine.build_citation_context(results, max_tokens=200)
        estimated_tokens = ContextBudgetManager.estimate_tokens(bounded_ctx)
        self.assertLessEqual(estimated_tokens, 260)  # within margin of safety

    def test_prompt_budget_manager_integration(self):
        results = self.engine.query("module", top_k=5)
        rag_context = self.engine.build_citation_context(results)

        messages = [
            {"role": "system", "content": "You are F.R.I.D.A.Y."},
            {"role": "user", "content": f"Answer based on this context:\n{rag_context}\nQuestion: What is module 3?"}
        ]

        # Ensure validate_and_bound_prompt keeps request bounded
        bounded_msgs, budget_result = context_budget_manager.validate_and_bound_prompt(
            messages,
            context_limit=4096
        )
        self.assertTrue(budget_result.is_valid)
        self.assertLessEqual(budget_result.estimated_tokens, 4096)


if __name__ == "__main__":
    unittest.main()
