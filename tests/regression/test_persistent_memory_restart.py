"""
REGRESSION TEST: Persistent Memory Across Restarts (Sections 4 & 5)
Root Cause: FridayBrain was disconnected from SQLite MemoryStore; preferences were
stored only in ephemeral session state and lost upon restart.
Fix Verification:
1. 'remember that my favorite color is orange' commits to SQLite memory.db.
2. Full process / brain restart preserves stored preference in SQLite.
3. Fresh brain instance correctly recalls 'orange'.
4. 'forget my favorite color' deletes the preference from SQLite.
5. Postcondition verification confirms SQLite row removal.
"""

import pytest
from friday_ui.core.engine import FridayBrain, FridaySignals
from friday_core.memory.manager import PersistentMemoryManager
from friday_core.memory.store import memory_store


def test_sqlite_memory_persistence_direct():
    """Verify PersistentMemoryManager commits and persists across fresh manager instances."""
    mgr1 = PersistentMemoryManager(store=memory_store)
    mgr1.set_preference("qa_test_city", "San Francisco", confirmed=True)

    # Simulate restart by creating fresh manager connected to same SQLite store
    mgr2 = PersistentMemoryManager(store=memory_store)
    val = mgr2.get_preference("qa_test_city")
    assert val == "San Francisco"

    # Cleanup
    mgr2.delete_preference("qa_test_city")
    assert mgr2.get_preference("qa_test_city") is None


@pytest.mark.asyncio
async def test_persistent_memory_brain_restart_cycle():
    signals1 = FridaySignals()
    brain1 = FridayBrain(signals1, None)

    # 1. Store preference
    store_res = await brain1.execute_smart_skill("remember that my favorite color is orange")
    assert store_res is not None
    assert "recorded that your favorite color is orange" in store_res

    # 2. Simulate complete application restart (destroy brain1, construct fresh brain2)
    del brain1
    signals2 = FridaySignals()
    brain2 = FridayBrain(signals2, None)

    # 3. Recall preference from fresh brain
    recall_res = await brain2.execute_smart_skill("what is my favorite color?")
    assert recall_res is not None
    assert "orange" in recall_res

    # 4. Forget preference
    forget_res = await brain2.execute_smart_skill("forget my favorite color")
    assert forget_res is not None
    assert "deleted your favorite color" in forget_res

    # 5. Verify gone from fresh brain3
    del brain2
    signals3 = FridaySignals()
    brain3 = FridayBrain(signals3, None)
    post_res = await brain3.execute_smart_skill("what is my favorite color?")
    assert "orange" not in (post_res or "")
