"""
F.R.I.D.A.Y. 3.0 — 5-Tier Risk Taxonomy
Categorizes operations into distinct security impact levels with explicit confirmation rules.
"""

from enum import Enum


class SecurityRiskLevel(str, Enum):
    SAFE = "SAFE"                  # Read-only queries, telemetry, clock, searching
    LOW_RISK = "LOW_RISK"          # Application launching, opening web URLs, reading local docs
    CAUTION = "CAUTION"            # Writing files in user documents, organizing files, changing app settings
    HIGH_RISK = "HIGH_RISK"        # Moving to Recycle Bin, killing user processes, downloading binaries
    RESTRICTED = "RESTRICTED"      # Permanent deletion, format drive, raw shell execution, registry writes


# Mapping of action identifiers to risk tiers
ACTION_RISK_MAP = {
    # SAFE
    "get_telemetry": SecurityRiskLevel.SAFE,
    "get_weather": SecurityRiskLevel.SAFE,
    "get_time": SecurityRiskLevel.SAFE,
    "list_files": SecurityRiskLevel.SAFE,
    "search": SecurityRiskLevel.SAFE,
    "inspect": SecurityRiskLevel.SAFE,
    # LOW_RISK
    "open_app": SecurityRiskLevel.LOW_RISK,
    "open_url": SecurityRiskLevel.LOW_RISK,
    "open_file": SecurityRiskLevel.LOW_RISK,
    "screenshot": SecurityRiskLevel.LOW_RISK,
    # CAUTION
    "write_file": SecurityRiskLevel.CAUTION,
    "organize_files": SecurityRiskLevel.CAUTION,
    "adjust_volume": SecurityRiskLevel.CAUTION,
    "change_setting": SecurityRiskLevel.CAUTION,
    # HIGH_RISK
    "recycle_file": SecurityRiskLevel.HIGH_RISK,
    "kill_process": SecurityRiskLevel.HIGH_RISK,
    "download_file": SecurityRiskLevel.HIGH_RISK,
    # RESTRICTED
    "permanent_delete": SecurityRiskLevel.RESTRICTED,
    "format_drive": SecurityRiskLevel.RESTRICTED,
    "shell_exec": SecurityRiskLevel.RESTRICTED,
    "registry_write": SecurityRiskLevel.RESTRICTED,
    "shutdown": SecurityRiskLevel.RESTRICTED,
    "restart": SecurityRiskLevel.RESTRICTED,
}


def get_action_risk_level(action_name: str) -> SecurityRiskLevel:
    return ACTION_RISK_MAP.get(action_name.lower(), SecurityRiskLevel.HIGH_RISK)
