"""
REGRESSION TEST: BUG-014 (Screenshot Capture Failure & Snipping Tool Loop)
Root Cause: gatekeeper.py mapped screenshot action to ms-screenclip: instead of capturing
and saving screen buffer to disk. PIL.ImageGrab failed on GUI threads with ERROR_BUSY.
Fix Verification:
1. 'take a screenshot and save it on the desktop' captures physical display buffer.
2. File is saved to disk and verified.
3. Image is readable with valid dimensions (e.g. 1920x1080).
4. Cleans up generated screenshot file.
"""

import os
import pytest
from pathlib import Path
from PIL import Image
from friday_ui.core.engine import FridayBrain, FridaySignals
from friday_core.skills.registry import skill_registry
from friday_core.skills.builtins.desktop_action import capture_and_save_screenshot


def test_capture_and_save_screenshot_direct_runtime():
    """Verify capture_and_save_screenshot captures live screen and verifies image."""
    desktop = Path(os.path.expanduser("~")) / "Desktop"
    shot_path = capture_and_save_screenshot(target_dir=desktop)

    assert shot_path is not None
    assert os.path.exists(shot_path)
    assert os.path.getsize(shot_path) > 0

    try:
        with Image.open(shot_path) as img:
            w, h = img.size
            assert w > 0
            assert h > 0
    finally:
        if os.path.exists(shot_path):
            os.unlink(shot_path)


@pytest.mark.asyncio
async def test_screenshot_intent_execution_and_verification():
    signals = FridaySignals()
    brain = FridayBrain(signals, None)

    cmd = "take a screenshot and save it on the desktop"
    response = await brain.execute_smart_skill(cmd)

    assert response is not None
    assert "Screenshot successfully captured" in response or "verified on disk" in response

    # Extract path from response or find the latest screenshot on Desktop
    desktop = Path(os.path.expanduser("~")) / "Desktop"
    screenshots = list(desktop.glob("screenshot_*.png"))
    assert len(screenshots) > 0, "No screenshot found on Desktop after execution."

    latest = max(screenshots, key=os.path.getctime)
    assert latest.stat().st_size > 0

    # Verify image integrity
    with Image.open(str(latest)) as img:
        assert img.size[0] > 0
        assert img.size[1] > 0

    # Cleanup
    try:
        latest.unlink()
    except Exception:
        pass
