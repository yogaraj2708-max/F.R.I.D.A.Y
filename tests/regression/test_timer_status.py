"""
REGRESSION TEST: Timer Status vs Clock Bug (Section 2)
Root Cause: _active_timers only held raw asyncio tasks without remaining-time tracking.
'how much time is left on my timer?' collided with 'the time' query, returning clock time.
Fix Verification:
1. 'how much time is left on my timer?' returns remaining countdown.
2. Must NOT return the current clock time.
3. TimerManager correctly reflects RUNNING and remaining seconds.
"""

import asyncio
import pytest
from datetime import datetime
from friday_ui.core.engine import FridayBrain, FridaySignals
from friday_core.skills.builtins.timer import timer_manager, TimerState


def test_timer_manager_lifecycle():
    """Verify TimerManager tracks countdown accurately."""
    entry = timer_manager.create_timer(120, "test countdown")
    assert entry.state == TimerState.RUNNING
    rem, t = timer_manager.get_remaining(entry.timer_id)
    assert rem is not None
    assert 115.0 <= rem <= 120.0

    # Cancel
    timer_manager.cancel_timer(entry.timer_id)
    assert entry.state == TimerState.CANCELLED


@pytest.mark.asyncio
async def test_timer_status_intent_returns_countdown_not_clock():
    signals = FridaySignals()
    brain = FridayBrain(signals, None)

    # 1. Initialize a 15-minute timer
    init_res = await brain.execute_smart_skill("set timer for 15 minutes")
    assert init_res is not None
    assert "Timer initialized" in init_res

    # 2. Query timer status
    status_res = await brain.execute_smart_skill("how much time is left on my timer?")
    assert status_res is not None

    # Must return countdown
    assert "remaining on your timer" in status_res
    assert "14 minute" in status_res or "15 minute" in status_res

    # Must NOT return current clock time
    curr_hour = datetime.now().strftime("%I")
    curr_minute = datetime.now().strftime("%M")
    # Verify clock sentence structure is absent
    assert "The current time is" not in status_res
    assert "It is currently" not in status_res

    # 3. Clean up timers
    brain.timer_mgr.cancel_timer()
