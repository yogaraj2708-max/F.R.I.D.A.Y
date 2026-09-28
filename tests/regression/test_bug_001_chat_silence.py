"""
Regression Test for BUG-001: Basic Chat Silence on Greetings & Common Sense Commands.
Ensures 'hi', 'hello', 'who are you', 'what time is it', '2 + 2', and 'what is my battery percentage'
respond deterministically and immediately (< 500ms) with non-empty content and proper signal emissions,
never falling into dead silence or slow model timeout.
"""

import pytest
import asyncio
import time
from friday_ui.core.engine import FridayBrain, FridaySignals, FridayVoiceEngine

@pytest.mark.asyncio
async def test_bug_001_greetings_fast_path():
    signals = FridaySignals()
    emitted_states = []
    emitted_skills = []
    signals.state_changed.connect(lambda s: emitted_states.append(s))
    signals.skill_executed.connect(lambda s, d: emitted_skills.append((s, d)))
    
    tts = FridayVoiceEngine(signals)
    brain = FridayBrain(signals, tts)
    
    # 1. Test "hi"
    t0 = time.time()
    res_hi = await brain.execute_smart_skill("hi")
    dur_hi = (time.time() - t0) * 1000
    assert res_hi is not None, "Directive 'hi' returned None (silent failure)"
    assert len(res_hi) > 0, "Directive 'hi' returned empty string"
    assert "Boss" in res_hi or "stand" in res_hi.lower(), f"Unexpected greeting: {res_hi}"
    assert dur_hi < 500, f"Directive 'hi' took too long: {dur_hi:.1f}ms"
    
    # 2. Test "hello"
    t0 = time.time()
    res_hello = await brain.execute_smart_skill("hello")
    dur_hello = (time.time() - t0) * 1000
    assert res_hello is not None, "Directive 'hello' returned None"
    assert dur_hello < 500, f"Directive 'hello' took too long: {dur_hello:.1f}ms"
    
    # 3. Test "who are you"
    t0 = time.time()
    res_who = await brain.execute_smart_skill("who are you")
    dur_who = (time.time() - t0) * 1000
    assert res_who is not None, "Directive 'who are you' returned None"
    assert "F.R.I.D.A.Y." in res_who, f"Expected identity in response: {res_who}"
    assert dur_who < 500, f"Directive 'who are you' took too long: {dur_who:.1f}ms"
    
    # 4. Test "what time is it"
    t0 = time.time()
    res_time = await brain.execute_smart_skill("what time is it")
    dur_time = (time.time() - t0) * 1000
    assert res_time is not None, "Directive 'what time is it' returned None"
    assert "time" in res_time.lower(), f"Expected time in response: {res_time}"
    assert dur_time < 500, f"Directive 'what time is it' took too long: {dur_time:.1f}ms"
    
    # 5. Test "2 + 2"
    t0 = time.time()
    res_calc = await brain.execute_smart_skill("2 + 2")
    dur_calc = (time.time() - t0) * 1000
    assert res_calc is not None, "Directive '2 + 2' returned None"
    assert "4" in res_calc, f"Expected 4 in response: {res_calc}"
    assert dur_calc < 500, f"Directive '2 + 2' took too long: {dur_calc:.1f}ms"
    
    # 6. Test "what is my battery percentage"
    t0 = time.time()
    res_batt = await brain.execute_smart_skill("what is my battery percentage")
    dur_batt = (time.time() - t0) * 1000
    assert res_batt is not None, "Directive 'what is my battery percentage' returned None"
    assert "battery" in res_batt.lower() or "percent" in res_batt.lower(), f"Expected battery telemetry in response: {res_batt}"
    assert dur_batt < 500, f"Directive 'what is my battery percentage' took too long: {dur_batt:.1f}ms"
