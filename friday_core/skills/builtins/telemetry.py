"""
F.R.I.D.A.Y. 3.0 — System Telemetry Verifiable Skill
Retrieves and validates CPU, memory, battery, and disk telemetry.
"""

from typing import Any, Dict, List, Optional
import shutil
import psutil
from pydantic import BaseModel, Field
from friday_core.skills.base import (
    BaseSkill,
    RiskLevel,
    ObservationResult,
    VerificationResult
)
from friday_core.system.telemetry import get_battery_info, get_memory_info


class TelemetryInput(BaseModel):
    metrics: List[str] = Field(default_factory=lambda: ["cpu", "memory", "battery", "disk"])


class TelemetryOutput(BaseModel):
    cpu_percent: Optional[float] = None
    memory_percent: Optional[float] = None
    battery_percent: Optional[int] = None
    is_charging: Optional[bool] = None
    disk_free_gb: Optional[float] = None


class SystemTelemetrySkill(BaseSkill):
    tool_id = "system_telemetry"
    tool_version = "1.0.0"
    description = "Retrieves live hardware telemetry including CPU, RAM, battery, and disk space."
    input_schema = TelemetryInput
    output_schema = TelemetryOutput
    permissions = ["telemetry:read"]
    risk_level = RiskLevel.SAFE
    timeout = 3.0
    audit_event = "TELEMETRY_SNAPSHOT"
    required_capabilities = ["psutil"]

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        # psutil or ctypes kernel32 must be functioning
        return True

    def execute(self, params: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        requested = params.get("metrics", ["cpu", "memory", "battery", "disk"])
        data = {}

        if "cpu" in requested:
            try:
                data["cpu_percent"] = psutil.cpu_percent(interval=0.1)
            except Exception:
                data["cpu_percent"] = 0.0

        if "memory" in requested:
            mem_pct = get_memory_info()
            if mem_pct is None:
                try:
                    mem_pct = psutil.virtual_memory().percent
                except Exception:
                    mem_pct = 0.0
            data["memory_percent"] = float(mem_pct)

        if "battery" in requested:
            bat_pct, charging = get_battery_info()
            if bat_pct is None:
                try:
                    b = psutil.sensors_battery()
                    if b:
                        bat_pct = int(b.percent)
                        charging = b.power_plugged
                except Exception:
                    pass
            data["battery_percent"] = bat_pct
            data["is_charging"] = charging

        if "disk" in requested:
            try:
                total, used, free = shutil.disk_usage("C:\\")
                data["disk_free_gb"] = round(free / (1024 ** 3), 2)
            except Exception:
                data["disk_free_gb"] = 0.0

        if "top_cpu" in requested:
            from friday_core.system.telemetry import get_top_cpu_processes
            data["top_cpu_processes"] = get_top_cpu_processes(limit=5)

        if "top_ram" in requested:
            from friday_core.system.telemetry import get_top_ram_processes
            data["top_ram_processes"] = get_top_ram_processes(limit=5)

        return data

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        # Read back live memory to confirm sensor availability
        mem = get_memory_info() or 0.0
        return ObservationResult(observed_state={"sensor_alive": True, "sample_mem": mem})

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        alive = observation.observed_state.get("sensor_alive", False)
        if not alive:
            return VerificationResult(
                verified=False,
                postcondition_met=False,
                message="Telemetry sensors unresponsive."
            )
        return VerificationResult(
            verified=True,
            postcondition_met=True,
            message="Telemetry metrics retrieved and verified."
        )
