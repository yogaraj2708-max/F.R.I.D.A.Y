"""
F.R.I.D.A.Y. 3.0 — Regression Test: Graphify Context Overflow & Budget Manager
Validates:
1. Reproduction of 16,062-token Graphify payload being bounded under 8,192 tokens.
2. GraphifyIndexRetriever extracts targeted symbols and real code windows without HTML/JSON dumps.
3. Preflight ContextBudgetManager enforces estimated_prompt_tokens < model_context_limit.
4. UI state machine transitions to 'idle' on context overflow without freezing on 'ACTIVE // THINKING'.
5. Preserves architectural and code context for the model.
"""

import os
import json
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from friday_core.context.budget import (
    ContextBudgetManager,
    context_budget_manager,
    DEFAULT_MODEL_CONTEXT_LIMIT
)
from friday_core.context.graphify_retriever import (
    GraphifyIndexRetriever,
    graphify_retriever,
    is_graphify_artifact
)


class TestGraphifyContextBudget:

    def test_graphify_artifact_detection(self):
        """Validates that all six Graphify artifacts are properly recognized."""
        artifacts = [
            ".graphify_analysis.json",
            ".graphify_labels.json",
            "graph.html",
            "graph.json",
            "GRAPH_REPORT.md",
            "manifest.json"
        ]
        for a in artifacts:
            assert is_graphify_artifact(a) is True
            assert is_graphify_artifact(f"C:\\workspace\\graphify-out\\{a}") is True

        assert is_graphify_artifact("main.py") is False
        assert is_graphify_artifact("README.md") is False

    def test_token_estimation_accuracy(self):
        """Verifies fast token estimation provides a safe upper bound."""
        sample_text = "def query_llm(prompt: str) -> str:\n    return 'Hello Boss'"
        tokens = ContextBudgetManager.estimate_tokens(sample_text)
        assert tokens > 0
        assert tokens < 100

        messages = [
            {"role": "system", "content": "You are F.R.I.D.A.Y."},
            {"role": "user", "content": sample_text}
        ]
        total_tokens = ContextBudgetManager.estimate_messages_tokens(messages)
        assert total_tokens > tokens

    def test_graphify_index_retrieval_bounds_and_content(self):
        """
        Verifies GraphifyIndexRetriever produces bounded context (< 4,456 tokens)
        and preserves key subsystem symbols and real python code snippets.
        """
        query = "this is your brain"
        ctx, ret_files, ret_symbols = graphify_retriever.retrieve_bounded_context(
            query=query,
            max_tokens=4000
        )

        # Context must not be empty
        assert len(ctx) > 100

        # Raw HTML must NEVER be in context
        assert "<html>" not in ctx.lower()
        assert "<script>" not in ctx.lower()
        assert "d3.v7" not in ctx.lower()

        # Token count must be well within budget
        estimated_tokens = ContextBudgetManager.estimate_tokens(ctx)
        assert estimated_tokens <= 4000, f"Retrieved context ({estimated_tokens} tokens) exceeded 4000 limit"

        # Key architectural symbols must be preserved
        assert any(s in ctx for s in ["F.R.I.D.A.Y.", "Architectural Index", "Entrypoints", "Adapters", "Targeted Source Excerpts"])

    def test_context_budget_bounds_oversized_16062_token_payload(self):
        """
        Regression test: Exact failure condition where prompt reaches 16,062 tokens.
        Budget manager MUST reduce/bound it under 8,192 tokens.
        """
        # Create a simulated 16,062-token prompt payload
        huge_content = (
            "[Attached Document: .graphify_analysis.json | Path: .graphify_analysis.json]\n```json\n" +
            ("{\"node\": 1, \"call\": \"ast_probe\"}\n" * 450) +
            "```\n\n" +
            "[Attached Document: graph.html | Path: graph.html]\n```html\n" +
            ("<div><svg class=\"d3-graph\"><g class=\"nodes\"></g></svg></div>\n" * 450) +
            "```\n\n" +
            "[Attached Document: graph.json | Path: graph.json]\n```json\n" +
            ("{\"links\": [{\"source\": \"A\", \"target\": \"B\"}]}\n" * 450) +
            "```\n\n" +
            "Boss Directive:\nthis is your brain"
        )

        messages = [
            {"role": "system", "content": "You are F.R.I.D.A.Y. Advanced AI Assistant."},
            {"role": "user", "content": huge_content}
        ]

        raw_estimate = ContextBudgetManager.estimate_messages_tokens(messages)
        assert raw_estimate > 10000, f"Raw estimate was {raw_estimate}, expected > 10000"

        # Apply preflight budget enforcement
        bounded_messages, result = context_budget_manager.validate_and_bound_prompt(
            messages,
            context_limit=8192
        )

        # Enforce Requirement 7: estimated_prompt_tokens < model_context_limit
        assert result.final_prompt_tokens < 8192, f"Final prompt tokens ({result.final_prompt_tokens}) exceeded 8192"
        assert result.truncation_occurred is True
        assert result.is_valid is True

        # Boss directive must still be intact
        final_user_content = bounded_messages[-1]["content"]
        assert "this is your brain" in final_user_content

    @pytest.mark.asyncio
    async def test_ui_recovers_to_idle_on_context_rejection(self):
        """
        Requirement 18: The UI must never remain stuck on ACTIVE // THINKING
        when context error occurs.
        """
        from friday_ui.core.engine import FridayBrain, FridaySignals

        signals = FridaySignals()
        signals.state_changed = MagicMock()
        signals.stream_finished = MagicMock()
        signals.stream_token = MagicMock()

        mock_tts = MagicMock()
        mock_tts.is_speaking = False
        mock_tts.cancel_event = MagicMock()
        mock_tts.cancel_event.is_set.return_value = False

        brain = FridayBrain(signals=signals, tts_engine=mock_tts)

        # Mock client.chat to raise 400 exceed_context_size_error
        class Mock400Error(Exception):
            pass

        brain.client.chat = AsyncMock(
            side_effect=Mock400Error(
                '{"error":{"code":400,"message":"request (16062 tokens) exceeds the available context size (8192 tokens)","type":"exceed_context_size_error"}}'
            )
        )

        response = await brain.query_llm("test prompt", stream_to_ui=True, stream_to_speech=False)

        # Brain must catch the error cleanly
        assert "Context Budget Limit Reached" in response

        # UI state MUST be emitted as idle
        signals.state_changed.emit.assert_any_call("idle")
