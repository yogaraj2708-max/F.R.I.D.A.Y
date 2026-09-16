"""
F.R.I.D.A.Y. Core System Package
Unified Windows system interactions, application launching, and hardware telemetry.
"""

from friday_core.system.apps import KNOWN_WINDOWS_APPS, get_registry_app_paths
from friday_core.system.launcher import (
    safe_launch,
    launch_application,
    find_and_open_desktop_or_system_item,
    bring_or_launch_vscode
)
from friday_core.system.telemetry import (
    get_battery_info,
    get_memory_info,
    adjust_volume
)

__all__ = [
    "KNOWN_WINDOWS_APPS",
    "get_registry_app_paths",
    "safe_launch",
    "launch_application",
    "find_and_open_desktop_or_system_item",
    "bring_or_launch_vscode",
    "get_battery_info",
    "get_memory_info",
    "adjust_volume"
]
