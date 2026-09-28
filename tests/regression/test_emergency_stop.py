"""
Regression Test: F.R.I.D.A.Y. 3.0 Global Emergency Stop Subsystem
Verifies instant cancellation across PEOV executor, state machine, child processes, and handlers.
"""

import subprocess
import sys
import time
import pytest
from friday_core.agent.emergency_stop import EmergencyStopManager
from friday_core.agent.state_machine import AgentStateMachine, AgentState
from friday_core.agent.executor import PEOVExecutor
from friday_core.agent.mission_store import MissionState, MissionStep, MissionStatus, MissionStore
import tempfile
from pathlib import Path


def test_emergency_stop_handlers_and_state():
    mgr = EmergencyStopManager()
    assert not mgr.is_stopped()

    handler_calls = []
    mgr.register_handler("tts", lambda: handler_calls.append("tts_stopped"))
    mgr.register_handler("stt", lambda: handler_calls.append("stt_stopped"))

    result = mgr.trigger_stop(source="HOTKEY_ESC")

    assert mgr.is_stopped()
    assert result["status"] == "STOPPED"
    assert result["source"] == "HOTKEY_ESC"
    assert "tts" in result["handlers_executed"]
    assert "stt" in result["handlers_executed"]
    assert handler_calls == ["tts_stopped", "stt_stopped"]

    # Reset
    mgr.reset()
    assert not mgr.is_stopped()


def test_emergency_stop_terminates_child_process():
    mgr = EmergencyStopManager()

    # Launch a real background sleeper process
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    pid = proc.pid
    mgr.track_pid(pid)

    assert proc.poll() is None  # Process is running

    result = mgr.trigger_stop(source="VOICE_STOP")
    assert pid in result["killed_pids"]

    # Wait briefly for OS to signal termination
    time.sleep(0.3)
    assert proc.poll() is not None  # Process has terminated
    mgr.reset()


def test_peov_executor_emergency_stop_halts_mission():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_missions.db"
        store = MissionStore(str(db_path))
        sm = AgentStateMachine()
        stop_mgr = EmergencyStopManager()

        executor = PEOVExecutor(
            store=store,
            stop_manager=stop_mgr,
            state_machine=sm
        )

        mission = MissionState(
            mission_id="mission_stop_test",
            goal="Test emergency stop halting execution",
            steps=[
                MissionStep(
                    step_id="step_1",
                    tool_id="system_status",
                    params={},
                    expected_outcome="Status reported"
                ),
                MissionStep(
                    step_id="step_2",
                    tool_id="system_status",
                    params={},
                    expected_outcome="Status reported second time"
                )
            ]
        )

        # Trigger emergency stop BEFORE or DURING execution
        stop_mgr.trigger_stop(source="CTRL_SHIFT_X")

        # Execute mission
        res = executor.execute_mission(mission)

        # Mission must be CANCELLED and zero steps completed
        assert res.status == MissionStatus.CANCELLED
        assert res.current_step == 0
        assert sm.current_state == AgentState.CANCELLED

        # Verify DB persisted status
        persisted = store.get_mission("mission_stop_test")
        assert persisted.status == MissionStatus.CANCELLED
