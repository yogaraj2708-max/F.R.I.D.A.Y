"""
F.R.I.D.A.Y. 3.0 — PEOV Mission Planner
Deconstructs goals into executable Directed Acyclic Graphs (DAG) of verified tool steps.
"""

from typing import Any, Dict, List, Optional
import uuid
import logging
from friday_core.agent.mission_store import MissionState, MissionStep, MissionStatus
from friday_core.skills.registry import skill_registry

logger = logging.getLogger("FRIDAY.Planner")


class PEOVPlanner:
    """
    Constructs structured DAG mission plans with dependency resolution and risk tagging.
    """
    def __init__(self, registry=None):
        self.registry = registry or skill_registry

    def create_mission(
        self,
        goal: str,
        steps: List[MissionStep],
        mission_id: Optional[str] = None
    ) -> MissionState:
        """
        Creates a structured, validated mission with topological dependencies.
        """
        m_id = mission_id or f"mission-{uuid.uuid4().hex[:8]}"

        # Compute dependency map
        dep_map: Dict[str, List[str]] = {}
        for s in steps:
            dep_map[s.step_id] = s.dependencies

        # Validate that referenced tools exist in registry
        for s in steps:
            skill = self.registry.get(s.tool_id)
            if skill:
                s.risk_level = skill.risk_level.value
                if not s.idempotency_key:
                    s.idempotency_key = f"{m_id}-{s.step_id}"

        mission = MissionState(
            mission_id=m_id,
            goal=goal,
            status=MissionStatus.PENDING,
            current_step=0,
            steps=steps,
            dependencies=dep_map
        )
        return mission

    def plan_organize_and_report(self, target_dir: str) -> MissionState:
        """Sample compound mission: organize folder then report system telemetry."""
        m_id = f"mission-{uuid.uuid4().hex[:8]}"
        step1 = MissionStep(
            step_id="step_organize",
            tool_id="file_organizer",
            params={"directory_path": target_dir, "dry_run": False},
            description=f"Organize files in {target_dir}",
            dependencies=[],
            risk_level="CAUTION",
            idempotency_key=f"{m_id}-organize"
        )
        step2 = MissionStep(
            step_id="step_telemetry",
            tool_id="system_telemetry",
            params={"metrics": ["disk", "memory"]},
            description="Inspect disk usage post-organization",
            dependencies=["step_organize"],
            risk_level="SAFE",
            idempotency_key=f"{m_id}-telemetry"
        )
        return self.create_mission(
            goal=f"Organize {target_dir} and verify remaining disk space",
            steps=[step1, step2],
            mission_id=m_id
        )

    def plan_compound_directive(self, command: str) -> Optional[MissionState]:
        """
        Decomposes a multi-stage user instruction into an executable PEOV mission graph.
        """
        from friday_core.agent.compound import compound_parser
        plan = compound_parser.parse(command)
        if not plan:
            return None

        m_id = f"mission-{uuid.uuid4().hex[:8]}"
        mission_steps: List[MissionStep] = []
        prev_step_id = None

        for idx, s in enumerate(plan.steps):
            step_id = f"step_{idx+1}_{s.action}"
            deps = [prev_step_id] if prev_step_id else []

            tool_id = s.action

            desc = f"Execute {s.action} on {s.target}"
            if s.action == "open_app":
                tool_id = "app_launcher"
                desc = f"Launch application '{s.params.get('app_name', s.target)}'"
            elif s.action == "ui_type_text":
                desc = f"Inject text '{s.params.get('text', '')}' into '{s.params.get('app_name', s.target)}'"
            elif s.action == "ui_key_press":
                desc = f"Press key '{s.params.get('key', '')}' in '{s.params.get('app_name', s.target)}'"
            elif s.action == "save_file":
                desc = f"Save file as '{s.params.get('filename', '')}'"
            elif s.action == "content_generation":
                desc = f"Generate authentic content for topic '{s.params.get('prompt', '')}'"
            elif s.action == "ui_focus":
                desc = f"Focus editor window '{s.params.get('app_name', s.target)}'"
            elif s.action == "ui_verify_content":
                desc = f"Verify inserted content in '{s.params.get('app_name', s.target)}' editor"
            elif s.action == "app_search":
                desc = f"Search '{s.params.get('query', '')}'"
            elif s.action == "app_navigate":
                desc = f"Navigate to '{s.params.get('path', '')}'"

            m_step = MissionStep(
                step_id=step_id,
                tool_id=tool_id,
                params=s.params,
                description=desc,
                dependencies=deps,
                idempotency_key=f"{m_id}-{step_id}"
            )
            mission_steps.append(m_step)
            prev_step_id = step_id

        return self.create_mission(
            goal=plan.goal,
            steps=mission_steps,
            mission_id=m_id
        )
