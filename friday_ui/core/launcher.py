"""
F.R.I.D.A.Y. 2.0 - Launcher Compatibility Bridge
Re-exports unified implementations from friday_core.system.
"""

from friday_core.system import (
    KNOWN_WINDOWS_APPS,
    get_registry_app_paths,
    safe_launch,
    launch_application,
    find_and_open_desktop_or_system_item,
    bring_or_launch_vscode,
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
