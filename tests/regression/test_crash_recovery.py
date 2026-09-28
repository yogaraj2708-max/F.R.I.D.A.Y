"""
Regression Test: F.R.I.D.A.Y. 3.0 PEOV Crash Recovery & Checkpoint Resumption
Verifies:
1. Persistent checkpointing of individual mission steps in SQLite.
2. Discovery of interrupted/incomplete missions on restart.
3. Resumption of execution from the exact checkpoint without re-running earlier completed steps.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from friday_core.agent.mission_store import MissionStore, MissionState, MissionStep, MissionStatus
from friday_core.agent.executor import PEOVExecutor
from friday_core.skills.registry import SkillRegistry
from friday_core.skills.base import SkillResult, VerificationResult


def test_crash_recovery_checkpoint_resumption():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_recovery.db"
        store = MissionStore(str(db_path))

        # Setup mock skill registry
        registry = SkillRegistry()
        executed_steps = []

        def mock_step_exec(tool_id, params, context=None, operation_id=None):
            executed_steps.append((tool_id, operation_id))
            return SkillResult(
                tool_id=tool_id,
                operation_id=operation_id or "op_1",
                success=True,
                data={"output_of": tool_id},
                verification=VerificationResult(
                    verified=True,
                    postcondition_met=True,
                    message=f"Verified {tool_id}"
                )
            )

        registry.execute_skill = MagicMock(side_effect=mock_step_exec)

        # Create 3-step mission
        mission = MissionState(
            mission_id="mission_crash_sim_01",
            goal="Test crash and resume across 3 steps",
            steps=[
                MissionStep(step_id="step_a", tool_id="tool_alpha", params={}),
                MissionStep(step_id="step_b", tool_id="tool_beta", params={}, dependencies=["step_a"]),
                MissionStep(step_id="step_c", tool_id="tool_gamma", params={}, dependencies=["step_b"]),
            ]
        )
        store.save_mission(mission)

        # Step 1 executes successfully, and then system crashes
        # Simulate step_a completion & checkpointing
        store.checkpoint_step(
            mission_id="mission_crash_sim_01",
            step_index=0,
            step_id="step_a",
            output={"result": "alpha_done"},
            verification={"status": "passed"},
            checkpoint_data={"marker": "after_alpha"}
        )
        # Mark mission as RUNNING (as it was when crash happened)
        store.update_status("mission_crash_sim_01", MissionStatus.RUNNING)

        # --- SIMULATE PROCESS RESTART ---
        # Create fresh store and executor instances pointing to the existing SQLite DB
        restarted_store = MissionStore(str(db_path))
        incomplete = restarted_store.get_incomplete_missions()
        assert len(incomplete) == 1
        recovered_mission = incomplete[0]

        assert recovered_mission.mission_id == "mission_crash_sim_01"
        assert recovered_mission.current_step == 1
        assert recovered_mission.steps[0].status == "COMPLETED"
        assert recovered_mission.steps[1].status == "PENDING"
        assert recovered_mission.steps[2].status == "PENDING"
        assert "step_a" in recovered_mission.outputs

        # Resume mission execution using PEOVExecutor
        executor = PEOVExecutor(registry=registry, store=restarted_store)
        final_state = executor.execute_mission(recovered_mission)

        # Assert mission completed
        assert final_state.status == MissionStatus.COMPLETED
        assert final_state.current_step == 3

        # Assert step_a was NOT re-executed, only step_b and step_c
        tool_ids_executed = [item[0] for item in executed_steps]
        assert "tool_alpha" not in tool_ids_executed
        assert tool_ids_executed == ["tool_beta", "tool_gamma"]

        # Verify persisted state on disk
        persisted = restarted_store.get_mission("mission_crash_sim_01")
        assert persisted.status == MissionStatus.COMPLETED
        assert "step_a" in persisted.outputs
        assert "step_b" in persisted.outputs
        assert "step_c" in persisted.outputs
