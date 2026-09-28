"""
Regression Test for BUG-002: Compound Application and Action Commands.
Verifies that compound directives such as 'open note pad and type FRIDAY IS TESTING CONTEXT',
'open calculator and calculate 25 * 4', 'open chrome and search for Python',
and 'open file explorer and navigate to Downloads' are properly decomposed into
sequential PEOV DAG missions and executed with closed-loop verification, rather than
being misinterpreted as monolithic application names.
"""

import pytest
import asyncio
from friday_ui.core.engine import FridayBrain, FridaySignals, FridayVoiceEngine
from friday_core.agent.compound import compound_parser
from friday_core.agent.planner import PEOVPlanner
from friday_core.agent.mission_store import MissionStatus

def test_compound_parser_decomposition():
    """Unit test for generalized compound intent parser."""
    test_cases = [
        ("open note pad and type FRIDAY IS TESTING CONTEXT", ["open_app", "ui_type_text"]),
        ("open notepad and type hello", ["open_app", "ui_type_text"]),
        ("open calculator and calculate 25 * 4", ["open_app", "calculate"]),
        ("open chrome and search for Python", ["open_app", "app_search"]),
        ("open file explorer and navigate to Downloads", ["open_app", "app_navigate"]),
        ("open Notepad, type hello, and save it as test.txt", ["open_app", "ui_type_text", "save_file"])
    ]
    for text, expected_actions in test_cases:
        plan = compound_parser.parse(text)
        assert plan is not None, f"Failed to parse compound command: '{text}'"
        actions = [s.action for s in plan.steps]
        assert actions == expected_actions, f"Expected {expected_actions}, got {actions} for '{text}'"

def test_peov_planner_compound_mission():
    """Verify DAG mission creation and step dependency wiring."""
    planner = PEOVPlanner()
    mission = planner.plan_compound_directive("open note pad and type FRIDAY IS TESTING CONTEXT")
    assert mission is not None
    assert len(mission.steps) == 2
    assert mission.steps[0].tool_id == "app_launcher"
    assert mission.steps[0].params["app_name"] == "note pad"
    assert mission.steps[1].tool_id == "ui_type_text"
    assert mission.steps[1].params["text"] == "FRIDAY IS TESTING CONTEXT"
    assert mission.steps[1].dependencies == [mission.steps[0].step_id]

@pytest.mark.asyncio
async def test_compound_runtime_execution():
    """Runtime test executing compound missions through FridayBrain."""
    signals = FridaySignals()
    tts = FridayVoiceEngine(signals)
    brain = FridayBrain(signals, tts)
    
    # 1. Calculator compound
    res_calc = await brain.execute_smart_skill("open calculator and calculate 25 * 4")
    assert res_calc is not None
    assert "Successfully" in res_calc
    assert "calculator" in res_calc.lower()
    
    # 2. Explorer navigation compound
    res_nav = await brain.execute_smart_skill("open file explorer and navigate to Downloads")
    assert res_nav is not None
    assert "Successfully" in res_nav
    assert "downloads" in res_nav.lower()
    
    # 3. Notepad and type compound (BUG-002 exact reproducer)
    res_notepad = await brain.execute_smart_skill("open note pad and type FRIDAY IS TESTING CONTEXT")
    assert res_notepad is not None
    assert "Successfully" in res_notepad
    assert "FRIDAY IS TESTING CONTEXT" in res_notepad
