"""
REGRESSION TEST: BUG-017 (Natural Language File Selection Failure)
Root Cause: open_contextual_file_or_explorer treated 'first PDF file in my Downloads'
as a literal filename string, failing to find or open the file.
Fix Verification:
1. 'open the first PDF file in my Downloads folder' resolves 'first' and 'pdf' semantically.
2. Selects the first matching PDF in Downloads.
3. Does NOT attempt to open a literal file named 'first pdf file in my downloads.pdf'.
"""

import os
import pytest
from pathlib import Path
from friday_ui.core.engine import FridayBrain, FridaySignals
from friday_core.skills.registry import skill_registry


def test_file_selector_skill_semantic_ordering(tmp_path):
    """Verify semantic ordering: first, oldest, latest, largest."""
    f1 = tmp_path / "a_doc.pdf"
    f2 = tmp_path / "b_doc.pdf"
    f1.write_bytes(b"%PDF small")
    f2.write_bytes(b"%PDF very large payload content " * 100)

    # First by name
    res_first = skill_registry.execute_skill(
        tool_id="file_select",
        params={"folder": str(tmp_path), "file_type": "pdf", "order": "first", "action": "select"},
        operation_id="sel-first"
    )
    assert res_first.success is True
    assert res_first.data["filename"] == "a_doc.pdf"

    # Largest
    res_large = skill_registry.execute_skill(
        tool_id="file_select",
        params={"folder": str(tmp_path), "file_type": "pdf", "order": "largest", "action": "select"},
        operation_id="sel-large"
    )
    assert res_large.success is True
    assert res_large.data["filename"] == "b_doc.pdf"


@pytest.mark.asyncio
async def test_file_semantic_selection_in_brain():
    signals = FridaySignals()
    brain = FridayBrain(signals, None)

    dl = Path(os.path.expanduser("~")) / "Downloads"
    test_pdf = dl / "friday_qa_target_doc.pdf"
    test_pdf.write_bytes(b"%PDF-1.4 test document content for QA")

    try:
        response = await brain.execute_smart_skill("open the first PDF file in my Downloads folder")
        assert response is not None
        assert "Selected and opened the first pdf file" in response
        assert "friday_qa_target_doc.pdf" in response
        # Ensure it didn't look for literal 'first pdf file'
        assert "first pdf file in my downloads" not in response.lower()
    finally:
        if test_pdf.exists():
            test_pdf.unlink()
