"""
REGRESSION TEST: File Organizer Preview / Dry Run Bug (Section 3)
Root Cause: organize_directory had no dry_run mode; _dispatch_semantic_intent intercepted
any command with 'files' and opened File Explorer.
Fix Verification:
1. 'scan my Downloads folder and show me what files you would organize, but don't move anything'
   returns preview report without opening File Explorer.
2. Zero filesystem mutations: files remain in root, zero directories created or moved.
3. organize_directory(..., dry_run=True) returns formatted preview table.
"""

import pytest
from pathlib import Path
from friday_ui.core.engine import FridayBrain, FridaySignals


@pytest.mark.asyncio
async def test_organize_directory_dry_run_zero_mutations(tmp_path):
    """Verify dry_run=True produces report and touches zero files on disk."""
    signals = FridaySignals()
    brain = FridayBrain(signals, None)

    # Create sample files
    f_pdf = tmp_path / "invoice.pdf"
    f_img = tmp_path / "photo.png"
    f_zip = tmp_path / "backup.zip"

    f_pdf.write_bytes(b"%PDF content")
    f_img.write_bytes(b"\x89PNG content")
    f_zip.write_bytes(b"PK zip content")

    initial_files = set(p.name for p in tmp_path.iterdir())

    report = await brain.organize_directory(str(tmp_path), dry_run=True)
    assert report is not None
    assert "Dry Run — Zero Mutations" in report
    assert "invoice.pdf" in report
    assert "photo.png" in report

    # Postcondition: No folders created, original files untouched
    post_files = set(p.name for p in tmp_path.iterdir())
    assert initial_files == post_files
    assert not (tmp_path / "Documents").exists()
    assert not (tmp_path / "Images").exists()
    assert not (tmp_path / "Archives").exists()


@pytest.mark.asyncio
async def test_organizer_preview_intent_in_brain(tmp_path):
    signals = FridaySignals()
    brain = FridayBrain(signals, None)

    # Place a test file in Downloads
    dl = Path.home() / "Downloads"
    t_file = dl / "friday_dryrun_sample.txt"
    t_file.write_text("dry run test payload")

    try:
        cmd = "scan my Downloads folder and show me what files you would organize, but don't move anything"
        response = await brain.execute_smart_skill(cmd)

        assert response is not None
        assert "Dry Run — Zero Mutations" in response or "Preview" in response

        # Verify the file was not moved
        assert t_file.exists(), "File was moved during dry-run preview!"
    finally:
        if t_file.exists():
            t_file.unlink()
