"""
F.R.I.D.A.Y. 3.0 — Master Audio Volume Verifiable Skill
Adjusts master system volume with postcondition observation and false-success detection.
"""

from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field
from friday_core.skills.base import (
    BaseSkill,
    RiskLevel,
    ObservationResult,
    VerificationResult
)
from friday_core.platform_guard import IS_WINDOWS
from friday_core.system.telemetry import adjust_volume, get_audio_state


class VolumeInput(BaseModel):
    action: Literal["up", "down", "mute", "unmute"]
    steps: int = Field(default=5, ge=1, le=50)


class VolumeOutput(BaseModel):
    action: str
    steps: int
    executed: bool
    is_muted: bool
    volume: float


class VolumeControlSkill(BaseSkill):
    tool_id = "audio_volume"
    tool_version = "1.1.0"
    description = "Adjusts system master volume (up, down, mute, unmute) via native Windows media APIs with verified postcondition."
    input_schema = VolumeInput
    output_schema = VolumeOutput
    permissions = ["audio:control"]
    risk_level = RiskLevel.LOW_RISK
    timeout = 3.0
    audit_event = "VOLUME_ADJUSTMENT"

    def __init__(self):
        super().__init__()
        self._pre_muted: bool = False
        self._pre_vol: float = 50.0

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        return IS_WINDOWS

    def execute(self, params: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        action = params.get("action", "up")
        steps = params.get("steps", 5)

        self._pre_muted, self._pre_vol = get_audio_state()

        # For up/down repeat by steps // 5 or at least 1
        repeats = max(1, steps // 5) if action in ["up", "down"] else 1
        for _ in range(repeats):
            adjust_volume(action)

        post_muted, post_vol = get_audio_state()
        return {
            "action": action,
            "steps": steps,
            "executed": True,
            "is_muted": post_muted,
            "volume": post_vol
        }

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        post_muted, post_vol = get_audio_state()
        return ObservationResult(observed_state={
            "audio_driver_active": IS_WINDOWS,
            "post_muted": post_muted,
            "post_vol": post_vol,
            "pre_muted": self._pre_muted,
            "pre_vol": self._pre_vol
        })

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        active = observation.observed_state.get("audio_driver_active", False)
        if not active:
            return VerificationResult(
                verified=False,
                postcondition_met=False,
                message="Windows audio endpoint not responsive."
            )

        action = params.get("action", "") if params else ""
        post_muted = observation.observed_state.get("post_muted", False)
        post_vol = observation.observed_state.get("post_vol", 0.0)
        pre_vol = observation.observed_state.get("pre_vol", 0.0)

        if action == "mute" and not post_muted:
            return VerificationResult(
                verified=False,
                postcondition_met=False,
                message="Postcondition failed: Master audio is not in muted state."
            )
        elif action == "unmute" and post_muted:
            return VerificationResult(
                verified=False,
                postcondition_met=False,
                message="Postcondition failed: Master audio remains muted after unmute directive."
            )
        elif action == "up" and post_vol < pre_vol:
            return VerificationResult(
                verified=False,
                postcondition_met=False,
                message=f"Postcondition failed: Volume decreased ({post_vol}% < {pre_vol}%) on increase directive."
            )
        elif action == "down" and post_vol > pre_vol:
            return VerificationResult(
                verified=False,
                postcondition_met=False,
                message=f"Postcondition failed: Volume increased ({post_vol}% > {pre_vol}%) on decrease directive."
            )

        status_str = f"Muted={post_muted}, Level={post_vol:.0f}%"
        return VerificationResult(
            verified=True,
            postcondition_met=True,
            message=f"Master volume adjusted ({action}) and verified via Windows Core Audio [{status_str}]."
        )
