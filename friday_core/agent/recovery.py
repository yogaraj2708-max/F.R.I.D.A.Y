"""
F.R.I.D.A.Y. 3.0 — Crash Recovery & Task Resume Engine
Restores missions interrupted by crash or unexpected termination.
Re-verifies completed steps without repeating side effects, identifies first incomplete step,
and safely completes the mission DAG.
"""

from typing import List, Optional, Any
import logging
from friday_core.agent.mission_store import MissionState, MissionStatus, mission_store
from friday_core.agent.executor import PEOVExecutor
from friday_core.skills.registry import skill_registry

logger = logging.getLogger("FRIDAY.Recovery")


class CrashRecoveryManager:
    """
    Manages crash detection, state reconstruction, and non-blind task resumption.
    """
    def __init__(self, store=None, executor=None, registry=None):
        self.store = store or mission_store
        self.registry = registry or skill_registry
        self.executor = executor or PEOVExecutor(registry=self.registry, store=self.store)

    def find_interrupted_missions(self) -> List[MissionState]:
        """Query persistent store for tasks left in RUNNING or PAUSED states."""
        return self.store.get_incomplete_missions()

    def resume_mission(self, mission_id: str, context: Any = None) -> Optional[MissionState]:
        """
        Safely resume an interrupted mission from its first incomplete step.
        """
        mission = self.store.get_mission(mission_id)
        if not mission:
            logger.error(f"Cannot resume mission '{mission_id}': record not found.")
            return None

        if mission.status == MissionStatus.COMPLETED:
            logger.info(f"Mission '{mission_id}' is already COMPLETED. No resume needed.")
            return mission

        # 1. Identify first incomplete step
        first_incomplete = mission.current_step
        logger.info(
            f"Restoring mission '{mission_id}' (Goal: '{mission.goal}'). "
            f"Resuming from step {first_incomplete + 1}/{len(mission.steps)}"
        )

        # 2. Idempotency Check on already completed steps
        for i in range(first_incomplete):
            prior_step = mission.steps[i]
            skill = self.registry.get(prior_step.tool_id)
            if skill:
                # Re-observe to ensure prior side effects are still intact
                obs = skill.observe(prior_step.idempotency_key or prior_step.step_id, prior_step.params)
                ver = skill.verify(obs, prior_step.params)
                if not ver.verified:
                    logger.warning(
                        f"Prior completed step '{prior_step.step_id}' failed postcondition verification during recovery. "
                        f"Must re-execute from step {i}."
                    )
                    mission.current_step = i
                    break

        # 3. Resume execution from current_step
        return self.executor.execute_mission(mission, context=context)

    def recover_all(self, context: Any = None) -> List[MissionState]:
        """Automatically scans and resumes all interrupted missions on startup."""
        incomplete = self.find_interrupted_missions()
        recovered = []
        for m in incomplete:
            res = self.resume_mission(m.mission_id, context=context)
            if res:
                recovered.append(res)
        return recovered
