"""
Regression test for Bug Fix #1 & #2: File Save Skill Registration, On-Disk Verification, and Text Replacement Semantics.
"""

import os
import tempfile
from pathlib import Path
from friday_core.skills.registry import skill_registry
from friday_core.agent.compound import compound_parser
from friday_core.agent.planner import PEOVPlanner


def test_save_file_skill_registered():
    """Verify save_file is properly registered in skill_registry."""
    skill = skill_registry.get("save_file")
    assert skill is not None, "save_file must be registered in skill_registry"
    assert skill.tool_id == "save_file"
    assert "system:filesystem" in skill.permissions


def test_save_file_physical_disk_verification():
    """Verify that save_file writes actual content to physical disk and verifies it."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_file = Path(tmp_dir) / "test_verify.txt"
        test_content = "F.R.I.D.A.Y. ZERO TRUST VERIFICATION TEST CONTENT"

        res = skill_registry.execute_skill(
            tool_id="save_file",
            params={
                "filename": str(test_file),
                "content": test_content
            },
            operation_id="test-save-verify-001"
        )

        assert res.success is True, f"Save skill failed: {res.error}"
        assert test_file.exists(), "File must physically exist on disk"
        disk_content = test_file.read_text(encoding="utf-8")
        assert disk_content == test_content, f"Content mismatch: expected '{test_content}', got '{disk_content}'"
        assert res.verification is not None
        assert res.verification.verified is True


def test_compound_parser_save_file_step():
    """Verify compound commands decompose into open_app, ui_type_text, and save_file."""
    plan = compound_parser.parse("open notepad, type hello friday, then save it as test.txt")
    assert plan is not None
    assert len(plan.steps) == 3
    assert plan.steps[0].action == "open_app"
    assert plan.steps[1].action == "ui_type_text"
    assert plan.steps[1].params["text"] == "hello friday"
    assert plan.steps[1].params["mode"] == "replace"
    assert plan.steps[2].action == "save_file"
    assert plan.steps[2].params["filename"] == "test.txt"


def test_compound_parser_four_stage_lines():
    """Verify multi-line compound with key press and file save."""
    plan = compound_parser.parse("open notepad, type line one, press enter, type line two, save as lines.txt")
    assert plan is not None
    assert len(plan.steps) == 5
    actions = [s.action for s in plan.steps]
    assert actions == ["open_app", "ui_type_text", "ui_key_press", "ui_type_text", "save_file"]
    # First typing replaces, second appends
    assert plan.steps[1].params["mode"] == "replace"
    assert plan.steps[3].params["mode"] == "append"
    assert plan.steps[4].params["filename"] == "lines.txt"
