"""
F.R.I.D.A.Y. 3.0 — Verifiable Pluggable Skill / Tool Base Framework
Implements the 9-stage verification lifecycle, typed schemas, idempotency guards,
and postcondition verification for all operating agent tools.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Type, Union
from datetime import datetime, timezone
import time
import uuid
import logging
from pydantic import BaseModel, ValidationError

logger = logging.getLogger("FRIDAY.Skills")


class RiskLevel(str, Enum):
    SAFE = "SAFE"
    LOW_RISK = "LOW_RISK"
    CAUTION = "CAUTION"
    HIGH_RISK = "HIGH_RISK"
    RESTRICTED = "RESTRICTED"


class ValidationResult(BaseModel):
    is_valid: bool
    errors: List[str] = []
    sanitized_params: Dict[str, Any] = {}


class AuthResult(BaseModel):
    authorized: bool
    reason: str = "Authorized"
    required_clearance: Optional[str] = None


class ObservationResult(BaseModel):
    observed_state: Dict[str, Any] = {}
    timestamp: str = ""
    raw_telemetry: Optional[Any] = None

    def model_post_init(self, __context: Any) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class VerificationResult(BaseModel):
    verified: bool
    postcondition_met: bool
    message: str = ""
    details: Dict[str, Any] = {}


class RollbackResult(BaseModel):
    success: bool
    message: str = ""
    reverted_changes: List[str] = []


class SkillResult(BaseModel):
    tool_id: str
    operation_id: str
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    verification: Optional[VerificationResult] = None
    observation: Optional[ObservationResult] = None
    duration_ms: float = 0.0
    idempotent_replay: bool = False
    audit_record: Dict[str, Any] = {}
    timestamp: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class EmptySchema(BaseModel):
    pass


class BaseSkill(ABC):
    """
    Abstract base class for all F.R.I.D.A.Y. 3.0 skills.
    Requires implementation of the 9-stage verification and execution lifecycle.
    """
    tool_id: str = "base_skill"
    tool_version: str = "1.0.0"
    description: str = "Base skill interface"
    input_schema: Type[BaseModel] = EmptySchema
    output_schema: Type[BaseModel] = EmptySchema
    permissions: List[str] = []
    risk_level: RiskLevel = RiskLevel.SAFE
    timeout: float = 10.0
    retry_policy: Dict[str, Any] = {"max_retries": 0, "backoff_factor": 1.0}
    idempotency_policy: Dict[str, Any] = {"enabled": True, "ttl_seconds": 3600}
    audit_event: str = "SKILL_EXECUTION"
    required_capabilities: List[str] = []

    def __init__(self):
        # In-memory execution registry for idempotency tracking
        self._execution_history: Dict[str, SkillResult] = {}
        self._cancelled_operations: set = set()

    def validate(self, params: Dict[str, Any]) -> ValidationResult:
        """
        Stage 1: Validate input parameters strictly against input_schema.
        Invalid tool arguments must be rejected before execution.
        """
        try:
            validated_obj = self.input_schema(**params)
            return ValidationResult(
                is_valid=True,
                errors=[],
                sanitized_params=validated_obj.model_dump()
            )
        except ValidationError as ve:
            errors = [f"{e['loc']}: {e['msg']}" for e in ve.errors()]
            logger.warning(f"[{self.tool_id}] Parameter validation failed: {errors}")
            return ValidationResult(
                is_valid=False,
                errors=errors,
                sanitized_params={}
            )
        except Exception as ex:
            return ValidationResult(
                is_valid=False,
                errors=[str(ex)],
                sanitized_params={}
            )

    def authorize(self, context: Any = None) -> AuthResult:
        """
        Stage 2: Check caller security context and required permissions.
        """
        if self.risk_level in [RiskLevel.HIGH_RISK, RiskLevel.RESTRICTED]:
            if not context or not getattr(context, "confirmed", False):
                return AuthResult(
                    authorized=False,
                    reason=f"Security clearance confirmation required for {self.risk_level.value} action.",
                    required_clearance=self.risk_level.value
                )
        return AuthResult(authorized=True, reason="Authorization confirmed.")

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        """
        Stage 3: Verify system prerequisites (e.g. file exists, target running, disk space).
        """
        return True

    @abstractmethod
    def execute(self, params: Dict[str, Any], operation_id: str) -> Any:
        """
        Stage 4: Perform the primary action.
        """
        pass

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        """
        Stage 5: Independently observe actual system state post-execution.
        """
        return ObservationResult(observed_state={"status": "completed"})

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        """
        Stage 6: Verify postcondition from independent observation.
        Never report success solely because command returned code 0.
        """
        return VerificationResult(
            verified=True,
            postcondition_met=True,
            message="Action completed and verified."
        )

    def rollback(self, operation_id: str, params: Dict[str, Any] = None) -> RollbackResult:
        """
        Stage 7: Revert side effects if verification fails and operation is reversible.
        """
        return RollbackResult(
            success=False,
            message=f"Rollback not implemented for {self.tool_id}."
        )

    def cancel(self, operation_id: str) -> None:
        """
        Stage 8: Cleanly abort an in-flight operation upon emergency stop or timeout.
        """
        self._cancelled_operations.add(operation_id)
        logger.info(f"[{self.tool_id}] Operation {operation_id} cancelled.")

    def is_cancelled(self, operation_id: str) -> bool:
        return operation_id in self._cancelled_operations

    def run_lifecycle(
        self,
        params: Dict[str, Any],
        context: Any = None,
        operation_id: Optional[str] = None
    ) -> SkillResult:
        """
        Stage 9: Full orchestrated execution lifecycle with idempotency and verification.
        """
        op_id = operation_id or f"{self.tool_id}-{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        # 0. Idempotency Check: Check if previously executed and verified
        idempotency_enabled = self.idempotency_policy.get("enabled", True)
        if idempotency_enabled and op_id in self._execution_history:
            prev = self._execution_history[op_id]
            # Verify if postcondition is still met
            obs = self.observe(op_id, params)
            ver = self.verify(obs, params)
            if ver.verified:
                logger.info(f"[{self.tool_id}] Idempotent replay for operation {op_id}.")
                return SkillResult(
                    tool_id=self.tool_id,
                    operation_id=op_id,
                    success=prev.success,
                    data=prev.data,
                    error=None,
                    verification=ver,
                    observation=obs,
                    duration_ms=(time.time() - start_time) * 1000.0,
                    idempotent_replay=True,
                    audit_record={"event": self.audit_event, "status": "REPLAYED"}
                )

        # 1. Validation
        val_res = self.validate(params)
        if not val_res.is_valid:
            return SkillResult(
                tool_id=self.tool_id,
                operation_id=op_id,
                success=False,
                error=f"Validation failed: {'; '.join(val_res.errors)}",
                duration_ms=(time.time() - start_time) * 1000.0,
                audit_record={"event": self.audit_event, "status": "VALIDATION_FAILED", "errors": val_res.errors}
            )
        sanitized = val_res.sanitized_params

        # 2. Authorization
        auth_res = self.authorize(context)
        if not auth_res.authorized:
            return SkillResult(
                tool_id=self.tool_id,
                operation_id=op_id,
                success=False,
                error=f"Authorization rejected: {auth_res.reason}",
                duration_ms=(time.time() - start_time) * 1000.0,
                audit_record={"event": self.audit_event, "status": "AUTH_REJECTED", "reason": auth_res.reason}
            )

        # 3. Precondition Check
        try:
            if not self.precondition_check(sanitized):
                return SkillResult(
                    tool_id=self.tool_id,
                    operation_id=op_id,
                    success=False,
                    error="Precondition check failed prior to execution.",
                    duration_ms=(time.time() - start_time) * 1000.0,
                    audit_record={"event": self.audit_event, "status": "PRECONDITION_FAILED"}
                )
        except Exception as ex:
            return SkillResult(
                tool_id=self.tool_id,
                operation_id=op_id,
                success=False,
                error=f"Precondition check exception: {ex}",
                duration_ms=(time.time() - start_time) * 1000.0,
                audit_record={"event": self.audit_event, "status": "PRECONDITION_EXCEPTION", "error": str(ex)}
            )

        # Check early cancellation
        if self.is_cancelled(op_id):
            return SkillResult(
                tool_id=self.tool_id,
                operation_id=op_id,
                success=False,
                error="Operation cancelled by user/emergency stop.",
                duration_ms=(time.time() - start_time) * 1000.0,
                audit_record={"event": self.audit_event, "status": "CANCELLED"}
            )

        # 4. Execution
        exec_data = None
        try:
            exec_data = self.execute(sanitized, op_id)
        except Exception as ex:
            logger.error(f"[{self.tool_id}] Execution error in {op_id}: {ex}")
            return SkillResult(
                tool_id=self.tool_id,
                operation_id=op_id,
                success=False,
                error=f"Execution error: {str(ex)}",
                duration_ms=(time.time() - start_time) * 1000.0,
                audit_record={"event": self.audit_event, "status": "EXECUTION_ERROR", "error": str(ex)}
            )

        # 5. Observation
        obs_res = self.observe(op_id, sanitized)

        # 6. Verification (False-Success Detection)
        ver_res = self.verify(obs_res, sanitized)
        duration_ms = (time.time() - start_time) * 1000.0

        if not ver_res.verified or not ver_res.postcondition_met:
            logger.warning(f"[{self.tool_id}] Postcondition verification failed for {op_id}: {ver_res.message}")
            # 7. Rollback if available
            rb_res = self.rollback(op_id, sanitized)
            res = SkillResult(
                tool_id=self.tool_id,
                operation_id=op_id,
                success=False,
                data=exec_data,
                error=f"Postcondition verification failed: {ver_res.message}",
                verification=ver_res,
                observation=obs_res,
                duration_ms=duration_ms,
                audit_record={
                    "event": self.audit_event,
                    "status": "VERIFICATION_FAILED",
                    "rollback": rb_res.model_dump()
                }
            )
            return res

        # Successful & Verified Result
        res = SkillResult(
            tool_id=self.tool_id,
            operation_id=op_id,
            success=True,
            data=exec_data,
            verification=ver_res,
            observation=obs_res,
            duration_ms=duration_ms,
            audit_record={"event": self.audit_event, "status": "VERIFIED_SUCCESS"}
        )

        if idempotency_enabled:
            self._execution_history[op_id] = res

        return res
