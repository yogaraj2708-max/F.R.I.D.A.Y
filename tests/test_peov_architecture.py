"""
Tests for F.R.I.D.A.Y. 3.0 PEOV Architecture, Mission State Machine, and Crash Recovery
Verifies:
1. State Machine transitions and rejection of invalid/illegal transitions.
2. Global Emergency Stop propagation across handlers and executor abort.
3. Persistent SQLite Mission State storage and retrieval.
4. 8-Stage Task Crash & Safe Resumption testing (Directive 10).
5. DAG dependency resolution and step sequencing.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

from friday_core.agent.state_machine import AgentState, AgentStateMachine, InvalidStateTransitionError
from friday_core.agent.emergency_stop import EmergencyStopManager
from friday_core.agent.mission_store import MissionStore, MissionState, MissionStep, MissionStatus
from friday_core.agent.planner import PEOVPlanner
from friday_core.agent.executor import PEOVExecutor
from friday_core.agent.recovery import CrashRecoveryManager
from friday_core.skills.registry import SkillRegistry
from tests.test_pluggable_skills import MockCreateFileSkill
from friday_core.skills.builtins.telemetry import SystemTelemetrySkill


class TestPEOVArchitecture(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="friday_peov_test_")
        self.db_path = os.path.join(self.temp_dir, "test_missions.db")
        self.store = MissionStore(self.db_path)
        self.stop_manager = EmergencyStopManager()
        self.state_machine = AgentStateMachine()

        self.registry = SkillRegistry()
        self.file_skill = MockCreateFileSkill(self.temp_dir)
        self.telemetry_skill = SystemTelemetrySkill()
        self.registry.register(self.file_skill)
        self.registry.register(self.telemetry_skill)

        self.planner = PEOVPlanner(registry=self.registry)
        self.executor = PEOVExecutor(
            registry=self.registry,
            store=self.store,
            stop_manager=self.stop_manager,
            state_machine=self.state_machine
        )

    def tearDown(self):
        self.store.close()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. State Machine Testing (Directive 15)
    def test_state_machine_valid_transitions(self):
        """Test standard operational pipeline transitions."""
        sm = AgentStateMachine()
        self.assertEqual(sm.current_state, AgentState.IDLE)

        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.THINKING)
        sm.transition_to(AgentState.PLANNING)
        sm.transition_to(AgentState.EXECUTING)
        sm.transition_to(AgentState.VERIFYING)
        sm.transition_to(AgentState.IDLE)
        self.assertEqual(sm.current_state, AgentState.IDLE)

    def test_state_machine_rejects_invalid_transitions(self):
        """Test that illegal transitions raise InvalidStateTransitionError."""
        sm = AgentStateMachine()

        # CANCELLED -> COMPLETE is strictly forbidden
        sm.transition_to(AgentState.THINKING)
        sm.transition_to(AgentState.CANCELLED)
        with self.assertRaises(InvalidStateTransitionError):
            sm.transition_to(AgentState.EXECUTING)

        # WAITING_APPROVAL -> CANCELLED -> EXECUTING (Approve after Stop must be rejected)
        sm.reset()
        sm.transition_to(AgentState.PLANNING)
        sm.transition_to(AgentState.WAITING_APPROVAL)
        sm.transition_to(AgentState.CANCELLED)
        with self.assertRaises(InvalidStateTransitionError):
            sm.transition_to(AgentState.EXECUTING, reason="Late Approval")

    # 2. Global Emergency Stop (Directive 7)
    def test_emergency_stop_propagation_and_interception(self):
        """Emergency stop aborts execution and triggers registered subsystem handlers."""
        stop_mgr = EmergencyStopManager()
        tts_called = False
        stt_called = False

        def tts_abort():
            nonlocal tts_called
            tts_called = True

        def stt_flush():
            nonlocal stt_called
            stt_called = True

        stop_mgr.register_handler("tts", tts_abort)
        stop_mgr.register_handler("stt", stt_flush)

        # Trigger Stop
        res = stop_mgr.trigger_stop(source="ESC")
        self.assertTrue(stop_mgr.is_stopped())
        self.assertTrue(tts_called)
        self.assertTrue(stt_called)
        self.assertEqual(res["status"], "STOPPED")

        # Create mission and verify executor immediately cancels without running steps
        step = MissionStep(
            step_id="s1",
            tool_id="test_create_file",
            params={"filename": "should_not_exist.txt"}
        )
        mission = self.planner.create_mission("Test emergency stop", [step])

        exec_mgr = PEOVExecutor(
            registry=self.registry,
            store=self.store,
            stop_manager=stop_mgr
        )
        out_mission = exec_mgr.execute_mission(mission)
        self.assertEqual(out_mission.status, MissionStatus.CANCELLED)
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir, "should_not_exist.txt")))

    # 3. Persistent Mission State (Directive 6)
    def test_mission_persistence_sqlite(self):
        """Mission states, DAG steps, outputs, and checkpoints persist to SQLite."""
        step1 = MissionStep(step_id="step_1", tool_id="system_telemetry", params={"metrics": ["cpu"]})
        mission = self.planner.create_mission("Persist telemetry check", [step1])

        self.store.save_mission(mission)
        loaded = self.store.get_mission(mission.mission_id)

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.mission_id, mission.mission_id)
        self.assertEqual(loaded.goal, mission.goal)
        self.assertEqual(len(loaded.steps), 1)
        self.assertEqual(loaded.steps[0].tool_id, "system_telemetry")

        # Advance step checkpoint
        self.store.checkpoint_step(
            mission_id=mission.mission_id,
            step_index=0,
            step_id="step_1",
            output={"cpu_percent": 15.0},
            verification={"verified": True},
            checkpoint_data={"marker": "step_1_done"}
        )

        reloaded = self.store.get_mission(mission.mission_id)
        self.assertEqual(reloaded.current_step, 1)
        self.assertEqual(reloaded.checkpoint_state["marker"], "step_1_done")
        self.assertEqual(reloaded.outputs["step_1"]["cpu_percent"], 15.0)

    # 4. Crash Recovery & Safe Resumption (Directive 10)
    def test_task_crash_recovery_cycle(self):
        """
        Required 8-Stage Scenario:
        1. create mission
        2. execute step 1
        3. simulate sudden crash / termination mid-mission
        4. relaunch
        5. restore task from DB
        6. identify first incomplete step (step 2)
        7. resume safely without duplicating step 1
        8. verify final state
        """
        # 1. Create multi-step mission
        step1 = MissionStep(
            step_id="step_alpha",
            tool_id="test_create_file",
            params={"filename": "file_alpha.txt", "content": "Alpha Content"},
            idempotency_key="idemp-alpha"
        )
        step2 = MissionStep(
            step_id="step_beta",
            tool_id="test_create_file",
            params={"filename": "file_beta.txt", "content": "Beta Content"},
            idempotency_key="idemp-beta",
            dependencies=["step_alpha"]
        )
        step3 = MissionStep(
            step_id="step_gamma",
            tool_id="system_telemetry",
            params={"metrics": ["memory"]},
            dependencies=["step_beta"]
        )

        mission = self.planner.create_mission("Multi-step crash test", [step1, step2, step3])
        self.store.save_mission(mission)

        # 2. Execute Step 1 manually and checkpoint
        res_step1 = self.file_skill.run_lifecycle(step1.params, operation_id=step1.idempotency_key)
        self.assertTrue(res_step1.success)
        self.store.checkpoint_step(
            mission_id=mission.mission_id,
            step_index=0,
            step_id="step_alpha",
            output=res_step1.data,
            verification=res_step1.verification.model_dump()
        )
        self.store.update_status(mission.mission_id, MissionStatus.RUNNING)

        # Confirm step 1 executed once
        self.assertEqual(self.file_skill.execution_count, 1)
        self.assertTrue(os.path.isfile(os.path.join(self.temp_dir, "file_alpha.txt")))
        self.assertFalse(os.path.isfile(os.path.join(self.temp_dir, "file_beta.txt")))

        # 3. Simulate sudden crash: destroy in-memory executor & close DB
        self.store.close()

        # 4. Relaunch: Instantiate brand new store, recovery manager, and executor
        new_store = MissionStore(self.db_path)
        recovery_mgr = CrashRecoveryManager(
            store=new_store,
            registry=self.registry
        )

        # 5. Restore task from persistent store
        incomplete = recovery_mgr.find_interrupted_missions()
        self.assertEqual(len(incomplete), 1)
        self.assertEqual(incomplete[0].mission_id, mission.mission_id)

        # 6. Identify first incomplete step is step 2 (index 1)
        self.assertEqual(incomplete[0].current_step, 1)

        # 7. Resume safely
        resumed_mission = recovery_mgr.resume_mission(mission.mission_id)

        # 8. Verify final state
        self.assertIsNotNone(resumed_mission)
        self.assertEqual(resumed_mission.status, MissionStatus.COMPLETED)
        self.assertEqual(resumed_mission.current_step, 3)

        # Idempotency check: file_alpha was NOT re-executed (only file_beta was executed)
        self.assertEqual(self.file_skill.execution_count, 2)  # 1 for alpha, 1 for beta
        self.assertTrue(os.path.isfile(os.path.join(self.temp_dir, "file_alpha.txt")))
        self.assertTrue(os.path.isfile(os.path.join(self.temp_dir, "file_beta.txt")))
        self.assertIn("memory_percent", resumed_mission.outputs["step_gamma"])

        new_store.close()


if __name__ == "__main__":
    unittest.main()
