"""
Tests for F.R.I.D.A.Y. 3.0 — Phase 12: Task Persistence, Resume & Crash Recovery
Validates:
1. Complete crash recovery lifecycle:
   - Create mission with multiple side-effecting steps
   - Execute first N steps
   - Simulate unexpected process termination (close database/context)
   - Relaunch (open fresh MissionStore from disk)
   - Restore task from persistent SQLite ledger
   - Identify first incomplete step
   - Re-verify prior completed steps without repeating side-effects
   - Safely resume execution and reach COMPLETED state.
2. Broken side-effect detection: if a previously completed step's postcondition fails upon relaunch
   (e.g., file deleted during downtime), recovery automatically rolls back to that step.
3. Idempotency key preservation across crash restarts.
4. Checkpoint state persistence and reload.
"""

import os
import tempfile
import unittest
from typing import Dict, Any

from pydantic import BaseModel
from friday_core.agent.mission_store import (
    MissionStore,
    MissionState,
    MissionStatus,
    MissionStep
)
from friday_core.skills.base import (
    BaseSkill,
    RiskLevel,
    ObservationResult,
    VerificationResult
)
from friday_core.skills.registry import SkillRegistry
from friday_core.agent.executor import PEOVExecutor
from friday_core.agent.recovery import CrashRecoveryManager


class StepTrackerParams(BaseModel):
    step_num: int
    payload: str


class StepTrackerSkill(BaseSkill):
    """Verifiable mock skill that tracks executions and side effects."""
    tool_id = "step_tracker"
    tool_version = "1.0.0"
    description = "Tracks step executions for crash recovery testing"
    input_schema = StepTrackerParams
    risk_level = RiskLevel.SAFE

    def __init__(self, disk_log_path: str):
        super().__init__()
        self.disk_log_path = disk_log_path

    def execute(self, params: Dict[str, Any], operation_id: str) -> Any:
        step_num = params["step_num"]
        payload = params["payload"]
        # Append to persistent disk log as simulated side effect
        with open(self.disk_log_path, "a", encoding="utf-8") as f:
            f.write(f"EXEC:{step_num}:{payload}\n")
        return {"step": step_num, "status": "executed"}

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        step_num = params.get("step_num", -1) if params else -1
        # Check if side effect is in disk log
        found = False
        if os.path.exists(self.disk_log_path):
            with open(self.disk_log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                found = any(f"EXEC:{step_num}:" in line for line in lines)
        return ObservationResult(observed_state={"recorded_on_disk": found, "step": step_num})

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        is_recorded = observation.observed_state.get("recorded_on_disk", False)
        return VerificationResult(
            verified=is_recorded,
            postcondition_met=is_recorded,
            message="Step verified in disk log" if is_recorded else "Step missing from disk log"
        )


class TestTaskPersistenceAndRecovery(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "missions.db")
        self.disk_log = os.path.join(self.temp_dir, "side_effects.log")

        self.registry = SkillRegistry()
        self.tracker_skill = StepTrackerSkill(disk_log_path=self.disk_log)
        self.registry.register(self.tracker_skill)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_unexpected_crash_and_safe_resume(self):
        """
        Scenario:
        1. Create mission with 4 steps
        2. Execute step 1 and step 2
        3. Simulate unexpected crash
        4. Re-open database fresh from disk
        5. Restore task and resume
        6. Verify step 1 and 2 were NOT repeated
        7. Verify step 3 and 4 were executed
        8. Verify final mission status is COMPLETED
        """
        # Session 1: Before Crash
        store1 = MissionStore(db_path=self.db_path)
        mission = MissionState(
            mission_id="m-crash-101",
            goal="Deploy cluster update",
            status=MissionStatus.PENDING,
            current_step=0,
            steps=[
                MissionStep(step_id="s1", tool_id="step_tracker", params={"step_num": 1, "payload": "init"}),
                MissionStep(step_id="s2", tool_id="step_tracker", params={"step_num": 2, "payload": "backup"}),
                MissionStep(step_id="s3", tool_id="step_tracker", params={"step_num": 3, "payload": "migrate"}),
                MissionStep(step_id="s4", tool_id="step_tracker", params={"step_num": 4, "payload": "cleanup"})
            ]
        )
        store1.save_mission(mission)

        # Execute only first 2 steps manually to simulate partial progress before crash
        for idx in range(2):
            step = mission.steps[idx]
            res = self.registry.execute_skill(step.tool_id, step.params, operation_id=step.step_id)
            self.assertTrue(res.success)
            step.status = "COMPLETED"
            store1.checkpoint_step(
                mission_id=mission.mission_id,
                step_index=idx,
                step_id=step.step_id,
                output=res.data,
                verification=res.verification.model_dump() if res.verification else {},
                checkpoint_data={"last_verified_step": step.step_id}
            )

        # Mark mission as RUNNING at step 2 when crash happens
        mission.status = MissionStatus.RUNNING
        mission.current_step = 2
        store1.save_mission(mission)

        # Simulate unexpected crash: close connections, drop in-memory objects
        store1.close()
        del store1

        # Session 2: After Crash & Relaunch
        store2 = MissionStore(db_path=self.db_path)
        recovery_mgr = CrashRecoveryManager(store=store2, registry=self.registry)

        # 1. Detect interrupted missions
        interrupted = recovery_mgr.find_interrupted_missions()
        self.assertEqual(len(interrupted), 1)
        self.assertEqual(interrupted[0].mission_id, "m-crash-101")
        self.assertEqual(interrupted[0].current_step, 2)

        # 2. Resume mission safely
        completed_mission = recovery_mgr.resume_mission("m-crash-101")
        self.assertIsNotNone(completed_mission)
        self.assertEqual(completed_mission.status, MissionStatus.COMPLETED)
        self.assertEqual(completed_mission.current_step, 4)

        # 3. Verify side effect log on disk:
        # Steps 1 and 2 must only appear ONCE (not repeated), followed by 3 and 4
        with open(self.disk_log, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines()]

        self.assertEqual(lines, [
            "EXEC:1:init",
            "EXEC:2:backup",
            "EXEC:3:migrate",
            "EXEC:4:cleanup"
        ])

        store2.close()

    def test_broken_side_effect_triggers_reexecution(self):
        """
        Validates that if a previously completed step's side effect is undone during downtime,
        recovery detects the postcondition failure and safely re-executes that step.
        """
        store = MissionStore(db_path=self.db_path)
        mission = MissionState(
            mission_id="m-tamper-202",
            goal="Build artifact",
            status=MissionStatus.RUNNING,
            current_step=1,
            steps=[
                MissionStep(step_id="s1", tool_id="step_tracker", params={"step_num": 1, "payload": "compile"}),
                MissionStep(step_id="s2", tool_id="step_tracker", params={"step_num": 2, "payload": "package"})
            ]
        )
        store.save_mission(mission)

        # Step 1 was supposedly completed, but disk log is EMPTY (side effect missing)
        self.assertFalse(os.path.exists(self.disk_log))

        recovery_mgr = CrashRecoveryManager(store=store, registry=self.registry)
        completed = recovery_mgr.resume_mission("m-tamper-202")

        self.assertIsNotNone(completed)
        self.assertEqual(completed.status, MissionStatus.COMPLETED)

        # Both steps must now be present in disk log
        with open(self.disk_log, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines()]

        self.assertEqual(lines, [
            "EXEC:1:compile",
            "EXEC:2:package"
        ])

        store.close()

    def test_recover_all_multiple_interrupted_missions(self):
        """Validates that recover_all() scans and recovers all interrupted missions."""
        store = MissionStore(db_path=self.db_path)
        m1 = MissionState(
            mission_id="m-batch-1",
            goal="Task A",
            status=MissionStatus.RUNNING,
            current_step=0,
            steps=[MissionStep(step_id="s1", tool_id="step_tracker", params={"step_num": 10, "payload": "A"})]
        )
        m2 = MissionState(
            mission_id="m-batch-2",
            goal="Task B",
            status=MissionStatus.PAUSED,
            current_step=0,
            steps=[MissionStep(step_id="s1", tool_id="step_tracker", params={"step_num": 20, "payload": "B"})]
        )
        store.save_mission(m1)
        store.save_mission(m2)

        recovery_mgr = CrashRecoveryManager(store=store, registry=self.registry)
        recovered = recovery_mgr.recover_all()
        self.assertEqual(len(recovered), 2)
        self.assertTrue(all(m.status == MissionStatus.COMPLETED for m in recovered))
        store.close()

    def test_already_completed_mission_is_not_reexecuted(self):
        """Validates that completed missions are safely returned without executing any steps."""
        store = MissionStore(db_path=self.db_path)
        m = MissionState(
            mission_id="m-done-303",
            goal="Already Finished",
            status=MissionStatus.COMPLETED,
            current_step=1,
            steps=[MissionStep(step_id="s1", tool_id="step_tracker", params={"step_num": 99, "payload": "done"})]
        )
        store.save_mission(m)

        recovery_mgr = CrashRecoveryManager(store=store, registry=self.registry)
        res = recovery_mgr.resume_mission("m-done-303")
        self.assertEqual(res.status, MissionStatus.COMPLETED)
        # Disk log should not have step 99
        self.assertFalse(os.path.exists(self.disk_log))
        store.close()


if __name__ == "__main__":
    unittest.main()
