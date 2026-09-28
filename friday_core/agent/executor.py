"""
F.R.I.D.A.Y. 3.0 — PEOV Mission Executor
Closed-loop execution engine with DAG dependency resolution, emergency stop interception,
and persistent step checkpointing.
"""

from typing import Any, Dict, Optional
import logging
from friday_core.agent.mission_store import MissionState, MissionStatus, mission_store
from friday_core.agent.emergency_stop import emergency_stop
from friday_core.agent.state_machine import AgentStateMachine, AgentState
from friday_core.skills.registry import skill_registry

logger = logging.getLogger("FRIDAY.Executor")


class PEOVExecutor:
    """
    Closed-loop executor for PEOV mission graphs.
    """
    def __init__(
        self,
        registry=None,
        store=None,
        stop_manager=None,
        state_machine=None
    ):
        self.registry = registry or skill_registry
        self.store = store or mission_store
        self.stop_manager = stop_manager or emergency_stop
        self.state_machine = state_machine or AgentStateMachine()

    def _resolve_step_params(self, params: Dict[str, Any], outputs: Dict[str, Any]) -> Dict[str, Any]:
        """Resolves dynamic parameter references from outputs of preceding DAG steps."""
        if not params or not outputs:
            return dict(params)
        resolved = {}
        for k, v in params.items():
            if isinstance(v, str) and v.startswith("$"):
                ref = v[1:].strip()
                val = None
                if "." in ref:
                    step_ref, field_ref = ref.split(".", 1)
                    if step_ref in outputs and isinstance(outputs[step_ref], dict):
                        val = outputs[step_ref].get(field_ref)
                    else:
                        for s_id, s_out in outputs.items():
                            if step_ref in s_id and isinstance(s_out, dict):
                                val = s_out.get(field_ref)
                                if val is not None:
                                    break
                else:
                    for s_id, s_out in outputs.items():
                        if isinstance(s_out, dict) and ref in s_out:
                            val = s_out[ref]
                            break
                resolved[k] = val if val is not None else v
            else:
                resolved[k] = v
        return resolved

    def execute_mission(self, mission: MissionState, context: Any = None) -> MissionState:
        """
        Executes a planned mission graph step-by-step with state verification and checkpointing.
        """
        # 1. State Machine Transition
        try:
            self.state_machine.transition_to(AgentState.EXECUTING, f"Starting mission {mission.mission_id}")
        except Exception as ex:
            logger.warning(f"State transition warning: {ex}")

        mission.status = MissionStatus.RUNNING
        self.store.save_mission(mission)

        # 2. Sequential / DAG Step Iteration starting from current_step
        while mission.current_step < len(mission.steps):
            # Check Emergency Stop Interception
            if self.stop_manager.is_stopped():
                logger.warning(f"🛑 [Executor] Emergency stop active. Aborting mission {mission.mission_id}")
                mission.status = MissionStatus.CANCELLED
                self.store.update_status(mission.mission_id, MissionStatus.CANCELLED, "Emergency stop triggered.")
                try:
                    self.state_machine.transition_to(AgentState.CANCELLED, "Emergency stop triggered")
                except Exception:
                    pass
                return mission

            idx = mission.current_step
            step = mission.steps[idx]
            step.status = "RUNNING"
            self.store.save_mission(mission)

            # Check Prerequisites / Dependencies
            deps_met = True
            for dep in step.dependencies:
                dep_step = next((s for s in mission.steps if s.step_id == dep), None)
                if not dep_step or dep_step.status != "COMPLETED":
                    deps_met = False
                    break

            if not deps_met:
                err_msg = f"Dependencies not satisfied for step '{step.step_id}'."
                logger.error(f"[{mission.mission_id}] {err_msg}")
                mission.status = MissionStatus.FAILED
                mission.errors.append(err_msg)
                step.status = "FAILED"
                self.store.update_status(mission.mission_id, MissionStatus.FAILED, err_msg)
                try:
                    self.state_machine.transition_to(AgentState.ERROR, err_msg)
                except Exception:
                    pass
                return mission

            # Execute Step via Pluggable Skill Framework
            op_id = step.idempotency_key or f"{mission.mission_id}-{step.step_id}"
            logger.info(f"[{mission.mission_id}] Executing step {idx + 1}/{len(mission.steps)}: '{step.step_id}' ({step.tool_id})")

            effective_params = self._resolve_step_params(step.params, mission.outputs)

            skill_res = self.registry.execute_skill(
                tool_id=step.tool_id,
                params=effective_params,
                context=context,
                operation_id=op_id
            )

            if not skill_res.success:
                err_msg = skill_res.error or "Step execution failed."
                logger.error(f"[{mission.mission_id}] Step '{step.step_id}' failed: {err_msg}")
                step.status = "FAILED"
                mission.status = MissionStatus.FAILED
                mission.errors.append(err_msg)
                self.store.update_status(mission.mission_id, MissionStatus.FAILED, err_msg)
                try:
                    self.state_machine.transition_to(AgentState.ERROR, err_msg)
                except Exception:
                    pass
                return mission

            # Step Verified & Checkpointed
            step.status = "COMPLETED"
            self.store.checkpoint_step(
                mission_id=mission.mission_id,
                step_index=idx,
                step_id=step.step_id,
                output=skill_res.data,
                verification=skill_res.verification.model_dump() if skill_res.verification else {},
                checkpoint_data={"last_verified_step": step.step_id}
            )

            # Advance in-memory state
            mission.outputs[step.step_id] = skill_res.data
            if skill_res.verification:
                mission.verification[step.step_id] = skill_res.verification.model_dump()
            mission.current_step += 1

        # All steps completed successfully
        mission.status = MissionStatus.COMPLETED
        self.store.update_status(mission.mission_id, MissionStatus.COMPLETED)
        try:
            self.state_machine.transition_to(AgentState.IDLE, f"Mission {mission.mission_id} completed successfully")
        except Exception:
            pass

        logger.info(f"✅ Mission {mission.mission_id} completed and verified.")
        return mission
