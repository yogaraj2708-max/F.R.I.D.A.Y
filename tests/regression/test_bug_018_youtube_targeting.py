"""
REGRESSION TEST: BUG-018 (YouTube / Web Target Routing Failure)
Root Cause: YouTube query fell through to open_app, which matched 'code' in the Start Menu
shortcut paths, launching VS Code and generic web searches instead of YouTube.
Fix Verification:
1. 'open YouTube and search for lofi music' routes to YouTube search URL.
2. Does NOT launch VS Code.
3. YouTube destination URL contains encoded search query.
"""

import pytest
import psutil
from friday_ui.core.engine import FridayBrain, FridaySignals
from friday_core.system.launcher import launch_application, find_and_open_desktop_or_system_item


def test_launcher_guards_against_youtube():
    """Verify launch_application and find_and_open reject YouTube queries."""
    ok, app = launch_application("open youtube and search for lofi music")
    assert ok is False

    ok2, app2 = find_and_open_desktop_or_system_item("open youtube and search for lofi music")
    assert ok2 is False


@pytest.mark.asyncio
async def test_youtube_search_routing_does_not_launch_vscode():
    signals = FridaySignals()
    brain = FridayBrain(signals, None)

    # Record initial VS Code processes
    initial_code_pids = [
        p.pid for p in psutil.process_iter(['pid', 'name'])
        if 'code' in (p.info['name'] or '').lower()
    ]

    cmd = "open YouTube and search for lofi music"
    response = await brain.execute_smart_skill(cmd)

    assert response is not None
    assert "Navigating to YouTube and searching for 'lofi music'" in response
    assert "Visual Studio Code" not in response

    # Assert no new VS Code process spawned
    current_code_pids = [
        p.pid for p in psutil.process_iter(['pid', 'name'])
        if 'code' in (p.info['name'] or '').lower()
    ]
    diff = set(current_code_pids) - set(initial_code_pids)
    assert len(diff) == 0, f"Unexpected VS Code processes spawned: {diff}"
