"""
F.R.I.D.A.Y. 3.0 — Developer / Coding Agent Coordinator
Coordinates code edit proposals, diff reviews, syntax checks, test verification,
atomic rollbacks, and git commits with mandatory human confirmation.
"""

import uuid
import logging
from typing import List, Dict, Any, Optional

from friday_core.dev_agent.models import (
    CodeFileChange,
    CodeChangePlan,
    CodeVerificationReport
)
from friday_core.dev_agent.diff_engine import DiffEngine
from friday_core.dev_agent.runner import TestRunner
from friday_core.dev_agent.git_manager import GitManager

logger = logging.getLogger("FRIDAY.DevAgent")


class DeveloperAgent:
    """
    Autonomous pair programmer and software maintenance agent for F.R.I.D.A.Y. 3.0.
    """
    def __init__(
        self,
        diff_engine: Optional[DiffEngine] = None,
        test_runner: Optional[TestRunner] = None,
        git_manager: Optional[GitManager] = None
    ):
        self.diff_engine = diff_engine or DiffEngine()
        self.test_runner = test_runner or TestRunner()
        self.git_manager = git_manager or GitManager()
        self._active_plans: Dict[str, CodeChangePlan] = {}

    def formulate_plan(
        self,
        task_description: str,
        file_edits: List[Dict[str, str]],  # [{"path": "...", "content": "..."}]
        requires_approval: bool = True
    ) -> CodeChangePlan:
        """Formulates a verified code change proposal with unified diffs."""
        plan_id = f"plan-{uuid.uuid4().hex[:8]}"
        changes: List[CodeFileChange] = []

        for edit in file_edits:
            fpath = edit["path"]
            pcontent = edit["content"]
            change = self.diff_engine.create_change_proposal(fpath, pcontent)
            changes.append(change)

        plan = CodeChangePlan(
            plan_id=plan_id,
            task_description=task_description,
            changes=changes,
            requires_human_approval=requires_approval,
            is_approved=not requires_approval,
            status="PROPOSED"
        )
        self._active_plans[plan_id] = plan
        logger.info(f"Formulated code change plan '{plan_id}' with {len(changes)} file(s).")
        return plan

    def apply_plan(self, plan_id: str, user_confirmed: bool = False) -> Dict[str, Any]:
        """
        Applies a change plan to disk.
        Enforces human approval gate if plan requires it.
        """
        plan = self._active_plans.get(plan_id)
        if not plan:
            return {"success": False, "error": f"Plan '{plan_id}' not found."}

        if plan.requires_human_approval and not user_confirmed:
            return {
                "success": False,
                "error": "Plan execution rejected: Explicit human approval is required.",
                "status": "WAITING_APPROVAL"
            }

        plan.is_approved = True
        applied_changes: List[CodeFileChange] = []

        for change in plan.changes:
            ok = self.diff_engine.apply_change(change)
            if not ok:
                logger.error(f"Failed to apply {change.file_path}. Rolling back prior edits...")
                for prior in applied_changes:
                    self.diff_engine.rollback_change(prior)
                plan.status = "REVERTED"
                return {
                    "success": False,
                    "error": f"Failed writing {change.file_path}. All changes rolled back.",
                    "status": "REVERTED"
                }
            applied_changes.append(change)

        plan.status = "APPLIED"
        return {"success": True, "plan_id": plan_id, "files_modified": len(applied_changes)}

    def verify_plan(self, test_path: str) -> CodeVerificationReport:
        """Runs test verification against the newly applied changes."""
        return self.test_runner.run_unittest(test_path)

    def rollback_plan(self, plan_id: str) -> bool:
        """Rolls back all files in the plan to their original state."""
        plan = self._active_plans.get(plan_id)
        if not plan:
            return False

        all_ok = True
        for change in reversed(plan.changes):
            if not self.diff_engine.rollback_change(change):
                all_ok = False

        plan.status = "REVERTED"
        return all_ok


# Global Singleton Developer Agent
developer_agent = DeveloperAgent()
