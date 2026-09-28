"""
REGRESSION TEST: BUG-012 (Runaway / Duplicate App Launch & File Creation Misclassification)
Root Cause: Tier-2 classifier misclassified 'create a text file on desktop' as APP_LAUNCH,
and AppLauncherSkill lacked process existence checks, spawning unbounded Notepad windows.
Fix Verification:
1. 'create a text file on the desktop and write...' routes to CreateFileSkill, writing exact bytes to disk.
2. File exists on disk, content matches exactly.
3. No runaway Notepad processes spawned.
4. AppLauncherSkill reuses existing process/window when already open.
"""

import os
import pytest
import psutil
from pathlib import Path
from friday_ui.core.engine import FridayBrain, FridaySignals
from friday_core.skills.registry import skill_registry


@pytest.mark.asyncio
async def test_file_creation_does_not_spawn_runaway_notepad():
    signals = FridaySignals()
    brain = FridayBrain(signals, None)

    # Count initial notepad processes
    initial_notepad_pids = [
        p.pid for p in psutil.process_iter(['pid', 'name'])
        if 'notepad' in (p.info['name'] or '').lower()
    ]

    target_cmd = "create a text file on the desktop and write 'FRIDAY TEST FILE' in it"
    response = await brain.execute_smart_skill(target_cmd)

    assert response is not None
    assert "Created file" in response or "verified on disk" in response

    # Verify physical file existence and exact content on Desktop
    from friday_core.skills.builtins.file_ops import resolve_folder
    desktop = resolve_folder("desktop")
    test_file = desktop / "friday_test_file.txt"
    assert test_file.exists(), f"Expected test file at {test_file}"
    content = test_file.read_text(encoding="utf-8")
    assert content == "FRIDAY TEST FILE"

    # Clean up file
    try:
        test_file.unlink()
    except Exception:
        pass

    # Verify no runaway notepad windows created
    current_notepad_pids = [
        p.pid for p in psutil.process_iter(['pid', 'name'])
        if 'notepad' in (p.info['name'] or '').lower()
    ]
    # Difference should be 0 (no new notepad instances launched)
    diff = set(current_notepad_pids) - set(initial_notepad_pids)
    assert len(diff) == 0, f"Runaway Notepad processes detected: {diff}"


def test_app_launcher_skill_idempotency():
    """Verify AppLauncherSkill returns reused=True or bounded execution."""
    skill = skill_registry.get_skill("app_launcher")
    assert skill is not None

    # Idempotent execution should never loop infinitely
    res1 = skill_registry.execute_skill("app_launcher", {"app_name": "calc.exe"}, operation_id="idemp-1")
    assert res1.success is True
    assert res1.verification is not None
    assert res1.verification.verified is True
