"""
F.R.I.D.A.Y. 3.0 — Math & Calculator Verifiable Skill
Computes mathematical expressions safely with deterministic verification.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from friday_core.skills.base import (
    BaseSkill,
    RiskLevel,
    ObservationResult,
    VerificationResult,
    RollbackResult
)
from friday_core.calc import safe_calculate


class CalculatorInput(BaseModel):
    expression: str = Field(..., description="Mathematical expression to evaluate")


class CalculatorOutput(BaseModel):
    expression: str
    result: str
    numeric_value: Optional[float] = None


class CalculatorSkill(BaseSkill):
    tool_id = "calculate"
    tool_version = "1.0.0"
    description = "Evaluates mathematical expressions safely using sandboxed AST parsing."
    input_schema = CalculatorInput
    output_schema = CalculatorOutput
    permissions = []
    risk_level = RiskLevel.SAFE
    timeout = 5.0
    audit_event = "CALCULATE"

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        expr = params.get("expression", "").strip()
        return bool(expr)

    def execute(self, params: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        expr = params.get("expression", "").strip()
        res = safe_calculate(expr)
        if res is not None:
            num_val = None
            try:
                import re
                m = re.search(r"[-+]?\d*\.?\d+", str(res))
                if m:
                    num_val = float(m.group(0))
            except Exception:
                num_val = None
            return {
                "expression": expr,
                "result": str(res),
                "numeric_value": num_val
            }
        else:
            raise ValueError(f"Unable to safely calculate expression: {expr}")

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        expr = params.get("expression", "") if params else ""
        res = safe_calculate(expr)
        return ObservationResult(observed_state={
            "expression": expr,
            "calculated": res is not None,
            "value": res
        })

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        calc = observation.observed_state.get("calculated", False)
        val = observation.observed_state.get("value")
        if calc and val is not None:
            return VerificationResult(
                verified=True,
                postcondition_met=True,
                message=f"Calculated result: {val}"
            )
        return VerificationResult(
            verified=False,
            postcondition_met=False,
            message="Math calculation failed postcondition check."
        )
