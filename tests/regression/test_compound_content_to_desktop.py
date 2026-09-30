"""
F.R.I.D.A.Y. 3.0 — Regression Test: Compound Content-Generation to Desktop
============================================================================

Validates the fix for the critical crash caused by:
  "write a summary of Harry Potter and put it in my note pad"

Root cause: The type_match regex at engine.py:2858 intercepted "write" as a
literal typing verb, sending raw parse artifacts into Notepad instead of routing
through the PEOV compound planner for LLM content generation + desktop insertion.

Fix applied in:
  1. friday_core/agent/compound.py — Reversed syntax support in parse()
  2. friday_ui/core/engine.py — Content-generation guard on type_match

References:
  - Crash Report: COMPOUND_PARSER_FAILURE
  - Affected Path: execute_smart_skill → type_match regex (Command Bar)
  - DAG: open_app → content_generation → ui_focus → ui_type_text → ui_verify_content
"""

import sys
import os
import re
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from friday_core.agent.compound import compound_parser, CompoundPlan


class TestCompoundContentGenerationCrash:
    """Regression test suite for the compound content-generation-to-desktop crash."""

    # ─── Reversed Syntax (Root Cause of the Crash) ───

    def test_crash_command_produces_valid_plan(self):
        """The exact crash command must produce a valid 5-step compound plan."""
        plan = compound_parser.parse("write a summary of Harry Potter and put it in my note pad")
        assert plan is not None
        assert len(plan.steps) == 5

    def test_crash_command_dag_structure(self):
        """Verify the full 5-step DAG for the crash command."""
        plan = compound_parser.parse("write a summary of Harry Potter and put it in my note pad")
        assert plan.steps[0].action == "open_app"
        assert plan.steps[1].action == "content_generation"
        assert plan.steps[2].action == "ui_focus"
        assert plan.steps[3].action == "ui_type_text"
        assert plan.steps[4].action == "ui_verify_content"

    def test_crash_command_content_gen_topic(self):
        """Content generation step must contain the topic, not literal text."""
        plan = compound_parser.parse("write a summary of Harry Potter and put it in my note pad")
        assert "summary" in plan.steps[1].params.get("prompt", "").lower()

    def test_crash_command_type_step_uses_ref(self):
        """Type step must reference $content_generation output, not literal text."""
        plan = compound_parser.parse("write a summary of Harry Potter and put it in my note pad")
        assert plan.steps[3].params["text"].startswith("$content_generation")

    def test_crash_command_targets_notepad(self):
        """App target must be resolved from 'note pad' in the command."""
        plan = compound_parser.parse("write a summary of Harry Potter and put it in my note pad")
        assert "note pad" in plan.steps[0].params.get("app_name", "").lower()

    # ─── Reversed Syntax Variants ───

    @pytest.mark.parametrize("command", [
        "write a welcome speech and put it in notepad",
        "write a birthday message and put it in notepad",
        "write a leave letter and put it in notepad",
        "write a report and insert it in my notepad",
        "draft a welcome speech and put it in notepad",
        "compose an email and paste it into word",
        "please write a summary of AI and put it in my notepad",
        "can you write a leave letter and put it in notepad",
        "write a memo and put it in my notepad",
        "write an essay about technology and put it in notepad",
    ])
    def test_reversed_syntax_variants(self, command):
        """All reversed-syntax compound commands must produce a content_generation step."""
        plan = compound_parser.parse(command)
        assert plan is not None, f"Parser returned None for: {command!r}"
        actions = [s.action for s in plan.steps]
        assert "content_generation" in actions, f"No content_generation step in: {actions}"

    # ─── Original Syntax Still Works ───

    def test_original_open_and_write_syntax(self):
        """The original 'open notepad and write a speech' syntax must still produce a 5-step DAG."""
        plan = compound_parser.parse("open notepad and write a welcome speech for a college event")
        assert plan is not None
        assert len(plan.steps) == 5
        assert plan.steps[1].action == "content_generation"

    def test_original_open_and_type_literal(self):
        """'open notepad and type hello world' must still work as literal typing."""
        plan = compound_parser.parse("open notepad and type hello world")
        assert plan is not None
        actions = [s.action for s in plan.steps]
        assert "ui_type_text" in actions
        assert "content_generation" not in actions

    # ─── Content-Generation Guard (Engine) ───

    def _simulate_engine_guard(self, command: str) -> bool:
        """Simulates the content-generation guard from engine.py execute_smart_skill."""
        cmd = command.lower().strip()
        type_match = re.match(
            r"^(?:can\s+you\s+|please\s+|could\s+you\s+|would\s+you\s+)?(?:type|input|enter|paste|append|insert|replace|overwrite|put|write)\s+(.+)$",
            command,
            re.IGNORECASE
        )
        _is_compound_content_gen = False
        if type_match and re.match(r"^(?:write|draft|compose)\s+", cmd, re.IGNORECASE):
            _raw_clause = type_match.group(1).strip()
            _reversed_m = re.search(
                r"\s+(?:and\s+)?(?:put|place|paste|insert|type)\s+(?:it\s+|that\s+)?(?:in|into|on)\s+(?:my\s+)?[a-zA-Z0-9_\-\s]+$",
                _raw_clause,
                re.IGNORECASE
            )
            if _reversed_m:
                _topic_part = _raw_clause[:_reversed_m.start()].strip()
                if compound_parser.is_generative_writing(_topic_part):
                    _is_compound_content_gen = True
        return _is_compound_content_gen

    @pytest.mark.parametrize("command", [
        "write a summary of Harry Potter and put it in my note pad",
        "write a welcome speech and put it in notepad",
        "write a report and insert it in my notepad",
    ])
    def test_guard_blocks_content_generation(self, command):
        """Guard must block content-generation compound commands from literal typing path."""
        assert self._simulate_engine_guard(command) is True

    @pytest.mark.parametrize("command", [
        "type hello world in notepad",
        "write hello world",
        "type this is a test in notepad",
        "put hello in my notepad",
        "write test123 in notepad",
    ])
    def test_guard_allows_literal_typing(self, command):
        """Guard must NOT block simple literal typing commands."""
        assert self._simulate_engine_guard(command) is False

    # ─── is_generative_writing Detection ───

    @pytest.mark.parametrize("text", [
        "a summary of Harry Potter",
        "a welcome speech for a college event",
        "a birthday message for my friend",
        "a leave letter for my manager",
        "an apology letter",
        "a report on climate change",
        "a memo about the meeting",
        "summary of artificial intelligence",
    ])
    def test_generative_detection_positive(self, text):
        assert compound_parser.is_generative_writing(text) is True

    @pytest.mark.parametrize("text", [
        "hello world",
        "this is a test",
        "123 Main Street",
        "var x = 42;",
        "the quick brown fox",
    ])
    def test_generative_detection_negative(self, text):
        assert compound_parser.is_generative_writing(text) is False
