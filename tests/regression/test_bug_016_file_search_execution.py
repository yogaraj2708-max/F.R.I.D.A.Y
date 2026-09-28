"""
REGRESSION TEST: BUG-016 (File Search Returns PowerShell Tutorial Instead of Execution)
Root Cause: No dedicated FileSearchSkill existed; query fell through to LLM conversational
fallback which generated PowerShell script instructions.
Fix Verification:
1. 'find all PDF files in my Downloads folder' executes FileSearchSkill.
2. Returns structured enumeration of real files on disk.
3. Does NOT return PowerShell / bash scripting instructions.
4. Correctly detects newly placed test files.
"""

import os
import pytest
from pathlib import Path
from friday_ui.core.engine import FridayBrain, FridaySignals
from friday_core.skills.registry import skill_registry


def test_file_search_skill_direct_runtime(tmp_path):
    """Verify FileSearchSkill finds created files in target directory."""
    # Create test structure
    (tmp_path / "doc1.pdf").write_bytes(b"%PDF-1.4 test 1")
    (tmp_path / "doc2.pdf").write_bytes(b"%PDF-1.4 test 2")
    (tmp_path / "notes.txt").write_text("not a pdf")

    res = skill_registry.execute_skill(
        tool_id="file_search",
        params={"folder": str(tmp_path), "file_type": "pdf", "query": "*.pdf"},
        operation_id="search-test-1"
    )

    assert res.success is True
    assert res.data["count"] == 2
    names = [f["name"] for f in res.data["files"]]
    assert "doc1.pdf" in names
    assert "doc2.pdf" in names
    assert "notes.txt" not in names


@pytest.mark.asyncio
async def test_file_search_intent_executes_without_instructions():
    signals = FridaySignals()
    brain = FridayBrain(signals, None)

    dl = Path(os.path.expanduser("~")) / "Downloads"
    test_file = dl / "friday_search_sample.pdf"
    test_file.write_bytes(b"%PDF-1.4 sample file for search test")

    try:
        response = await brain.execute_smart_skill("find all PDF files in my Downloads folder")
        assert response is not None

        # Must execute file search and list real files
        assert "Found" in response or "matching files" in response
        assert "friday_search_sample.pdf" in response

        # Must NOT contain scripting instructions
        assert "Get-ChildItem" not in response
        assert "PowerShell" not in response
        assert "dir -r" not in response
        assert "bash" not in response
    finally:
        if test_file.exists():
            test_file.unlink()
